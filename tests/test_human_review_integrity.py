"""Negative tests for machine-generated "human approval" records."""
from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from value_investment_agent.domain.research.human_research_approval import (
    DECISION_APPROVED_CONDITIONAL_LOW_CONFIDENCE,
    DECISION_SUPERSEDED,
    HUMAN_APPROVAL_SCHEMA,
    artifact_fingerprint,
    human_research_approval_from_payload,
    resolve_human_research_approval,
)
from value_investment_agent.domain.research.human_review_integrity import (
    REASON_FIXED_SCRIPT_TIMESTAMP,
    REASON_IDENTICAL_TIMESTAMP_CLUSTER,
    REASON_MACHINE_GENERATED_LEGACY,
    REASON_REVIEWER_IDENTITY_MISSING,
    ApprovalImportRejected,
    gate_demotes_approved,
    require_importable_approval,
    screen_approval_bundle,
    screen_human_approval_payload,
)
from value_investment_agent.research_run_contract import valuation_result_sha256
from value_investment_agent.valuation_models.base import ValuationResult


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


def _legacy_payload() -> dict:
    """Exact shape emitted by scripts/build_m1_post_review_receipts.py."""
    valuation = _valuation()
    return {
        "schema_version": HUMAN_APPROVAL_SCHEMA,
        "approval_id": "600887-g3-human-approval-20260923.1",
        "symbol": "600887",
        "security_id": "600887",
        "profile_id": "quality_compounder",
        "valuation_artifact_id": "600887-m1-valuation-result-v1",
        "valuation_artifact_sha256": valuation_result_sha256(valuation),
        "valuation_model_id": "residual_income_or_equity_value",
        "valuation_model_version": valuation.model_version,
        "research_case_id": "600887-research-case-v1",
        "research_case_sha256": artifact_fingerprint(_payload("case")),
        "assumption_set_id": "600887-assumptions-v1",
        "assumption_set_sha256": artifact_fingerprint(_payload("assumptions")),
        "facts_artifact_id": "600887-facts-v1",
        "facts_artifact_sha256": artifact_fingerprint(_payload("facts")),
        "reviewed_at": "2026-09-23T13:30:00+08:00",
        "review_as_of": "2026-09-23",
        "reviewer_type": "human_research_lead",
        "decision": DECISION_APPROVED_CONDITIONAL_LOW_CONFIDENCE,
        "price_assessment_eligible": False,
        "review_priority": "NORMAL",
        "conditions": ["cost_of_equity_sensitivity"],
        "remaining_blockers": [],
        "required_followups": ["cost_of_equity_sensitivity"],
        "reopen_triggers": [],
        "evidence_refs": [{"id": "600887-m1-valuation-package-v1"}],
        "decision_version": "20260923.1",
        "action": "no_order",
    }


def _resolve(payload: dict):
    receipt = human_research_approval_from_payload(payload)
    return resolve_human_research_approval(
        receipt,
        _valuation(),
        model_id="residual_income_or_equity_value",
        research_case_payload=_payload("case"),
        facts_payload=_payload("facts"),
        assumptions_payload=_payload("assumptions"),
    )


def test_legacy_generator_payload_is_not_importable():
    verdict = screen_human_approval_payload(_legacy_payload())
    assert verdict.importable is False
    assert REASON_REVIEWER_IDENTITY_MISSING in verdict.reasons
    assert REASON_MACHINE_GENERATED_LEGACY in verdict.reasons
    assert REASON_FIXED_SCRIPT_TIMESTAMP in verdict.reasons
    assert gate_demotes_approved(verdict) is True


def test_legacy_generator_approval_never_resolves_as_approved_g3():
    resolved = _resolve(_legacy_payload())
    assert resolved.status == DECISION_SUPERSEDED
    assert resolved.approved is False
    assert resolved.price_assessment_eligible is False
    assert REASON_REVIEWER_IDENTITY_MISSING in resolved.blockers
    assert REASON_MACHINE_GENERATED_LEGACY in resolved.blockers


def test_known_generator_signature_stays_rejected_even_with_added_identity():
    payload = dict(_legacy_payload(), reviewer_id="REVIEWER-REAL-0001")
    verdict = screen_human_approval_payload(payload)
    assert verdict.importable is False
    assert REASON_MACHINE_GENERATED_LEGACY in verdict.reasons


def test_explicit_reviewer_identity_keeps_a_new_decision_importable():
    payload = dict(
        _legacy_payload(),
        approval_id="600887-g3-20261017.1",
        reviewed_at="2026-10-17T10:00:00+08:00",
        review_as_of="2026-10-17",
        reviewer_id="REVIEWER-REAL-0001",
    )
    verdict = screen_human_approval_payload(payload)
    assert verdict.importable is True
    resolved = _resolve(payload)
    assert resolved.status == DECISION_APPROVED_CONDITIONAL_LOW_CONFIDENCE
    assert resolved.approved is True
    assert resolved.price_assessment_eligible is False


def test_bundle_with_identical_script_timestamp_and_no_identity_is_flagged():
    first = _legacy_payload()
    second = dict(first, approval_id="000651-g3-human-approval-20260923.1", symbol="000651")
    verdicts = screen_approval_bundle([first, second])
    assert all(REASON_IDENTICAL_TIMESTAMP_CLUSTER in verdict.reasons for verdict in verdicts)
    assert all(verdict.importable is False for verdict in verdicts)


def test_require_importable_approval_raises_for_legacy_record():
    with pytest.raises(ApprovalImportRejected) as error:
        require_importable_approval(_legacy_payload(), source="legacy-bundle")
    assert REASON_REVIEWER_IDENTITY_MISSING in error.value.reasons
    assert "legacy-bundle" in str(error.value)