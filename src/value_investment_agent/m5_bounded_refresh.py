"""Offline execution of an event-bound research refresh through the shared service."""
from __future__ import annotations

from datetime import datetime
import hashlib
import json

from .m5_bounded_recalculation_result import evaluate_bounded_recalculation
from .m5_event_dependencies import DependencyGraph, KIND_VALUATION_INPUTS, KIND_VALUATION_RESULT
from .m5_event_run import M5EventRunReceipt
from .m5_recalculation_plan import BoundedRecalculationPlan, _sha
from .m5_research_artifact_graph import attach_valuation_input_descriptor
from .research_application import ResearchApplicationService
from .research_artifact_repository import ResearchArtifactRepository
from .research_artifacts import (
    ARTIFACT_MODEL_VALIDITY, ARTIFACT_VALUATION_RESULT, SCOPE_SECURITY,
    canonicalize_artifact_payload, sha256_text,
)
from .research_input import ResearchInputDescriptor, build_research_run_spec
from .research_runtime_import import RuntimeArtifactCandidate
from .research_artifact_codecs import artifact_payload
from .valuation_router import route_profile


def _validated_context(
    *, receipt: M5EventRunReceipt, graph: DependencyGraph,
    plan: BoundedRecalculationPlan, facts_artifact: dict,
    facts_source_sha256: str, descriptor: ResearchInputDescriptor,
    prior_candidate: RuntimeArtifactCandidate,
    operating_basis_bytes: bytes, assumption_package_bytes: bytes,
    repository: ResearchArtifactRepository,
    evaluated_at: datetime,
    prior_artifact_id: str | None = None,
):
    baseline = evaluate_bounded_recalculation(
        receipt=receipt, graph=graph, plan=plan, facts_artifact=facts_artifact,
        facts_source_sha256=facts_source_sha256, evaluated_at=evaluated_at,
    )
    if plan.blocked or descriptor.point_in_time.computed_at > evaluated_at:
        raise ValueError("Bounded refresh cannot execute with a graph gap or future input")
    if any(not any(task.dependency_kind == KIND_VALUATION_INPUTS
                   and event.event_id in task.event_ids for task in plan.tasks)
           for event in receipt.active_events):
        raise ValueError("Every refreshed event must invalidate valuation inputs")
    input_nodes = [node for node in graph.nodes()
                   if node.symbol == descriptor.symbol and node.kind == KIND_VALUATION_INPUTS]
    if len(input_nodes) != 1:
        raise ValueError("Bounded refresh requires one complete valuation input node")
    base_graph = DependencyGraph(node for node in graph.nodes() if node != input_nodes[0])
    rebuilt = attach_valuation_input_descriptor(
        graph=base_graph, descriptor=descriptor, receipt=receipt,
        operating_basis_bytes=operating_basis_bytes,
        assumption_package_bytes=assumption_package_bytes,
    )
    if rebuilt.as_policy() != graph.as_policy():
        raise ValueError("Frozen graph valuation inputs do not match the descriptor")
    old_nodes = [node for node in graph.nodes()
                 if node.symbol == descriptor.symbol and node.kind == KIND_VALUATION_RESULT]
    if len(old_nodes) != 1 or prior_candidate.source_sha256 != old_nodes[0].version:
        raise ValueError("Prior valuation does not match the frozen graph")
    if (prior_candidate.symbol != descriptor.symbol
        or prior_candidate.artifact_type != ARTIFACT_VALUATION_RESULT
        or hashlib.sha256(prior_candidate.source_path.read_bytes()).hexdigest()
        != prior_candidate.source_sha256):
        raise ValueError("Prior valuation source bytes do not match the frozen graph")
    prior = (repository.load_by_id(prior_artifact_id) if prior_artifact_id else
             repository.load_latest(SCOPE_SECURITY, descriptor.symbol,
                                    ARTIFACT_VALUATION_RESULT))
    repository.verify(prior)
    if (prior.envelope.payload_sha256
        != sha256_text(canonicalize_artifact_payload(prior_candidate.payload))
        or prior.envelope.identity.artifact_type != ARTIFACT_VALUATION_RESULT
        or prior.envelope.identity.scope_key != descriptor.symbol
        or prior.envelope.identity.available_at >= descriptor.point_in_time.available_at):
        raise ValueError("Prior persisted valuation differs from the pinned source")
    return baseline, prior


