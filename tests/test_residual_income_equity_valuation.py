from datetime import date, datetime, timezone
from decimal import Decimal as D

import pytest

from value_investment_agent.research_case import ResearchCase
from value_investment_agent.valuation_confidence import ConfidenceEvidence
from value_investment_agent.valuation_models.residual_income import (
    MODEL_VERSION,
    QualityCompounderFacts,
    ResidualIncomeEquityValuationModel,
    ResidualIncomeScenarioInputs,
    scenario_value,
)


def case():
    return ResearchCase(
        symbol="600519",
        name="测试质量复利公司",
        as_of=date(2025, 12, 31),
        run_id="test",
        generated_at=datetime(2025, 12, 31, tzinfo=timezone.utc),
        research_version="test",
        industry="消费品",
        investment_path="成熟优质复利",
        thesis="测试",
        return_driver="测试",
        mispricing_hypothesis="未证明",
        financial_summary={"period_end": "2025-12-31"},
        positives=[],
        counter_evidence=[],
        thesis_breakers=[],
        next_events=[],
        evidence_status="partial",
        valuation_status="not_ready",
        research_status="financial_scope_partial",
        blockers=[],
        evidence_refs=[{"id": "case", "path": "case.json", "sha256": "x"}],
        quote_date=None,
        financial_period=date(2025, 12, 31),
        missing_date_reasons={"quote_date": "not used"},
    )


def complete_scenarios():
    return {
        "bear": ResidualIncomeScenarioInputs(
            cost_of_equity=D("0.10"),
            forecast_roes=(D("0.10"),),
            terminal_roe=D("0.08"),
            terminal_growth=D("0.02"),
        ),
        "base": ResidualIncomeScenarioInputs(
            cost_of_equity=D("0.10"),
            forecast_roes=(D("0.10"),),
            terminal_roe=D("0.10"),
            terminal_growth=D("0.02"),
        ),
        "bull": ResidualIncomeScenarioInputs(
            cost_of_equity=D("0.10"),
            forecast_roes=(D("0.10"),),
            terminal_roe=D("0.12"),
            terminal_growth=D("0.02"),
        ),
    }


def complete_facts(**overrides):
    values = {
        "symbol": "600519",
        "as_of": date(2025, 12, 31),
        "verified": True,
        "confidence": "低",
        "evidence_refs": [{"id": "facts", "path": "facts.json", "sha256": "y"}],
        "blockers": [],
        "operating_inputs": {
            "start_book_equity": D("1000"),
            "ordinary_shares": D("100"),
        },
        "scenario_inputs": complete_scenarios(),
    }
    values.update(overrides)
    return QualityCompounderFacts(**values)


def confidence_evidence():
    return ConfidenceEvidence(
        data_completeness=D("1"),
        business_stability="high",
        parameter_sensitivity="low",
        cyclicality="low",
        forecast_horizon_years=10,
        terminal_value_share=D("0.30"),
        cross_check_disagreement=D("0.05"),
        evidence_refs=[{"id": "quality-confidence-evidence"}],
    )


def test_unverified_facts_fail_closed_into_a_unified_valuation_result():
    facts = QualityCompounderFacts(
        symbol="600519",
        as_of=date(2025, 12, 31),
        verified=False,
        confidence="低",
        evidence_refs=[{"id": "facts", "path": "facts.json", "sha256": "y"}],
        blockers=["ordinary_shares_not_verified"],
    )

    result = ResidualIncomeEquityValuationModel().value(facts, case())

    assert result.model_type == "residual_income_or_equity_value"
    assert (result.bear_value, result.base_value, result.bull_value) == (
        None,
        None,
        None,
    )
    assert result.status == "not_ready"
    assert "financial_facts_not_verified" in result.blockers
    assert "quality_compounder_input_missing:start_book_equity" in result.blockers
    assert "quality_compounder_input_missing:ordinary_shares" in result.blockers


def test_complete_synthetic_scenarios_produce_ordered_conditional_values():
    result = ResidualIncomeEquityValuationModel().value(complete_facts(), case())

    assert result.status == "conditional_research_only"
    assert result.bear_value < result.base_value < result.bull_value
    assert abs(result.base_value - D("10")) < D("1e-20")
    assert result.blockers == []
    assert result.model_version == MODEL_VERSION
    assert result.assumptions["status"] == "conditional_research_only"
    assert "market price" not in result.assumptions["scope"]


def test_shared_scenario_arithmetic_reconciles_residual_income_and_dividends():
    calculation = scenario_value(D("1000"), D("100"), D("0.10"), {
        "forecast_roe": ("0.10",),
        "terminal_roe": "0.10",
        "terminal_growth": "0.02",
    })

    assert abs(D(calculation["conditional_equity_value_cny"]) - D("1000")) < D("1e-20")
    assert abs(D(calculation["dividend_crosscheck_difference_cny"])) < D("0.01")
    assert D(calculation["terminal_residual_income_cny"]) == D("0")


def test_verified_facts_with_missing_common_inputs_fail_closed():
    facts = complete_facts(operating_inputs={})

    result = ResidualIncomeEquityValuationModel().value(facts, case())

    assert result.status == "not_ready"
    assert (result.bear_value, result.base_value, result.bull_value) == (
        None,
        None,
        None,
    )
    assert "quality_compounder_input_missing:start_book_equity" in result.blockers
    assert "quality_compounder_input_missing:ordinary_shares" in result.blockers


def test_partial_scenario_set_fails_closed_without_inventing_a_missing_value():
    scenarios = complete_scenarios()
    scenarios.pop("bull")

    result = ResidualIncomeEquityValuationModel().value(
        complete_facts(scenario_inputs=scenarios),
        case(),
    )

    assert result.status == "not_ready"
    assert (
        "quality_compounder_scenarios_must_contain_exactly_bear_base_bull"
        in result.blockers
    )
    assert (result.bear_value, result.base_value, result.bull_value) == (
        None,
        None,
        None,
    )


def test_invalid_terminal_arithmetic_is_rejected():
    scenarios = complete_scenarios()
    scenarios["base"] = ResidualIncomeScenarioInputs(
        cost_of_equity=D("0.10"),
        forecast_roes=(D("0.10"),),
        terminal_roe=D("0.10"),
        terminal_growth=D("0.10"),
    )

    with pytest.raises(ValueError, match="terminal assumptions"):
        ResidualIncomeEquityValuationModel().value(
            complete_facts(scenario_inputs=scenarios),
            case(),
        )


def test_rule_based_confidence_does_not_promote_conditional_status():
    facts = complete_facts(confidence_evidence=confidence_evidence())

    result = ResidualIncomeEquityValuationModel().value(facts, case())

    assert result.status == "conditional_research_only"
    assert result.confidence == "高"
    assert result.assumptions["confidence_assessment"]["confidence"] == "高"
    assert result.assumptions["confidence_assessment"]["blockers"] == []
