"""Admit one archived dual-source close against a research version (TL7-P1).

The daily assistant and the read-only Web projection both call
``admit_quote_for_research`` so a quote cannot be "admitted" on one surface and
"stale" on the other. The function never admits a price the ResearchCase
cannot legally see: a quote dated after the registered research cutoff stays
unadmitted, and the verdict names the reason instead of a display price.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
import json
from pathlib import Path
from typing import Any, Callable
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


def _current_event_validity(validity, current_window: bool):
    if current_window:
        return validity
    # A historical no-event review cannot establish today's state; keep known damage.
    stale = validity.status == "STALE"
    return replace(validity, status="STALE" if stale else "UNKNOWN",
        material_event_found=True if stale else None,
        blockers=list(dict.fromkeys([*validity.blockers, "CURRENT_EVENT_COVERAGE_NOT_VERIFIED"])))


# 每个准入结果给用户一句下一步；未收录的状态不推测含义。
_NEXT_STEPS = {
    "QUOTE_VERIFIED_WITHOUT_RESEARCH_DISPLAY_ONLY": "收盘已核验，可供展示；完成正式研究登记后才能评估价格比较资格。",
    "QUOTE_VERIFIED_FOR_RESEARCH_INPUT": "行情已可作为研究输入；价格比较仍需模型有效性与正式人工门通过。",
    "QUOTE_VERIFIED_BUT_RESEARCH_STALE": "行情晚于研究截止日：先完成研究重登记与事件复核，再重跑价格桥接。",
    "HISTORICAL_VERIFIED_CLOSE_DISPLAY_ONLY": "该收盘仅作展示；需以覆盖该行情的截止日重新研究后，才能作为估值比较输入。",
    "NOT_ADMITTED": "先修复上方原因（登记、来源或官方日历校验），再重跑价格桥接。",
    "PENDING_EXTERNAL_DATA": "先采集并通过双源校验的收盘行情，再登记到当前行情绑定。",
    "POINTER_UNAVAILABLE": "先登记当前行情绑定（config/current-quote-bridge.json）。",
}


def admit_quote_for_research(root: Path, bundle: Path | None, symbol: str, research_day: str | None,
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
            expected_sha256=digest, require_current_b1=True)
        cutoff = datetime.fromisoformat(raw["finished_at"])
        if cutoff.utcoffset() is None or cutoff > today:
            raise ValueError("行情抓取时间无效或在未来")
        if snapshot.blockers == ["B1 requires same-session post-close acquisition"]:
            # A next-morning download can still prove the last completed close.
            # It must never acquire same-session/PIT or formal price permission.
            archived = quote_snapshot_from_bundle_file(
                path, root, symbol=symbol, ref_id="daily-assistant-quote-" + digest,
                expected_sha256=digest, require_current_b1=False)
            if (archived.status == QUOTE_STATUS_VERIFIED_CLOSE and archived.quote_date
                    and archived.quote_date < cutoff.astimezone(CHINA).date()):
                snapshot = archived
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
            latest = None
            calendar_hashes = None
            try:
                resolved = resolve_session_reference(raw["references"][symbol], raw["documents"])
                venue = resolved["calendar_exchange"]
                if venue == "SSE":
                    latest, calendar_hashes = latest_sse_2026_session(resolved["calendar_documents"], today)
                elif venue == "SZSE":
                    latest, calendar_hashes = latest_szse_session(resolved["calendar_documents"], today.astimezone(CHINA))
                else:
                    raise ValueError("unsupported calendar")
            except (ValueError, KeyError, TypeError) as error:
                return None, None, {**check, "status": "NOT_ADMITTED",
                    "display_scope": "VERIFIED_ARCHIVE_NOT_CURRENT_PRICE",
                    "reason": "历史行情仅可回放；当前官方日历未证明最近收盘：" + str(error)}
            if latest != snapshot.quote_date.isoformat():
                # Keep the computed latest completed session in the verdict: the
                # user must see which session superseded this archived close.
                reason = ("历史行情仅可回放；当前官方日历给出的最近已完成交易日为 "
                          + latest + "；该归档报价不是最近一个已完成交易日。") if isinstance(latest, str) else (
                    "历史行情仅可回放；当前官方日历未证明最近收盘：归档报价不是最近一个已完成交易日。")
                verdict = {**check, "status": "NOT_ADMITTED",
                           "display_scope": "VERIFIED_ARCHIVE_NOT_CURRENT_PRICE",
                           "reason": reason}
                if isinstance(latest, str):
                    verdict["latest_completed_session"] = latest
                return None, None, verdict
            check.update(display_scope="LAST_COMPLETED_CLOSE_DISPLAY_ONLY",
                         latest_completed_session=latest, calendar_hashes=calendar_hashes,
                         is_historical_close=True)
        else:
            # A verified close collected on the current local day already passed
            # the dual-source close proof (provider timestamps after 15:00 for a
            # matching session), so it is itself the latest completed session.
            # Leaving it unset made the packet freshness for the newest close
            # UNKNOWN instead of FRESH.
            check["latest_completed_session"] = snapshot.quote_date.isoformat()
        if research_day is None:
            return None, None, {**check, "status": "QUOTE_VERIFIED_WITHOUT_RESEARCH_DISPLAY_ONLY",
                "reason": "双源收盘已核验；尚无绑定的完整研究包，仅作事实展示，不授予价格比较或交易资格。"}
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


def quote_compatibility_ladder(verdict: dict[str, Any],
                               research_day: str | None) -> dict[str, dict[str, Any]]:
    """Split the four compatibility questions that must never be conflated.

    VERIFIED_QUOTE: the archived close itself passed dual-source verification.
    RESEARCH_COMPATIBLE: the registered research cutoff covers the quote date.
    COMPARISON_ELIGIBLE: an admitted same-session close may feed a price
    comparison (the published bridge still has the final say).
    FORMAL_DECISION_ELIGIBLE: needs the human G3 approval and the decision
    gates; this execution layer never grants it.
    """
    status = verdict.get("status")
    quote_date = verdict.get("quote_date")
    verified = status in {"QUOTE_VERIFIED_FOR_RESEARCH_INPUT",
                          "QUOTE_VERIFIED_WITHOUT_RESEARCH_DISPLAY_ONLY",
                          "QUOTE_VERIFIED_BUT_RESEARCH_STALE",
                          "HISTORICAL_VERIFIED_CLOSE_DISPLAY_ONLY"}
    compatible = bool(verified and isinstance(quote_date, str) and isinstance(research_day, str)
                      and quote_date <= research_day)
    admitted = verdict.get("price_admitted") is True
    if verified:
        verified_reason = "双源收盘行情已通过核验并归档。"
    else:
        verified_reason = str(verdict.get("reason") or "行情未通过双源核验。")
    if compatible:
        compatible_reason = f"登记研究截止日 {research_day} 覆盖报价日 {quote_date}。"
    elif verified and research_day is None:
        compatible_reason = "尚无绑定的完整研究包；核验收盘仅供事实展示。"
    elif verified:
        compatible_reason = (f"报价日 {quote_date} 晚于登记研究截止日 {research_day}；"
                             "须先完成研究重登记与事件复核。")
    else:
        compatible_reason = "报价未通过核验，无法判断研究覆盖。"
    if compatible and admitted:
        comparison_reason = "行情已准入且研究覆盖报价日；价格比较仍以已发布桥接为准。"
    elif compatible:
        comparison_reason = "研究覆盖报价日，但该收盘不是当前可比价（仅展示）；不构成价格比较资格。"
    else:
        comparison_reason = compatible_reason
    if compatible:
        historical_reason = (f"归档收盘 {quote_date} 在登记研究截止日 {research_day} 之内；"
                             "可用于历史重建对比（HISTORICAL_RECONSTRUCTION），不是当前决策依据。")
    elif verified:
        historical_reason = compatible_reason
    else:
        historical_reason = "报价未通过核验，无法用于历史重建对比。"
    return {
        "verified_quote": {"eligible": verified, "reason": verified_reason},
        "research_compatible": {"eligible": compatible, "reason": compatible_reason},
        "historical_reconstruction_eligible": {"eligible": compatible, "reason": historical_reason},
        "comparison_eligible": {"eligible": bool(compatible and admitted),
                                "reason": comparison_reason},
        "formal_decision_eligible": {
            "eligible": False,
            "reason": "正式投资决策资格需 G3 人工批准与决策门通过；执行层不评估、不预支。",
        },
    }


@dataclass(frozen=True)
class CurrentSnapshotBridgeContext:
    """Trusted in-process DI only; never construct from an HTTP/JSON approval flag."""
    policy_binding: dict
    baseline_reviews_binding: dict
    authorize_policy: Callable


def _execute_snapshot_bridge(root, symbol, today, context, entry, bundle, pointer_digest, result):
    from .current_snapshot_validity import evaluate_current_snapshot_validity, SCOPE
    from ...price_bridge import bridge_with_quote

    result = deepcopy(result)
    result.update(status="CURRENT_SNAPSHOT_VALIDITY_BLOCKED", price_admitted=False,
                  scope=SCOPE, formal_eligibility=False, strategy_approval_granted=False)
    result["compatibility"]["original_cutoff_compatible"] = deepcopy(
        result["compatibility"]["research_compatible"])
    result["compatibility"]["research_compatible"] = {"eligible": False, "scope": SCOPE}
    result["compatibility"]["comparison_eligible"] = {"eligible": False, "scope": SCOPE}
    try:
        if type(context) is not CurrentSnapshotBridgeContext or not callable(context.authorize_policy):
            raise ValueError("Current snapshot comparison requires trusted internal DI")
        if result["research_case"] is None:
            raise ValueError("Current snapshot comparison requires registered research")
        args = dict(root=root, symbol=symbol, now=today,
            incremental_binding_ref=deepcopy(entry["incremental_validity_binding"]),
            baseline_reviews_binding=deepcopy(context.baseline_reviews_binding),
            policy_binding=deepcopy(context.policy_binding), authorize_policy=context.authorize_policy)
        snapshot = evaluate_current_snapshot_validity(**args)
        result["current_snapshot_validity"] = snapshot.as_policy()
        if not snapshot.usable_for_research_comparison:
            raise ValueError("Current snapshot not usable: " + ";".join(snapshot.blockers))
        if (result["quote_verification_status"] not in {
                "QUOTE_VERIFIED_FOR_RESEARCH_INPUT", "QUOTE_VERIFIED_BUT_RESEARCH_STALE",
                "HISTORICAL_VERIFIED_CLOSE_DISPLAY_ONLY"}
                or result["quote"]["latest_completed_session"] != result["quote"]["quote_date"]):
            raise ValueError("Current snapshot requires latest officially completed verified quote")
        quote = quote_snapshot_from_bundle_file(bundle, root, symbol=symbol,
            ref_id="current-snapshot-quote-" + entry["quote_bundle_sha256"],
            expected_sha256=entry["quote_bundle_sha256"], require_current_b1=True)
        if quote.status != QUOTE_STATUS_VERIFIED_CLOSE or quote.blockers:
            raise ValueError("Current snapshot quote rejected: " + ";".join(quote.blockers))
        comparison = bridge_with_quote(snapshot.valuation, snapshot.model_validity, quote,
                                       blockers=snapshot.valuation.blockers)
        # Repeat the complete native approval/source closure after shared calculation.
        replay = evaluate_current_snapshot_validity(**args)
        result["current_snapshot_validity"] = replay.as_policy()
        if not replay.usable_for_research_comparison or replay != snapshot:
            raise ValueError("Current snapshot inputs or approval changed during comparison")
        _, _, final_verdict = admit_quote_for_research(root, bundle, symbol,
            result["research_day"], today=today)
        final_quote = quote_snapshot_from_bundle_file(bundle, root, symbol=symbol,
            ref_id="current-snapshot-quote-" + entry["quote_bundle_sha256"],
            expected_sha256=entry["quote_bundle_sha256"], require_current_b1=True)
        if (final_verdict.get("bundle_sha256") != entry["quote_bundle_sha256"]
                or final_verdict.get("quote_date") != result["quote"]["latest_completed_session"]
                or final_quote != quote or sha256_file(root / POINTER_PATH) != pointer_digest):
            raise ValueError("Current snapshot quote or pointer changed during comparison")
        if comparison.bridge_status != "READY" or comparison.blockers or snapshot.model_validity.blockers:
            raise ValueError("Shared PriceBridge rejected snapshot comparison: " +
                             ";".join(comparison.blockers or [comparison.bridge_status]))
        scope = dict(scope=SCOPE, knowledge_as_of=snapshot.as_policy()["knowledge_as_of"],
            observed_at=snapshot.as_policy()["observed_at"], full_calendar_window_elapsed=False,
            strict_contemporaneous_pit=False, research_comparison_only=True,
            source_assurance=snapshot.as_policy()["source_assurance"],
            formal_eligibility=False, strategy_approval_granted=False, action="no_order")
        result["price_comparison"] = {**json.loads(comparison.to_json()), **scope}
        result["conditional_valuation"] = json.loads(snapshot.valuation.to_json())
        result["current_event_coverage"] = {**scope, "status": "CURRENT_AS_OF_SNAPSHOT",
            "required_through": today.astimezone(CHINA).date().isoformat(), "covered_through": None}
        result["compatibility"]["research_compatible"] = {**scope, "eligible": True,
            "coverage_basis": SCOPE, "reason": "仅限已核验时点的研究价格比较；原研究日未变。"}
        result["compatibility"]["comparison_eligible"] = {**scope, "eligible": True,
            "reason": "Shared PriceBridge READY for as-of research comparison only"}
        result.update(status="QUOTE_VERIFIED_WITH_CURRENT_ASOF_SNAPSHOT", price_admitted=True,
            reason="READY: as-of research price comparison only", **scope,
            next_step="不授予正式资格、策略或账户权限；真实政策仍须独立批准。")
    except (ValueError, KeyError, TypeError, OSError, AttributeError) as error:
        result.update(reason=str(error), next_step="复核绑定、政策、来源及 B1；不得回退为全天覆盖。")
        result["price_comparison"] = {"bridge_status": "INVALID", "scope": SCOPE,
            "blockers": [str(error)], "formal_eligibility": False, "action": "no_order"}
        result["compatibility"]["comparison_eligible"]["reason"] = str(error)
    return result


def execute_quote_bridge_for_symbol(root: Path, symbol: str, *, today: datetime,
        current_snapshot_context: CurrentSnapshotBridgeContext | None = None) -> dict[str, Any]:
    """Run the shared admission for one symbol against the pinned registration.

    The result is total and hash-checked: it never raises, never admits a price the
    registered research cutoff cannot legally see, and names the exact blocking
    field so the Web page and the CLI cannot disagree about one archived close.
    A trusted in-process snapshot context selects a separate, explicitly scoped
    as-of research comparison; it never changes the original research cutoff or
    grants formal eligibility. No context means the unchanged legacy path.
    """
    root = root.resolve()
    execution: dict[str, Any] = {
        "schema_version": EXECUTION_SCHEMA, "action": "no_order", "symbol": symbol,
        "status": "POINTER_UNAVAILABLE", "reason": "未登记当前行情绑定。",
        "price_admitted": False, "research_case": None, "research_day": None,
        "quote": None, "pointer": None, "sources": [],
        "compatibility": None,
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
        observation_only = entry.get("registration_scope") == "QUOTE_OBSERVATION_ONLY"
        if observation_only and any(entry.get(key) is not None for key in (
                "research_package", "research_package_sha256", "incremental_validity_binding")):
            raise ValueError("仅展示行情登记不得包含研究或增量准入绑定")
        case = None if observation_only else _research_case_binding(root, entry)
        execution["research_case"] = case
        execution["research_day"] = case["research_as_of"] if case else None
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
        _, _, verdict = admit_quote_for_research(root, bundle, symbol, execution["research_day"],
                                                 today=today)
    except (ValueError, KeyError, TypeError, OSError) as error:
        return {**execution, "status": "NOT_ADMITTED", "reason": "行情包无法准入：" + str(error),
                "next_step": _NEXT_STEPS["NOT_ADMITTED"]}
    status = str(verdict.get("status"))
    result = {**execution, "status": status, "quote_verification_status": status, "reason": verdict.get("reason"),
            "price_admitted": bool(verdict.get("price_admitted")),
            "quote": {key: verdict.get(key) for key in (
                "quote_date", "display_price", "collected_at", "display_scope",
                "is_historical_close", "latest_completed_session", "bundle_path", "bundle_sha256")},
            "sources": verdict.get("source_evidence") or [],
            "compatibility": quote_compatibility_ladder(verdict, execution["research_day"]),
            "next_step": _NEXT_STEPS.get(status, "按以上原因复核后重跑价格桥接。")}
    if current_snapshot_context is not None:
        return _execute_snapshot_bridge(root, symbol, today, current_snapshot_context,
                                        entry, bundle, pointer_digest, result)
    if "incremental_validity_binding" in entry:
        ref = entry["incremental_validity_binding"]
        display_b1_rejected = False
        coverage_replayed = False
        result["incremental_validity"] = {"status": "UNKNOWN", "binding_ref": ref,
            "review_cutoff": None, "announcement_count": None, "model_validity": None,
            "blockers": [], "action": "no_order", "formal_eligibility": False}
        try:
            from .incremental_validity import (read_bound_json, resolve_incremental_model_validity,
                                               rebuild_registered_valuation, verify_incremental_observation_sources)
            from ...price_bridge import bridge_with_quote

            _, binding = read_bound_json(root, ref, "incremental validity binding")
            review_cutoff = date.fromisoformat(binding["review_cutoff"])
            _, observation = read_bound_json(root, binding["observation_ref"], "incremental observation")
            _, scan = read_bound_json(root, binding["scan_ref"], "incremental scan")
            announcement_sources = {source.get("path"): {
                "title": item["title"], "source_url": item["source_url"],
                "announcement_id": item["announcement_id"], "published_at": item["published_at"]}
                for item in scan["announcements"] for source in item["evidence_refs"]}
            sources = [{**source, **announcement_sources.get(source.get("path"), {})}
                       for source in observation["source_bindings"]]
            # Preserve verified scan metadata even when a later model-validity
            # replay fails, so users never see a fabricated or placeholder window.
            result["incremental_validity"].update(
                review_cutoff=review_cutoff.isoformat(),
                announcement_count=len(scan["announcements"]),
                source_bindings=sources, scan_ref=binding["scan_ref"],
                observation_ref=binding["observation_ref"],
                announcements=scan["announcements"],
                observed_at=observation["acquired_at"],
                full_calendar_window_elapsed=observation["full_calendar_window_elapsed"])
            current_day = today.astimezone(ZoneInfo("Asia/Shanghai")).date()
            current_window = review_cutoff == current_day
            full_window = observation["full_calendar_window_elapsed"] is True
            result["current_event_coverage"] = {
                "required_through": current_day.isoformat(),
                "query_through": review_cutoff.isoformat(),
                "covered_through": review_cutoff.isoformat() if full_window else None,
                "observed_at": observation["acquired_at"],
                "full_calendar_window_elapsed": full_window,
                "status": ("FULL_WINDOW" if full_window else "PARTIAL_CURRENT_SNAPSHOT") if current_window
                    else ("CLOSED_WINDOW_NOT_CURRENT" if full_window else "SNAPSHOT_NOT_CURRENT")}
            validity = resolve_incremental_model_validity(root=root, symbol=symbol, binding_ref=ref,
                review_cutoff=review_cutoff, today=today)
            verify_incremental_observation_sources(root, observation)
            coverage_replayed = True
            from .research_materiality_reviews import apply_registered_materiality_review
            validity, materiality_route = apply_registered_materiality_review(
                root=root, symbol=symbol, today=today, fallback=validity)
            historical_validity = validity
            if not current_window:
                result["historical_model_validity"] = json.loads(validity.to_json())
            validity = _current_event_validity(validity, current_window)
            result["incremental_validity"].update(status=validity.status,
                model_validity=json.loads(validity.to_json()), blockers=list(validity.blockers),
                materiality_review_route=materiality_route)
            if status not in {"QUOTE_VERIFIED_FOR_RESEARCH_INPUT", "QUOTE_VERIFIED_BUT_RESEARCH_STALE",
                              "HISTORICAL_VERIFIED_CLOSE_DISPLAY_ONLY"}:
                raise ValueError("Incremental comparison requires a current verified quote: " + str(verdict.get("reason")))
            if verdict.get("latest_completed_session") != verdict.get("quote_date"):
                raise ValueError("Incremental comparison requires the latest officially completed session")
            quote = quote_snapshot_from_bundle_file(bundle, root, symbol=symbol,
                ref_id="incremental-price-quote-" + entry["quote_bundle_sha256"],
                expected_sha256=entry["quote_bundle_sha256"], require_current_b1=True)
            if quote.blockers == ["B1 requires same-session post-close acquisition"]:
                # Display verification above remains valid; strict comparison
                # admission independently rejects the acquisition timing.
                display_b1_rejected = True
                raise ValueError("展示收盘已通过双源及最近完成交易日核验，但未满足 B1 同交易日收盘后采集要求；仅供事实展示，不准入正式价格比较。")
            valuation = rebuild_registered_valuation(root, symbol)
            result["conditional_valuation"] = json.loads(valuation.to_json())
            comparison = bridge_with_quote(valuation, validity, quote, blockers=valuation.blockers)
            result["price_comparison"] = json.loads(comparison.to_json())
            # Recheck all supplemental bytes and the registration after computation.
            coverage_replayed = False
            replayed = resolve_incremental_model_validity(root=root, symbol=symbol, binding_ref=ref,
                review_cutoff=review_cutoff, today=today)
            verify_incremental_observation_sources(root, observation)
            replayed, replayed_route = apply_registered_materiality_review(
                root=root, symbol=symbol, today=today, fallback=replayed)
            replayed = _current_event_validity(replayed, current_window)
            if replayed_route != materiality_route:
                raise ValueError("Materiality review changed during price comparison")
            if replayed.to_json() != validity.to_json() or sha256_file(pointer_path) != pointer_digest:
                raise ValueError("Incremental inputs changed during price comparison")
            coverage_replayed = True
            eligible = comparison.bridge_status == "READY" and not comparison.blockers and not validity.blockers
            if not current_window:
                reason = "当前公告尚未复核至 " + current_day.isoformat() + "；旧报价与旧窗口只保留历史比较。"
                result["historical_price_comparison"] = json.loads(bridge_with_quote(
                    valuation, historical_validity, quote, blockers=valuation.blockers).to_json())
            result["compatibility"]["original_cutoff_compatible"] = dict(result["compatibility"]["research_compatible"])
            result["compatibility"]["incremental_model_compatible"] = {"eligible": validity.status == "VALID" and not validity.blockers,
                "reason": "原模型有效性经显式增量证据重验；原研究截止日未改变。"}
            if eligible:
                result["compatibility"]["research_compatible"] = {"eligible": True,
                    "coverage_basis": "EXPLICIT_INCREMENTAL_VALIDITY",
                    "reason": f"原截止日 {case['research_as_of']} 未变；显式增量复核覆盖至 {review_cutoff}，共享价格桥通过。"}
            result["compatibility"]["comparison_eligible"] = {"eligible": eligible,
                "reason": ("共享 PriceBridge 实际重建结果：" + comparison.bridge_status) if current_window else reason}
            result.update(status="QUOTE_VERIFIED_WITH_INCREMENTAL_VALIDITY" if eligible else "INCREMENTAL_VALIDITY_BLOCKED",
                price_admitted=eligible, reason=("；".join(comparison.blockers) or comparison.bridge_status)
                    if current_window else reason,
                next_step="增量证据仅支持条件研究比较；G3 与正式决策门仍须独立通过。" if eligible else
                          "完成所绑定公告的材料性及模型适用性复核；不得修改研究截止日或预支 G3。")
        except (ValueError, KeyError, TypeError, OSError, AttributeError) as error:
            if not coverage_replayed:
                result.pop("current_event_coverage", None)
                result["incremental_validity"].update(full_calendar_window_elapsed=None, observed_at=None)
            result["incremental_validity"]["blockers"] = list(dict.fromkeys([
                *result["incremental_validity"]["blockers"], str(error)]))
            result.update(status="INCREMENTAL_VALIDITY_BLOCKED", price_admitted=False,
                reason=str(error), next_step=(
                    "展示收盘无需重复核验；等待满足 B1 的同交易日收盘后采集，再独立复核研究、模型、事件及价格比较门禁；不得以展示价替代正式比较输入。"
                    if display_b1_rejected else "修复显式增量绑定或原模型重建输入，并完成公告材料性复核。"))
            result["price_comparison"] = {"bridge_status": "INVALID", "blockers": [str(error)]}
            result["compatibility"]["comparison_eligible"] = {"eligible": False, "reason": str(error)}
            result.pop("conditional_valuation", None)
    return result


def pin_quote_bridge_for_symbol(root: Path, symbol: str, bundle: str | Path,
                                package: str | Path | None, *,
                                registered_at: str | None = None) -> dict[str, Any]:
    """Register one archived close against one research package (explicit action).

    Registration only records which quote and which research version belong
    together; it approves nothing. The admission verdict stays with
    ``execute_quote_bridge_for_symbol`` and is recomputed on every read.
    """
    root = root.resolve()
    if len(symbol) != 6 or not symbol.isascii() or not symbol.isdigit():
        raise ValueError("Invalid quote symbol")
    bundle_path = _resolve_under_runtime(root, str(bundle), "quote bundle")
    bundle_digest = sha256_file(bundle_path)
    case, package_digest = None, None
    if package is not None:
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
    previous = quotes.get(symbol) or {}
    if case is None and isinstance(previous, dict) and previous.get("research_package"):
        raise ValueError("不得以仅展示登记覆盖已有研究绑定")
    quotes[symbol] = {"quote_bundle": bundle_path.relative_to(root).as_posix(),
                      "quote_bundle_sha256": bundle_digest,
                      "research_package": case["package_path"] if case else None,
                      "research_package_sha256": package_digest, "registered_at": stamp}
    if case is None:
        quotes[symbol]["registration_scope"] = "QUOTE_OBSERVATION_ONLY"
    if (case is not None and isinstance(previous, dict) and previous.get("research_package") == case["package_path"]
            and previous.get("research_package_sha256") == package_digest
            and "incremental_validity_binding" in previous):
        quotes[symbol]["incremental_validity_binding"] = previous["incremental_validity_binding"]
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
