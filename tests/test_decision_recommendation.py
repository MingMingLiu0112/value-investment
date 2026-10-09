from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from value_investment_agent.application.decision.build_decision_recommendation import (
    build_decision_recommendation,
)
from value_investment_agent.domain.decision.decision_recommendation import (
    ACTION_NO_ORDER,
    PORTFOLIO_BLOCKED_PRIVATE_INPUT,
    RECOMMENDATION_BUY_CANDIDATE,
    RECOMMENDATION_NO_ACTION,
    DecisionRecommendation,
    LEGACY_DECISION_RECOMMENDATION_SCHEMA,
    decision_recommendation_from_payload,
)
from value_investment_agent.domain.research.human_research_approval import (
    DECISION_APPROVED_RESEARCH_ONLY,
    HumanResearchApprovalReceipt,
    artifact_fingerprint,
)
from value_investment_agent.event_materiality import (
    DECISION_NOT_MATERIAL,
    EVENT_MATERIALITY_SCHEMA,
    EventMaterialityDecision,
    EventMaterialityReview,
)
from value_investment_agent.model_validity import ModelValidity
from value_investment_agent.pre_decision_eligibility import (
    STATUS_ELIGIBLE,
    PreDecisionEligibility,
)
from value_investment_agent.price_attractiveness import (
    STATUS_RESEARCH_ATTRACTIVE,
    PriceAttractivenessAssessment,
)
from value_investment_agent.price_bridge import PriceBridgeResult
from value_investment_agent.research_artifact_codecs import (
    artifact_payload,
    decode_artifact,
)
from value_investment_agent.research_artifacts import (
    ARTIFACT_DECISION_RECOMMENDATION,
    ARTIFACT_EVENT_MATERIALITY_REVIEW,
    ARTIFACT_HUMAN_RESEARCH_APPROVAL,
    ARTIFACT_MODEL_VALIDITY,
    ARTIFACT_PRE_DECISION_ELIGIBILITY,
    ARTIFACT_PRICE_ATTRACTIVENESS,
    ARTIFACT_PRICE_BRIDGE,
    ARTIFACT_RESEARCH_CASE,
    ARTIFACT_VALUATION_RESULT,
    ResearchArtifactEnvelope,
    ResearchArtifactIdentity,
    StoredResearchArtifact,
    SCOPE_SECURITY,
)
from value_investment_agent.research_case import ResearchCase
from value_investment_agent.research_run_contract import valuation_result_sha256
from value_investment_agent.valuation_models.base import ValuationResult


SYMBOL = "600887"
AS_OF = date(2026, 9, 22)
REF = {"id": "case-source", "sha256": "a" * 64}
MODEL_ID = "residual_income_or_equity_value"


def _facts_payload() -> dict:
    return {"artifact_id": "facts-d2", "schema_version": "fixture-v1", "value": "facts"}


def _assumptions_payload() -> dict:
    return {
        "artifact_id": "assumptions-d2",
        "schema_version": "fixture-v1",
        "value": "assumptions",
    }


def _case() -> ResearchCase:
    def statement(text: str) -> dict:
        return {"kind": "hypothesis", "text": text, "evidence_refs": ["case-source"]}

    return ResearchCase(
        symbol=SYMBOL,
        name="伊利股份",
        as_of=AS_OF,
        run_id="d2-run",
        generated_at=datetime(2026, 9, 22, tzinfo=timezone.utc),
        research_version="d2-v1",
        industry="食品饮料",
        investment_path="quality_compounder",
        thesis="品牌与渠道支持长期现金回报",
        return_driver="经营现金流转换",
        mispricing_hypothesis="尚未证明市场系统性低估",
        financial_summary={"period_end": AS_OF.isoformat()},
        positives=[statement("质量证据"), statement("渠道证据"), statement("现金证据")],
        counter_evidence=[statement("利润下行"), statement("竞争加剧"), statement("估值条件未证明")],
        thesis_breakers=[statement("品牌力永久下降"), statement("现金转换永久恶化"), statement("治理恶化")],
        next_events=[{"kind": "gap", "text": "下一期财报"}],
        evidence_status="verified",
        valuation_status="approved_low_confidence",
        research_status="financial_scope_approved",
        blockers=[],
        evidence_refs=[REF],
        quote_date=AS_OF,
        financial_period=AS_OF,
        missing_date_reasons={},
    )


