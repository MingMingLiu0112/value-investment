from decimal import Decimal

import pytest

from value_investment_agent.materiality import (
    MATERIALITY_HIGH,
    MATERIALITY_LOW,
    MATERIALITY_UNKNOWN,
    TREATMENT_IGNORE_WITH_DISCLOSURE,
    TREATMENT_REQUIRE_MORE_EVIDENCE,
    TREATMENT_SCENARIO_STRESS,
    ScopeMaterialityAssessment,
    materiality_applicability_effect,
    materiality_from_payload,
)


def assessment(**overrides):
    values = {
        "symbol": "000333",
        "issue_id": "finance_business_carve_out",
        "metric": "net_profit_to_consolidated_attributable",
        "estimated_exposure_ratio": Decimal("0.0093"),
        "downside_impact": Decimal("-0.01"),
        "upside_impact": Decimal("0.01"),
        "materiality": MATERIALITY_LOW,
        "treatment": TREATMENT_IGNORE_WITH_DISCLOSURE,
        "rationale": "The unaudited and audited size observations bound the finance entity below 1% of attributable profit",
        "evidence_refs": [{"id": "midea_finance_company_size_observation"}],
        "blockers": [],
    }
    values.update(overrides)
    return ScopeMaterialityAssessment(**values)


def test_quantified_low_materiality_can_ignore_with_disclosure():
    outcome = assessment()

    assert outcome.materiality == MATERIALITY_LOW
    assert outcome.treatment == TREATMENT_IGNORE_WITH_DISCLOSURE
    assert outcome.fail_closed is False


def test_low_materiality_without_quantification_is_rejected():
    with pytest.raises(ValueError, match="quantified exposure"):
        assessment(
            estimated_exposure_ratio=None,
            downside_impact=None,
            upside_impact=None,
        )


def test_unknown_materiality_must_fail_closed():
    outcome = assessment(
        estimated_exposure_ratio=None,
        downside_impact=None,
        upside_impact=None,
        materiality=MATERIALITY_UNKNOWN,
        treatment=TREATMENT_REQUIRE_MORE_EVIDENCE,
    )

    assert outcome.fail_closed is True
    assert outcome.treatment == TREATMENT_REQUIRE_MORE_EVIDENCE


def test_unknown_materiality_cannot_be_relabeled_unimportant():
    with pytest.raises(ValueError, match="must fail closed"):
        assessment(
            materiality=MATERIALITY_UNKNOWN,
            treatment=TREATMENT_IGNORE_WITH_DISCLOSURE,
        )


def test_materiality_never_changes_model_applicability_by_itself():
    outcome = assessment()
    effect = materiality_applicability_effect(outcome, "MODEL_NOT_APPLICABLE")

    assert effect["applicability_status_before"] == "MODEL_NOT_APPLICABLE"
    assert effect["applicability_status_after"] == "MODEL_NOT_APPLICABLE"
    assert effect["model_unlocked"] is False


def test_high_materiality_requires_stress_or_block():
    assert assessment(
        materiality=MATERIALITY_HIGH,
        treatment=TREATMENT_SCENARIO_STRESS,
    ).materiality == MATERIALITY_HIGH
    with pytest.raises(ValueError, match="HIGH materiality"):
        assessment(
            materiality=MATERIALITY_HIGH,
            treatment=TREATMENT_IGNORE_WITH_DISCLOSURE,
        )


def test_json_roundtrip_preserves_quantification():
    original = assessment()
    restored = materiality_from_payload(original.as_policy())

    assert restored.estimated_exposure_ratio == Decimal("0.0093")
    assert restored.materiality == MATERIALITY_LOW
    assert restored.fail_closed is False
