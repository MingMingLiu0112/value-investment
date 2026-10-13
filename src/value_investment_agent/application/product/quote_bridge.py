"""Admit one archived dual-source close against a research version (TL7-P1).

The daily assistant and the read-only Web projection both call
``admit_quote_for_research`` so a quote cannot be "admitted" on one surface and
"stale" on the other. The function never admits a price the ResearchCase
cannot legally see: a quote dated after the registered research cutoff stays
unadmitted, and the verdict names the reason instead of a display price.
"""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .common import load_json_object, require_inside, sha256_file
from ...quote_session_conversion import quote_snapshot_from_bundle_file
from ...quote_snapshot import QUOTE_STATUS_VERIFIED_CLOSE
from ...quote_session_collection import resolve_session_reference
from ...quote_sessions import latest_sse_2026_session, latest_szse_session


CHINA = ZoneInfo("Asia/Shanghai")
POINTER_PATH = "config/current-quote-bridge.json"
POINTER_SCHEMA = "current-quote-bridge-v1"
EXECUTION_SCHEMA = "quote-bridge-execution-v1"


# 每个准入结果给用户一句下一步；未收录的状态不推测含义。
_NEXT_STEPS = {
    "QUOTE_VERIFIED_FOR_RESEARCH_INPUT": "行情已可作为研究输入；价格比较仍需模型有效性与正式人工门通过。",
    "QUOTE_VERIFIED_BUT_RESEARCH_STALE": "行情晚于研究截止日：先完成研究重登记与事件复核，再重跑价格桥接。",
    "HISTORICAL_VERIFIED_CLOSE_DISPLAY_ONLY": "该收盘仅作展示；需以覆盖该行情的截止日重新研究后，才能作为估值比较输入。",
    "NOT_ADMITTED": "先修复上方原因（登记、来源或官方日历校验），再重跑价格桥接。",
    "PENDING_EXTERNAL_DATA": "先采集并通过双源校验的收盘行情，再登记到当前行情绑定。",
    "POINTER_UNAVAILABLE": "先登记当前行情绑定（config/current-quote-bridge.json）。",
}


def admit_quote_for_research(root: Path, bundle: Path | None, symbol: str, research_day: str,
                             *, today: datetime) -> tuple[Path | None, str | None, dict[str, Any]]:
    """Return (admitted bundle path, digest, verdict) for one archived quote."""
    if bundle is None:
        return None, None, {"status": "PENDING_EXTERNAL_DATA", "reason": "未提供本次双源收盘行情。"}
    path = require_inside(root / "runtime", bundle, "quote bundle")
    try:
        digest = sha256_file(path)
        raw = load_json_object(path, "quote bundle")
        snapshot = quote_snapshot_from_bundle_file(
            path, root, symbol=symbol, ref_id="daily-assistant-quote-" + digest,
            expected_sha256=digest)
        cutoff = datetime.fromisoformat(raw["finished_at"])
        if cutoff.utcoffset() is None or cutoff > today:
            raise ValueError("行情抓取时间无效或在未来")
        if snapshot.status != QUOTE_STATUS_VERIFIED_CLOSE or snapshot.quote_date is None:
            raise ValueError("双源收盘行情未通过准入：" + "; ".join(snapshot.blockers))
        check = {"quote_date": snapshot.quote_date.isoformat(),
                 "bundle_path": path.relative_to(root).as_posix(), "bundle_sha256": digest,
                 "source_evidence": snapshot.evidence_refs,
                 "collected_at": cutoff.isoformat(),
                 "display_price": str(snapshot.current_price) if getattr(snapshot, "current_price", None) is not None else None,
                 "price_admitted": False}
        local_day = today.astimezone(CHINA).date()
        historical = cutoff.astimezone(CHINA).date() != local_day or snapshot.quote_date != local_day
        if historical:
            try:
                resolved = resolve_session_reference(raw["references"][symbol], raw["documents"])
                venue = resolved["calendar_exchange"]
                if venue == "SSE":
                    latest, calendar_hashes = latest_sse_2026_session(resolved["calendar_documents"], today)
                elif venue == "SZSE":
                    latest, calendar_hashes = latest_szse_session(resolved["calendar_documents"], today.astimezone(CHINA))
                else:
                    raise ValueError("unsupported calendar")
                if latest != snapshot.quote_date.isoformat():
                    raise ValueError("归档报价不是最近一个已完成交易日")
            except (ValueError, KeyError, TypeError) as error:
                return None, None, {**check, "status": "NOT_ADMITTED",
                    "display_scope": "VERIFIED_ARCHIVE_NOT_CURRENT_PRICE",
                    "reason": "历史行情仅可回放；当前官方日历未证明最近收盘：" + str(error)}
            check.update(display_scope="LAST_COMPLETED_CLOSE_DISPLAY_ONLY",
                         latest_completed_session=latest, calendar_hashes=calendar_hashes,
                         is_historical_close=True)
        if snapshot.quote_date.isoformat() > research_day:
            return None, None, {**check, "status": "QUOTE_VERIFIED_BUT_RESEARCH_STALE",
                "reason": "行情晚于当前 ResearchCase 截止日；须先更新官方事件和模型有效性"}
        if historical:
            return None, None, {**check, "status": "HISTORICAL_VERIFIED_CLOSE_DISPLAY_ONLY",
                "reason": "最近已完成交易日历史收盘，仅作展示；未作为本次研究价格或真实交易会话准入。"}
        return path, digest, {**check, "price_admitted": True,
                              "status": "QUOTE_VERIFIED_FOR_RESEARCH_INPUT"}
    except (ValueError, KeyError, TypeError, OSError) as error:
        return None, None, {"status": "NOT_ADMITTED", "reason": str(error),
                            "bundle_path": path.relative_to(root).as_posix()}