def _valuation() -> ValuationResult:
    return ValuationResult(
        symbol=SYMBOL,
        model_type="residual_income_or_equity_value",
        valuation_date=AS_OF,
        bear_value=Decimal("20"),
        base_value=Decimal("30"),
        bull_value=Decimal("40"),
        confidence="中",
        assumptions={"basis": "fixture"},
        sensitivities=[],
        evidence_refs=[{"id": "valuation-source"}],
        blockers=[],
        status="approved_research_only",
        model_version="model-v1",
    )


def _validity(*, blockers: list[str] | None = None) -> ModelValidity:
    return ModelValidity(
        model_id="model-v1",
        symbol=SYMBOL,
        model_as_of=AS_OF,
        valid_from=AS_OF,
        last_material_event_check=AS_OF,
        financial_statement_changed=False,
        capital_structure_changed=False,
        material_event_found=False,
        status="VALID",
        blockers=list(blockers or []),
        evidence_refs=[{"id": "validity-source"}],
    )


def _bridge(*, blockers: list[str] | None = None) -> PriceBridgeResult:
    valuation = _valuation()
    price = Decimal("18")
    return PriceBridgeResult(
        symbol=SYMBOL,
        valuation_date=AS_OF,
        quote_date=AS_OF,
        current_price=price,
        margin_to_bear=(valuation.bear_value - price) / valuation.bear_value,
        margin_to_base=(valuation.base_value - price) / valuation.base_value,
        model_validity_status="VALID",
        quote_status="verified_close",
        bridge_status="READY",
        evidence_refs=[{"id": "bridge-source"}],
        quote_evidence_refs=[{"id": "quote-source", "sha256": "b" * 64}],
        blockers=list(blockers or []),
        model_id="model-v1",
        model_version="model-v1",
        model_as_of=AS_OF,
        quote_symbol=SYMBOL,
        valuation_bear_value=valuation.bear_value,
        valuation_base_value=valuation.base_value,
    )


def _price(status: str = STATUS_RESEARCH_ATTRACTIVE) -> PriceAttractivenessAssessment:
    valuation = _valuation()
    bridge = _bridge()
    return PriceAttractivenessAssessment(
        symbol=SYMBOL,
        profile_id="quality_compounder",
        status=status,
        margin_to_bear=bridge.margin_to_bear,
        margin_to_base=bridge.margin_to_base,
        downside_reference=valuation.bear_value,
        upside_reference=valuation.base_value,
        confidence=valuation.confidence,
        reasons=["fixture"],
        blockers=[],
        evidence_refs=[{"id": "price-source"}],
    )


def _predecision() -> PreDecisionEligibility:
    return PreDecisionEligibility(
        symbol=SYMBOL,
        decision_as_of=AS_OF,
        status=STATUS_ELIGIBLE,
        approval_status="APPROVED_RESEARCH_ONLY",
        model_validity_status="VALID",
        price_bridge_status="READY",
        event_review_watermark=AS_OF,
        blockers=(),
        evidence_refs=({"id": "predecision-source"},),
        price_attractiveness_status=STATUS_RESEARCH_ATTRACTIVE,
        positive_price_review_eligible=True,
    )


