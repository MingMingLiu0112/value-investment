"""Fail-closed receipt for a human decision to seek more event-bound evidence."""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
import re
from typing import Any, Mapping, Sequence

from .m5_event_run import M5EventRunReceipt


SCHEMA = "m5-event-bound-scenario-review-v1"
DECISION = "NEED_MORE_EVIDENCE"
BLOCKERS = (
    "POST_EVENT_OPERATING_EVIDENCE_INSUFFICIENT",
    "EVENT_DATE_DISCOUNT_INPUTS_NOT_REVIEWED",
    "DISTRIBUTION_RETENTION_NOT_REVIEWED",
    "TERMINAL_ASSUMPTIONS_NOT_REVIEWED",
)
AXES = ("base_roe_path", "bear_roe_path", "bull_roe_path",
        "terminal_roe_growth", "cost_of_equity_retention")
TRIGGERS = (
    "post_event_target_sku_volume",
    "post_event_channel_mix",
    "post_event_realized_price_margin",
    "next_official_post_event_report",
    "updated_parent_consolidated_cash_flow",
    "distribution_remittance_capital_allocation",
    "dated_cny_discount_inputs",
    "forecast_horizon_roe_fade_terminal_evidence",
)
TRIGGER_BLOCKERS = {
    "post_event_target_sku_volume": BLOCKERS[0],
    "post_event_channel_mix": BLOCKERS[0],
    "post_event_realized_price_margin": BLOCKERS[0],
    "next_official_post_event_report": BLOCKERS[0],
    "updated_parent_consolidated_cash_flow": BLOCKERS[2],
    "distribution_remittance_capital_allocation": BLOCKERS[2],
    "dated_cny_discount_inputs": BLOCKERS[1],
    "forecast_horizon_roe_fade_terminal_evidence": BLOCKERS[3],
}
_KEYS = frozenset({
    "schema_version", "symbol", "recorded_at", "reviewer_type", "provenance",
    "source_sha256", "review_package_sha256", "receipt_id", "receipt_state_sha256",
    "graph_sha256", "facts_payload_sha256", "facts_file_sha256",
    "pending_input_sha256", "pending_input_file_sha256",
    "bounded_result_sha256", "material_events", "axis_decisions", "decision",
    "event_bound_scenario_inputs_approved", "valuation_refresh_approved",
    "blockers", "evidence_triggers", "recalculation_status", "model_executed",
    "new_valuation_result", "action", "review_sha256",
})


