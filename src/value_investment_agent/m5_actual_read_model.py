"""Read-only projection of a reviewed actual disclosure run for M7."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from .m5_event_dependencies import DependencyGraph
from .m5_event_run import M5EventRunReceipt
from .m5_recalculation_plan import BoundedRecalculationPlan


def build_actual_event_read_model(
    *, queue: Mapping[str, Any], reviews: Sequence[Mapping[str, Any]],
    receipt: M5EventRunReceipt, graph: DependencyGraph,
    plan: BoundedRecalculationPlan, facts_artifact: Mapping[str, Any] | None = None,
    outcome_receipt: Mapping[str, Any] | None = None,
    facts_source_sha256: str | None = None,
) -> dict[str, Any]:
    if receipt.namespace != "ACTUAL" or receipt.action != "no_order" or plan.action != "no_order":
        raise ValueError("Actual no-order receipt and plan are required")
    if plan.receipt_id != receipt.receipt_id or plan.receipt_sha256 != receipt.state_sha256:
        raise ValueError("Recalculation plan does not bind the event receipt")
    from .m5_recalculation_plan import _sha
    if plan.graph_sha256 != _sha(graph.as_policy()):
        raise ValueError("Recalculation plan does not bind the dependency graph")
    outcomes_by_event = {}
    if outcome_receipt is not None:
        from .m5_bounded_recalculation_result import validate_bounded_recalculation_result
        validate_bounded_recalculation_result(outcome_receipt, receipt=receipt, plan=plan)
        outcomes_by_event = {item["event_id"]: item for item in outcome_receipt["outcomes"]}
        if len(outcomes_by_event) != len(outcome_receipt["outcomes"]):
            raise ValueError("Duplicate bounded recalculation outcome")
    scans = queue.get("scans") or ()
    if len(scans) != 1:
        raise ValueError("Read model requires exactly one pinned security scan")
    scan = scans[0]
    symbol = scan["symbol"]
    announcements = {item["announcement_id"]: item for item in scan["announcements"]}
    if len(announcements) != len(scan["announcements"]):
        raise ValueError("Duplicate announcement identity")
    decisions = [decision for review in reviews for decision in review.get("decisions", ())]
    by_announcement = {item["announcement_id"]: item for item in decisions}
    if len(by_announcement) != len(decisions):
        raise ValueError("Duplicate materiality decision")
    rows = []
    active_by_source = {event.source_event_id: event for event in receipt.active_events}
    if len(active_by_source) != len(receipt.active_events):
        raise ValueError("Duplicate actual source event")
    for announcement_id, decision in sorted(by_announcement.items()):
        source = announcements.get(announcement_id)
        if source is None or decision["symbol"] != symbol or decision["published_at"] != source["published_at"]:
            raise ValueError("Human decision is not bound to this announcement")
        refs = [ref for ref in source.get("evidence_refs", ())
                if ref.get("sha256") == decision["source_sha256"]
                and ref.get("source_url") == source["source_url"]]
        if len(refs) != 1 or decision["source_ref"]["sha256"] != decision["source_sha256"]:
            raise ValueError("Human decision PDF hash does not match archived source")
        materiality = decision["human_decision"]
        event = active_by_source.get("materiality-review:" + decision["event_decision_id"])
        if materiality == "MATERIAL_REQUIRES_RECALCULATION" and event is None:
            raise ValueError("Recalculation decision is missing its active actual event")
        if event is not None:
            if event.symbol != symbol or event.current_state.get("source_sha256") != decision["source_sha256"]:
                raise ValueError("Actual event is not bound to the reviewed PDF")
            tasks = [task for task in plan.tasks if event.event_id in task.event_ids]
            if not tasks:
                raise ValueError("Actual event has no bounded recalculation task")
            dependencies = sorted({task.dependency_kind for task in tasks})
            blockers = sorted({blocker for task in tasks for blocker in task.blockers})
            outcome = outcomes_by_event.get(event.event_id)
            if outcome is not None:
                if set(outcome["task_ids"]) != {task.task_id for task in tasks}:
                    raise ValueError("Recalculation outcome tasks do not match the plan")
                recalculation_status = outcome["status"]
                blockers = outcome["blockers"]
            else:
                recalculation_status = "RECALCULATION_PENDING"
        else:
            tasks, dependencies, blockers = [], [], []
            recalculation_status = "NO_RECALCULATION_REQUIRED"
        rows.append({
            "symbol": symbol, "announcement_id": announcement_id,
            "title": source["title"], "published_at": source["published_at"],
            "source_url": source["source_url"], "pdf_sha256": decision["source_sha256"],
            "review_id": decision["event_decision_id"], "materiality": materiality,
            "event_id": event.event_id if event else None,
            "affected_dependencies": dependencies, "recalculation_status": recalculation_status,
            "blockers": blockers, "recalculation_task_ids": [task.task_id for task in tasks],
            "new_valuation_result": None, "requires_human_decision_review": bool(tasks),
            "action": "no_order",
        })
    if set(by_announcement) != {
        item["announcement_id"] for item in scan["announcements"]
        if item.get("review_status") == "PENDING_HUMAN_REVIEW"
    }:
        raise ValueError("Human review does not cover the exact candidate queue")
    if facts_artifact is not None:
        facts = facts_artifact["payload"]
        from .research_artifacts import canonicalize_artifact_payload, sha256_text
        fact_nodes = [node for node in graph.nodes()
                      if node.symbol == symbol and node.kind == "financial_facts"]
        if (facts["symbol"] != symbol or facts["action"] != "no_order"
            or facts_artifact["identity"]["artifact_type"] != "financial_facts"
            or sha256_text(canonicalize_artifact_payload(facts)) != facts_artifact["payload_sha256"]
            or len(fact_nodes) != 1
            or (facts_source_sha256 is not None and fact_nodes[0].version != facts_source_sha256)
            or tuple(fact_nodes[0].evidence_refs) != tuple(facts_artifact.get("evidence_refs", ()))
            or (outcome_receipt is not None
                and outcome_receipt["facts_payload_sha256"] != facts_artifact["payload_sha256"])):
            raise ValueError("Verified facts artifact is not bound to this security")
    elif outcome_receipt is not None:
        raise ValueError("Bounded recalculation outcome requires verified facts")
    return {
        "schema_version": "m5-actual-event-read-model-v1", "symbol": symbol,
        "queue_id": queue["queue_id"], "receipt_id": receipt.receipt_id,
        "plan_id": plan.plan_id, "graph_sha256": plan.graph_sha256,
        "recalculation_result_sha256": outcome_receipt["result_sha256"] if outcome_receipt else None,
        "reviewed_count": len(rows), "pending_human_review": 0,
        "verified_fact_count": len(facts_artifact["payload"]["facts"]) if facts_artifact else 0,
        "rows": rows, "requires_human_review": True, "action": "no_order",
    }