def _approval_bundle() -> tuple[
    HumanResearchApprovalReceipt, dict, dict, dict
]:
    _, case_payload = artifact_payload(_case())
    facts_payload = _facts_payload()
    assumptions_payload = _assumptions_payload()
    receipt = HumanResearchApprovalReceipt(
        approval_id="approval-d2",
        symbol=SYMBOL,
        security_id=SYMBOL,
        profile_id="quality_compounder",
        valuation_artifact_id="valuation-d2",
        valuation_artifact_sha256=valuation_result_sha256(_valuation()),
        valuation_model_id=MODEL_ID,
        valuation_model_version=_valuation().model_version,
        research_case_id="case-d2",
        research_case_sha256=artifact_fingerprint(case_payload),
        assumption_set_id="assumptions-d2",
        assumption_set_sha256=artifact_fingerprint(assumptions_payload),
        facts_artifact_id="facts-d2",
        facts_artifact_sha256=artifact_fingerprint(facts_payload),
        reviewed_at=datetime(2026, 9, 22, tzinfo=timezone.utc),
        review_as_of=AS_OF,
        reviewer_type="human_research_lead",
        decision=DECISION_APPROVED_RESEARCH_ONLY,
        price_assessment_eligible=True,
        remaining_blockers=(),
        evidence_refs=({"id": "approval-source"},),
    )
    return receipt, case_payload, facts_payload, assumptions_payload


def _dependencies() -> dict:
    approval, case_payload, facts_payload, assumptions_payload = _approval_bundle()
    return {
        "research_case": _case(),
        "valuation": _valuation(),
        "model_validity": _validity(),
        "price_bridge": _bridge(),
        "price_attractiveness": _price(),
        "pre_decision": _predecision(),
        "human_approval": approval,
        "event_materiality": _event_materiality(),
        "model_id": MODEL_ID,
        "research_case_payload": case_payload,
        "facts_payload": facts_payload,
        "assumptions_payload": assumptions_payload,
        "additional_blockers": (),
    }


def _stored_dependencies(dependencies: dict) -> dict[str, StoredResearchArtifact]:
    types = {
        "research_case": ARTIFACT_RESEARCH_CASE,
        "valuation": ARTIFACT_VALUATION_RESULT,
        "model_validity": ARTIFACT_MODEL_VALIDITY,
        "price_bridge": ARTIFACT_PRICE_BRIDGE,
        "price_attractiveness": ARTIFACT_PRICE_ATTRACTIVENESS,
        "pre_decision": ARTIFACT_PRE_DECISION_ELIGIBILITY,
        "human_approval": ARTIFACT_HUMAN_RESEARCH_APPROVAL,
        "event_materiality": ARTIFACT_EVENT_MATERIALITY_REVIEW,
    }
    stored = {}
    for role, artifact_type in types.items():
        if role not in dependencies:
            continue
        _, payload = artifact_payload(dependencies[role])
        identity = ResearchArtifactIdentity(
            scope_type=SCOPE_SECURITY,
            scope_key=SYMBOL,
            artifact_type=artifact_type,
            schema_version="research-artifact-v1",
            as_of=AS_OF,
            available_at=datetime(2026, 9, 22, tzinfo=timezone.utc),
        )
        stored[role] = StoredResearchArtifact(
            artifact_id=f"fixture-{role}",
            envelope=ResearchArtifactEnvelope.build(
                identity=identity, payload=payload, run_id="d2-run"
            ),
            created_at=datetime(2026, 9, 22, tzinfo=timezone.utc),
        )
    return stored


def _event_materiality() -> EventMaterialityReview:
    reviewed_at = datetime(2026, 9, 22, tzinfo=timezone.utc)
    decision = EventMaterialityDecision(
        event_decision_id="event-d2",
        symbol=SYMBOL,
        announcement_id="1225511409",
        title="fixture disclosure",
        published_at=datetime(2026, 8, 27, tzinfo=timezone.utc),
        source_ref={"id": "event-source", "sha256": "c" * 64},
        source_sha256="c" * 64,
        machine_candidate_reason="fixture candidate",
        human_decision=DECISION_NOT_MATERIAL,
        affected_domains=(),
        affected_fact_fields=(),
        affected_assumptions=(),
        affected_artifacts=(),
        requires_recalculation=False,
        requires_model_stale=False,
        requires_followup=False,
        reviewed_at=reviewed_at,
        review_notes=("fixture review",),
    )
    return EventMaterialityReview(
        review_id="review-d2",
        schema_version=EVENT_MATERIALITY_SCHEMA,
        symbol=SYMBOL,
        scan_id="scan-d2",
        scan_sha256="d" * 64,
        scan_from=date(2026, 8, 1),
        scan_to=AS_OF,
        reviewed_at=reviewed_at,
        review_as_of=AS_OF,
        reviewer_type="human_research_lead",
        decisions=(decision,),
        evidence_refs=({"id": "scan-d2", "sha256": "d" * 64},),
    )


