"""Human-readable rendering of source-bound existing research, without calculations."""
from __future__ import annotations

from typing import Any, Mapping
from dataclasses import replace
from datetime import date
from decimal import Decimal

from ...application.product.decision_surface import (
    current_recommendation_type, verify_current_decision_workbench,
)
from ...domain.research.research_run_contract import valuation_result_sha256
from ...valuation_models.base import ValuationResult
from ...price_bridge import price_bridge_from_payload
from ...investment_decision import (
    STATUS_INSUFFICIENT_RESEARCH,
    evaluate_investment_decision,
    investment_decision_review_from_payload,
)
from ...pre_decision_eligibility import pre_decision_eligibility_from_payload
from .product_workbench import EvidenceRecord, ProductWorkbenchReadModel
from .valuation_step import company_with_pending_price_bridge, workbench_with_bound_valuation


_RECOMMENDATION_REVIEW_TEXT = {
    "BUY_CANDIDATE": "证券级研究和价格前置满足，可进入人工买入复核。",
    "ADD_CANDIDATE": "证券级研究支持加仓复核；仍需真实持仓、原始买入逻辑与组合约束，不产生订单。",
    "HOLD": "证券级研究与原始买入逻辑未发现需减仓的变化，可进入人工持有复核；不产生订单。",
    "TRIM_CANDIDATE": "研究或原始论点出现削弱信号，可进入人工减仓复核；不产生订单。",
    "SELL_CANDIDATE": "研究或原始论点出现破裂信号，可进入人工退出复核；不产生订单。",
    "NO_ACTION": "当前证据或价格条件未形成可执行研究候选；不代表卖出，也不产生订单。",
}


