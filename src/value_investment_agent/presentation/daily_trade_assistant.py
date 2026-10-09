"""One manual, no-order research-to-product run using existing domain services."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ..application.product.common import load_json_object, require_inside, sha256_file, write_new_json
from ..application.product.workbench import build_current_workbench_for_symbol
from ..application.product.decision_surface import project_verified_decision_workbench, verify_current_decision_workbench
from ..application.product.agent_research_surface import project_verified_agent_packet
from ..application.product.research_publication_input import load_research_publication_input
from ..application.research.agent_review.supervisor import run_agent_research_pilot
from ..application.research.agent_review.llm_pilot import run_llm_research_pilot
from ..infrastructure.agent_runtime.provider import MockLLMProvider
from .read_models.existing_research_report import public_workbench_payload_from_snapshot
from .read_models.product_workbench import product_workbench_from_payload
from .excel.product_workbench import write_product_workbench_candidate
from ..quote_session_conversion import quote_snapshot_from_bundle_file
from ..quote_snapshot import QUOTE_STATUS_VERIFIED_CLOSE


CHINA = ZoneInfo("Asia/Shanghai")
DECISION_NAMES = {
    "BUY_CANDIDATE": "买入人工复核候选", "ADD_CANDIDATE": "加仓人工复核候选",
    "HOLD": "继续持有并跟踪", "TRIM_CANDIDATE": "减仓人工复核候选",
    "SELL_CANDIDATE": "退出人工复核候选", "NO_ACTION": "暂不行动",
}


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
    digest = sha256_file(path)
    try:
        raw = load_json_object(path, "quote bundle")
        snapshot = quote_snapshot_from_bundle_file(
            path, root, symbol=symbol,
            ref_id="daily-assistant-quote-" + digest, expected_sha256=digest,
        )
        cutoff = datetime.fromisoformat(raw["finished_at"])
        if cutoff.utcoffset() is None or cutoff > today:
            raise ValueError("行情抓取时间无效或在未来")
        observed_day = cutoff.astimezone(CHINA).date()
        if observed_day != today.astimezone(CHINA).date():
            raise ValueError("历史行情仅可回放，不能作为本次最新价格")
        if snapshot.status != QUOTE_STATUS_VERIFIED_CLOSE or snapshot.quote_date is None:
            raise ValueError("双源收盘行情未通过准入：" + "; ".join(snapshot.blockers))
        if snapshot.quote_date.isoformat() > research_day:
            return None, None, {
                "status": "QUOTE_VERIFIED_BUT_RESEARCH_STALE",
                "reason": "行情晚于当前 ResearchCase 截止日；须先更新官方事件和模型有效性",
                "quote_date": snapshot.quote_date.isoformat(),
                "bundle_path": path.relative_to(root).as_posix(),
                "bundle_sha256": digest,
                "source_evidence": snapshot.evidence_refs,
            }
        return path, digest, {"status": "QUOTE_VERIFIED_FOR_RESEARCH_INPUT",
                              "quote_date": snapshot.quote_date.isoformat(),
                              "bundle_path": path.relative_to(root).as_posix(),
                              "bundle_sha256": digest,
                              "source_evidence": snapshot.evidence_refs}
    except (ValueError, KeyError, TypeError, FileNotFoundError) as error:
        return None, None, {"status": "NOT_ADMITTED", "reason": str(error),
                            "bundle_path": path.relative_to(root).as_posix(),
                            "bundle_sha256": digest}


def _render_report(workbench: dict[str, Any], payload: dict[str, Any] | None,
                   quote_check: dict[str, Any], agent_scope: str | None,
                   previous: dict[str, Any] | None, agent_error: str | None) -> str:
    decision = workbench.get("decision_recommendation") or {}
    valuation = workbench.get("valuation") or {}
    kind = decision.get("recommendation_type", "NO_ACTION")
    prior_kind = (previous or {}).get("suggested_state")
    scenario = decision.get("valuation_range") or {}
    def display_value(key: str) -> str:
        value = scenario.get(key)
        if value is None:
            return "无"
        try:
            amount = Decimal(str(value))
            return f"{amount:.2f}" if amount.is_finite() else "无"
        except (InvalidOperation, ValueError):
            return "无"
    conditions = decision.get("recommendation_reasons") or []
    prior_blockers = set(((previous or {}).get("decision_recommendation") or {}).get("blockers") or ())
    new_blockers = set(decision.get("blockers") or ())
    lines = [f"# {workbench['symbol']} 每日交易前研究辅助", "",
             f"- 研究截止：{decision.get('decision_as_of', '未形成')}",
             f"- 证券级状态：{kind}（{DECISION_NAMES.get(kind, '待核验')}）；`action=no_order`，不是订单。",
             f"- 上次状态：{prior_kind or '无已绑定上次结果'}；变化：{'未变化' if prior_kind == kind else '需核对新旧证据'}。",
             f"- 行情准入：{quote_check['status']}；{quote_check.get('reason', quote_check.get('quote_date', ''))}",
             f"- 已核验行情日期：{quote_check.get('quote_date', '未准入')}；决策中价格：{decision.get('current_price') or '无'}。",
             f"- 价格桥：{decision.get('price_bridge_status', '未形成')}；价格吸引力：{decision.get('price_attractiveness_status', '未形成')}",
             f"- 估值状态：{valuation.get('status', '未形成')}；情景只按原模型适用范围阅读，未批准不得当作买点。",
             f"- Bear / Base / Bull：{display_value('bear')} / {display_value('base')} / {display_value('bull')} {scenario.get('currency', '')}。",
             "- 私人组合：BLOCKED_PRIVATE_INPUT；position_guidance=null。", "",
             "## 主要阻塞与下一次复核", ""]
    lines.extend(f"- {item}" for item in decision.get("blockers", [])[:12])
    lines.extend(["", "## 本次与上次的差异", ""])
    lines.extend(f"- 新增阻塞：{item}" for item in sorted(new_blockers - prior_blockers)[:8])
    lines.extend(f"- 已消除阻塞：{item}" for item in sorted(prior_blockers - new_blockers)[:8])
    if not new_blockers ^ prior_blockers:
        lines.append("- 已绑定阻塞清单无变化；不代表新的官方证据已形成。")
    lines.extend(["", "## 候选状态依据", ""])
    lines.extend(f"- {'关键前置条件仍有阻塞' if item == 'blockers_present' else item}"
                 for item in conditions[:8])
    if kind in {"BUY_CANDIDATE", "ADD_CANDIDATE"}:
        lines.append(f"- 现有规则价格区域：{decision.get('entry_zone') or '未登记'}；仍需人工复核。")
    if kind in {"TRIM_CANDIDATE", "SELL_CANDIDATE"}:
        lines.append("- 该风险降低候选以已绑定的原始买入逻辑和反证为准，不能由单一 AI 观点触发。")
    lines.extend(["", "## 研究逻辑与反证", "",
                  str(decision.get("thesis") or "尚未形成已批准论点。"), ""])
    lines.extend(f"- 反证：{item.get('text', '')}" for item in decision.get("counter_evidence", [])[:4])
    lines.extend(f"- 待观察：{item.get('text', '')}" for item in decision.get("next_events", [])[:4])
    if payload is not None:
        company = next(card for card in payload["companies"] if card["symbol"] == workbench["symbol"])
        lines.extend(["", "## 决策门禁", "", "| 环节 | 状态 | 原因 |", "| --- | --- | --- |"])
        for step in company.get("decision_process", []):
            lines.append(f"| {step['key']} | {step['status']} | {str(step['reason']).replace('|', '；')} |")
        lines.extend(["", "## Agent 待复核发现", "",
                      f"模式：{agent_scope or '未准入'}；{agent_error or '不得成为正式财务事实或独立卖出触发。'}", ""])
        for item in company.get("agent_research", []):
            lines.append(f"- [{item['role']}/{item['finding_type']}] {item['claim']}；来源：{', '.join(item['evidence_refs'])}")
        lines.extend(["", "## 来源审计", ""])
        for item in payload["audit"]["evidence"]:
            if item.get("artifact_type") in {"verified_decision_workbench", "AGENT_RESEARCH_SOURCE",
                                             "QUOTE_SESSION_REVALIDATED"}:
                lines.append(f"- {item['evidence_id']}：{item.get('path', '')}；SHA-256={item.get('sha256', '')}")
    lines.extend(["", "本报告仅供人工研究复核。不得把条件情景、模拟 Agent 或历史价格当作正式交易建议。", ""])
    if payload is None:
        lines.extend([f"Agent 状态：{agent_scope or '未准入'}；{agent_error or '未请求'}。",
                      "产品 Excel：缺少与当前研究日期匹配的来源核验发布输入，本次仅交付证券级工作台。", ""])
    return "\n".join(lines)


def _project_quote_gate(payload: dict[str, Any], *, symbol: str,
                        quote_check: dict[str, Any]) -> None:
    if quote_check["status"] not in {
        "QUOTE_VERIFIED_BUT_RESEARCH_STALE", "QUOTE_VERIFIED_FOR_RESEARCH_INPUT",
    }:
        return
    digest = quote_check["bundle_sha256"]
    evidence_id = f"daily-quote-{symbol}-{digest[:16]}"
    company = next(card for card in payload["companies"] if card["symbol"] == symbol)
    payload["audit"]["evidence"].append({
        "evidence_id": evidence_id, "title": f"{symbol} 双源收盘行情原始包（不代表估值准入）",
        "artifact_type": "QUOTE_SESSION_REVALIDATED",
        "path": quote_check["bundle_path"], "sha256": digest,
        "available_at": quote_check["quote_date"], "action": "no_order",
    })
    payload["today_items"].append({
        "category": "MARKET_DATA", "company": company["company_name"], "symbol": symbol,
        "what_happened": f"{quote_check['quote_date']} 双源收盘行情已核验。",
        "why_it_matters": quote_check.get("reason", "报价仍须随模型与事件门复核。"),
        "current_status": "尚未构成买卖依据" if quote_check["status"] == "QUOTE_VERIFIED_BUT_RESEARCH_STALE" else "行情已提交价格桥复核",
        "next_step": "更新官方事件、研究截止日及模型有效性后重新运行。",
        "evidence_refs": [evidence_id],
    })
    payload["overview"]["pending_count"] = len(payload["today_items"])


def run_daily_trade_assistant(*, root: Path, symbol: str, case: dict[str, Any],
                              output_dir: Path, quote_bundle: Path | None = None,
                              agent_mode: str = "offline", quote_error: str | None = None) -> dict[str, Any]:
    root = root.resolve()
    output_dir = require_inside(root / "runtime", output_dir, "daily assistant output")
    if output_dir.exists():
        raise FileExistsError("daily assistant run directory already exists")
    if agent_mode not in {"offline", "mock", "none"}:
        raise ValueError("paid model calls are excluded from this entry")
    package_path, package_sha = _pinned(root, case, "package")
    request_path, request_sha = _pinned(root, case, "schedule_request")
    package = load_json_object(package_path, "research package")
    request = load_json_object(request_path, "research scope")
    if package.get("symbol") != symbol or request.get("symbol") != symbol:
        raise ValueError("case symbol mismatch")
    publication = None
    if "publication_input" in case:
        publication_path, publication_sha = _pinned(root, case, "publication_input")
        publication = load_research_publication_input(
            root=root, path=publication_path, expected_sha256=publication_sha,
        )
    previous = None
    if "previous_workbench" in case:
        prior_path, _ = _pinned(root, case, "previous_workbench")
        previous = load_json_object(prior_path, "previous workbench")
        verify_current_decision_workbench(previous)
        if previous.get("symbol") != symbol:
            raise ValueError("previous workbench symbol mismatch")
    if agent_mode == "mock":
        fixture_path, _ = _pinned(root, case, "mock_responses")
        responses = load_json_object(fixture_path, "mock responses")
    else:
        responses = None
    now = datetime.now(timezone.utc)
    research_day = package["point_in_time"]["research_as_of"]
    quote_path, quote_sha, quote_check = _quote_for_case(
        root, quote_bundle, symbol, research_day, today=now,
    )
    if quote_bundle is None and quote_error is not None:
        quote_check = {"status": "COLLECTION_FAILED", "reason": quote_error}
    output_dir.mkdir(parents=True)
    workbench_path = output_dir / "workbench.json"
    outcome = build_current_workbench_for_symbol(
        root=root, symbol=symbol, package_path=package_path, output_path=workbench_path,
        schedule_request=request, schedule_request_sha256=request_sha,
        quote_path=quote_path, quote_sha256=quote_sha,
        recommendation_schema_version="advisory-decision-recommendation-v3",
    )
    workbench = outcome["result"]
    packet_path = None
    agent_scope = None
    agent_error = None
    if workbench.get("decision_recommendation") is not None and agent_mode != "none":
        packet_path = output_dir / "agent-packet.json"
        try:
            if agent_mode == "offline":
                packet = run_agent_research_pilot(root=root, symbol=symbol,
                    workbench=workbench_path, workbench_sha256=sha256_file(workbench_path), output=packet_path)
            else:
                packet = run_llm_research_pilot(root=root, symbol=symbol,
                    workbench=workbench_path, workbench_sha256=sha256_file(workbench_path),
                    output=packet_path, provider=MockLLMProvider({key: json.dumps(value, ensure_ascii=False)
                                                                  for key, value in responses.items()}), mode="mock")
            agent_scope = packet["scope"]
        except ValueError as error:
            if packet_path.exists():
                raise
            packet_path = None
            agent_error = str(error)
    payload = None
    workbook_path = None
    if publication is not None and workbench.get("decision_recommendation") is not None:
        payload = public_workbench_payload_from_snapshot(publication["snapshot"])
        payload["generated_at"] = datetime.now(timezone.utc).isoformat()
        if payload["as_of"] != workbench["decision_recommendation"]["decision_as_of"]:
            raise ValueError("publication and current decision research dates differ")
        project_verified_decision_workbench(payload, root=root, path=workbench_path,
                                            expected_sha256=sha256_file(workbench_path))
        _project_quote_gate(payload, symbol=symbol, quote_check=quote_check)
        if packet_path is not None:
            project_verified_agent_packet(payload, root=root, path=packet_path,
                                          expected_sha256=sha256_file(packet_path))
        model = product_workbench_from_payload(payload)
        workbook_path = output_dir / "trade-assistant-preview.xlsx"
        write_product_workbench_candidate(model, output=workbook_path, root=root)
    report_path = output_dir / "report.md"
    report_path.write_text(_render_report(workbench, payload, quote_check, agent_scope,
                                          previous, agent_error), encoding="utf-8")
    receipt = {"schema_version": "daily-trade-assistant-receipt-v1", "symbol": symbol,
        "generated_at": datetime.now(timezone.utc).isoformat(), "action": "no_order",
        "research_as_of": research_day, "recommendation_type": workbench.get("suggested_state"),
        "quote_check": quote_check, "agent_scope": agent_scope, "agent_error": agent_error,
        "portfolio_input_status": "BLOCKED_PRIVATE_INPUT", "position_guidance": None,
        "canonical_workbook_written": False,
        "inputs": {"package": package_sha, "schedule_request": request_sha,
                   "publication_input": case.get("publication_input_sha256"),
                   "previous_workbench": case.get("previous_workbench_sha256"),
                   "mock_responses": case.get("mock_responses_sha256") if agent_mode == "mock" else None},
        "outputs": {name: {"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path)}
                    for name, path in (("workbench", workbench_path), ("agent_packet", packet_path),
                                       ("preview", workbook_path), ("report", report_path)) if path is not None}}
    write_new_json(output_dir / "receipt.json", receipt)
    return receipt
