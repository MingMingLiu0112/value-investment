from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from value_investment_agent.human_research_approval import (
    DECISION_APPROVED_CONDITIONAL_LOW_CONFIDENCE,
    DECISION_REJECTED_NEEDS_REWORK,
    DECISION_SUPERSEDED,
    HumanResearchApprovalReceipt,
    artifact_fingerprint,
    resolve_human_research_approval,
)
from value_investment_agent.research_run_contract import valuation_result_sha256
from value_investment_agent.valuation_models.base import ValuationResult


REVIEWED_AT = datetime(2026, 9, 23, 5, 30, tzinfo=timezone.utc)
REVIEW_AS_OF = date(2026, 9, 23)


def _payload(name: str) -> dict:
    return {"artifact_id": name, "schema_version": "fixture-v1", "value": name}


def _valuation() -> ValuationResult:
    return ValuationResult(
        symbol="600887",
        model_type="residual_income_or_equity_value",
        valuation_date=date(2026, 9, 22),
        bear_value=Decimal("10"),
        base_value=Decimal("17"),
        bull_value=Decimal("24"),
        confidence="低",
        assumptions={"status": "conditional_research_only"},
        sensitivities=[],
        evidence_refs=[{"id": "valuation"}],
        blockers=[],
        status="conditional_research_only",
        model_version="residual-income-equity-shared-v1",
    )


def _receipt(
    *,
    decision: str,
    price_assessment_eligible: bool,
    remaining_blockers=(),
    conditions=(),
    required_followups=(),
    action="no_order",
) -> HumanResearchApprovalReceipt:
    valuation = _valuation()
    return HumanResearchApprovalReceipt(
        approval_id="600887-g3-20260923.1",
        symbol="600887",
        security_id="600887",
        profile_id="quality_compounder",
        valuation_artifact_id="600887-m1-valuation-result-v1",
        valuation_artifact_sha256=valuation_result_sha256(valuation),
        valuation_model_id="residual_income_or_equity_value",
        valuation_model_version=valuation.model_version,
        research_case_id="600887-research-case-v1",
        research_case_sha256=artifact_fingerprint(_payload("case")),
        assumption_set_id="600887-assumptions-v1",
        assumption_set_sha256=artifact_fingerprint(_payload("assumptions")),
        facts_artifact_id="600887-facts-v1",
        facts_artifact_sha256=artifact_fingerprint(_payload("facts")),
        reviewed_at=REVIEWED_AT,
        review_as_of=REVIEW_AS_OF,
        reviewer_type="human_research_lead",
        decision=decision,
        price_assessment_eligible=price_assessment_eligible,
        review_priority="NORMAL",
        conditions=tuple(conditions),
        remaining_blockers=tuple(remaining_blockers),
        required_followups=tuple(required_followups),
        evidence_refs=({"id": "approval-pdf"},),
        action=action,
    )


def test_rejected_receipt_is_not_approved_and_still_binds_current_value():
    receipt = _receipt(
        decision=DECISION_REJECTED_NEEDS_REWORK,
        price_assessment_eligible=False,
        remaining_blockers=("non_operating_bridge_unverified",),
    )
    valuation = _valuation()

    resolved = resolve_human_research_approval(
        receipt,
        valuation,
        model_id="residual_income_or_equity_value",
        research_case_payload=_payload("case"),
        facts_payload=_payload("facts"),
        assumptions_payload=_payload("assumptions"),
    )

    assert resolved.approved is False
    assert resolved.status == DECISION_REJECTED_NEEDS_REWORK
    assert resolved.price_assessment_eligible is False
    assert "non_operating_bridge_unverified" in resolved.blockers
    assert resolved.action == "no_order"


def test_changed_valuation_hash_supersedes_old_approval():
    receipt = _receipt(
        decision=DECISION_APPROVED_CONDITIONAL_LOW_CONFIDENCE,
        price_assessment_eligible=False,
        conditions=("cost_of_equity_sensitivity",),
        required_followups=("cost_of_equity_sensitivity",),
    )
    changed = replace(_valuation(), base_value=Decimal("18"))

    resolved = resolve_human_research_approval(
        receipt,
        changed,
        model_id="residual_income_or_equity_value",
        research_case_payload=_payload("case"),
        facts_payload=_payload("facts"),
        assumptions_payload=_payload("assumptions"),
    )

    assert resolved.status == DECISION_SUPERSEDED
    assert resolved.valuation_bound is False
    assert resolved.dependencies_bound is True
    assert "valuation_artifact_changed" in resolved.blockers


def test_new_assumption_payload_does_not_silently_inherit_approval():
    receipt = _receipt(
        decision=DECISION_APPROVED_CONDITIONAL_LOW_CONFIDENCE,
        price_assessment_eligible=True,
    )
    changed_assumptions = _payload("assumptions")
    changed_assumptions["value"] = "new-assumption-version"

    resolved = resolve_human_research_approval(
        receipt,
        _valuation(),
        model_id="residual_income_or_equity_value",
        research_case_payload=_payload("case"),
        facts_payload=_payload("facts"),
        assumptions_payload=changed_assumptions,
    )

    assert resolved.status == DECISION_SUPERSEDED
    assert resolved.dependencies_bound is False
    assert "assumption_set_sha256_changed" in resolved.blockers


def test_conditional_approval_can_remain_research_only_and_block_price():
    receipt = _receipt(
        decision=DECISION_APPROVED_CONDITIONAL_LOW_CONFIDENCE,
        price_assessment_eligible=False,
        conditions=("normalized_roe_review",),
        required_followups=("normalized_roe_review",),
    )
    resolved = resolve_human_research_approval(
        receipt,
        _valuation(),
        model_id="residual_income_or_equity_value",
        research_case_payload=_payload("case"),
        facts_payload=_payload("facts"),
        assumptions_payload=_payload("assumptions"),
    )

    assert resolved.approved is True
    assert resolved.price_assessment_eligible is False
    assert resolved.action == "no_order"


def test_approval_receipt_cannot_introduce_order_semantics():
    with pytest.raises(ValueError, match="no_order"):
        _receipt(
            decision=DECISION_REJECTED_NEEDS_REWORK,
            price_assessment_eligible=False,
            remaining_blockers=("blocker",),
            action="order",
        )


def test_symbol_identity_conflict_fails_closed():
    receipt = _receipt(
        decision=DECISION_REJECTED_NEEDS_REWORK,
        price_assessment_eligible=False,
        remaining_blockers=("blocker",),
    )
    other = replace(_valuation(), symbol="000651")
    resolved = resolve_human_research_approval(
        receipt,
        other,
        model_id="residual_income_or_equity_value",
    )

    assert resolved.status == DECISION_SUPERSEDED
    assert "valuation_symbol_mismatch" in resolved.blockers
