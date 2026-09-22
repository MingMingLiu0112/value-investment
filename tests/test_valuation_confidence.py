from decimal import Decimal as D

import pytest

from value_investment_agent.valuation_confidence import (
    ConfidenceEvidence,
    evaluate_confidence,
)


def evidence(**overrides):
    values = dict(
        data_completeness=D("1"),
        business_stability="high",
        parameter_sensitivity="low",
        cyclicality="low",
        forecast_horizon_years=10,
        terminal_value_share=D("0.50"),
        cross_check_disagreement=D("0.05"),
        evidence_refs=[{"id": "confidence-evidence"}],
    )
    values.update(overrides)
    return ConfidenceEvidence(**values)


def test_complete_high_quality_evidence_returns_high_confidence():
    result = evaluate_confidence(evidence())

    assert result.confidence == "高"
    assert result.blockers == []


def test_missing_terminal_and_cross_check_evidence_is_low_not_assumed_neutral():
    result = evaluate_confidence(evidence(
        terminal_value_share=None,
        cross_check_disagreement=None,
    ))

    assert result.confidence == "低"
    assert "terminal_value_share_not_measured" in result.blockers
    assert "cross_check_disagreement_not_measured" in result.blockers


def test_terminal_value_dependence_above_medium_policy_is_low():
    result = evaluate_confidence(evidence(terminal_value_share=D("0.80")))

    assert result.confidence == "低"
    assert "terminal_value_share_above_medium_policy" in result.blockers


def test_high_cyclicality_without_high_business_stability_is_low():
    result = evaluate_confidence(evidence(
        cyclicality="high",
        business_stability="medium",
    ))

    assert result.confidence == "低"
    assert "high_cyclicality_without_high_business_stability" in result.blockers


def test_medium_boundary_factors_return_medium_not_high():
    result = evaluate_confidence(evidence(
        forecast_horizon_years=8,
        terminal_value_share=D("0.70"),
        cross_check_disagreement=D("0.15"),
    ))

    assert result.confidence == "中"
    assert result.blockers == []


def test_unknown_sensitivity_fails_closed_to_low():
    result = evaluate_confidence(evidence(parameter_sensitivity="unknown"))

    assert result.confidence == "低"
    assert "parameter_sensitivity_unknown" in result.blockers


def test_invalid_confidence_inputs_are_rejected():
    with pytest.raises(ValueError, match="completeness"):
        ConfidenceEvidence(**{
            **evidence().__dict__,
            "data_completeness": D("1.01"),
        })
    with pytest.raises(ValueError, match="references"):
        ConfidenceEvidence(**{
            **evidence().__dict__,
            "evidence_refs": [],
        })
