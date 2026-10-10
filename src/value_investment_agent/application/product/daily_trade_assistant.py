"""Manual research orchestration; rendering is supplied by the product boundary."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from .common import load_json_object, require_inside, sha256_file, write_new_json
from .daily_assets import inspect_daily_case_assets
from .workbench import build_current_workbench_for_symbol
from .decision_surface import verify_current_decision_workbench
from .research_publication_input import load_research_publication_input
from ..research.agent_review.supervisor import run_agent_research_pilot
from ..research.agent_review.llm_pilot import run_llm_research_pilot
from ...infrastructure.agent_runtime.provider import MockLLMProvider
from ...quote_session_conversion import quote_snapshot_from_bundle_file
from ...quote_snapshot import QUOTE_STATUS_VERIFIED_CLOSE
from ...quote_session_collection import resolve_session_reference
from ...quote_sessions import latest_sse_2026_session, latest_szse_session
import json


CHINA = ZoneInfo("Asia/Shanghai")


def _pinned(root: Path, case: dict[str, Any], name: str) -> tuple[Path, str]:
    path = require_inside(root, root / case[name], name)
    digest = case[name + "_sha256"]
    if sha256_file(path) != digest:
        raise ValueError(f"{name} hash mismatch")
    return path, digest


def _quote_for_case(root: Path, bundle: Path | None, symbol: str, research_day: str,
                    *, today: datetime) -> tuple[Path | None, str | None, dict[str, Any]]:
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
        return path, digest, {**check, "status": "QUOTE_VERIFIED_FOR_RESEARCH_INPUT"}
    except (ValueError, KeyError, TypeError, OSError) as error:
        return None, None, {"status": "NOT_ADMITTED", "reason": str(error),
                            "bundle_path": path.relative_to(root).as_posix()}


def run_daily_trade_assistant(*, root: Path, symbol: str, case: dict[str, Any],
        output_dir: Path, report_renderer: Callable, preview_builder: Callable | None = None,
        quote_bundle: Path | None = None, agent_mode: str = "offline",
        quote_error: str | None = None) -> dict[str, Any]:
    root = root.resolve()
    output_dir = require_inside(root / "runtime", output_dir, "daily assistant output")
    if output_dir.exists():
        raise FileExistsError("daily assistant run directory already exists")
    if agent_mode not in {"offline", "mock", "none"}:
        raise ValueError("paid model calls are excluded from this entry")
    assets = inspect_daily_case_assets(root=root, case=case, agent_mode=agent_mode)
    required_blockers = [row for row in assets["blockers"] if row["required_for_research"]]
    optional_blockers = [row for row in assets["blockers"] if not row["required_for_research"]]
    mismatch = next((row for row in required_blockers if row["status"] == "HASH_MISMATCH"), None)
    if mismatch is not None:
        raise ValueError(f"{mismatch['role']} hash mismatch: {mismatch['path']}")
    if required_blockers:
        output_dir.mkdir(parents=True)
        write_new_json(output_dir / "asset-index.json", assets)
        report_path = output_dir / "report.md"
        report_path.write_text("# " + symbol + " 研究资产待恢复\n\n"
            + "本次没有生成研究或价格结论，不能将文件完整性当作研究批准。\n\n"
            + "\n".join(f"- {row['status']}：{row['path']}；预期 SHA-256={row['expected_sha256']}"
                          for row in assets["blockers"])
            + "\n\n使用 --recover-assets-from 指定项目内恢复目录；仅恢复相同 Hash 的原件，已有文件不覆盖。\n",
            encoding="utf-8")
        result = {"schema_version": "daily-trade-assistant-receipt-v1", "symbol": symbol,
                  "status": "BLOCKED_RESEARCH_ASSETS", "action": "no_order",
                  "generated_at": datetime.now(timezone.utc).isoformat(),
                  "recommendation_type": "NO_ACTION", "quote_check": {"status": "NOT_EVALUATED_ASSETS_MISSING"},
                  "agent_scope": None, "agent_error": None, "position_guidance": None,
                  "portfolio_input_status": "BLOCKED_PRIVATE_INPUT", "canonical_workbook_written": False,
                  "outputs": {key: {"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path)}
                              for key, path in (("asset_index", output_dir / "asset-index.json"), ("report", report_path))}}
        write_new_json(output_dir / "receipt.json", result)
        return result
    package_path, package_sha = _pinned(root, case, "package")
    request_path, request_sha = _pinned(root, case, "schedule_request")
    package = load_json_object(package_path, "research package")
    request = load_json_object(request_path, "research scope")
    if package.get("symbol") != symbol or request.get("symbol") != symbol:
        raise ValueError("case symbol mismatch")
    publication = None
    if "publication_input" in case and not optional_blockers:
        publication_path, publication_sha = _pinned(root, case, "publication_input")
        publication = load_research_publication_input(root=root, path=publication_path,
                                                      expected_sha256=publication_sha)
    previous = None
    if "previous_workbench" in case and not optional_blockers:
        prior_path, _ = _pinned(root, case, "previous_workbench")
        previous = load_json_object(prior_path, "previous workbench")
        verify_current_decision_workbench(previous)
        if previous.get("symbol") != symbol:
            raise ValueError("previous workbench symbol mismatch")
    responses = None
    if agent_mode == "mock" and not optional_blockers:
        fixture_path, _ = _pinned(root, case, "mock_responses")
        responses = load_json_object(fixture_path, "mock responses")
    research_day = package["point_in_time"]["research_as_of"]
    quote_path, quote_sha, quote_check = _quote_for_case(root, quote_bundle, symbol,
        research_day, today=datetime.now(timezone.utc))
    if quote_bundle is None and quote_error is not None:
        quote_check = {"status": "COLLECTION_FAILED", "reason": quote_error}
    output_dir.mkdir(parents=True)
    write_new_json(output_dir / "asset-index.json", assets)
    workbench_path = output_dir / "workbench.json"
    outcome = build_current_workbench_for_symbol(root=root, symbol=symbol,
        package_path=package_path, output_path=workbench_path, schedule_request=request,
        schedule_request_sha256=request_sha, quote_path=quote_path, quote_sha256=quote_sha,
        recommendation_schema_version="advisory-decision-recommendation-v3")
    workbench = outcome["result"]
    packet_path = None
    agent_scope = agent_error = None
    if agent_mode == "mock" and responses is None:
        agent_error = "Mock fixture unavailable; research still runs without simulated Agent findings."
    if workbench.get("decision_recommendation") is not None and agent_mode != "none" and not (agent_mode == "mock" and responses is None):
        packet_path = output_dir / "agent-packet.json"
        try:
            kwargs = dict(root=root, symbol=symbol, workbench=workbench_path,
                          workbench_sha256=sha256_file(workbench_path), output=packet_path)
            if agent_mode == "offline":
                packet = run_agent_research_pilot(**kwargs)
            else:
                packet = run_llm_research_pilot(**kwargs, provider=MockLLMProvider(
                    {key: json.dumps(value, ensure_ascii=False) for key, value in responses.items()}), mode="mock")
            agent_scope = packet["scope"]
        except ValueError as error:
            if packet_path.exists():
                raise
            packet_path = None
            agent_error = str(error)
    payload = workbook_path = None
    preview_error = None
    if publication is not None and workbench.get("decision_recommendation") is not None and preview_builder is not None:
        try:
            payload, workbook_path = preview_builder(root=root, publication=publication,
                workbench=workbench, workbench_path=workbench_path, output_dir=output_dir,
                quote_check=quote_check, packet_path=packet_path, symbol=symbol,
                publication_path=publication_path, publication_sha256=publication_sha)
        except (ValueError, OSError) as error:
            preview_error = str(error)
    report_path = output_dir / "report.md"
    report_path.write_text(report_renderer(workbench, payload, quote_check, agent_scope,
                                           previous, agent_error), encoding="utf-8")
    if optional_blockers:
        with report_path.open("a", encoding="utf-8") as report:
            report.write("\n## 可选展示或历史对比资产缺口\n\n公共研究继续运行，未伪造 Excel 或上次结果。\n")
            for row in optional_blockers:
                report.write(f"- {row['status']}：{row['path']}\n")
    if preview_error:
        with report_path.open("a", encoding="utf-8") as report:
            report.write("\n## 展示链未完成\n\n证券级研究报告仍可阅读；没有宣称 Excel 通过验证。\n- " + preview_error + "\n")
    result = {"schema_version": "daily-trade-assistant-receipt-v1", "symbol": symbol,
        "status": "RESEARCH_RUN_COMPLETED_WITH_ADMISSION_STATUS", "generated_at": datetime.now(timezone.utc).isoformat(),
        "action": "no_order", "research_as_of": research_day,
        "recommendation_type": workbench.get("suggested_state"), "quote_check": quote_check,
        "agent_scope": agent_scope, "agent_error": agent_error,
        "portfolio_input_status": "BLOCKED_PRIVATE_INPUT", "position_guidance": None,
        "canonical_workbook_written": False,
        "optional_asset_blockers": optional_blockers,
        "preview_error": preview_error,
        "preview_generated": workbook_path is not None,
        "comparison": {"previous_result_bound": previous is not None,
            "changed_fields": [key for key in ("recommendation_type", "valuation_range",
                "model_validity", "price_bridge_status", "price_attractiveness_status",
                "entry_zone", "reduce_zone", "blockers", "next_events", "counter_evidence")
                if ((previous or {}).get("decision_recommendation") or {}).get(key)
                != (workbench.get("decision_recommendation") or {}).get(key)] if previous is not None else []},
        "implementation_bindings": [{"path": name, "sha256": sha256_file(root / name)}
            for name in ("scripts/current/run_daily_trade_assistant.py",
                         "src/value_investment_agent/application/product/daily_trade_assistant.py",
                         "src/value_investment_agent/application/product/daily_assets.py",
                         "src/value_investment_agent/presentation/daily_trade_assistant.py",
                         "scripts/current/render_product_artifact_pages.mjs") if (root / name).is_file()],
        "inputs": {"package": package_sha, "schedule_request": request_sha,
                   "publication_input": case.get("publication_input_sha256"),
                   "previous_workbench": case.get("previous_workbench_sha256"),
                   "mock_responses": case.get("mock_responses_sha256") if agent_mode == "mock" else None},
        "outputs": {name: {"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path)}
                    for name, path in (("workbench", workbench_path), ("agent_packet", packet_path),
                       ("preview", workbook_path), ("report", report_path), ("asset_index", output_dir / "asset-index.json"))
                    if path is not None}}
    for name in ("product-read-model", "product-publication-input", "display-input"):
        path = output_dir / (name + ".json")
        if path.is_file():
            result["outputs"][name.replace("-", "_")] = {
                "path": path.relative_to(root).as_posix(), "sha256": sha256_file(path)}
    write_new_json(output_dir / "receipt.json", result)
    return result