def _sha(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def _expected_events(receipt: M5EventRunReceipt,
                     decisions: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    by_source = {"materiality-review:" + item["event_decision_id"]: item
                 for item in decisions}
    if len(by_source) != len(decisions):
        raise ValueError("Duplicate materiality decisions")
    result = []
    if receipt.action != "no_order" or len({event.symbol for event in receipt.active_events}) != 1:
        raise ValueError("Scenario review requires one no-order security")
    for event in receipt.active_events:
        decision = by_source.get(event.source_event_id)
        if (decision is None or decision["human_decision"] != "MATERIAL_REQUIRES_RECALCULATION"
            or decision["symbol"] != event.symbol
            or event.current_state.get("source_sha256") != decision["source_sha256"]):
            raise ValueError("Scenario review event lacks matching materiality decision")
        result.append({
            "event_id": event.event_id,
            "source_event_id": event.source_event_id,
            "materiality_decision_id": decision["event_decision_id"],
            "announcement_id": decision["announcement_id"],
            "pdf_sha256": decision["source_sha256"],
            "source_url": decision["source_ref"]["source_url"],
        })
    if not result:
        raise ValueError("Scenario review requires active material events")
    return sorted(result, key=lambda row: row["event_id"])


def build_need_more_evidence_review(
    *, source_bytes: bytes, review_package_bytes: bytes,
    pending_input_bytes: bytes,
    receipt: M5EventRunReceipt, decisions: Sequence[Mapping[str, Any]],
    graph_sha256: str, facts_payload_sha256: str, facts_file_sha256: str,
    bounded_result_sha256: str, recorded_at: str,
) -> dict[str, Any]:
    if (not source_bytes or not review_package_bytes or not pending_input_bytes
        or receipt.namespace != "ACTUAL"):
        raise ValueError("ACTUAL review requires original user and research package bytes")
    recorded = datetime.fromisoformat(recorded_at)
    if recorded.tzinfo is None or recorded < receipt.generated_at:
        raise ValueError("Scenario review record time is invalid")
    events = _expected_events(receipt, decisions)
    if len({item["symbol"] for item in decisions}) != 1:
        raise ValueError("Scenario review requires one security")
    if any(recorded < datetime.fromisoformat(item["reviewed_at"]) for item in decisions):
        raise ValueError("Scenario review predates materiality review")
    pending = json.loads(pending_input_bytes)
    pending_sources = {(item["sha256"], item["location"]) for item in pending["sources"]}
    if (pending["symbol"] != receipt.active_events[0].symbol
        or pending["facts"]["scenario_inputs"] is not None
        or pending["assumptions"] is not None
        or pending.get("valuation_approval") is not None
        or pending.get("input_sha256") is None
        or (receipt.state_sha256, "m5-actual-receipt") not in pending_sources
        or any((event["pdf_sha256"], event["source_url"]) not in pending_sources
               for event in events)):
        raise ValueError("Scenario review requires the blocked event-bound input lineage")
    result: dict[str, Any] = {
        "schema_version": SCHEMA,
        "symbol": receipt.active_events[0].symbol,
        "recorded_at": recorded_at,
        "reviewer_type": "user",
        "provenance": "USER_SUPPLIED_HUMAN_RESEARCH_REVIEW",
        "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "review_package_sha256": hashlib.sha256(review_package_bytes).hexdigest(),
        "receipt_id": receipt.receipt_id,
        "receipt_state_sha256": receipt.state_sha256,
        "graph_sha256": graph_sha256,
        "facts_payload_sha256": facts_payload_sha256,
        "facts_file_sha256": facts_file_sha256,
        "pending_input_sha256": pending["input_sha256"],
        "pending_input_file_sha256": hashlib.sha256(pending_input_bytes).hexdigest(),
        "bounded_result_sha256": bounded_result_sha256,
        "material_events": events,
        "axis_decisions": {axis: "NOT_APPROVED" for axis in AXES},
        "decision": DECISION,
        "event_bound_scenario_inputs_approved": False,
        "valuation_refresh_approved": False,
        "blockers": list(BLOCKERS),
        "evidence_triggers": [
            {"kind": kind, "addresses": TRIGGER_BLOCKERS[kind],
             "on_evidence": "REOPEN_RESEARCH"} for kind in TRIGGERS
        ],
        "recalculation_status": "STILL_NOT_READY",
        "model_executed": False,
        "new_valuation_result": None,
        "action": "no_order",
    }
    result["review_sha256"] = _sha(result)
    return result


def validate_need_more_evidence_review(
    review: Mapping[str, Any], *, source_bytes: bytes, review_package_bytes: bytes,
    pending_input_bytes: bytes,
    receipt: M5EventRunReceipt, decisions: Sequence[Mapping[str, Any]],
    graph_sha256: str, facts_payload_sha256: str, facts_file_sha256: str,
    bounded_result_sha256: str,
) -> None:
    if set(review) != _KEYS or not re.fullmatch(r"[0-9a-f]{64}", str(review.get("review_sha256", ""))):
        raise ValueError("Scenario review schema or hash is invalid")
    expected = build_need_more_evidence_review(
        source_bytes=source_bytes, review_package_bytes=review_package_bytes,
        pending_input_bytes=pending_input_bytes,
        receipt=receipt, decisions=decisions, graph_sha256=graph_sha256,
        facts_payload_sha256=facts_payload_sha256, facts_file_sha256=facts_file_sha256,
        bounded_result_sha256=bounded_result_sha256,
        recorded_at=review["recorded_at"],
    )
    if dict(review) != expected:
        raise ValueError("Scenario review differs from original human decision or event evidence")
