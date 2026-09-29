from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from value_investment_agent.research_case import ResearchCase
from value_investment_agent.valuation_models.cyclical import (
    CyclicalFacts,
    CyclicalNormalizedValuationModel,
    value_normalized_equity,
)
from value_investment_agent.valuation_confidence import ConfidenceEvidence


def case():
    return ResearchCase(
        symbol="601088", name="中国神华", as_of=date(2026, 9, 21), run_id="test",
        generated_at=datetime(2026, 9, 21, tzinfo=timezone.utc), research_version="test",
        industry="煤炭", investment_path="周期正常化", thesis="测试", return_driver="测试",
        mispricing_hypothesis="未证明", financial_summary={"period_end": "2025-12-31"},
        positives=[], counter_evidence=[], thesis_breakers=[], next_events=[],
        evidence_status="partial", valuation_status="not_ready", research_status="financial_scope_partial",
        blockers=[], evidence_refs=[{"id": "case", "path": "case.json", "sha256": "x"}],
        quote_date=None, financial_period=date(2025, 12, 31),
        missing_date_reasons={"quote_date": "not used"},
    )


def complete_inputs():
    return {
        "bear_normalized_parent_operating_profit": Decimal("80"),
        "base_normalized_parent_operating_profit": Decimal("100"),
        "bull_normalized_parent_operating_profit": Decimal("120"),
        "cash_tax_rate": Decimal("0.25"),
        "maintenance_capex": Decimal("40"),
        "normalized_working_capital_change": Decimal("10"),
        "discount_rate": Decimal("0.10"),
        "long_term_growth": Decimal("0.02"),
        "resource_life_years": 30,
        "net_cash_attributable_to_parent": Decimal("200"),
        "ordinary_shares": Decimal("1000"),
        "trough_parent_operating_profit": Decimal("60"),
        "unit_cost": Decimal("350"),
    }


def test_unverified_cyclical_facts_fail_closed():
    facts = CyclicalFacts(
        symbol="601088", as_of=date(2025, 12, 31), verified=False, confidence="低",
        evidence_refs=[{"id": "facts", "path": "facts.json", "sha256": "y"}],
        blockers=["mid_cycle_time_series_not_verified"],
    )
    result = CyclicalNormalizedValuationModel().value(facts, case())
    assert result.model_type == "cyclical_normalized"
    assert (result.bear_value, result.base_value, result.bull_value) == (None, None, None)
    assert result.status == "not_ready"
    assert "financial_facts_not_verified" in result.blockers
    assert "cyclical_input_missing:resource_life_years" in result.blockers


def test_complete_cyclical_arithmetic_uses_finite_resource_life_and_net_cash():
    facts = CyclicalFacts(
        symbol="601088", as_of=date(2025, 12, 31), verified=True, confidence="低",
        evidence_refs=[{"id": "facts", "path": "facts.json", "sha256": "y"}],
        blockers=[], operating_inputs=complete_inputs(),
    )
    result = CyclicalNormalizedValuationModel().value(facts, case())
    assert result.status == "conditional_research_only"
    assert result.bear_value < result.base_value < result.bull_value
    assert Decimal("0.31") < result.bear_value < Decimal("0.32")
    assert Decimal("0.48") < result.base_value < Decimal("0.49")
    assert Decimal("0.64") < result.bull_value < Decimal("0.65")