_MISSING = object()


def _build(
    *,
    validity=None,
    bridge=None,
    price_attractiveness=None,
    predecision=_MISSING,
    approval=_MISSING,
    event_materiality=_MISSING,
) -> DecisionRecommendation:
    human_approval, case_payload, facts_payload, assumptions_payload = (
        _approval_bundle()
    )
    case = _case()
    valuation = _valuation()
    selected_validity = validity or _validity()
    selected_bridge = bridge or _bridge()
    selected_price = price_attractiveness or _price()
    selected_predecision = _predecision() if predecision is _MISSING else predecision
    selected_approval = human_approval if approval is _MISSING else approval
    selected_event = _event_materiality() if event_materiality is _MISSING else event_materiality
    dependency_values = _dependencies() | {
        "research_case": case,
        "valuation": valuation,
        "model_validity": selected_validity,
        "price_bridge": selected_bridge,
        "price_attractiveness": selected_price,
        "pre_decision": selected_predecision,
        "human_approval": selected_approval,
        "event_materiality": selected_event,
    }
    stored_dependencies = _stored_dependencies({
        role: value for role, value in dependency_values.items() if value is not None
    })
    return build_decision_recommendation(
        run_id="d2-run",
        research_case=case,
        valuation=valuation,
        model_validity=selected_validity,
        price_bridge=selected_bridge,
        price_attractiveness=selected_price,
        pre_decision=selected_predecision,
        human_approval=selected_approval,
        model_id=MODEL_ID,
        research_case_payload=case_payload,
        facts_payload=facts_payload,
        assumptions_payload=assumptions_payload,
        event_materiality=selected_event,
        dependency_artifacts=stored_dependencies,
    )


def test_decision_recommendation_positive_contract_is_no_order_and_no_position():
    recommendation = _build()
    payload = recommendation.as_policy()

    assert recommendation.recommendation_action == RECOMMENDATION_BUY_CANDIDATE
    assert recommendation.action == ACTION_NO_ORDER
    assert recommendation.portfolio_input_status == PORTFOLIO_BLOCKED_PRIVATE_INPUT
    assert recommendation.position_guidance is None
    assert payload["valuation_range"]["base"] == "30"
    assert payload["current_price"] == "18"
    assert payload["entry_zone"]["low"] == "20"
    assert payload["entry_zone"]["high"] == "30"
    assert "target_weight" not in payload
    assert "order_quantity" not in payload


def test_positive_gates_without_stored_dependencies_remain_no_action():
    dependencies = _dependencies()
    recommendation = build_decision_recommendation(
        run_id="d2-run",
        research_case=dependencies["research_case"],
        valuation=dependencies["valuation"],
        model_validity=dependencies["model_validity"],
        price_bridge=dependencies["price_bridge"],
        price_attractiveness=dependencies["price_attractiveness"],
        pre_decision=dependencies["pre_decision"],
        human_approval=dependencies["human_approval"],
        model_id=MODEL_ID,
        research_case_payload=dependencies["research_case_payload"],
        facts_payload=dependencies["facts_payload"],
        assumptions_payload=dependencies["assumptions_payload"],
        event_materiality=dependencies["event_materiality"],
    )
    assert recommendation.recommendation_action == RECOMMENDATION_NO_ACTION
    assert "decision_dependency_artifacts_unavailable" in recommendation.blockers
    assert recommendation.action == ACTION_NO_ORDER


