from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal

from value_investment_agent.event_materiality import (
    DECISION_NOT_MATERIAL,
    DECISION_REQUIRES_DECOMPOSITION,
    DECISION_REQUIRES_RECALCULATION,
    EVENT_MATERIALITY_SCHEMA,
    EventMaterialityDecision,
    EventMaterialityReview,
)
from value_investment_agent.human_research_approval import (
    DECISION_APPROVED_CONDITIONAL_LOW_CONFIDENCE,
    DECISION_REJECTED_NEEDS_REWORK,
    HumanResearchApprovalReceipt,
    artifact_fingerprint,
)
from value_investment_agent.model_validity import ModelValidity
from value_investment_agent.price_attractiveness import (
    STATUS_NOT_ASSESSABLE,
    STATUS_RESEARCH_ATTRACTIVE,
    assess_price_attractiveness,
)
from value_investment_agent.price_bridge import PriceBridgeResult
from value_investment_agent.pre_decision_eligibility import (
    STATUS_ELIGIBLE,
    STATUS_NOT_ELIGIBLE,
    evaluate_pre_decision_eligibility,
    pre_decision_eligibility_from_payload,
)
from value_investment_agent.research_gate import CONCLUSION_RESEARCH_READY, ResearchGate
from value_investment_agent.research_run_contract import valuation_result_sha256
from value_investment_agent.valuation_models.base import ValuationResult


SYMBOL = "600887"
MODEL_ID = "residual_income_or_equity_value"
MODEL_VERSION = "residual-income-equity-shared-v1"
AS_OF = date(2026, 9, 22)
REVIEWED_AT = datetime(2026, 9, 23, 5, 30, tzinfo=timezone.utc)


def _payload(name: str) -> dict:
    return {"artifact_id": name, "schema_version": "fixture-v1", "value": name}


def _valuation() -> ValuationResult:
    return ValuationResult(
        symbol=SYMBOL,
        model_type=MODEL_ID,
        valuation_date=AS_OF,
        bear_value=Decimal("10"),
        base_value=Decimal("17"),
        bull_value=Decimal("24"),
        confidence="中",
        assumptions={"status": "conditional_research_only"},
        sensitivities=[],
        evidence_refs=[{"id": "valuation"}],
        blockers=[],
        status="conditional_research_only",
        model_version=MODEL_VERSION,
    )


def _receipt(
    *,
    decision: str,
    price_assessment_eligible: bool,
    remaining_blockers=(),
) -> HumanResearchApprovalReceipt:
    valuation = _valuation()
    return HumanResearchApprovalReceipt(
        approval_id="600887-g3-20260923.1",
        symbol=SYMBOL,
        security_id=SYMBOL,
        profile_id="quality_compounder",
        valuation_artifact_id="600887-m1-valuation-result-v1",
        valuation_artifact_sha256=valuation_result_sha256(valuation),
        valuation_model_id=MODEL_ID,
        valuation_model_version=MODEL_VERSION,
        research_case_id="600887-research-case-v1",
        research_case_sha256=artifact_fingerprint(_payload("case")),
        assumption_set_id="600887-assumptions-v1",
        assumption_set_sha256=artifact_fingerprint(_payload("assumptions")),
        facts_artifact_id="600887-facts-v1",
        facts_artifact_sha256=artifact_fingerprint(_payload("facts")),
        reviewed_at=REVIEWED_AT,
        review_as_of=REVIEWED_AT.date(),
        reviewer_type="human_research_lead",
        decision=decision,
        price_assessment_eligible=price_assessment_eligible,
        remaining_blockers=tuple(remaining_blockers),
        evidence_refs=({"id": "approval"},),
    )