def test_scenario_inputs_override_common_assumptions_and_remain_auditable():
    facts = CyclicalFacts(
        symbol="601088", as_of=date(2025, 12, 31), verified=True, confidence="低",
        evidence_refs=[{"id": "facts", "path": "facts.json", "sha256": "y"}],
        blockers=[], operating_inputs=complete_inputs(),
        scenario_operating_inputs={
            "bear": {
                "cash_tax_rate": Decimal("0.25"),
                "maintenance_capex": Decimal("45"),
                "normalized_working_capital_change": Decimal("5"),
                "discount_rate": Decimal("0.10"),
                "long_term_growth": Decimal("0"),
                "resource_life_years": 25,
                "net_cash_attributable_to_parent": Decimal("0"),
                "unit_cost": Decimal("400"),
            },
            "base": {
                "cash_tax_rate": Decimal("0.20"),
                "maintenance_capex": Decimal("35"),
                "normalized_working_capital_change": Decimal("2"),
                "discount_rate": Decimal("0.09"),
                "long_term_growth": Decimal("0"),
                "resource_life_years": 33,
                "net_cash_attributable_to_parent": Decimal("10"),
                "unit_cost": Decimal("350"),
            },
            "bull": {
                "cash_tax_rate": Decimal("0.15"),
                "maintenance_capex": Decimal("25"),
                "normalized_working_capital_change": Decimal("0"),
                "discount_rate": Decimal("0.08"),
                "long_term_growth": Decimal("0"),
                "resource_life_years": 40,
                "net_cash_attributable_to_parent": Decimal("20"),
                "unit_cost": Decimal("300"),
            },
        },
    )

    result = CyclicalNormalizedValuationModel().value(facts, case())

    assert result.status == "conditional_research_only"
    assert result.bear_value < result.base_value < result.bull_value
    assert result.sensitivities[0]["maintenance_capex"] == "45"
    assert result.sensitivities[1]["cash_tax_rate"] == "0.20"
    assert result.sensitivities[2]["resource_life_years"] == 40
    assert result.assumptions["scenario_inputs"]["bear"]["unit_cost"] == "400"


def test_one_missing_scenario_override_fails_closed():
    inputs = complete_inputs()
    inputs.pop("cash_tax_rate")
    facts = CyclicalFacts(
        symbol="601088", as_of=date(2025, 12, 31), verified=True, confidence="低",
        evidence_refs=[{"id": "facts", "path": "facts.json", "sha256": "y"}],
        blockers=[], operating_inputs=inputs,
        scenario_operating_inputs={
            "bear": {"cash_tax_rate": Decimal("0.25")},
            "base": {"cash_tax_rate": Decimal("0.20")},
        },
    )

    result = CyclicalNormalizedValuationModel().value(facts, case())

    assert result.status == "not_ready"
    assert "cyclical_input_missing:bull_cash_tax_rate" in result.blockers


def test_missing_profit_inputs_preserve_available_scenario_diagnostics():
    inputs = complete_inputs()
    for name in CyclicalFacts.SCENARIO_PROFIT_INPUTS:
        inputs.pop(name)
    facts = CyclicalFacts(
        symbol="601088", as_of=date(2025, 12, 31), verified=True, confidence="低",
        evidence_refs=[{"id": "facts", "path": "facts.json", "sha256": "y"}],
        blockers=["acquisition_adjusted_parent_profit_bridge_unresolved"],
        operating_inputs=inputs,
        scenario_operating_inputs={
            "bear": {"unit_cost": Decimal("180.2")},
            "base": {"unit_cost": Decimal("171.6")},
            "bull": {"unit_cost": Decimal("108.5")},
        },
    )

    result = CyclicalNormalizedValuationModel().value(facts, case())

    assert result.status == "not_ready"
    assert (result.bear_value, result.base_value, result.bull_value) == (None, None, None)
    assert set(result.assumptions["missing_inputs"]) == set(CyclicalFacts.SCENARIO_PROFIT_INPUTS)
    assert result.assumptions["scenario_inputs"]["bear"]["unit_cost"] == "180.2"
    assert result.assumptions["scenario_inputs"]["base"]["unit_cost"] == "171.6"
    assert result.assumptions["scenario_inputs"]["bull"]["unit_cost"] == "108.5"


