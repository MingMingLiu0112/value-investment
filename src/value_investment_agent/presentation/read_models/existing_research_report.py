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
    return '\n'.join(lines)