def _resolve_under_runtime(root: Path, declared: str, label: str) -> Path:
    """Resolve a registered path against the project root, then keep it under runtime."""
    path = Path(declared)
    if not path.is_absolute():
        path = root / path
    return require_inside(root / "runtime", path, label)


def _research_case_binding(root: Path, entry: dict[str, Any]) -> dict[str, Any]:
    """Re-derive the research cutoff from the pinned package instead of copying it."""
    declared = entry.get("research_package")
    expected = entry.get("research_package_sha256")
    if not isinstance(declared, str) or not isinstance(expected, str):
        raise ValueError("登记缺少研究包路径或 Hash")
    path = _resolve_under_runtime(root, declared, "research package")
    digest = sha256_file(path)
    if digest != expected:
        raise ValueError("研究包 Hash 与登记不一致")
    package = load_json_object(path, "research package")
    point_in_time = package.get("point_in_time")
    research_day = point_in_time.get("research_as_of") if isinstance(point_in_time, dict) else None
    if not isinstance(research_day, str) or not research_day:
        raise ValueError("研究包缺少 point_in_time.research_as_of")
    return {"package_path": path.relative_to(root).as_posix(), "package_sha256": digest,
            "package_version": package.get("package_version"), "research_as_of": research_day}


def execute_quote_bridge_for_symbol(root: Path, symbol: str, *, today: datetime) -> dict[str, Any]:
    """Run the shared admission for one symbol against the pinned registration.

    The result is total and hash-checked: it never raises, never admits a price the
    registered research cutoff cannot legally see, and names the exact blocking
    field so the Web page and the CLI cannot disagree about one archived close.
    """
    root = root.resolve()
    execution: dict[str, Any] = {
        "schema_version": EXECUTION_SCHEMA, "action": "no_order", "symbol": symbol,
        "status": "POINTER_UNAVAILABLE", "reason": "未登记当前行情绑定。",
        "price_admitted": False, "research_case": None, "research_day": None,
        "quote": None, "pointer": None, "sources": [],
        "next_step": _NEXT_STEPS["POINTER_UNAVAILABLE"]}
    pointer_path = root / POINTER_PATH
    try:
        if not pointer_path.is_file():
            return execution
        pointer_digest = sha256_file(pointer_path)
        pointer = load_json_object(pointer_path, "quote bridge pointer")
        if pointer.get("schema_version") != POINTER_SCHEMA or pointer.get("action") != "no_order":
            raise ValueError("登记文件的 schema 或 action 不合法")
        entries = pointer.get("quotes")
        if not isinstance(entries, dict):
            raise ValueError("登记文件缺少 quotes")
        entry = entries.get(symbol)
        if not isinstance(entry, dict):
            return {**execution, "pointer": {"path": POINTER_PATH, "sha256": pointer_digest},
                    "status": "PENDING_EXTERNAL_DATA", "reason": "该标的尚未登记双源收盘行情。",
                    "next_step": _NEXT_STEPS["PENDING_EXTERNAL_DATA"]}
        execution["pointer"] = {"path": POINTER_PATH, "sha256": pointer_digest}
        case = _research_case_binding(root, entry)
        execution["research_case"] = case
        execution["research_day"] = case["research_as_of"]
        declared_bundle = entry.get("quote_bundle")
        if not isinstance(declared_bundle, str):
            raise ValueError("登记缺少行情包路径")
        bundle = _resolve_under_runtime(root, declared_bundle, "quote bundle")
        if sha256_file(bundle) != entry.get("quote_bundle_sha256"):
            raise ValueError("行情包 Hash 与登记不一致")
    except (ValueError, KeyError, TypeError, OSError) as error:
        return {**execution, "status": "NOT_ADMITTED", "reason": "行情登记不可用：" + str(error),
                "next_step": _NEXT_STEPS["NOT_ADMITTED"]}
    try:
        _, _, verdict = admit_quote_for_research(root, bundle, symbol, case["research_as_of"],
                                                 today=today)
    except (ValueError, KeyError, TypeError, OSError) as error:
        return {**execution, "status": "NOT_ADMITTED", "reason": "行情包无法准入：" + str(error),
                "next_step": _NEXT_STEPS["NOT_ADMITTED"]}
    status = str(verdict.get("status"))
    return {**execution, "status": status, "reason": verdict.get("reason"),
            "price_admitted": bool(verdict.get("price_admitted")),
            "quote": {key: verdict.get(key) for key in (
                "quote_date", "display_price", "collected_at", "display_scope",
                "is_historical_close", "latest_completed_session", "bundle_path", "bundle_sha256")},
            "sources": verdict.get("source_evidence") or [],
            "next_step": _NEXT_STEPS.get(status, "按以上原因复核后重跑价格桥接。")}


