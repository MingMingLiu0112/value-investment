"""Synthetic full-repository decisions; never real issuer/human approval."""
from copy import deepcopy
from dataclasses import replace

import pytest

from test_advisory_decision_recommendation_v3 import (
    MODEL_ID, AS_OF, _consistency, _entry, _repository_dependencies, _save_object,
)
from value_investment_agent.application.decision.build_advisory_decision_recommendation_v3 import (
    build_advisory_decision_recommendation_v3,
)
from value_investment_agent.application.decision.restore_decision_recommendation import (
    verify_decision_recommendation_payload,
)
from value_investment_agent.application.product.value_decision_explanation import (
    project_value_decision_explanation,
)
from value_investment_agent.research_artifact_codecs import artifact_payload
from value_investment_agent.human_research_approval import artifact_fingerprint
from value_investment_agent.pre_decision_eligibility import evaluate_pre_decision_eligibility
from value_investment_agent.valuation_assumptions import ValuationAssumptionSet
from approval_transport_fixture import mint_fixture_approval


def synthetic_restored(kind):
    state = {"ADD_CANDIDATE": "FULFILLED", "HOLD": "CONSISTENT",
             "TRIM_CANDIDATE": "WEAKENED", "SELL_CANDIDATE": "BROKEN"}.get(kind)
    entry = _entry() if state else None
    review = _consistency(state) if state else None
    positive = kind in {"BUY_CANDIDATE", "ADD_CANDIDATE"}
    repository, stored, values = _repository_dependencies(
        entry=entry, consistency=review, include_positive_gate=positive)
    facts_payload = artifact_payload(values["financial_facts"])[1]
    assumptions_payload = {}
    if positive:
        values["valuation_assumptions"] = ValuationAssumptionSet(
            symbol=values["research_case"].symbol, profile_id="quality_compounder",
            model_type=MODEL_ID, as_of=AS_OF, assumptions=[], status="READY",
            blockers=[], evidence_refs=[])
        assumptions_payload = artifact_payload(values["valuation_assumptions"])[1]
        values["human_approval"] = replace(values["human_approval"],
            facts_artifact_sha256=artifact_fingerprint(facts_payload),
            assumption_set_sha256=artifact_fingerprint(assumptions_payload))
        values["human_approval"] = mint_fixture_approval(values["human_approval"])
        values["pre_decision"] = evaluate_pre_decision_eligibility(
            gate=values["research_gate"], valuation=values["valuation"],
            approval=values["human_approval"], model_validity=values["model_validity"],
            price_bridge=values["price_bridge"], event_materiality=values["event_materiality"],
            decision_as_of=AS_OF, model_id=MODEL_ID,
            research_case_payload=artifact_payload(values["research_case"])[1],
            facts_payload=facts_payload, assumptions_payload=assumptions_payload,
            price_attractiveness=values["price_attractiveness"])
        for role in ("valuation_assumptions", "human_approval", "pre_decision"):
            stored[role] = _save_object(repository, values[role], role + "-exact")
    decision = build_advisory_decision_recommendation_v3(
        run_id="p2-p3a-synthetic-" + kind,
        research_case=values["research_case"], valuation=values["valuation"],
        model_validity=values["model_validity"],
        price_bridge=values.get("price_bridge"),
        price_attractiveness=values.get("price_attractiveness"),
        pre_decision=values.get("pre_decision"),
        human_approval=values.get("human_approval"),
        entry_thesis=entry, investment_consistency_review=review, model_id=MODEL_ID,
        research_case_payload=artifact_payload(values["research_case"])[1],
        facts_payload=facts_payload, assumptions_payload=assumptions_payload,
        dependency_artifacts=stored, event_materiality=values["event_materiality"],
    )
    assert decision.recommendation_type == kind
    return verify_decision_recommendation_payload(
        repository, payload=decision.as_policy(),
        human_approval_provenance_verifier=mint_fixture_approval,
    )


@pytest.mark.parametrize("kind", ["BUY_CANDIDATE", "ADD_CANDIDATE", "HOLD",
                                  "TRIM_CANDIDATE", "SELL_CANDIDATE", "NO_ACTION"])
def test_all_actions_use_full_repository_replay_and_unchanged_explanation(kind):
    restored = synthetic_restored(kind)
    original = deepcopy(restored.recommendation.as_policy())
    explanation = project_value_decision_explanation(restored, evidence_scope="SYNTHETIC_TEST")
    assert explanation["candidate_action"] == kind
    assert explanation["action"] == "no_order" and explanation["position_guidance"] is None
    assert explanation["verification"]["repository_replay"] is True
    assert explanation["valuation_range"] == original["valuation_range"]
    assert explanation["recommendation_reasons"] == original["recommendation_reasons"]
    assert explanation["counter_evidence"] == original["counter_evidence"]
    assert explanation["next_events"] == original["next_events"]
    assert explanation["decision_changed"] is False and explanation["approval_changed"] is False
    if kind in {"BUY_CANDIDATE", "ADD_CANDIDATE"}:
        assert explanation["requires_human_review"] is True
        assert explanation["price_context"]["formal_comparison"]["current_price"] == original["current_price"]
    else:
        assert explanation["price_context"]["formal_comparison"] is None
    explanation["counter_evidence"].append({"text": "caller mutation"})
    assert restored.recommendation.as_policy() == original


@pytest.mark.parametrize("kind,state", [("HOLD", "CONSISTENT"), ("ADD_CANDIDATE", "FULFILLED"),
                                       ("TRIM_CANDIDATE", "WEAKENED"), ("SELL_CANDIDATE", "BROKEN")])
def test_thesis_transitions_retain_original_entry_and_comparison_evidence(kind, state):
    explanation = project_value_decision_explanation(synthetic_restored(kind), evidence_scope="SYNTHETIC_TEST")
    assert explanation["entry_id"] == _entry().entry_id
    assert explanation["thesis_consistency_status"] == state
    assert explanation["investment_consistency_review"]["comparisons"][0]["evidence_refs"]
    if kind in {"TRIM_CANDIDATE", "SELL_CANDIDATE"}:
        assert explanation["price_context"]["price_bridge"] is None
        assert explanation["price_context"]["formal_comparison"] is None


def test_explanation_rejects_unverified_or_arbitrary_input():
    restored = synthetic_restored("BUY_CANDIDATE")
    with pytest.raises(ValueError, match="repository-restored"):
        project_value_decision_explanation(restored.recommendation.as_policy(), evidence_scope="SYNTHETIC_TEST")
    with pytest.raises(ValueError, match="successful existing replay"):
        project_value_decision_explanation(replace(restored, verification={}), evidence_scope="SYNTHETIC_TEST")
    with pytest.raises(ValueError, match="explicit"):
        project_value_decision_explanation(restored, evidence_scope="APPROVED_REAL_HUMAN")
