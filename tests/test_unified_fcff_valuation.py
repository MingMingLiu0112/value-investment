import json
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal as D
from pathlib import Path

import pytest

from value_investment_agent.research_case import ResearchCase
from value_investment_agent.scenario_valuation import BridgeItem, ForecastYear, Terminal
from value_investment_agent.valuation_confidence import ConfidenceEvidence
from value_investment_agent.valuation_models.fcff import (
    FCFFScenarioInputs,
    FCFFValuationModel,
    FinancialFacts,
)


ROOT = Path(__file__).resolve().parents[1]


def case():
    return ResearchCase(
        symbol="000333", name="美的集团", as_of=date(2025, 12, 31), run_id="test",
        generated_at=datetime(2025, 12, 31, tzinfo=timezone.utc), research_version="test",
        industry="家电", investment_path="成长价值", thesis="测试", return_driver="测试",
        mispricing_hypothesis="未证明", financial_summary={"period_end": "2025-12-31"},
        positives=[], counter_evidence=[], thesis_breakers=[], next_events=[],
        evidence_status="partial", valuation_status="not_ready", research_status="financial_scope_blocked",
        blockers=[], evidence_refs=[{"id": "case", "path": "case.json", "sha256": "x"}],
        quote_date=None, financial_period=date(2025, 12, 31),
        missing_date_reasons={"quote_date": "not used"},
    )


def scenario_inputs(ebit: str) -> FCFFScenarioInputs:
    ebit_value = D(ebit)
    return FCFFScenarioInputs(
        forecast=(
            ForecastYear(2025, ebit_value, D("0.25"), D("10"), D("10"), D("0"), D("0.10"), ("synthetic_ebit",)),
        ),
        terminal=Terminal(ebit_value, D("0"), D("0.10"), D("0.10"), ("synthetic_terminal",)),
        bridge=(),
        operating_exposure_ids=("industrial_operation",),
        ordinary_shares=D("100"),
        share_evidence_refs=("synthetic_shares",),
    )


def complete_scenarios():
    return {
        "bear": scenario_inputs("80"),
        "base": scenario_inputs("100"),
        "bull": scenario_inputs("120"),
    }


def confidence_evidence(**overrides):
    values = {
        "data_completeness": D("1"),
        "business_stability": "high",
        "parameter_sensitivity": "low",
        "cyclicality": "low",
        "forecast_horizon_years": 10,
        "terminal_value_share": D("0.50"),
        "cross_check_disagreement": D("0.05"),
        "evidence_refs": [{"id": "fcff-confidence-evidence"}],
    }
    values.update(overrides)
    return ConfidenceEvidence(**values)


def test_unverified_facts_fail_closed_into_a_unified_valuation_result():
    facts = FinancialFacts(
        symbol="000333", as_of=date(2025, 12, 31), verified=False,
        evidence_refs=[{"id": "facts", "path": "facts.json", "sha256": "y"}],
        blockers=["ordinary_shares_not_verified"],
    )

    result = FCFFValuationModel().value(facts, case())

    assert result.model_type == "FCFF"
    assert (result.bear_value, result.base_value, result.bull_value) == (None, None, None)
    assert result.status == "not_ready"
    assert "financial_facts_not_verified" in result.blockers
    assert "fcff_input_missing:ebit" in result.blockers


def test_fcff_contract_names_every_required_input_before_scenario_math():
    facts = FinancialFacts(symbol="000333", as_of=date(2025, 12, 31), verified=True,
                           evidence_refs=[{"id": "facts"}], blockers=[],
                           operating_inputs={"ebit": None, "wacc": None})
    assert facts.missing_fcff_inputs == [
        "ebit", "cash_tax_rate", "depreciation", "capex", "working_capital_change",
        "wacc", "net_debt", "non_operating_assets", "shares",
    ]


def test_complete_synthetic_scenarios_produce_ordered_research_only_values():
    facts = FinancialFacts(
        symbol="000333", as_of=date(2025, 12, 31), verified=True,
        evidence_refs=[{"id": "facts", "path": "facts.json", "sha256": "y"}],
        blockers=[], scenario_inputs=complete_scenarios(),
    )

    result = FCFFValuationModel().value(facts, case())

    assert result.status == "conditional_research_only"
    assert result.bear_value < result.base_value < result.bull_value
    assert abs(result.bear_value - D("7.81818181818181818181818181818181818182")) < D("1e-20")
    assert abs(result.base_value - D("9.77272727272727272727272727272727272727")) < D("1e-20")
    assert abs(result.bull_value - D("11.7272727272727272727272727272727272727")) < D("1e-20")
    assert [item["scenario"] for item in result.sensitivities] == ["bear", "base", "bull"]
    assert result.sensitivities[0]["arithmetic_status"] == "research_arithmetic_only"
    assert result.sensitivities[0]["evidence_refs"] == [
        "synthetic_ebit", "synthetic_shares", "synthetic_terminal",
    ]
    assert result.model_version == "fcff-shared-scenario-v1"


def test_partial_scenario_set_fails_closed_without_inventing_the_missing_value():
    facts = FinancialFacts(
        symbol="000333", as_of=date(2025, 12, 31), verified=True,
        evidence_refs=[{"id": "facts"}], blockers=[],
        scenario_inputs={"bear": scenario_inputs("80"), "base": scenario_inputs("100")},
    )

    result = FCFFValuationModel().value(facts, case())

    assert result.status == "not_ready"
    assert (result.bear_value, result.base_value, result.bull_value) == (None, None, None)
    assert "fcff_scenarios_must_contain_exactly_bear_base_bull" in result.blockers