def _decision(decision: str = DECISION_NOT_MATERIAL) -> EventMaterialityDecision:
    expected = {
        DECISION_NOT_MATERIAL: (False, False, False),
        DECISION_REQUIRES_RECALCULATION: (True, True, False),
        DECISION_REQUIRES_DECOMPOSITION: (False, False, True),
    }
    recalc, stale, followup = expected[decision]
    return EventMaterialityDecision(
        event_decision_id=f"event-{decision}",
        symbol=SYMBOL,
        announcement_id="1225511409",
        title="fixture disclosure",
        published_at=datetime(2026, 8, 27, tzinfo=timezone.utc),
        source_ref={"id": "interim-pdf"},
        source_sha256="a" * 64,
        machine_candidate_reason="fixture rule candidate",
        human_decision=decision,
        affected_domains=(),
        affected_fact_fields=(),
        affected_assumptions=(),
        affected_artifacts=(),
        requires_recalculation=recalc,
        requires_model_stale=stale,
        requires_followup=followup,
        reviewed_at=REVIEWED_AT,
        review_notes=("fixture review",),
    )


def _review(decision: str = DECISION_NOT_MATERIAL) -> EventMaterialityReview:
    return EventMaterialityReview(
        review_id="600887-event-review-20260923",
        schema_version=EVENT_MATERIALITY_SCHEMA,
        symbol=SYMBOL,
        scan_id="600887-scan-20260923T051018Z",
        scan_sha256="b" * 64,
        scan_from=date(2026, 8, 27),
        scan_to=AS_OF,
        reviewed_at=REVIEWED_AT,
        review_as_of=REVIEWED_AT.date(),
        reviewer_type="human_research_lead",
        decisions=(_decision(decision),),
        evidence_refs=({"id": "scan"},),
    )


def _gate() -> ResearchGate:
    return ResearchGate(
        symbol=SYMBOL,
        results={
            "G0_证据门": True,
            "G1_财务门": True,
            "G2_商业论点门": True,
            "G3_估值门": True,
        },
        blockers=[],
        conclusion=CONCLUSION_RESEARCH_READY,
    )


def _validity() -> ModelValidity:
    return ModelValidity(
        model_id=MODEL_VERSION,
        symbol=SYMBOL,
        model_as_of=AS_OF,
        valid_from=AS_OF,
        last_material_event_check=AS_OF,
        financial_statement_changed=False,
        capital_structure_changed=False,
        material_event_found=False,
        status="VALID",
        blockers=[],
        evidence_refs=[{"id": "event-check"}],
    )


def _bridge() -> PriceBridgeResult:
    valuation = _valuation()
    price = Decimal("8")
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
        evidence_refs=[{"id": "quote"}],
        quote_evidence_refs=[{"id": "quote", "sha256": "c" * 64}],
        blockers=[],
        model_id=MODEL_VERSION,
        model_version=MODEL_VERSION,
        model_as_of=AS_OF,
        quote_symbol=SYMBOL,
        valuation_bear_value=valuation.bear_value,
        valuation_base_value=valuation.base_value,
    )


def _eligibility(
    *,
    approval: HumanResearchApprovalReceipt,
    review: EventMaterialityReview,
    price_assessment=None,
):
    return evaluate_pre_decision_eligibility(
        gate=_gate(),
        valuation=_valuation(),
        approval=approval,
        model_validity=_validity(),
        price_bridge=_bridge(),
        event_materiality=review,
        decision_as_of=AS_OF,
        model_id=MODEL_ID,
        research_case_payload=_payload("case"),
        facts_payload=_payload("facts"),
        assumptions_payload=_payload("assumptions"),
        price_attractiveness=price_assessment,
    )


def test_rejected_approval_with_ready_bridge_is_not_assessable_and_not_eligible():
    approval = _receipt(
        decision=DECISION_REJECTED_NEEDS_REWORK,
        price_assessment_eligible=False,
        remaining_blockers=("non_operating_bridge_unverified",),
    )
    price = assess_price_attractiveness(
        _gate(),
        _valuation(),
        _bridge(),
        profile_id="quality_compounder",
        human_approval_price_assessment_eligible=False,
    )
    eligibility = _eligibility(approval=approval, review=_review(), price_assessment=price)

    assert price.status == STATUS_NOT_ASSESSABLE
    assert eligibility.status == STATUS_NOT_ELIGIBLE
    assert "human_research_approval_not_valid" in eligibility.blockers
    assert "human_approval_price_assessment_not_eligible" in eligibility.blockers
    assert eligibility.action == "no_order"