def test_stored_valuation_reference_must_match_decision_input():
    dependencies = _dependencies()
    mismatched = dict(dependencies)
    mismatched["valuation"] = replace(
        dependencies["valuation"], base_value=Decimal("31")
    )
    with pytest.raises(ValueError, match="valuation payload does not match input"):
        build_decision_recommendation(
            run_id="d2-run",
            research_case=dependencies["research_case"],
            valuation=dependencies["valuation"],
            model_validity=dependencies["model_validity"],
            price_bridge=dependencies["price_bridge"],
            price_attractiveness=dependencies["price_attractiveness"],
            pre_decision=dependencies["pre_decision"],
            human_approval=dependencies["human_approval"],
            model_id=MODEL_ID,
            research_case_payload=dependencies["research_case_payload"],
            facts_payload=dependencies["facts_payload"],
            assumptions_payload=dependencies["assumptions_payload"],
            event_materiality=dependencies["event_materiality"],
            dependency_artifacts=_stored_dependencies(mismatched),
        )


def test_model_validity_blocker_propagates_to_no_action():
    recommendation = _build(validity=_validity(blockers=["material_event_unresolved"]))

    assert recommendation.recommendation_action == RECOMMENDATION_NO_ACTION
    assert "material_event_unresolved" in recommendation.blockers


def test_price_bridge_blocker_propagates_to_no_action():
    recommendation = _build(bridge=_bridge(blockers=["quote_identity_mismatch"]))

    assert recommendation.recommendation_action == RECOMMENDATION_NO_ACTION
    assert "quote_identity_mismatch" in recommendation.blockers


def test_missing_predecision_cannot_invent_a_buy_review():
    recommendation = _build(predecision=None)

    assert recommendation.recommendation_action == RECOMMENDATION_NO_ACTION
    assert recommendation.position_guidance is None
    assert recommendation.portfolio_input_status == PORTFOLIO_BLOCKED_PRIVATE_INPUT


def test_missing_resolved_approval_or_event_review_fails_closed():
    missing_approval = build_decision_recommendation(
        run_id="d2-run",
        research_case=_case(),
        valuation=_valuation(),
        model_validity=_validity(),
        price_bridge=_bridge(),
        price_attractiveness=_price(),
        pre_decision=_predecision(),
        human_approval=None,
        model_id=MODEL_ID,
        research_case_payload=_approval_bundle()[1],
        facts_payload=_approval_bundle()[2],
        assumptions_payload=_approval_bundle()[3],
        event_materiality=_event_materiality(),
    )
    missing_event = _build(event_materiality=None)

    assert missing_approval.recommendation_action == RECOMMENDATION_NO_ACTION
    assert "human_research_approval_not_resolved" in missing_approval.blockers
    assert missing_event.recommendation_action == RECOMMENDATION_NO_ACTION
    assert "event_materiality_review_unavailable" in missing_event.blockers


def test_binding_identity_mismatch_fails_closed():
    recommendation = _build(
        bridge=replace(_bridge(), model_version="model-v2"),
    )

    assert recommendation.recommendation_action == RECOMMENDATION_NO_ACTION
    assert any(
        "price bridge model version" in blocker for blocker in recommendation.blockers
    )


def test_low_confidence_price_assessment_cannot_raise_positive_action():
    recommendation = _build(
        price_attractiveness=replace(_price(), confidence="低"),
    )

    assert recommendation.recommendation_action == RECOMMENDATION_NO_ACTION


def test_positive_payload_cannot_be_upgraded_without_dependency_revalidation():
    payload = _build().as_policy()
    assert payload["decision_input_sha256"]
    assert any(ref.get("sha256") == "b" * 64 for ref in payload["evidence_refs"])

    forged = dict(payload)
    forged["price_attractiveness_status"] = "NOT_ASSESSABLE"
    with pytest.raises(ValueError, match="RESEARCH_ATTRACTIVE"):
        decision_recommendation_from_payload(forged)

    mismatched = dict(payload)
    mismatched["decision_input_sha256"] = "e" * 64
    dependencies = _dependencies()
    with pytest.raises(ValueError, match="fingerprint does not match"):
        decision_recommendation_from_payload(
            mismatched,
            dependencies=dependencies,
        )

    tampered = dict(payload)
    tampered["valuation_range"] = dict(payload["valuation_range"])
    tampered["valuation_range"]["base"] = "31"
    with pytest.raises(ValueError, match="payload fingerprint"):
        decision_recommendation_from_payload(
            tampered,
            dependencies=dependencies,
        )