def public_workbench_payload_from_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Adapt retained public read-model snapshots through the existing validator."""
    if snapshot.get("action") != "no_order" or snapshot.get("portfolio", {}).get("real_data_available") is not False:
        raise ValueError("snapshot adapter supports public nonpersonalized workbenches only")

    def statuses(value):
        if isinstance(value, dict):
            if set(value) == {"code", "user_label"}:
                return value["code"]
            return {key: statuses(item) for key, item in value.items()}
        if isinstance(value, list):
            return [statuses(item) for item in value]
        return value

    data = statuses(dict(snapshot))
    summaries = data.pop("stage_summaries")
    data["stages"] = {stage["stage_key"]: stage for stage in summaries}
    if len(data["stages"]) != len(summaries):
        raise ValueError("duplicate snapshot stage")
    operational = data["stages"].get("m6")
    if operational is not None and operational.get("status") == "PARTIAL":
        operational["status"] = "OPERATIONAL_NOT_STARTED"
        operational["detail"] = (
            "Legacy snapshot PARTIAL does not attest operational acceptance; "
            "conservatively displayed as OPERATIONAL_NOT_STARTED. " + operational["detail"]
        )
    data["audit"] = {"evidence": data.pop("audit_evidence"),
                     "event_decisions": data.pop("event_audit_decisions", [])}
    for company in data["companies"]:
        price = company.get("price", {})
        if price.get("status") == "NOT_READY" and price.get("available") is False:
            price["status"] = "UNAVAILABLE"
        company["decision_review"] = [{"label": label, "value": value}
                                      for label, value in company.get("decision_review", [])]
    for event in data.get("events", []):
        event["event_type"] = event.pop("category")
    return data


def project_existing_research_workbench(
    model: ProductWorkbenchReadModel, payload: Mapping[str, Any],
) -> ProductWorkbenchReadModel:
    """Consume verified application output; file verification stays upstream."""
    render_existing_research_report(payload)
    research = payload["research"]
    if payload["symbol"] != research["symbol"]:
        raise ValueError("workbench and research symbol mismatch")
    cards = [card for card in model.companies if card.symbol == research["symbol"]]
    if len(cards) != 1:
        raise ValueError("existing research requires exactly one matching card")
    if any(step.status != "BLOCKED" for step in cards[0].decision_process if step.key != "valuation"):
        raise ValueError("existing research cannot inherit approved decision gates")
    raw = dict(research["valuation"])
    raw["valuation_date"] = date.fromisoformat(raw["valuation_date"])
    for key in ("bear_value", "base_value", "bull_value"):
        raw[key] = None if raw[key] is None else Decimal(raw[key])
    valuation = ValuationResult(**raw)
    digest = research["dependency_view"]["valuation_result_sha256"]
    if valuation_result_sha256(valuation) != digest:
        raise ValueError("workbench valuation hash mismatch")
    records = {record.evidence_id: record for record in model.audit_evidence}
    for source in research["source_records"]:
        record = EvidenceRecord(
            source["evidence_id"], source["title"], source["artifact_type"],
            source["path"], source["sha256"], date.fromisoformat(source["available_at"]),
            source_url=source.get("source_url"),
        )
        prior = records.get(record.evidence_id)
        if prior is not None and any(getattr(prior, field) != getattr(record, field)
                                     for field in ("path", "sha256", "available_at", "source_url", "action")):
            raise ValueError("existing research evidence conflicts with workbench audit")
        records[record.evidence_id] = record
    projected = workbench_with_bound_valuation(
        replace(model, audit_evidence=tuple(records.values())), valuation,
        expected_sha256=digest, assessment_id=research["artifact_sha256"],
    )
    bridge = price_bridge_from_payload(valuation, research["price_bridge"])
    projected = replace(projected, companies=tuple(
        company_with_pending_price_bridge(card, valuation, bridge)
        if card.symbol == valuation.symbol else card for card in projected.companies
    ))
    negative = research.get("negative_decision_review")
    if negative is None:
        return projected
    if (negative.get("scope") != "CURRENT_FAIL_CLOSED_READ_OF_EXISTING_RESEARCH"
            or negative.get("action") != "no_order"
            or negative.get("portfolio_input_status") != "BLOCKED_PRIVATE_INPUT"
            or negative.get("position_guidance") is not None
            or negative.get("price_attractiveness", {}).get("status") != "NOT_ASSESSABLE"):
        raise ValueError("Existing negative decision scope is invalid")
    predecision = pre_decision_eligibility_from_payload(negative["pre_decision_eligibility"])
    review = investment_decision_review_from_payload(negative["investment_decision_review"])
    if (predecision.status != "NOT_ELIGIBLE"
            or review.status != STATUS_INSUFFICIENT_RESEARCH
            or review.predecision_status != predecision.status
            or review.price_attractiveness_status != "NOT_ASSESSABLE"
            or review.portfolio_preconditions.provided
            or review.symbol != valuation.symbol
            or predecision.symbol != valuation.symbol
            or predecision.decision_as_of != review.decision_as_of):
        raise ValueError("Existing negative decision differs from the research scope")
    refs = {ref.artifact_type: ref for ref in review.bundle.artifact_refs}
    if (refs.get("existing_valuation_artifact") is None
            or refs["existing_valuation_artifact"].sha256 != research["artifact_sha256"]
            or refs.get("original_research_package") is None
            or refs["original_research_package"].sha256 != research["dependency_view"]["source_package_sha256"]):
        raise ValueError("Existing negative decision evidence differs from pinned research")
    reproduced = evaluate_investment_decision(
        predecision=predecision, bundle=review.bundle,
        decision_as_of=review.decision_as_of, decision_intent=None,
        confidence=review.confidence, created_at=review.created_at,
        rule_version=review.rule_version,
    )
    if reproduced.as_policy() != review.as_policy():
        raise ValueError("Existing negative decision does not replay")
    if review.decision_as_of != model.as_of:
        return projected
    if review.created_at > model.generated_at:
        raise ValueError("Existing negative decision is not available at product generation")
    cards = []
    for card in projected.companies:
        if card.symbol != valuation.symbol:
            cards.append(card)
            continue
        steps = tuple(
            replace(step, reason=review.summary, next_action="补齐研究、事件与当前价格证据后重新复核。")
            if step.key == "decision_gate" else step
            for step in card.decision_process
        )
        cards.append(replace(
            card,
            decision_process=steps,
            decision_review=(*card.decision_review,
                ("当前决策状态", "研究不足"),
                ("价格区域", "暂不可评估"),
                ("为什么不能买", review.summary),
                ("人工买入复核条件", "需完成研究批准、事件覆盖、模型有效性和当前报价桥接，再由用户人工复核。"),
                ("人工加仓复核条件", "需真实持仓、原始买入逻辑与组合容量；当前未评估。"),
                ("停止加仓条件", "模型失效、重大反证或原始投资逻辑受损时暂停并复核。"),
                ("减仓/退出复核触发", "需真实 Entry Thesis 与组合输入；当前不产生个人减仓或退出判断。"),
                ("个人仓位", "尚未接入真实组合；不生成个人仓位建议。"),
            ),
        ))
    return replace(projected, companies=tuple(cards))


def render_existing_research_report(payload: Mapping[str, Any]) -> str:
    if (payload.get("schema_version") != "product-existing-research-workbench-v1"
            or payload.get("action") != "no_order"
            or payload.get("scope") != "EXISTING_RESEARCH_ONLY_NOT_CURRENT_ADVICE"):
        raise ValueError("unsupported existing research report scope")
    research = payload["research"]
    if (research.get("action") != "no_order" or research.get("suggested_state") != "NOT_READY"
            or research.get("position_guidance") is not None):
        raise ValueError("existing report cannot admit decisions or positions")
    valuation = research["valuation"]
    lines = [f"# {payload['symbol']} Research Workbench", "",
             "Existing research only; NOT current investment advice.",
             "Decision: NOT_READY. Position guidance: unavailable. action=no_order.", "",
             "## Valuation", "",
             f"Valuation date: {valuation.get('valuation_date')}",
             f"Model: {valuation.get('model_type')}",
             f"Confidence: {valuation.get('confidence')}",
             f"Bear / Base / Bull: {valuation.get('bear_value')} / {valuation.get('base_value')} / {valuation.get('bull_value')}",
             "", "These are retained model outputs, not admitted current fair values.",
             "", "## Why There Is No Current Decision", ""]
    lines.extend(f"- {item}" for item in research["blockers"])
    lines += ["", f"Model validity: {research['model_validity']}",
              f"Strict PIT: {research['strict_pit']}",
              "Current price and portfolio approval are not established.",
              "", "## Original Evidence", ""]
    for source in research["source_records"]:
        lines += [f"- {source['evidence_id']}",
                  f"  Source: {source.get('source_url') or 'not supplied'}",
                  f"  Local original: {source['path']}",
                  f"  SHA-256: {source['sha256']}",
                  f"  Availability basis: {source['availability_basis']}"]
    lines += ["", "## Reopen Conditions", "",
              "New official evidence satisfying the registered case-specific evidence stop;",
              "admitted current event coverage, model validity and quote basis;",
              "research/decision approval and private portfolio constraints before personalized guidance.",
              "A hash match does not prove historical availability or research approval.", ""]
    return "\n".join(lines)
def render_current_research_readiness(payload: dict) -> str:
    """Explain existing research stops without rerunning or admitting research."""
    if (payload.get("schema_version") != "product-current-workbench-request-v1"
            or payload.get("action") != "no_order"
            or payload.get("position_guidance") is not None
            or payload.get("canonical_workbook_written") is not False):
        raise ValueError("unsupported current research readiness scope")
    stopped = payload.get("research_status") == "BLOCKED_BY_RESEARCH_SCHEDULER"
    if stopped:
        if payload.get("suggested_state") != "NOT_READY" or any(
            payload.get(key) is not None for key in (
                "valuation", "price_bridge", "current_status", "price_attractiveness",
                "pre_decision_eligibility", "decision_recommendation", "artifact_bundle",
            )
        ):
            raise ValueError("stopped research cannot expose newly admitted results")
    else:
        restored = verify_current_decision_workbench(payload)
        recommendation = restored.recommendation
        kind = current_recommendation_type(recommendation)
        if payload.get("suggested_state") != kind:
            raise ValueError("current readiness state differs from verified recommendation")
        zone = restored.dependency_objects.get("price_attractiveness")
        valuation = restored.dependency_objects["valuation"]
        price_status = (
            zone.status
            if zone is not None
            else recommendation.price_attractiveness_status
        )
        price_status_text = price_status
        if zone is None or price_status == "NOT_ASSESSABLE":
            price_status_text = (
                "暂不可评估；原因：当前报价或价格评估未形成；"
                "所需证据：可验证报价、报价日及适用价格桥接"
            )
        lines = [f"# {recommendation.symbol} 当前证券级研究与决策复核", "",
                 f"当前建议类型：{kind}",
                 _RECOMMENDATION_REVIEW_TEXT.get(
                     kind,
                     "当前建议类型无法映射到人工复核文案；只展示已验证结果，不产生订单。",
                 ),
                 "这是非个性化的证券级研究结果，需人工复核；不产生订单。",
                 "组合输入：BLOCKED_PRIVATE_INPUT；个人仓位：position_guidance=null。",
                 "加仓、持有、减仓和退出的个人判断仍需真实持仓、IPS 与原始 Entry Thesis。", "",
                 "## 已绑定研究结果", "",
                 f"研究日期：{recommendation.decision_as_of}",
                 f"研究论点：{recommendation.thesis}",
                 f"原始模型状态：{valuation.status}；置信度：{recommendation.confidence}",
                 f"Bear / Base / Bull：{recommendation.valuation_range.bear} / "
                 f"{recommendation.valuation_range.base} / {recommendation.valuation_range.bull}",
                 f"价格桥接：{recommendation.price_bridge_status}",
                 f"价格状态：{price_status_text}", "",
                 "## 原因与阻断", ""]
        lines.extend(f"- {reason}" for reason in dict.fromkeys(
            [*recommendation.recommendation_reasons, *recommendation.blockers]
        ))
        lines.extend(["", "## 下一触发", ""])
        lines.extend(f"- {item['text']}" for item in recommendation.next_events if item.get("text"))
        lines.extend(["", "## 证据边界", "",
                      "推荐及依赖已通过制品哈希、身份、可用时间与现有决策验证链回放。",
                      "原始模型状态与精确绑定批准分别保留；候选状态不代表个人组合通过。"])
        lines.extend(
            f"- {role}：{artifact.artifact_id}；SHA-256：{artifact.envelope.payload_sha256}"
            for role, artifact in sorted(restored.dependencies.items())
        )
        lines.extend(["", "本报告展示已有结果，不重新研究、计算估值或修改原 Excel。",
                      "action=no_order", ""])
        return "\n".join(lines)
    labels = {
        "ordinary_share_denominator_unbounded": "普通股股数口径尚未明确，不能可靠计算每股价值",
        "financial_business_cash_debt_split_missing": "金融业务与工业业务的现金、债务口径尚未分清",
        "internal_eliminations_missing": "内部抵销缺失，工业业务估值口径尚未闭合",
        "project_level_maintenance_growth_capex_missing": "维持性与增长性资本开支缺少项目级区分",
        "current_perimeter_parent_earnings_bridge_incomplete": "当前合并范围与归母利润的跨周期桥接尚未完成",
        "ordinary_vs_special_dividend_basis_unresolved": "普通与特殊分红尚未明确，不能确认正常化股息",
        "settlement_refinancing_and_post_maturity_cash_debt_unverified": "到期融资的偿付、续融资和后续现金债务尚未验证",
    }
    lines = [f"# {payload['symbol']} 当前研究缺项与重开条件", "",
             "## 现在能做什么", "",
             "当前不形成买入、加仓、持有、减仓或退出建议，也不给出建议仓位。",
             "可以继续查看已封存研究与已披露事实；它们不等于当前模型、价格或研究准入。",
             "局部证据等待不阻塞其他独立工程，不通过重复抓取同一材料伪造进展。", "",
             "## 关键研究缺项", ""]
    stops = payload.get("evidence_stops", [])
    if not isinstance(stops, list):
        raise ValueError("evidence stops must be a list")
    for stop in stops:
        if stop.get("symbol") != payload["symbol"]:
            raise ValueError("readiness stop symbol mismatch")
        lines.extend([f"### {labels.get(stop['blocker_id'], stop['blocker_id'])}", "",
                      f"- 研究问题：{stop['research_question_id']}",
                      f"- 涉及期间：{stop['period']}",
                      f"- 指定官方来源：{stop['source_id']}",
                      f"- 重新开展条件（原文）：{stop['reopen_condition']}",
                      f"- 已查材料编号：{', '.join(stop['reviewed_evidence_ids']) or '未记录'}", ""])
    if not stops:
        lines.append("此工作台没有登记公司证据停止项；这不代表研究或交易已获批准。")
    gate = payload.get("schedule_gate")
    if gate is not None:
        if not isinstance(gate, dict) or gate.get("allowed") is not False:
            raise ValueError("stopped readiness requires a denied schedule gate")
        lines.extend(["## 为什么没有重复研究", "", str(gate.get("reason", gate["status"])), ""])
    source_hash = payload["research_receipt"]["input_sha256"].get("evidence_stop_ledger")
    lines.extend(["## 证据边界", "",
                  "材料编号来自停止台账，不是本报告新核验的财报数字、历史可用时间或研究批准。",
                  f"停止台账 SHA-256：{source_hash or '本结果未绑定停止台账'}",
                  "这份报告只展示现有缺项，没有消耗重开授权、重新计算估值或修改原 Excel。",
                  "action=no_order", ""])
    return "\n".join(lines)


def render_cutoff_replay_report(payload: dict) -> str:
    if (payload.get('schema_version') != 'observed-workbench-cutoff-replay-v1'
            or payload.get('action') != 'no_order'
            or payload.get('historical_execution_validated') is not False):
        raise ValueError('unsupported observation replay report')
    lines = ['# Observed Research Result Cutoff Replay', '',
        f"Symbol: {payload['symbol']}", f"Result known at: {payload['result_known_at']}", '',
        '| Cutoff (UTC) | Result availability | Decision | Orders / fills |',
        '| --- | --- | --- | --- |']
    for row in payload['rows']:
        if row['action'] != 'no_order' or row['orders'] or row['fills']:
            raise ValueError('observation replay cannot contain execution')
        lines.append(f"| {row['cutoff']} | {row['status']} | {row['suggested_state']} | 0 / 0 |")
    lines.extend(['', '## Interpretation', '', payload['limitation'], '',
        'Earlier public filings may have existed, but this result is not backdated to their reporting periods.',
        'No historical execution, strategy effectiveness, strict PIT admission or current investment advice is established.',
        'Current model validity, price bridge, research approval and portfolio gates remain outstanding.',
        '', f"Source workbench SHA-256: {payload['workbench_sha256']}", 'action=no_order', ''])
    reconstruction = payload.get('reconstructed_financial_inputs')
    if reconstruction is not None:
        lines.extend(['## Separate Retrospective Financial Inputs', '',
            'Disclosure dates are taken from the hash-bound official index. Date-only records are usable conservatively from the following midnight.',
            'This is not historical registration of assumptions or strict PIT admission.', '',
            '| Cutoff | Eligible reviewed facts | Missing facts |', '| --- | --- | --- |'])
        for point in reconstruction['cutoffs']:
            names = ', '.join(fact['fact_name'] for fact in point['eligible_facts']) or 'none'
            lines.append(f"| {point['cutoff']} | {names} | {', '.join(point['missing_facts']) or 'none'} |")
        lines.extend(['', 'Numeric-source review does not establish a complete FinancialFacts gate, model validity, quote or investment approval.', ''])
    history = payload.get('historical_price_bridge')
    if history is not None:
        lines.extend(['## Historical Quote and Event Integrity', '',
            'Retained observations only; not current advice or strategy validation.',
            f"Quote captured at: {history['quote_observed_at']}",
            f"Event original integrity: {history['event_evidence_audit']['status']}", '',
            f"Valuation result observed at: {history['valuation_observed_at']}",
            '| Cutoff | Quote observed | Valuation observed | Historical price | Bridge arithmetic | Blockers |',
            '| --- | --- | --- | --- | --- | --- |'])
        for row in history['rows']:
            price = row['quote']['current_price'] if row['quote'] else 'unavailable'
            bridge_status = row['bridge'].get('bridge_status', 'not admitted') if row['bridge'] else 'not admitted'
            lines.append(f"| {row['cutoff']} | {row['quote_observed']} | {row['valuation_observed']} | {price} | {bridge_status} | {'; '.join(row['blockers'])} |")
        lines.extend(['', '### Original Recovery Audit', ''])
        for ref in history['event_evidence_audit']['references']:
            if ref.get('recovered_path'):
                lines.append(f"- {ref['id']}: original path remains {ref['original_path_status']}; exact sealed bytes verified at {ref['recovered_path']} (SHA-256 {ref['recovered_sha256']}).")
        lines.append('Bridge arithmetic readiness is not research approval. Pre-model events, assumption timing, strict PIT and current quote freshness remain separate gates.')
        lines.extend(['', 'Decision remains NOT_READY; no orders, fills or position guidance.', ''])
    review = payload.get('event_source_review')
    if review is not None:
        lines.extend(['## Original Announcement Review Packet', '',
            f"Status: {review['status']}",
            'Machine-extracted text is not an approved materiality conclusion. Physical page numbers are 1-based.', ''])
        for event in review['events']:
            lines.extend([f"### {event['announcement_id']} {event['title']}",
                f"Published: {event['published_at']}; review: {event['materiality_review']}", ''])
            for source in event['sources']:
                lines.extend([f"Original: {source['source_url']}", f"SHA-256: {source['sha256']}",
                    f"Text status: {source['text_status']}", ''])
                for page in source['pages'][:3]:
                    lines.extend([f"Physical page {page['physical_page']} (excerpt; full text retained in JSON):", '',
                        *('> ' + line for line in page['text'][:1800].splitlines()), ''])
            lines.extend('- ' + question for question in event['unresolved_questions'])
            lines.append('')
    scenario = payload.get('execution_engineering_scenario')
    if scenario is not None:
        lines.extend(['## Synthetic Execution Mechanism Scenario', '',
            'SYNTHETIC ENGINEERING FIXTURE: prices, capital and proposals are NOT real investment decisions.',
            'This does not pass historical execution, strategy effectiveness, strict PIT or production gates.', '',
            '| Session | Fixture state | Synthetic fill | Rejection | Shares | Cash events |',
            '| --- | --- | --- | --- | --- | --- |'])
        for row in scenario['journal']:
            fill = row.get('fill')
            summary = 'none' if fill is None else f"{fill['side']} {fill['quantity']} @ {fill['price']}; fee {fill['fee_cny']}"
            lines.append(f"| {row['date']} | {row['decision']} | {summary} | {row.get('rejected_order_reason') or 'none'} | {row['holding_shares']} | {len(row['cash_events'])} |")
        lines.extend(['', *scenario['cost_limitations'], 'No performance claim; action=no_order.', ''])
    expectations = payload.get('reverse_equity_expectations')
    if expectations is not None:
        lines.extend(['## Conditional Historical Price Expectations', '',
            f"Quote date: {expectations['quote_date']}; model basis date: {expectations['valuation_date']}",
            'Only terminal ROE is inverted; all other pinned assumptions remain fixed.',
            'This comparison uses retrospective scenarios, not then-known forecasts or a current recommendation.', '',
            '| Scenario | Price | Original terminal ROE | Price-implied terminal ROE | Forward check |',
            '| --- | --- | --- | --- | --- |'])
        for row in expectations['scenarios']:
            if row['status'] == 'NOT_ASSESSABLE':
                lines.append(f"| {row['scenario']} | unavailable | unavailable | NOT_ASSESSABLE | unavailable |")
            else:
                original_roe = format(Decimal(row['original_terminal_roe']), '.1%')
                implied_roe = format(Decimal(row['implied_terminal_roe']), '.1%')
                checked_price = format(Decimal(row['forward_reconciled_price']), '.2f')
                lines.append(f"| {row['scenario']} | {row['market_price']} | {original_roe} | {implied_roe} | {checked_price} |")
        lines.extend(['', expectations['limitation'], 'A high implied ROE can reflect different assumptions, risk or model inadequacy; it does not prove mispricing.', ''])
    metrics = payload.get('disclosed_metric_review')
    if metrics is not None:
        lines.extend(['## Source-Bound Reported Metrics', '',
            'Later annual-report comparative figures are not backdated to their original financial periods.',
            'Reported weighted ROE is not forecast ROE on opening book equity. Operating cash flow is not free cash flow.', '',
            '| Metric | Period | Value | Unit | Physical page |', '| --- | --- | --- | --- | --- |'])
        for fact in metrics['facts']:
            lines.append(f"| {fact['metric_name']} | {fact['period']} | {fact['value']} | {fact['unit']} | {fact['physical_page']} |")
        lines.extend(['', metrics['limitation'], 'Financial gate and forecast assumptions remain unapproved; action=no_order.', ''])
    cash_proxy = payload.get('reported_cash_proxy')
    if cash_proxy is not None:
        lines.extend(['## Descriptive CFO Less Cash Capex', '',
            'This is NOT FCFF, FCFE, maintenance free cash flow or proven dividend capacity.', '',
            '| Period | Consolidated CFO (CNY) | Cash capex (CNY) | Descriptive residual (CNY) |',
            '| --- | --- | --- | --- |'])
        for row in cash_proxy['rows']:
            if row['status'] == 'NOT_ASSESSABLE':
                lines.append(f"| {row['period']} | unavailable | unavailable | NOT_ASSESSABLE |")
            else:
                lines.append(f"| {row['period']} | {row['cfo_cny']} | {row['cash_capex_cny']} | {row['proxy_cny']} |")
        lines.extend(['', 'Maintenance/growth split, acquisitions, debt/interest, minority cash claims and financial-subsidiary flows require further review.',
                      'No dividend sustainability or valuation model admission; action=no_order.', ''])
    change = payload.get('reported_cash_change')
    if change is not None:
        labels = dict(sales_receipts='销售收款变化', interest_receipts='利息等收款变化',
            tax_refunds='退税收款变化', other_receipts='其他经营收款变化',
            purchases_paid='采购付款变化的影响', employees_paid='职工付款变化的影响',
            taxes_paid='税费付款变化的影响', other_payments='其他经营付款变化的影响')
        lines.extend(['## 经营现金流变化桥接', '',
            f"{change['prior_period']} → {change['current_period']}；变动合计 {Decimal(change['cfo_change_cny']) / Decimal('100000000'):.2f}亿元。",
            '| 项目 | 对CFO变化的贡献（亿元） |', '| --- | --- |'])
        for key, value in change['contributions_cny'].items():
            lines.append(f"| {labels[key]} | {Decimal(value) / Decimal('100000000'):.2f} |")
        lines.extend(['', f"原件：{change['source_binding']['source_url']}；SHA256={change['source_binding']['sha256']}",
            '现金流入、流出及变动贡献按原始元金额精确对账；表中亿元数仅用于阅读。',
            '这是现金收付款的描述性桥接，不证明下降原因具有持续性；销售回款不等于收入，'
            '营运资本与一次性因素仍需附注研究。不能据此批准分红能力、预测或买卖建议。action=no_order。', ''])
    return '\n'.join(lines)
