"""Dedicated current projection checks using real dependency replay."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from types import SimpleNamespace

import pytest

from test_decision_recommendation import (
    AS_OF, MODEL_ID, SYMBOL, _approval_bundle, _bridge, _case,
    _event_materiality, _valuation, _validity,
)
from test_research_application import residual_facts
from test_product_workbench_excel import _payload
from value_investment_agent.application.decision.artifact_bundle import export_artifact_bundle
from value_investment_agent.application.decision.build_decision_recommendation import build_decision_recommendation
from value_investment_agent.application.product.decision_surface import (
    current_recommendation_type, project_verified_decision_workbench,
    verify_current_decision_workbench,
)
from value_investment_agent.domain.research.human_research_approval import artifact_fingerprint
from value_investment_agent.domain.decision.decision_recommendation import (
    DECISION_RECOMMENDATION_SCHEMA, LEGACY_DECISION_RECOMMENDATION_SCHEMA,
    recommendation_payload_fingerprint,
)
from value_investment_agent.domain.research.research_gate import evaluate_with_human_approval
from value_investment_agent.pre_decision_eligibility import evaluate_pre_decision_eligibility
from value_investment_agent.price_attractiveness import assess_price_attractiveness
from value_investment_agent.research_artifact_codecs import artifact_payload
from value_investment_agent.research_artifacts import (
    ARTIFACT_DECISION_RECOMMENDATION, ResearchArtifactEnvelope,
    ResearchArtifactIdentity, StoredResearchArtifact,
)
from value_investment_agent.research_run_contract import valuation_result_sha256
from value_investment_agent.valuation_assumptions import ValuationAssumptionSet
from value_investment_agent.presentation.read_models.product_workbench import product_workbench_from_payload


def _stored(role, artifact_type, payload):
    return StoredResearchArtifact(
        artifact_id=f"current-{role}",
        envelope=ResearchArtifactEnvelope.build(
            identity=ResearchArtifactIdentity(
                scope_type="security", scope_key=SYMBOL, artifact_type=artifact_type,
                schema_version="c3-v1", as_of=AS_OF,
                available_at=datetime(2026, 9, 22, tzinfo=timezone.utc),
            ),
            payload=payload, run_id="current-projection-test",
        ),
        created_at=datetime(2026, 9, 22, tzinfo=timezone.utc),
    )


def decision_workbench(*, confidence="中", approval_state=None, financial_pass=True,
                       business_pass=True, valuation_status="conditional_research_only",
                       missing_approval=False, validity_state="VALID",
                       schema_version=DECISION_RECOMMENDATION_SCHEMA):
    case = _case()
    if not financial_pass:
        case = replace(case, research_status="incomplete")
    if not business_pass:
        case = replace(case, positives=[])
    facts = replace(residual_facts(SYMBOL), as_of=AS_OF, confidence=confidence)
    valuation = replace(_valuation(), status=valuation_status, confidence=confidence)
    validity = _validity()
    if validity_state != "VALID":
        validity = replace(validity, status=validity_state, blockers=["model_review_required"])
    bridge = _bridge()
    assumptions = ValuationAssumptionSet(
        symbol=SYMBOL, profile_id="quality_compounder", model_type=MODEL_ID,
        as_of=AS_OF, assumptions=[], status="READY", blockers=[], evidence_refs=[],
    )
    case_payload = artifact_payload(case)[1]
    facts_payload = artifact_payload(facts)[1]
    assumptions_payload = artifact_payload(assumptions)[1]
    approval = replace(
        _approval_bundle()[0],
        valuation_artifact_sha256=valuation_result_sha256(valuation),
        research_case_sha256=artifact_fingerprint(case_payload),
        facts_artifact_sha256=artifact_fingerprint(facts_payload),
        assumption_set_sha256=artifact_fingerprint(assumptions_payload),
    )
    if approval_state is not None:
        approval = replace(approval, decision=approval_state, price_assessment_eligible=False,
                           remaining_blockers=("approval_review_required",))
    gate = evaluate_with_human_approval(
        case, valuation, model_id=MODEL_ID, approval=approval,
        research_case_payload=case_payload, facts_payload=facts_payload,
        assumptions_payload=assumptions_payload,
    )
    price = assess_price_attractiveness(
        gate, valuation, bridge, profile_id="quality_compounder",
        human_approval_price_assessment_eligible=approval.price_assessment_eligible,
    )
    event = _event_materiality()
    predecision = evaluate_pre_decision_eligibility(
        gate=gate, valuation=valuation, approval=approval, model_validity=validity,
        price_bridge=bridge, event_materiality=event, decision_as_of=AS_OF,
        model_id=MODEL_ID, research_case_payload=case_payload, facts_payload=facts_payload,
        assumptions_payload=assumptions_payload, price_attractiveness=price,
    )
    objects = dict(
        research_case=case, financial_facts=facts, valuation_assumptions=assumptions,
        valuation=valuation, model_validity=validity, price_bridge=bridge,
        price_attractiveness=price, human_approval=approval,
        research_gate=gate, pre_decision=predecision, event_materiality=event,
    )
    if missing_approval:
        del objects["human_approval"]
        del objects["pre_decision"]
    dependencies = {
        role: _stored(role, *artifact_payload(value)) for role, value in objects.items()
    }
    recommendation = build_decision_recommendation(
        run_id="current-projection-test", research_case=case, valuation=valuation,
        model_validity=validity, price_bridge=bridge, price_attractiveness=price,
        human_approval=None if missing_approval else approval,
        pre_decision=None if missing_approval else predecision,
        event_materiality=event, model_id=MODEL_ID, decision_as_of=AS_OF,
        research_case_payload=None if missing_approval else case_payload,
        facts_payload=None if missing_approval else facts_payload,
        assumptions_payload=None if missing_approval else assumptions_payload,
        dependency_artifacts=dependencies,
        schema_version=schema_version,
    )
    recommendation_payload = recommendation.as_policy()
    stored_decision = _stored("decision", ARTIFACT_DECISION_RECOMMENDATION, recommendation_payload)
    return {
        "schema_version": "product-current-workbench-request-v1",
        "generated_at": "2026-09-22T12:00:00+00:00", "symbol": SYMBOL,
        "research_status": "COMPLETED", "action": "no_order",
        "portfolio_input_status": "BLOCKED_PRIVATE_INPUT", "position_guidance": None,
        "canonical_workbook_written": False, "suggested_state": recommendation.recommendation_type,
        "decision_recommendation": recommendation_payload,
        "artifact_bundle": export_artifact_bundle([*dependencies.values(), stored_decision]),
    }


def project(tmp_path, workbench, *, stale=True):
    runtime = tmp_path / "runtime"
    runtime.mkdir(exist_ok=True)
    source = runtime / "decision.json"
    source.write_text(json.dumps(workbench, ensure_ascii=False), encoding="utf-8")
    payload = _payload()
    payload["generated_at"] = "2026-09-22T13:00:00+00:00"
    payload["as_of"] = AS_OF.isoformat()
    payload["companies"][0]["symbol"] = SYMBOL
    payload["opportunities"][0]["symbol"] = SYMBOL
    if stale:
        from value_investment_agent.presentation.read_models.product_workbench import DECISION_STEP_TITLES
        payload["companies"][0]["decision_process"] = [
            {"key": key, "status": "PASS", "reason": "stale", "next_action": "stale",
             "assessment_id": "stale", "evidence_refs": ["evidence-1"]}
            for key in DECISION_STEP_TITLES
        ]
    project_verified_decision_workbench(
        payload, root=tmp_path, path=source,
        expected_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
    )
    product_workbench_from_payload(payload)
    return payload


def test_approved_conditional_model_refreshes_all_steps_without_personal_position(tmp_path):
    workbench = decision_workbench()
    assert workbench["suggested_state"] == "BUY_CANDIDATE"
    assert "recommendation_action" not in workbench["decision_recommendation"]
    result = project(tmp_path, workbench)
    steps = {step["key"]: step for step in result["companies"][0]["decision_process"]}
    for key, step in steps.items():
        assert step["status"] == (
            "BLOCKED" if key == "portfolio_gate" else "CONDITIONAL" if key == "decision_gate" else "PASS"
        )
        assert step["reason"] != "stale"
        assert step["assessment_id"].startswith("decision-workbench-")
        assert step["evidence_refs"] != ["evidence-1"]
    assert "position_guidance=null" in steps["portfolio_gate"]["reason"]
    assert verify_current_decision_workbench(workbench).dependency_objects["valuation"].status == "conditional_research_only"


def test_waiting_price_zone_is_projected_without_inferring_failed_research(tmp_path):
    workbench = decision_workbench(confidence="低")
    assert workbench["suggested_state"] == "NO_ACTION"
    result = project(tmp_path, workbench, stale=False)
    card = result["companies"][0]
    assert {item["label"]: item["value"] for item in card["decision_review"]}["价格区域"] == "等待更好的价格"
    steps = {step["key"]: step for step in card["decision_process"]}
    assert steps["research_gate"]["status"] == "PASS"
    assert steps["decision_gate"]["status"] == "BLOCKED"
    assert steps["portfolio_gate"]["status"] == "BLOCKED"


def test_latest_replayed_case_replaces_inherited_business_and_counterevidence(tmp_path):
    workbench = decision_workbench(confidence="低")
    result = project(tmp_path, workbench)
    card = result["companies"][0]
    recommendation = verify_current_decision_workbench(workbench).recommendation
    sections = {item["key"]: item for item in card["sections"]}
    assert sections["business_quality"]["summary"] == recommendation.thesis
    expected = "；".join(item["text"] for item in recommendation.counter_evidence)
    assert sections["risks_counterevidence"]["summary"] == expected
    reviews = {item["label"]: item["value"] for item in card["decision_review"]}
    assert reviews["最强反证"] == expected
    for key in ("business_quality", "risks_counterevidence"):
        assert sections[key]["evidence_refs"][0].startswith("decision-workbench-")
        assert sections[key]["status"] == "PARTIAL"
    assert recommendation.action == "no_order"
    assert workbench["suggested_state"] == "NO_ACTION"


@pytest.mark.parametrize("options, blocked", [
    ({"financial_pass": False}, "financial_facts"),
    ({"business_pass": False}, "business_quality"),
    ({"missing_approval": True}, "research_gate"),
    ({"approval_state": "REJECTED_NEEDS_REWORK"}, "valuation"),
    ({"approval_state": "SUPERSEDED"}, "research_gate"),
    ({"validity_state": "UNKNOWN"}, "model_applicability"),
])
def test_negative_dependencies_replace_old_pass(tmp_path, options, blocked):
    workbench = decision_workbench(**options)
    assert workbench["suggested_state"] == "NO_ACTION"
    result = project(tmp_path, workbench)
    steps = {step["key"]: step for step in result["companies"][0]["decision_process"]}
    assert steps[blocked]["status"] == "BLOCKED"
    assert steps["portfolio_gate"]["status"] == "BLOCKED"
    assert steps["decision_gate"]["status"] == "BLOCKED"
    assert all(step["reason"] != "stale" for step in steps.values())


def test_type_property_precedes_legacy_field():
    assert current_recommendation_type(SimpleNamespace(
        recommendation_type="NO_ACTION", recommendation_action="BUY_CANDIDATE",
    )) == "NO_ACTION"
    assert current_recommendation_type(SimpleNamespace(recommendation_action="NO_ACTION")) == "NO_ACTION"


def test_legacy_v1_payload_projects_via_typed_property(tmp_path):
    workbench = decision_workbench(schema_version=LEGACY_DECISION_RECOMMENDATION_SCHEMA)
    assert "recommendation_action" in workbench["decision_recommendation"]
    assert "recommendation_type" not in workbench["decision_recommendation"]
    result = project(tmp_path, workbench)
    assert result["companies"][0]["decision_process"][-1]["status"] == "CONDITIONAL"
    assert verify_current_decision_workbench(workbench).recommendation.as_policy() == workbench["decision_recommendation"]


def test_current_workbench_allows_generation_after_research_date():
    workbench = decision_workbench()
    workbench["generated_at"] = "2026-09-23T00:00:00+00:00"

    restored = verify_current_decision_workbench(workbench)

    assert restored.recommendation.decision_as_of.isoformat() == "2026-09-22"


def forged_candidate():
    workbench = decision_workbench(approval_state="REJECTED_NEEDS_REWORK")
    recommendation = workbench["decision_recommendation"]
    recommendation["recommendation_type"] = "BUY_CANDIDATE"
    recommendation["blockers"] = []
    recommendation["price_attractiveness_status"] = "RESEARCH_ATTRACTIVE"
    recommendation["entry_zone"] = decision_workbench()["decision_recommendation"]["entry_zone"]
    recommendation["recommendation_payload_sha256"] = recommendation_payload_fingerprint(recommendation)
    workbench["suggested_state"] = "BUY_CANDIDATE"
    decision = _stored("decision", ARTIFACT_DECISION_RECOMMENDATION, recommendation)
    rows = workbench["artifact_bundle"]["artifacts"]
    rows[-1] = export_artifact_bundle([decision])["artifacts"][0]
    return workbench


def test_rehashed_candidate_without_approval_fails_semantic_replay(tmp_path):
    with pytest.raises(ValueError, match="full repository replay"):
        project(tmp_path, forged_candidate())


@pytest.mark.parametrize("change", ["future", "symbol", "state", "hash", "unbound"])
def test_invalid_workbench_rejected_before_projection(tmp_path, change):
    workbench = deepcopy(decision_workbench())
    if change == "future":
        workbench["generated_at"] = "2026-09-21T12:00:00+00:00"
    elif change == "symbol":
        workbench["symbol"] = "600519"
    elif change == "state":
        workbench["suggested_state"] = "NO_ACTION"
    elif change == "hash":
        workbench["artifact_bundle"]["artifacts"][0]["canonical_payload"] += " "
    else:
        workbench.pop("artifact_bundle")
    with pytest.raises(ValueError):
        project(tmp_path, workbench)