def test_dated_scenario_must_match_financial_facts_as_of_date():
    scenarios = complete_scenarios()
    scenarios["base"] = replace(scenarios["base"], valuation_date=date(2025, 12, 30))
    facts = FinancialFacts(
        symbol="000333", as_of=date(2025, 12, 31), verified=True,
        evidence_refs=[{"id": "facts"}], blockers=[], scenario_inputs=scenarios,
    )

    result = FCFFValuationModel().value(facts, case())

    assert result.status == "not_ready"
    assert "fcff_scenario_valuation_date_mismatch:base" in result.blockers


def test_invalid_terminal_arithmetic_is_rejected():
    scenarios = complete_scenarios()
    scenarios["base"] = replace(
        scenarios["base"],
        terminal=Terminal(D("100"), D("0.10"), D("0.10"), D("0.10"), ("synthetic_terminal",)),
    )
    facts = FinancialFacts(
        symbol="000333", as_of=date(2025, 12, 31), verified=True,
        evidence_refs=[{"id": "facts"}], blockers=[], scenario_inputs=scenarios,
    )

    with pytest.raises(ValueError, match="growth"):
        FCFFValuationModel().value(facts, case())


def test_double_counted_bridge_exposure_is_rejected():
    scenarios = complete_scenarios()
    scenarios["base"] = replace(scenarios["base"], bridge=(
        BridgeItem("financial_asset", "nonoperating_asset", D("10"), ("industrial_operation",), ("evidence",)),
        BridgeItem("same_exposure", "debt", D("5"), ("industrial_operation",), ("evidence",)),
    ))
    facts = FinancialFacts(
        symbol="000333", as_of=date(2025, 12, 31), verified=True,
        evidence_refs=[{"id": "facts"}], blockers=[], scenario_inputs=scenarios,
    )

    with pytest.raises(ValueError, match="Double-counted"):
        FCFFValuationModel().value(facts, case())


def test_equity_bridge_is_applied_and_its_evidence_is_retained():
    scenarios = complete_scenarios()
    scenarios["base"] = replace(scenarios["base"], bridge=(
        BridgeItem("industrial_net_debt", "debt", D("100"), ("debt_claim",), ("synthetic_debt",)),
    ))
    facts = FinancialFacts(
        symbol="000333", as_of=date(2025, 12, 31), verified=True,
        evidence_refs=[{"id": "facts"}], blockers=[], scenario_inputs=scenarios,
    )

    result = FCFFValuationModel().value(facts, case())

    assert abs(result.base_value - D("8.77272727272727272727272727272727272727")) < D("1e-20")
    base_sensitivity = next(item for item in result.sensitivities if item["scenario"] == "base")
    assert "synthetic_debt" in base_sensitivity["evidence_refs"]


def test_rule_based_confidence_is_recorded_without_promoting_research_status():
    facts = FinancialFacts(
        symbol="000333", as_of=date(2025, 12, 31), verified=True,
        evidence_refs=[{"id": "facts"}], blockers=[],
        scenario_inputs=complete_scenarios(),
        confidence_evidence=confidence_evidence(),
    )

    result = FCFFValuationModel().value(facts, case())

    assert result.status == "conditional_research_only"
    assert result.confidence == "高"
    assert result.assumptions["confidence_assessment"]["confidence"] == "高"
    assert result.assumptions["confidence_assessment"]["blockers"] == []


def test_unmeasured_confidence_evidence_downgrades_to_low():
    facts = FinancialFacts(
        symbol="000333", as_of=date(2025, 12, 31), verified=True,
        evidence_refs=[{"id": "facts"}], blockers=[],
        scenario_inputs=complete_scenarios(),
        confidence_evidence=confidence_evidence(
            terminal_value_share=None,
            cross_check_disagreement=None,
        ),
    )

    result = FCFFValuationModel().value(facts, case())

    assert result.status == "conditional_research_only"
    assert result.confidence == "低"
    assert "terminal_value_share_not_measured" in result.assumptions["confidence_assessment"]["blockers"]


@pytest.mark.parametrize("shares", ["0", "1.5"])
def test_invalid_share_denominator_is_rejected(shares):
    scenarios = complete_scenarios()
    scenarios["base"] = replace(scenarios["base"], ordinary_shares=D(shares))
    facts = FinancialFacts(
        symbol="000333", as_of=date(2025, 12, 31), verified=True,
        evidence_refs=[{"id": "facts"}], blockers=[], scenario_inputs=scenarios,
    )

    with pytest.raises(ValueError, match="ordinary-share count"):
        FCFFValuationModel().value(facts, case())


def test_existing_midea_production_payload_still_yields_not_ready():
    audit = json.loads((ROOT / "runtime/company-research/midea-fcff-facts-20260922/evidence.json").read_text(encoding="utf-8"))
    facts = FinancialFacts(
        symbol="000333", as_of=date.fromisoformat(audit["as_of_period"]),
        verified=audit["financial_scope_approved"] is True,
        evidence_refs=[{"id": "midea_fcff_facts", "path": "runtime/company-research/midea-fcff-facts-20260922/evidence.json"}],
        blockers=list(audit.get("per_share_blockers", [])),
        operating_inputs={key: (None if value is None else D(str(value)))
                          for key, value in audit.get("fcff_inputs", {}).items()},
    )

    result = FCFFValuationModel().value(facts, case())

    assert result.status == "not_ready"
    assert (result.bear_value, result.base_value, result.bull_value) == (None, None, None)
    assert "fcff_input_missing:ebit" in result.blockers
    assert "fy2025_accounting_weighted_denominator_disclosed_but_not_current_valuation_denominator" in result.blockers