def pin_quote_bridge_for_symbol(root: Path, symbol: str, bundle: str | Path,
                                package: str | Path, *,
                                registered_at: str | None = None) -> dict[str, Any]:
    """Register one archived close against one research package (explicit action).

    Registration only records which quote and which research version belong
    together; it approves nothing. The admission verdict stays with
    ``execute_quote_bridge_for_symbol`` and is recomputed on every read.
    """
    root = root.resolve()
    bundle_path = _resolve_under_runtime(root, str(bundle), "quote bundle")
    bundle_digest = sha256_file(bundle_path)
    package_path = _resolve_under_runtime(root, str(package), "research package")
    package_digest = sha256_file(package_path)
    if load_json_object(package_path, "research package").get("symbol") != symbol:
        raise ValueError("研究包与标的不一致")
    case = _research_case_binding(root, {
        "research_package": package_path.relative_to(root).as_posix(),
        "research_package_sha256": package_digest})
    quotes: dict[str, Any] = {}
    pointer_file = root / POINTER_PATH
    if pointer_file.is_file():
        current = load_json_object(pointer_file, "quote bridge pointer")
        if current.get("schema_version") != POINTER_SCHEMA or current.get("action") != "no_order":
            raise ValueError("现有登记文件的 schema 或 action 不合法")
        if not isinstance(current.get("quotes"), dict):
            raise ValueError("现有登记文件缺少 quotes")
        quotes = dict(current["quotes"])
    stamp = registered_at or datetime.now(timezone.utc).isoformat()
    quotes[symbol] = {"quote_bundle": bundle_path.relative_to(root).as_posix(),
                      "quote_bundle_sha256": bundle_digest,
                      "research_package": case["package_path"],
                      "research_package_sha256": package_digest, "registered_at": stamp}
    pointer_file.parent.mkdir(parents=True, exist_ok=True)
    pointer_file.write_text(json.dumps({
        "schema_version": POINTER_SCHEMA, "action": "no_order",
        "note": "登记一份已归档的双源收盘行情；登记本身不构成估值或交易批准。",
        "registered_at": stamp, "quotes": quotes}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    return {"action": "no_order", "pointer_path": POINTER_PATH,
            "pointer_sha256": sha256_file(pointer_file), "symbol": symbol,
            "quote_bundle_sha256": bundle_digest, "research_case": case,
            "registered_at": stamp}
