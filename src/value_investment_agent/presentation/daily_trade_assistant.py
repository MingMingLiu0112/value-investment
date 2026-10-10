"""One manual, no-order research-to-product run using existing domain services."""
from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import asdict
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo
import os
import subprocess
from ..application.product.common import sha256_file, write_new_json
from ..application.product.research_publication_input import prepare_research_publication_input
from ..application.product.daily_trade_assistant import _quote_for_case
from ..application.product.daily_trade_assistant import run_daily_trade_assistant as run_daily_application
from ..application.product.decision_surface import project_verified_decision_workbench
from ..application.product.agent_research_surface import project_verified_agent_packet
from .read_models.existing_research_report import public_workbench_payload_from_snapshot
from .read_models.product_workbench import product_workbench_from_payload
from .excel.product_workbench import _user_text
DECISION_NAMES = {
    "BUY_CANDIDATE": "买入人工复核候选", "ADD_CANDIDATE": "加仓人工复核候选",
    "HOLD": "继续持有并跟踪", "TRIM_CANDIDATE": "减仓人工复核候选",
    "SELL_CANDIDATE": "退出人工复核候选", "NO_ACTION": "暂不行动",
}


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
             f"- 独立行情观察：{quote_check.get('display_price') or '无'}；行情抓取：{quote_check.get('collected_at') or '未取得'}；展示范围：{quote_check.get('display_scope') or '本次行情核验'}。",
             f"- 价格桥：{decision.get('price_bridge_status', '未形成')}；价格吸引力：{decision.get('price_attractiveness_status', '未形成')}",
             f"- 估值状态：{valuation.get('status', '未形成')}；情景只按原模型适用范围阅读，未批准不得当作买点。",
             f"- Bear / Base / Bull：{display_value('bear')} / {display_value('base')} / {display_value('bull')} {scenario.get('currency', '')}。",
             "- 私人组合：BLOCKED_PRIVATE_INPUT；position_guidance=null。", "",
             "## 主要阻塞与下一次复核", ""]
    contract_status = (workbench.get("source_verification") or {}).get("source_contract_status")
    if contract_status == "LEGACY_CONTRACT_NOT_REAL_INPUT_ADMISSION":
        lines.insert(11, "- 输入范围：历史研究包回放，未取得当前真实输入准入；原件 Hash 完整不等于金融事实已批准。")
    lines.extend(f"- {item}" for item in decision.get("blockers", [])[:12])
    lines.extend(["", "## 本次与上次的差异", ""])
    lines.extend(f"- 新增阻塞：{item}" for item in sorted(new_blockers - prior_blockers)[:8])
    lines.extend(f"- 已消除阻塞：{item}" for item in sorted(prior_blockers - new_blockers)[:8])
    if not new_blockers ^ prior_blockers:
        lines.append("- 已绑定阻塞清单无变化；不代表新的官方证据已形成。")
    if previous is not None:
        prior_decision = previous.get("decision_recommendation") or {}
        for key, title in (("valuation_range", "估值情景"), ("model_validity", "模型有效性"),
                           ("price_bridge_status", "价格桥"), ("price_attractiveness_status", "价格吸引力"),
                           ("entry_zone", "买入复核区域"), ("reduce_zone", "减仓复核区域"),
                           ("next_events", "下一触发"), ("counter_evidence", "反面证据")):
            if prior_decision.get(key) != decision.get(key):
                before = json.dumps(prior_decision.get(key), ensure_ascii=False, sort_keys=True)
                after = json.dumps(decision.get(key), ensure_ascii=False, sort_keys=True)
                lines.append(f"- {title}变化：{before} -> {after}；请核对来源，变化不等于批准。")
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
    lines.extend(["", "## 决策实际引用", ""])
    for ref in decision.get("evidence_refs", []):
        if isinstance(ref, dict):
            lines.append(f"- {ref.get('id', '来源')}：{ref.get('path') or ref.get('location') or ref.get('url') or ''}；SHA-256={ref.get('sha256', '')}")
    if quote_check.get("bundle_path"):
        lines.append(f"- 行情原始响应：{quote_check['bundle_path']}；SHA-256={quote_check.get('bundle_sha256', '未验证')}")
    return "\n".join(lines)