def execute_bounded_research_refresh(
    *, receipt: M5EventRunReceipt, graph: DependencyGraph,
    plan: BoundedRecalculationPlan, facts_artifact: dict,
    facts_source_sha256: str, descriptor: ResearchInputDescriptor,
    prior_candidate: RuntimeArtifactCandidate,
    operating_basis_bytes: bytes, assumption_package_bytes: bytes,
    application: ResearchApplicationService,
    evaluated_at: datetime,
) -> dict:
    """Compute only the affected company's new research; never make an order."""
    baseline, prior = _validated_context(
        receipt=receipt, graph=graph, plan=plan, facts_artifact=facts_artifact,
        facts_source_sha256=facts_source_sha256, descriptor=descriptor,
        prior_candidate=prior_candidate, operating_basis_bytes=operating_basis_bytes,
        assumption_package_bytes=assumption_package_bytes,
        repository=application.repository,
        evaluated_at=evaluated_at,
    )
    outcome = application.run_company_research(build_research_run_spec(descriptor))
    if outcome.valuation is None or outcome.valuation.status == "not_ready":
        raise ValueError("Complete valuation inputs did not produce a model result")
    if any(value is None for value in (
        outcome.valuation.bear_value, outcome.valuation.base_value,
        outcome.valuation.bull_value,
    )):
        raise ValueError("Refreshed valuation is missing scenario values")
    stored = {artifact.envelope.identity.artifact_type: artifact
              for artifact in outcome.stored_artifacts}
    refreshed = stored[ARTIFACT_VALUATION_RESULT]
    application.repository.verify(refreshed)
    if (refreshed.artifact_id == prior.artifact_id
        or refreshed.envelope.run_id != descriptor.run_id
        or refreshed.envelope.identity.available_at != descriptor.point_in_time.available_at
        or application.repository.load_latest(
            SCOPE_SECURITY, descriptor.symbol, ARTIFACT_VALUATION_RESULT,
        ).artifact_id != refreshed.artifact_id):
        raise ValueError("Bounded refresh did not persist a distinct new valuation version")
    validity = stored.get(ARTIFACT_MODEL_VALIDITY)
    if validity is not None:
        application.repository.verify(validity)
    # A generic VALID scan cannot establish that this material event was re-reviewed.
    status = "MODEL_STALE"
    reference = {
        "artifact_id": refreshed.artifact_id,
        "payload_sha256": refreshed.envelope.payload_sha256,
        "model_version": outcome.valuation.model_version,
        "valuation_date": outcome.valuation.valuation_date.isoformat(),
        "research_run_id": descriptor.run_id,
        "input_sha256": descriptor.input_sha256,
        "model_validity_artifact_id": validity.artifact_id if validity else None,
        "model_validity_status": outcome.model_validity.status if outcome.model_validity else "UNKNOWN",
        "event_validity_status": "UNRECONCILED",
    }
    results = []
    for item in baseline["outcomes"]:
        results.append({**item, "status": status,
                        "router_status": outcome.valuation.status,
                        "blockers": ["event_bound_model_validity_not_reconciled"],
                        "model_executed": True,
                        "new_valuation_result": reference})
    payload = {
        "schema_version": "m5-bounded-research-refresh-v1",
        "evaluated_at": evaluated_at.isoformat(),
        "receipt_id": receipt.receipt_id,
        "receipt_sha256": receipt.state_sha256,
        "plan_id": plan.plan_id,
        "plan_sha256": _sha(plan.as_policy()),
        "graph_sha256": _sha(graph.as_policy()),
        "facts_payload_sha256": facts_artifact["payload_sha256"],
        "prior_valuation_artifact_id": prior.artifact_id,
        "prior_valuation_payload_sha256": prior.envelope.payload_sha256,
        "outcomes": results,
        "requires_human_review": True,
        "action": "no_order",
    }
    payload["result_sha256"] = hashlib.sha256(json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    validate_bounded_research_refresh(
        payload, receipt=receipt, graph=graph, plan=plan,
        facts_artifact=facts_artifact, facts_source_sha256=facts_source_sha256,
        descriptor=descriptor, prior_candidate=prior_candidate,
        operating_basis_bytes=operating_basis_bytes,
        assumption_package_bytes=assumption_package_bytes,
        repository=application.repository,
    )
    return payload


def validate_bounded_research_refresh(
    payload: dict, *, receipt: M5EventRunReceipt, graph: DependencyGraph,
    plan: BoundedRecalculationPlan, facts_artifact: dict,
    facts_source_sha256: str, descriptor: ResearchInputDescriptor,
    prior_candidate: RuntimeArtifactCandidate, operating_basis_bytes: bytes,
    assumption_package_bytes: bytes,
    repository: ResearchArtifactRepository,
) -> None:
    if payload.get("schema_version") != "m5-bounded-research-refresh-v1":
        raise ValueError("Unsupported bounded refresh result")
    body = {key: value for key, value in payload.items() if key != "result_sha256"}
    if _sha(body) != payload.get("result_sha256"):
        raise ValueError("Bounded refresh result hash mismatch")
    evaluated_at = datetime.fromisoformat(payload["evaluated_at"])
    baseline, prior = _validated_context(
        receipt=receipt, graph=graph, plan=plan, facts_artifact=facts_artifact,
        facts_source_sha256=facts_source_sha256, descriptor=descriptor,
        prior_candidate=prior_candidate, operating_basis_bytes=operating_basis_bytes,
        assumption_package_bytes=assumption_package_bytes,
        repository=repository,
        evaluated_at=evaluated_at,
        prior_artifact_id=payload.get("prior_valuation_artifact_id"),
    )
    if (payload.get("receipt_id") != receipt.receipt_id
        or payload.get("receipt_sha256") != receipt.state_sha256
        or payload.get("plan_id") != plan.plan_id
        or payload.get("plan_sha256") != _sha(plan.as_policy())
        or payload.get("graph_sha256") != _sha(graph.as_policy())
        or payload.get("facts_payload_sha256") != facts_artifact["payload_sha256"]
        or payload.get("prior_valuation_artifact_id") != prior.artifact_id
        or payload.get("prior_valuation_payload_sha256") != prior.envelope.payload_sha256
        or payload.get("requires_human_review") is not True
        or payload.get("action") != "no_order"):
        raise ValueError("Bounded refresh result is not bound to its frozen inputs")
    outcomes = payload.get("outcomes", ())
    if (len(outcomes) != len(baseline["outcomes"])
        or {item.get("event_id") for item in outcomes}
        != {item["event_id"] for item in baseline["outcomes"]}):
        raise ValueError("Bounded refresh outcomes do not cover active events exactly once")
    first_ref = outcomes[0]["new_valuation_result"]
    refreshed = repository.load_by_id(first_ref["artifact_id"])
    repository.verify(refreshed)
    val_identity = refreshed.envelope.identity
    val_payload = refreshed.envelope.payload_object()
    route = route_profile(descriptor.profile_id, descriptor.requested_model)
    expected_valuation = route.build_model().value(descriptor.facts, descriptor.research_case)
    _, expected_payload = artifact_payload(expected_valuation)
    if (val_identity.artifact_type != ARTIFACT_VALUATION_RESULT
        or val_identity.scope_key != descriptor.symbol
        or val_identity.available_at != descriptor.point_in_time.available_at
        or refreshed.envelope.run_id != descriptor.run_id
        or refreshed.artifact_id == prior.artifact_id
        or val_payload != expected_payload
        or val_payload.get("status") == "not_ready"
        or any(val_payload.get(key) is None for key in
               ("bear_value", "base_value", "bull_value"))):
        raise ValueError("Refreshed valuation artifact is not a distinct complete result")
    if repository.load_latest(
        SCOPE_SECURITY, descriptor.symbol, ARTIFACT_VALUATION_RESULT,
    ).artifact_id != refreshed.artifact_id:
        raise ValueError("Refreshed valuation is no longer the current research version")
    validity_id = first_ref.get("model_validity_artifact_id")
    validity = repository.load_by_id(validity_id) if validity_id else None
    if validity is not None:
        repository.verify(validity)
        if (validity.envelope.identity.artifact_type != ARTIFACT_MODEL_VALIDITY
            or validity.envelope.identity.scope_key != descriptor.symbol
            or validity.envelope.run_id != descriptor.run_id):
            raise ValueError("Refreshed model validity artifact does not match")
    expected_ref = {
        "artifact_id": refreshed.artifact_id,
        "payload_sha256": refreshed.envelope.payload_sha256,
        "model_version": val_payload["model_version"],
        "valuation_date": val_payload["valuation_date"],
        "research_run_id": descriptor.run_id,
        "input_sha256": descriptor.input_sha256,
        "model_validity_artifact_id": validity_id,
        "model_validity_status": validity.envelope.payload_object()["status"] if validity else "UNKNOWN",
        "event_validity_status": "UNRECONCILED",
    }
    for item, expected in zip(outcomes, baseline["outcomes"]):
        if (item.get("event_id") != expected["event_id"]
            or item.get("source_event_id") != expected["source_event_id"]
            or item.get("symbol") != expected["symbol"]
            or item.get("task_ids") != expected["task_ids"]
            or item.get("status") != "MODEL_STALE"
            or item.get("router_status") != val_payload["status"]
            or item.get("blockers") != ["event_bound_model_validity_not_reconciled"]
            or item.get("model_executed") is not True
            or item.get("new_valuation_result") != expected_ref
            or item.get("requires_human_review") is not True
            or item.get("action") != "no_order"):
            raise ValueError("Bounded refresh outcome does not match persisted artifacts")