def test_nonpositive_bear_cash_flow_blocks_and_preserves_diagnostic_values():
    facts = CyclicalFacts(
        symbol="601088", as_of=date(2025, 12, 31), verified=True, confidence="低",
        evidence_refs=[{"id": "facts", "path": "facts.json", "sha256": "y"}],
        blockers=[], operating_inputs=complete_inputs(),
        scenario_operating_inputs={
            "bear": {
                "maintenance_capex": Decimal("60"),
                "normalized_working_capital_change": Decimal("10"),
            },
        },
    )

    result = CyclicalNormalizedValuationModel().value(facts, case())

    assert result.status == "not_ready"
    assert result.bear_value is None
    assert any("cyclical_scenario_blocked:bear" in item for item in result.blockers)
    assert result.sensitivities[0]["normalized_distributable_cash"] == "-10.00"
    assert result.sensitivities[0]["maintenance_capex"] == "60"


def test_inverted_scenario_values_fail_closed_and_preserve_diagnostics():
    inputs = complete_inputs()
    inputs["bear_normalized_parent_operating_profit"] = Decimal("120")
    inputs["base_normalized_parent_operating_profit"] = Decimal("100")
    inputs["bull_normalized_parent_operating_profit"] = Decimal("80")
    facts = CyclicalFacts(
        symbol="601088", as_of=date(2025, 12, 31), verified=True, confidence="低",
        evidence_refs=[{"id": "facts", "path": "facts.json", "sha256": "y"}],
        blockers=[], operating_inputs=inputs,
    )

    result = CyclicalNormalizedValuationModel().value(facts, case())

    assert result.status == "not_ready"
    assert (result.bear_value, result.base_value, result.bull_value) == (None, None, None)
    assert result.blockers == ["cyclical_scenario_values_not_monotonic"]
    assert len(result.sensitivities) == 3
    assert Decimal(result.sensitivities[0]["per_share_value"]) > Decimal(
        result.sensitivities[1]["per_share_value"]
    )


def test_unknown_scenario_input_is_rejected():
    facts = CyclicalFacts(
        symbol="601088", as_of=date(2025, 12, 31), verified=True, confidence="低",
        evidence_refs=[{"id": "facts", "path": "facts.json", "sha256": "y"}],
        blockers=[], operating_inputs=complete_inputs(),
        scenario_operating_inputs={
            "bear": {"bull_normalized_parent_operating_profit": Decimal("120")},
        },
    )

    with pytest.raises(ValueError, match="Unknown scenario-specific cyclical input"):
        CyclicalNormalizedValuationModel().value(facts, case())


def test_normalized_arithmetic_does_not_accept_growth_at_or_above_discount_rate():
    inputs = complete_inputs()
    inputs["long_term_growth"] = Decimal("0.10")
    facts = CyclicalFacts(
        symbol="601088", as_of=date(2025, 12, 31), verified=True, confidence="低",
        evidence_refs=[{"id": "facts", "path": "facts.json", "sha256": "y"}],
        blockers=[], operating_inputs=inputs,
    )
    with pytest.raises(ValueError, match="growth"):
        CyclicalNormalizedValuationModel().value(facts, case())


def test_rule_based_confidence_can_accompany_a_conditional_cycle_result():
    facts = CyclicalFacts(
        symbol="601088", as_of=date(2025, 12, 31), verified=True, confidence="低",
        evidence_refs=[{"id": "facts", "path": "facts.json", "sha256": "y"}],
        blockers=[], operating_inputs=complete_inputs(),
        confidence_evidence=ConfidenceEvidence(
            data_completeness=Decimal("1"),
            business_stability="high",
            parameter_sensitivity="medium",
            cyclicality="low",
            forecast_horizon_years=30,
            terminal_value_share=Decimal("0"),
            cross_check_disagreement=Decimal("0.08"),
            evidence_refs=[{"id": "cyclical-confidence-evidence"}],
        ),
    )

    result = CyclicalNormalizedValuationModel().value(facts, case())

    assert result.status == "conditional_research_only"
    assert result.confidence == "中"
    assert result.assumptions["confidence_assessment"]["confidence"] == "中"
