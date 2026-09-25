"""Human event-level reconciliation after a validated bounded research refresh."""
from __future__ import annotations

from datetime import datetime
import hashlib
from typing import Any, Mapping, Sequence

from .event_materiality import (
    REVIEWER_HUMAN_RESEARCH_LEAD, event_materiality_decision_from_payload,
)
from .m5_bounded_refresh import validate_bounded_research_refresh
from .m5_recalculation_plan import _sha


_REVIEW_KEYS = frozenset({
    "schema_version", "receipt_id", "receipt_sha256", "plan_id", "plan_sha256",
    "graph_sha256", "refresh_result_sha256", "facts_payload_sha256",
    "assumption_package_sha256", "reviewer_id", "reviewer_type", "reviewed_at",
    "event_reviews", "requires_human_decision_review", "action", "review_sha256",
})
_EVENT_KEYS = frozenset({
    "event_id", "source_event_id", "materiality_decision_id", "pdf_sha256",
    "affected_domains", "affected_fact_fields", "affected_assumptions",
    "affected_artifacts", "valuation_artifact_id", "verdict", "review_notes",
    "evidence_sha256",
})
_VERDICTS = {"EVENT_REFRESH_ACCEPTED", "EVENT_REFRESH_REJECTED"}


def validate_event_refresh_review(
    review: Mapping[str, Any], *, refresh: dict,
    decisions: Sequence[Mapping[str, Any]], refresh_validation: dict,
) -> bool:
    """Return True only when every material event was explicitly reconciled."""
    validate_bounded_research_refresh(refresh, **refresh_validation)
    if set(review) != _REVIEW_KEYS or review.get("schema_version") != "m5-event-refresh-review-v1":
        raise ValueError("Event refresh review schema is incomplete")
    body = {key: value for key, value in review.items() if key != "review_sha256"}
    if _sha(body) != review.get("review_sha256"):
        raise ValueError("Event refresh review hash mismatch")
    receipt = refresh_validation["receipt"]
    plan = refresh_validation["plan"]
    graph = refresh_validation["graph"]
    facts = refresh_validation["facts_artifact"]
    assumption_bytes = refresh_validation["assumption_package_bytes"]
    reviewed_at = datetime.fromisoformat(review["reviewed_at"])
    if (reviewed_at.tzinfo is None
        or reviewed_at < datetime.fromisoformat(refresh["evaluated_at"])
        or review["receipt_id"] != receipt.receipt_id
        or review["receipt_sha256"] != receipt.state_sha256
        or review["plan_id"] != plan.plan_id
        or review["plan_sha256"] != _sha(plan.as_policy())
        or review["graph_sha256"] != _sha(graph.as_policy())
        or review["refresh_result_sha256"] != refresh["result_sha256"]
        or review["facts_payload_sha256"] != facts["payload_sha256"]
        or review["assumption_package_sha256"] != hashlib.sha256(assumption_bytes).hexdigest()
        or not isinstance(review["reviewer_id"], str) or not review["reviewer_id"].strip()
        or review["reviewer_type"] != REVIEWER_HUMAN_RESEARCH_LEAD
        or review["requires_human_decision_review"] is not True
        or review["action"] != "no_order"):
        raise ValueError("Event refresh review is not bound to validated evidence")
    by_source = {
        "materiality-review:" + item["event_decision_id"]:
            event_materiality_decision_from_payload(item)
        for item in decisions
    }
    by_event = {event.event_id: event for event in receipt.active_events}
    outcomes = {item["event_id"]: item for item in refresh["outcomes"]}
    rows = review["event_reviews"]
    if (not isinstance(rows, list) or len(rows) != len(by_event)
        or {item.get("event_id") for item in rows} != set(by_event)):
        raise ValueError("Event refresh review must cover every active event exactly once")
    for row in rows:
        if set(row) != _EVENT_KEYS:
            raise ValueError("Event refresh review row schema is incomplete")
        event = by_event[row["event_id"]]
        decision = by_source.get(event.source_event_id)
        if decision is None or decision.reviewed_at is None:
            raise ValueError("Event refresh review lacks original human materiality decision")
        pdf_refs = [ref for ref in event.evidence_refs
                    if ref.get("sha256") and ref.get("source_url")]
        if len(pdf_refs) != 1:
            raise ValueError("Event refresh review lacks one original PDF")
        value = outcomes[event.event_id]["new_valuation_result"]
        expected_hashes = sorted({
            pdf_refs[0]["sha256"], receipt.state_sha256,
            facts["payload_sha256"], review["assumption_package_sha256"],
            value["payload_sha256"],
        })
        if (row["source_event_id"] != event.source_event_id
            or row["materiality_decision_id"] != decision.event_decision_id
            or row["pdf_sha256"] != decision.source_sha256
            or row["pdf_sha256"] != pdf_refs[0]["sha256"]
            or row["affected_domains"] != list(decision.affected_domains)
            or row["affected_fact_fields"] != list(decision.affected_fact_fields)
            or row["affected_assumptions"] != list(decision.affected_assumptions)
            or row["affected_artifacts"] != list(decision.affected_artifacts)
            or row["valuation_artifact_id"] != value["artifact_id"]
            or row["verdict"] not in _VERDICTS
            or not isinstance(row["review_notes"], str) or not row["review_notes"].strip()
            or row["evidence_sha256"] != expected_hashes
            or reviewed_at < decision.reviewed_at):
            raise ValueError("Event refresh review does not reconcile the material event")
    accepted = all(row["verdict"] == "EVENT_REFRESH_ACCEPTED" for row in rows)
    if accepted and any(
        item["new_valuation_result"]["model_validity_status"] != "VALID"
        or item["new_valuation_result"]["model_validity_artifact_id"] is None
        for item in refresh["outcomes"]
    ):
        raise ValueError("Event refresh cannot reconcile non-VALID model validity")
    return accepted