def test_positive_restoration_rejects_missing_dependency_objects():
    payload = _build().as_policy()
    with pytest.raises(ValueError, match="dependency contracts are incomplete"):
        decision_recommendation_from_payload(
            payload,
            dependencies={},
        )


def test_case_and_valuation_blockers_prevent_positive_action():
    approval, case_payload, facts_payload, assumptions_payload = _approval_bundle()
    recommendation = build_decision_recommendation(
        run_id="d2-run",
        research_case=replace(_case(), blockers=["case blocker"]),
        valuation=replace(_valuation(), blockers=["valuation blocker"]),
        model_validity=_validity(),
        price_bridge=_bridge(),
        price_attractiveness=_price(),
        pre_decision=_predecision(),
        human_approval=approval,
        model_id=MODEL_ID,
        research_case_payload=case_payload,
        facts_payload=facts_payload,
        assumptions_payload=assumptions_payload,
        event_materiality=_event_materiality(),
    )

    assert recommendation.recommendation_action == RECOMMENDATION_NO_ACTION
    assert "research_case:case blocker" in recommendation.blockers
    assert "valuation:valuation blocker" in recommendation.blockers


def test_future_approval_review_cannot_raise_positive_action():
    approval, case_payload, facts_payload, assumptions_payload = _approval_bundle()
    future_approval = replace(
        approval,
        reviewed_at=datetime(2026, 9, 23, tzinfo=timezone.utc),
        review_as_of=date(2026, 9, 23),
    )
    recommendation = build_decision_recommendation(
        run_id="d2-run",
        research_case=_case(),
        valuation=_valuation(),
        model_validity=_validity(),
        price_bridge=_bridge(),
        price_attractiveness=_price(),
        pre_decision=_predecision(),
        human_approval=future_approval,
        model_id=MODEL_ID,
        research_case_payload=case_payload,
        facts_payload=facts_payload,
        assumptions_payload=assumptions_payload,
        event_materiality=_event_materiality(),
        decision_as_of=AS_OF,
    )

    assert recommendation.recommendation_action == RECOMMENDATION_NO_ACTION
    assert "human_approval_after_decision" in recommendation.blockers


def test_protected_non_positive_actions_require_dependency_fingerprint():
    payload = _build().as_policy()
    payload["recommendation_type"] = "SELL_CANDIDATE"
    payload["decision_input_sha256"] = None

    with pytest.raises(ValueError, match="D3 recommendation actions are not implemented"):
        decision_recommendation_from_payload(payload)


def test_bridge_scenario_and_price_assessment_binding_drift_fail_closed():
    with pytest.raises(ValueError, match="margins must be recomputed"):
        replace(_bridge(), valuation_base_value=Decimal("31"))

    approval, case_payload, facts_payload, assumptions_payload = _approval_bundle()
    mismatched_price = replace(_price(), upside_reference=Decimal("99"))
    recommendation = build_decision_recommendation(
        run_id="d2-run",
        research_case=_case(),
        valuation=_valuation(),
        model_validity=_validity(),
        price_bridge=_bridge(),
        price_attractiveness=mismatched_price,
        pre_decision=_predecision(),
        human_approval=approval,
        model_id=MODEL_ID,
        research_case_payload=case_payload,
        facts_payload=facts_payload,
        assumptions_payload=assumptions_payload,
        event_materiality=_event_materiality(),
    )

    assert recommendation.recommendation_action == RECOMMENDATION_NO_ACTION
    assert any("upside reference" in item for item in recommendation.blockers)


def test_positive_recommendation_rejects_blockers_and_unsafe_fields():
    with pytest.raises(ValueError, match="Positive recommendation cannot carry blockers"):
        replace(_build(), blockers=("contradiction",))
    with pytest.raises(ValueError, match="cannot invent position guidance"):
        replace(_build(), position_guidance={"target_weight": "0.1"})