def _project_quote_gate(payload: dict[str, Any], *, symbol: str,
                        quote_check: dict[str, Any]) -> None:
    if quote_check["status"] not in {
        "QUOTE_VERIFIED_BUT_RESEARCH_STALE", "QUOTE_VERIFIED_FOR_RESEARCH_INPUT",
        "HISTORICAL_VERIFIED_CLOSE_DISPLAY_ONLY",
    }:
        return
    digest = quote_check["bundle_sha256"]
    evidence_id = f"daily-quote-{symbol}-{digest[:16]}"
    company = next(card for card in payload["companies"] if card["symbol"] == symbol)
    payload["audit"]["evidence"].append({
        "evidence_id": evidence_id, "title": f"{symbol} 双源收盘行情原始包（不代表估值准入）",
        "artifact_type": "QUOTE_SESSION_REVALIDATED",
        "path": quote_check["bundle_path"], "sha256": digest,
        "available_at": (datetime.fromisoformat(quote_check["collected_at"]).astimezone(
            ZoneInfo("Asia/Shanghai")).date().isoformat() if quote_check.get("collected_at")
            else quote_check["quote_date"]), "action": "no_order",
    })
    payload["today_items"].append({
        "category": "MARKET_DATA", "company": company["company_name"], "symbol": symbol,
        "what_happened": f"{quote_check['quote_date']} 双源收盘行情已核验。" + (
            "最近完成交易日的历史收盘，非今天的新行情。" if quote_check.get("is_historical_close") else "") + (
            f"独立观察 {quote_check['display_price']} 元，尚未进入决策价格。" if quote_check.get("display_price") else ""),
        "why_it_matters": quote_check.get("reason", "报价仍须随模型与事件门复核。"),
        "current_status": "行情已提交价格桥复核" if quote_check["status"] == "QUOTE_VERIFIED_FOR_RESEARCH_INPUT" else "尚未构成买卖依据",
        "next_step": "更新官方事件、研究截止日及模型有效性后重新运行。",
        "evidence_refs": [evidence_id],
    })
    payload["overview"]["pending_count"] = len(payload["today_items"])


def _build_preview(*, root, publication, workbench, workbench_path, output_dir,
                   quote_check, packet_path, symbol, publication_path,
                   publication_sha256, report_only=False):
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
    read_model = output_dir / "product-read-model.json"
    write_new_json(read_model, {
        "schema_version": "historical-company-read-model-preview-v1",
        "snapshot": json.loads(json.dumps(asdict(model), default=str)),
        "publication_input_binding": {"path": publication_path.relative_to(root).as_posix(),
                                      "sha256": publication_sha256},
        "decision_workbench_binding": {"path": workbench_path.relative_to(root).as_posix(),
                                       "sha256": sha256_file(workbench_path)},
        "agent_packet_binding": {"path": packet_path.relative_to(root).as_posix(),
                                 "sha256": sha256_file(packet_path)} if packet_path else None,
        "historical_preview": True, "canonical_written": False, "action": "no_order"})
    handoff_path = output_dir / "product-publication-input.json"
    handoff = prepare_research_publication_input(root=root, read_model_path=read_model,
        expected_sha256=sha256_file(read_model), output_path=handoff_path)
    if report_only:
        return payload, None
    strings = set()
    pending = [handoff["snapshot"]]
    while pending:
        item = pending.pop()
        if isinstance(item, str):
            strings.add(item)
        elif isinstance(item, dict):
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
    display_path = output_dir / "display-input.json"
    policy = root / "src/value_investment_agent/presentation/excel/product_workbench.py"
    write_new_json(display_path, {"input_sha256": sha256_file(handoff_path),
        "policy_binding": {"path": policy.relative_to(root).as_posix(), "sha256": sha256_file(policy)},
        "strings": {text: _user_text(text) for text in sorted(strings)},
        "action": "no_order", "canonical_written": False})
    node = Path(os.environ.get("ARTIFACT_NODE", str(Path.home() /
        ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe")))
    if not node.is_file():
        raise ValueError("Artifact Node runtime unavailable; use --report-only for verified research output")
    workbook_path = output_dir / "trade-assistant-preview.xlsx"
    args = [str(node), str(root / "scripts/current/render_product_artifact_pages.mjs"),
        "--publication-input", str(handoff_path), "--sha256", sha256_file(handoff_path),
        "--display-input", str(display_path), "--output", str(workbook_path)]
    try:
        result = subprocess.run(args, cwd=root, capture_output=True, text=True,
                                encoding="utf-8", timeout=180)
    except subprocess.SubprocessError as error:
        raise ValueError("Artifact preview subprocess failed: " + str(error)) from error
    write_new_json(output_dir / "excel-command.json", {"arguments": args,
        "exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr,
        "action": "no_order", "canonical_written": False})
    if result.returncode:
        raise ValueError("Artifact Excel preview failed: " + result.stderr[-2000:])
    return payload, workbook_path


def run_daily_trade_assistant(*, report_only=False, **kwargs) -> dict[str, Any]:
    from functools import partial
    return run_daily_application(**kwargs, report_renderer=_render_report,
                                 preview_builder=partial(_build_preview, report_only=report_only))
