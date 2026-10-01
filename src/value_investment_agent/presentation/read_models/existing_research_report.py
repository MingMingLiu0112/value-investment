"""Human-readable rendering of source-bound existing research, without calculations."""
from __future__ import annotations

from typing import Any, Mapping
from dataclasses import replace
from datetime import date
from decimal import Decimal

from ...domain.research.research_run_contract import valuation_result_sha256
from ...valuation_models.base import ValuationResult
from ...price_bridge import price_bridge_from_payload
from .product_workbench import EvidenceRecord, ProductWorkbenchReadModel
from .valuation_step import company_with_pending_price_bridge, workbench_with_bound_valuation


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
        if price.get("status") in {"NOT_READY", "PENDING_EXTERNAL_DATA"} and price.get("available") is False:
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
    return replace(projected, companies=tuple(
        company_with_pending_price_bridge(card, valuation, bridge)
        if card.symbol == valuation.symbol else card for card in projected.companies
    ))


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
    return '\n'.join(lines)
