from datetime import datetime, timezone
from dataclasses import replace
from types import SimpleNamespace

import pytest

from value_investment_agent.m5_bounded_recalculation_result import (
    evaluate_bounded_recalculation, validate_bounded_recalculation_result,
)
from value_investment_agent.m5_event_dependencies import DependencyGraph, DependencyNode
from value_investment_agent.m5_recalculation_plan import (
    STATUS_BLOCKED_GRAPH_GAP, _sha, build_bounded_recalculation_plan,
)
from value_investment_agent.research_artifacts import canonicalize_artifact_payload, sha256_text


def _inputs():
    at = datetime(2026, 9, 25, tzinfo=timezone.utc)
    ref = {"id": "official-pdf", "source_url": "https://static.cninfo.com.cn/finalpage/a.pdf", "sha256": "c" * 64}
    event = SimpleNamespace(event_id="event-1", source_event_id="review-1", symbol="600519",
                            current_state={"direct_dependency_kinds": ["valuation_inputs"]},
                            evidence_refs=(ref,))
    receipt = SimpleNamespace(namespace="ACTUAL", action="no_order", receipt_id="receipt-1",
                              state_sha256="a" * 64, active_events=(event,), generated_at=at,
                              invalidations=(SimpleNamespace(event_id="event-1"),))
    graph = DependencyGraph((DependencyNode(
        node_id="facts-1", kind="financial_facts", symbol="600519", inputs=(),
        version="b" * 64, evidence_refs=(ref,),
    ),))
    plan = build_bounded_recalculation_plan(receipt=receipt, graph=graph, generated_at=at)
    payload = {"schema_version": "m5-verified-financial-facts-v1", "symbol": "600519",
               "pdf_sha256": "c" * 64, "source_url": ref["source_url"],
               "facts": [{"field": "operating_revenue", "value": "1"}], "action": "no_order"}
    facts = {"identity": {"artifact_type": "financial_facts", "scope_key": "600519"},
             "payload": payload, "payload_sha256": sha256_text(canonicalize_artifact_payload(payload)),
             "evidence_refs": [ref]}
    return dict(receipt=receipt, graph=graph, plan=plan, facts_artifact=facts,
                evaluated_at=at, facts_source_sha256="b" * 64)


def test_missing_registered_valuation_inputs_produces_hashed_not_ready_result():
    args = _inputs()
    result = evaluate_bounded_recalculation(**args)
    assert result["outcomes"][0]["status"] == "STILL_NOT_READY"
    assert result["outcomes"][0]["router_status"] == "NOT_READY_MISSING_VALUATION_INPUTS"
    assert result["outcomes"][0]["model_executed"] is False
    assert result["outcomes"][0]["new_valuation_result"] is None
    validate_bounded_recalculation_result(result, receipt=args["receipt"], plan=args["plan"])


def test_tampered_not_ready_result_cannot_claim_recalculated():
    args = _inputs()
    result = evaluate_bounded_recalculation(**args)
    result["outcomes"][0]["status"] = "RECALCULATED"
    with pytest.raises(ValueError, match="hash mismatch"):
        validate_bounded_recalculation_result(result, receipt=args["receipt"], plan=args["plan"])


def test_rehashed_false_status_is_rejected():
    args = _inputs()
    result = evaluate_bounded_recalculation(**args)
    result["outcomes"][0]["status"] = "RECALCULATED"
    result["result_sha256"] = _sha({key: value for key, value in result.items()
                                    if key != "result_sha256"})
    with pytest.raises(ValueError, match="bounded tasks"):
        validate_bounded_recalculation_result(result, receipt=args["receipt"], plan=args["plan"])


def test_wrong_facts_file_version_is_rejected():
    args = _inputs()
    args["facts_source_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="file hash"):
        evaluate_bounded_recalculation(**args)


def test_rehashed_duplicate_outcome_is_rejected():
    args = _inputs()
    result = evaluate_bounded_recalculation(**args)
    result["outcomes"].append(dict(result["outcomes"][0]))
    result["result_sha256"] = _sha({key: value for key, value in result.items()
                                    if key != "result_sha256"})
    with pytest.raises(ValueError, match="exactly once"):
        validate_bounded_recalculation_result(result, receipt=args["receipt"], plan=args["plan"])


def test_wrong_facts_pdf_evidence_is_rejected():
    args = _inputs()
    args["facts_artifact"]["evidence_refs"][0] = dict(
        args["facts_artifact"]["evidence_refs"][0], sha256="0" * 64,
    )
    with pytest.raises(ValueError, match="PDF evidence"):
        evaluate_bounded_recalculation(**args)


def test_plan_that_omits_one_invalidated_dependency_is_rejected():
    args = _inputs()
    args["receipt"].active_events[0].current_state["direct_dependency_kinds"] = [
        "financial_facts", "valuation_inputs",
    ]
    full_plan = build_bounded_recalculation_plan(
        receipt=args["receipt"], graph=args["graph"], generated_at=args["evaluated_at"],
    )
    args["plan"] = replace(full_plan, tasks=full_plan.tasks[:1])
    with pytest.raises(ValueError, match="omits or changes"):
        evaluate_bounded_recalculation(**args)