def test_decision_recommendation_artifact_roundtrip():
    recommendation = _build()
    artifact_type, payload = artifact_payload(recommendation)
    with pytest.raises(ValueError, match="requires a repository"):
        decode_artifact(artifact_type, payload)
    assert artifact_type == ARTIFACT_DECISION_RECOMMENDATION
    assert payload == recommendation.as_policy()


def test_recommendation_type_is_separate_from_order_action_and_sealed():
    recommendation = _build()
    payload = recommendation.as_policy()
    assert payload["schema_version"] == "advisory-decision-recommendation-v2"
    assert payload["recommendation_type"] == "BUY_CANDIDATE"
    assert payload["action"] == "no_order"
    assert "recommendation_action" not in payload
    restored = decision_recommendation_from_payload(payload, dependencies=_dependencies())
    assert restored.recommendation_type == "BUY_CANDIDATE"
    payload["recommendation_type"] = "NO_ACTION"
    with pytest.raises(ValueError, match="payload fingerprint"):
        decision_recommendation_from_payload(payload)


def test_legacy_recommendation_preserves_its_exact_payload_and_hash():
    legacy = replace(
        _build(), schema_version=LEGACY_DECISION_RECOMMENDATION_SCHEMA,
        recommendation_payload_sha256=None,
    )
    payload = legacy.as_policy()
    assert "recommendation_type" not in payload
    assert payload["recommendation_action"] == "BUY_CANDIDATE"
    restored = decision_recommendation_from_payload(payload, dependencies=_dependencies())
    assert restored.as_policy() == payload
    assert restored.recommendation_payload_sha256 == legacy.recommendation_payload_sha256


@pytest.mark.parametrize("schema", [
    "advisory-decision-recommendation-v1", "advisory-decision-recommendation-v2",
])
def test_recommendation_rejects_ambiguous_classification_fields(schema):
    payload = _build().as_policy()
    payload.update(schema_version=schema, recommendation_action="NO_ACTION")
    with pytest.raises(ValueError, match="classification"):
        decision_recommendation_from_payload(payload)


def _conditional_recommendation(*, stale_approval=False, missing_approval=False):
    case = replace(_case(), valuation_status="under_review")
    valuation = replace(_valuation(), status="conditional_research_only")
    approval, _, facts_payload, assumptions_payload = _approval_bundle()
    _, case_payload = artifact_payload(case)
    approval = replace(
        approval,
        research_case_sha256=artifact_fingerprint(case_payload),
        valuation_artifact_sha256=valuation_result_sha256(valuation),
    )
    if stale_approval:
        approval = replace(approval, facts_artifact_sha256="f" * 64)
    dependencies = _dependencies() | {
        "research_case": case, "valuation": valuation, "human_approval": approval,
    }
    return build_decision_recommendation(
        run_id="conditional-d2", research_case=case, valuation=valuation,
        model_validity=_validity(), price_bridge=_bridge(),
        price_attractiveness=_price(), pre_decision=_predecision(),
        human_approval=None if missing_approval else approval, model_id=MODEL_ID,
        research_case_payload=case_payload, facts_payload=facts_payload,
        assumptions_payload=assumptions_payload,
        event_materiality=_event_materiality(),
        dependency_artifacts=_stored_dependencies(dependencies),
    )


def test_bound_approval_admits_conditional_model_without_rewriting_valuation():
    recommendation = _conditional_recommendation()
    assert recommendation.recommendation_type == "BUY_CANDIDATE"
    assert recommendation.action == "no_order"
    assert recommendation.position_guidance is None
    assert not recommendation.blockers


@pytest.mark.parametrize("options", [
    {"stale_approval": True}, {"missing_approval": True},
])
def test_conditional_model_cannot_bypass_exact_research_approval(options):
    recommendation = _conditional_recommendation(**options)
    assert recommendation.recommendation_type == "NO_ACTION"
    assert "valuation_status_not_approved_for_research" in recommendation.blockers
