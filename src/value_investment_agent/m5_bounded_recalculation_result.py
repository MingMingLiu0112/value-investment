"""Fail-closed result of attempting to route an ACTUAL bounded recalculation."""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
import re
from typing import Any, Mapping

from .m5_event_dependencies import DependencyGraph
from .m5_event_run import M5EventRunReceipt
from .m5_recalculation_plan import (
    BoundedRecalculationPlan, STATUS_BLOCKED_GRAPH_GAP, _sha,
    build_bounded_recalculation_plan,
)
from .research_artifacts import canonicalize_artifact_payload, sha256_text


def evaluate_bounded_recalculation(
    *, receipt: M5EventRunReceipt, graph: DependencyGraph,
    plan: BoundedRecalculationPlan, facts_artifact: Mapping[str, Any],
    evaluated_at: datetime, facts_source_sha256: str | None = None,
) -> dict[str, Any]:
    if evaluated_at.tzinfo is None or evaluated_at < plan.generated_at:
        raise ValueError("Recalculation result needs a real, later timestamp")
    if receipt.namespace != "ACTUAL" or receipt.action != "no_order" or plan.action != "no_order":
        raise ValueError("Only an ACTUAL no-order run can enter bounded recalculation")
    if (plan.receipt_id != receipt.receipt_id or plan.receipt_sha256 != receipt.state_sha256
        or plan.graph_sha256 != _sha(graph.as_policy())):
        raise ValueError("Recalculation inputs do not match the frozen plan")
    expected_plan = build_bounded_recalculation_plan(
        receipt=receipt, graph=graph, generated_at=plan.generated_at,
    )
    if plan.as_policy() != expected_plan.as_policy():
        raise ValueError("Recalculation plan omits or changes invalidated dependencies")
    facts = facts_artifact["payload"]
    identity = facts_artifact["identity"]
    if (facts.get("schema_version") != "m5-verified-financial-facts-v1"
        or facts.get("action") != "no_order" or not facts.get("facts")
        or identity["artifact_type"] != "financial_facts"
        or identity["scope_key"] != facts.get("symbol")
        or sha256_text(canonicalize_artifact_payload(facts)) != facts_artifact["payload_sha256"]):
        raise ValueError("Versioned financial facts are not verified")
    symbols = {event.symbol for event in receipt.active_events}
    if symbols != {facts["symbol"]}:
        raise ValueError("Financial facts do not match the actual event security")
    matching_events = [
        event for event in receipt.active_events
        if any(ref.get("sha256") == facts.get("pdf_sha256")
               and ref.get("source_url") == facts.get("source_url")
               for ref in event.evidence_refs)
    ]
    if (len(matching_events) != 1
        or not isinstance(facts.get("announcement_id"), str)
        or facts["announcement_id"] not in re.findall(r"\d+", matching_events[0].source_event_id)):
        raise ValueError("Verified facts filing is not bound to exactly one ACTUAL event")
    fact_nodes = [node for node in graph.nodes()
                  if node.symbol == facts["symbol"] and node.kind == "financial_facts"]
    if len(fact_nodes) != 1:
        raise ValueError("Verified facts are absent from the dependency graph")
    fact_node = fact_nodes[0]
    if (facts_source_sha256 is not None and fact_node.version != facts_source_sha256):
        raise ValueError("Verified facts file hash does not match the dependency node")
    if (len(facts_artifact.get("evidence_refs", ())) != 1
        or facts_artifact["evidence_refs"][0].get("sha256") != facts.get("pdf_sha256")
        or facts_artifact["evidence_refs"][0].get("source_url") != facts.get("source_url")
        or tuple(fact_node.evidence_refs) != tuple(facts_artifact["evidence_refs"])):
        raise ValueError("Verified facts PDF evidence does not match the dependency node")
    outcomes = []
    for event in receipt.active_events:
        tasks = [task for task in plan.tasks if event.event_id in task.event_ids]
        if not tasks:
            raise ValueError("Active event has no bounded tasks")
        blockers = sorted({blocker for task in tasks for blocker in task.blockers})
        if any(task.status == STATUS_BLOCKED_GRAPH_GAP for task in tasks):
            status = "STILL_NOT_READY"
            router_status = (
                "NOT_READY_MISSING_VALUATION_INPUTS"
                if "missing_dependency_node:valuation_inputs" in blockers else "NOT_READY_GRAPH_GAP"
            )
        else:
            status = "EVIDENCE_REQUIRED"
            router_status = "NOT_READY_PENDING_DOMAIN_REVALIDATION"
        outcomes.append({
            "event_id": event.event_id, "source_event_id": event.source_event_id,
            "symbol": event.symbol, "task_ids": [task.task_id for task in tasks],
            "status": status, "router_status": router_status,
            "blockers": blockers, "model_executed": False,
            "new_valuation_result": None, "requires_human_review": True,
            "action": "no_order",
        })
    payload = {
        "schema_version": "m5-bounded-recalculation-result-v1",
        "evaluated_at": evaluated_at.isoformat(),
        "receipt_id": receipt.receipt_id, "receipt_sha256": receipt.state_sha256,
        "plan_id": plan.plan_id, "plan_sha256": _sha(plan.as_policy()),
        "graph_sha256": plan.graph_sha256,
        "facts_payload_sha256": facts_artifact["payload_sha256"],
        "outcomes": outcomes, "requires_human_review": True, "action": "no_order",
    }
    payload["result_sha256"] = hashlib.sha256(json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    return payload


def validate_bounded_recalculation_result(
    payload: Mapping[str, Any], *, receipt: M5EventRunReceipt,
    plan: BoundedRecalculationPlan,
) -> None:
    if (payload.get("schema_version") != "m5-bounded-recalculation-result-v1"
        or payload.get("receipt_id") != receipt.receipt_id
        or payload.get("receipt_sha256") != receipt.state_sha256
        or payload.get("plan_id") != plan.plan_id
        or payload.get("plan_sha256") != _sha(plan.as_policy())
        or payload.get("action") != "no_order"):
        raise ValueError("Bounded recalculation result is not bound to its inputs")
    body = {key: value for key, value in payload.items()
            if key not in {"result_sha256", "input_file_sha256"}}
    if hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":")).encode("utf-8")).hexdigest() != payload.get("result_sha256"):
        raise ValueError("Bounded recalculation result hash mismatch")
    events = {event.event_id: event for event in receipt.active_events}
    outcomes = payload.get("outcomes", ())
    if len(outcomes) != len(events) or {item.get("event_id") for item in outcomes} != set(events):
        raise ValueError("Recalculation outcomes must cover active events exactly once")
    for item in outcomes:
        event = events[item["event_id"]]
        tasks = [task for task in plan.tasks if event.event_id in task.event_ids]
        blockers = sorted({blocker for task in tasks for blocker in task.blockers})
        graph_gap = any(task.status == STATUS_BLOCKED_GRAPH_GAP for task in tasks)
        expected_status = "STILL_NOT_READY" if graph_gap else "EVIDENCE_REQUIRED"
        expected_router = ("NOT_READY_MISSING_VALUATION_INPUTS"
                           if "missing_dependency_node:valuation_inputs" in blockers
                           else "NOT_READY_GRAPH_GAP") if graph_gap else "NOT_READY_PENDING_DOMAIN_REVALIDATION"
        if (not tasks or item.get("source_event_id") != event.source_event_id
            or item.get("symbol") != event.symbol
            or set(item.get("task_ids", ())) != {task.task_id for task in tasks}
            or len(item.get("task_ids", ())) != len(tasks)
            or item.get("blockers") != blockers
            or item.get("status") != expected_status
            or item.get("router_status") != expected_router
            or item.get("requires_human_review") is not True
            or item.get("new_valuation_result") is not None
            or item.get("model_executed") is not False
            or item.get("action") != "no_order"):
            raise ValueError("Recalculation outcome does not match its bounded tasks")