def test_conditional_approval_with_price_flag_disabled_stays_not_eligible():
    approval = _receipt(
        decision=DECISION_APPROVED_CONDITIONAL_LOW_CONFIDENCE,
        price_assessment_eligible=False,
    )
    price = assess_price_attractiveness(
        _gate(),
        _valuation(),
        _bridge(),
        profile_id="quality_compounder",
        human_approval_price_assessment_eligible=False,
    )
    eligibility = _eligibility(approval=approval, review=_review(), price_assessment=price)

    assert price.status == STATUS_NOT_ASSESSABLE
    assert eligibility.approval_status == DECISION_APPROVED_CONDITIONAL_LOW_CONFIDENCE
    assert eligibility.status == STATUS_NOT_ELIGIBLE
    assert "human_approval_price_assessment_not_eligible" in eligibility.blockers


def test_hypothetical_complete_chain_can_become_eligible_without_an_order():
    approval = _receipt(
        decision=DECISION_APPROVED_CONDITIONAL_LOW_CONFIDENCE,
        price_assessment_eligible=True,
    )
    price = assess_price_attractiveness(
        _gate(),
        _valuation(),
        _bridge(),
        profile_id="quality_compounder",
        human_approval_price_assessment_eligible=True,
    )
    eligibility = _eligibility(approval=approval, review=_review(), price_assessment=price)

    assert price.status == STATUS_RESEARCH_ATTRACTIVE
    assert eligibility.status == STATUS_ELIGIBLE
    assert eligibility.blockers == ()
    assert eligibility.action == "no_order"


def test_unresolved_recalculation_and_decomposition_block_eligibility():
    approval = _receipt(
        decision=DECISION_APPROVED_CONDITIONAL_LOW_CONFIDENCE,
        price_assessment_eligible=True,
    )
    recalculation = _eligibility(
        approval=approval,
        review=_review(DECISION_REQUIRES_RECALCULATION),
    )
    decomposition = _eligibility(
        approval=approval,
        review=_review(DECISION_REQUIRES_DECOMPOSITION),
    )

    assert recalculation.status == STATUS_NOT_ELIGIBLE
    assert "unresolved_event_recalculation" in recalculation.blockers
    assert decomposition.status == STATUS_NOT_ELIGIBLE
    assert "unresolved_event_decomposition" in decomposition.blockers


def test_predecision_payload_round_trip_preserves_fail_closed_contract():
    approval = _receipt(
        decision=DECISION_REJECTED_NEEDS_REWORK,
        price_assessment_eligible=False,
        remaining_blockers=("blocker",),
    )
    eligibility = _eligibility(approval=approval, review=_review())
    restored = pre_decision_eligibility_from_payload(eligibility.as_policy())

    assert restored == eligibility
    assert restored.status == STATUS_NOT_ELIGIBLE
    assert restored.action == "no_order"


def test_superseded_approval_cannot_be_repackaged_as_eligible():
    receipt = _receipt(
        decision=DECISION_APPROVED_CONDITIONAL_LOW_CONFIDENCE,
        price_assessment_eligible=True,
    )
    changed = replace(_valuation(), base_value=Decimal("18"))
    eligibility = evaluate_pre_decision_eligibility(
        gate=_gate(),
        valuation=changed,
        approval=receipt,
        model_validity=_validity(),
        price_bridge=_bridge(),
        event_materiality=_review(),
        decision_as_of=AS_OF,
        model_id=MODEL_ID,
        research_case_payload=_payload("case"),
        facts_payload=_payload("facts"),
        assumptions_payload=_payload("assumptions"),
    )

    assert eligibility.approval_status == "SUPERSEDED"
    assert eligibility.status == STATUS_NOT_ELIGIBLE
    assert "valuation_artifact_changed" in eligibility.blockers
