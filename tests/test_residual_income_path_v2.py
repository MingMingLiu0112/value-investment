"""Synthetic annual retention tests; no market data or research approval."""
from dataclasses import replace
from datetime import datetime
from decimal import Decimal as D, localcontext

import pytest

from test_residual_income_equity_valuation import case, complete_facts, confidence_evidence
from value_investment_agent.valuation_models.residual_income import (
    MODEL_VERSION as LEGACY_VERSION, ResidualIncomeEquityValuationModel,
    ResidualIncomeScenarioInputs, ResidualIncomeValuationTiming, scenario_value,
)
from value_investment_agent.valuation_models.residual_income_path_v2 import (
    MODEL_VERSION, ResidualIncomePathScenarioInputs,
    ResidualIncomePathValuationModel, scenario_calculation,
)
from value_investment_agent.valuation_router import ValuationModelRegistration

PATH = tuple(map(D, ("0", "1", ".2", ".8", ".1", ".7", ".3", ".6", ".4", ".5")))


def scenario(**kwargs):
    values = dict(cost_of_equity=D(".1"), forecast_roes=(D(".16"),) * 10,
                  terminal_roe=D(".12"), terminal_growth=D("0"),
                  forecast_retentions=PATH)
    return ResidualIncomePathScenarioInputs(**(values | kwargs))


def facts(**kwargs):
    return complete_facts(**(dict(
        scenario_inputs={k: scenario() for k in ("bear", "base", "bull")}
    ) | kwargs))


def test_ten_year_profit_book_dividend_reconciliation():
    s = scenario()
    result = scenario_calculation(facts(), s)
    with localcontext() as ctx:
        ctx.prec = 48
        book, ri, ddm = D(1000), D(0), D(0)
        for year, row in enumerate(result["forecast_years"], 1):
            profit = book * s.forecast_roes[year - 1]
            dividend = profit * (1 - PATH[year - 1])
            closing = book + profit - dividend
            assert D(row["opening_book_equity_cny"]) == book
            assert D(row["net_income_assumption_cny"]) == profit
            assert D(row["dividend_assumption_cny"]) == dividend
            assert D(row["closing_book_equity_cny"]) == closing
            assert D(row["retention_assumption"]) == PATH[year - 1]
            assert D(row["discount_factor"]) == D("1.1") ** year
            ri += (profit - D(".1") * book) / D("1.1") ** year
            ddm += dividend / D("1.1") ** year
            book = closing
        ri += D(1000) + (D(".12") - D(".1")) * book / D(".1") / D("1.1") ** 10
        ddm += D(".12") * book / D(".1") / D("1.1") ** 10
        assert abs(D(result["conditional_equity_value_cny"]) - ri) < D("1e-40")
        assert abs(D(result["dividend_crosscheck_equity_value_cny"]) - ddm) < D("1e-40")
        assert abs(ri - ddm) < D("1e-40")
    assert D(result["terminal_retention_assumption"]) == 0
    averaged = scenario_value(D(1000), D(100), D(".1"), {
        "forecast_roe": s.forecast_roes, "retention": sum(PATH) / 10,
        "terminal_roe": s.terminal_roe, "terminal_growth": D(0),
    })
    assert abs(D(result["conditional_equity_value_cny"]) -
               D(averaged["conditional_equity_value_cny"])) > D(".01")


@pytest.mark.parametrize("growth", [D(0), D(".02")])
def test_constant_path_matches_legacy_including_terminal_contract(growth):
    s = scenario(forecast_retentions=(D(".3"),) * 10, terminal_growth=growth)
    actual = scenario_calculation(facts(), s)
    expected = scenario_value(D(1000), D(100), s.cost_of_equity, {
        "forecast_roe": s.forecast_roes, "retention": D(".3"),
        "terminal_roe": s.terminal_roe, "terminal_growth": growth,
    })
    assert actual["forecast_years"] == expected["forecast_years"]
    for key in ("conditional_equity_value_cny", "dividend_crosscheck_equity_value_cny",
                "terminal_first_dividend_cny", "terminal_retention_assumption"):
        assert abs(D(actual[key]) - D(expected[key])) < D("1e-40")


@pytest.mark.parametrize("changes", [
    {"forecast_retentions": ()}, {"forecast_retentions": (D(".3"),)},
    {"forecast_retentions": (D("NaN"),) * 10},
    {"forecast_retentions": (D("Infinity"),) * 10},
    {"forecast_retentions": (D("-0.1"),) * 10},
    {"forecast_retentions": (D("1.1"),) * 10},
    {"forecast_retentions": [D(".3")] * 10},
    {"forecast_roes": (D("NaN"),) * 10},
    {"cost_of_equity": D("NaN")}, {"terminal_roe": D("NaN")},
    {"terminal_growth": D("NaN")}, {"terminal_growth": D(".1")},
    {"terminal_roe": D(0)}, {"forecast_roes": (D("-.1"),) * 10},
    {"retention": D(".4")}, {"currency": "USD"},
])
def test_invalid_scenario_contract(changes):
    with pytest.raises(ValueError):
        scenario(**changes)


@pytest.mark.parametrize("field,value", [
    ("start_book_equity", D("NaN")), ("ordinary_shares", D("Infinity")),
    ("start_book_equity", D(0)), ("ordinary_shares", D(-1)),
])
def test_invalid_equity_boundary(field, value):
    f = facts()
    f = replace(f, operating_inputs=f.operating_inputs | {field: value})
    with pytest.raises(ValueError):
        scenario_calculation(f, scenario())


@pytest.mark.parametrize("changes", [
    {"verified": False}, {"blockers": ["unresolved"]},
    {"operating_inputs": {}}, {"scenario_inputs": None},
    {"scenario_inputs": {}},
    {"scenario_inputs": {"bear": scenario()}},
    {"scenario_inputs": {"bear": {}, "base": {}, "bull": {}}},
])
def test_normal_gates_equal_legacy(changes):
    f = facts(**changes)
    old = ResidualIncomeEquityValuationModel().value(f, case())
    new = ResidualIncomePathValuationModel().value(f, case())
    assert old.status == new.status == "not_ready"
    assert old.blockers == new.blockers
    assert old.evidence_refs == new.evidence_refs
    assert new.base_value is None
    assert new.model_version == MODEL_VERSION != LEGACY_VERSION


def test_conditional_only_confidence_and_no_mutation():
    f = facts(confidence_evidence=confidence_evidence())
    c = case()
    original = repr((f, c))
    result = ResidualIncomePathValuationModel().value(f, c)
    assert result.status == result.assumptions["status"] == "conditional_research_only"
    assert result.model_version == MODEL_VERSION != LEGACY_VERSION
    assert result.confidence == "高"
    assert len(result.sensitivities) == 3
    assert repr((f, c)) == original


def test_legacy_typed_scenarios_are_not_silently_used():
    result = ResidualIncomePathValuationModel().value(complete_facts(), case())
    assert result.status == "not_ready"
    assert "quality_compounder_scenario_inputs_must_be_typed" in result.blockers
    with pytest.raises(ValueError, match="typed"):
        scenario_calculation(facts(), complete_facts().scenario_inputs["base"])


@pytest.mark.parametrize("change", [
    {"symbol": "000001"}, {"confidence": "invalid"},
])
def test_common_contract_rejection(change):
    with pytest.raises(ValueError):
        ResidualIncomePathValuationModel().value(facts(**change), case())


def test_missing_and_conflicting_evidence_rejected():
    with pytest.raises(ValueError):
        ResidualIncomePathValuationModel().value(
            facts(evidence_refs=[]), replace(case(), evidence_refs=[]))
    with pytest.raises(ValueError, match="conflict"):
        ResidualIncomePathValuationModel().value(
            facts(evidence_refs=[{"id": "case", "sha256": "conflicting"}]), case())


@pytest.mark.parametrize("year", [2025, 2099])
def test_timing_cannot_be_relabelled_to_facts_date(year):
    timing = ResidualIncomeValuationTiming(
        datetime.fromisoformat(f"{year}-01-01T00:00:00+08:00"),
        datetime.fromisoformat(f"{year}-06-01T00:00:00+08:00"),
        ({"id": "timing"},),
    )
    f = facts(valuation_timing=timing)
    with pytest.raises(ValueError, match="does not match facts"):
        scenario_calculation(f, scenario())
    with pytest.raises(ValueError, match="does not match facts"):
        ResidualIncomePathValuationModel().value(f, case())


def test_registry_factory_contract_without_global_registration():
    registration = ValuationModelRegistration(
        "residual_income_path_v2", "residual_income_or_equity_value",
        ResidualIncomePathValuationModel, type(facts()),
        ("start_book_equity", "ordinary_shares", "scenario_inputs"),
    )
    assert isinstance(registration.build(), ResidualIncomePathValuationModel)


from value_investment_agent.valuation_models.residual_income_path_v2 import (
    ResidualIncomeContractDispatcher, SUPPORTED_MODEL_VERSIONS,
)
from value_investment_agent.valuation_models.residual_income import DATED_MODEL_VERSION


@pytest.mark.parametrize("changes", [{}, {"verified": False}, {"scenario_inputs": None},
                                     {"scenario_inputs": {}}, {"operating_inputs": {}}])
def test_dispatcher_legacy_is_exact_delegation(changes):
    f = complete_facts(**changes)
    dispatcher = ResidualIncomeContractDispatcher()
    assert isinstance(dispatcher, ResidualIncomeEquityValuationModel)
    assert dispatcher.value(f, case()) == ResidualIncomeEquityValuationModel().value(f, case())


def test_dispatcher_legacy_dated_is_exact_delegation():
    timing = ResidualIncomeValuationTiming(
        datetime.fromisoformat("2025-01-01T00:00:00+08:00"),
        datetime.fromisoformat("2025-06-01T00:00:00+08:00"),
        ({"id": "dated-dispatch"},),
    )
    f = complete_facts(as_of=timing.valuation_at.date(), valuation_timing=timing)
    result = ResidualIncomeContractDispatcher().value(f, case())
    assert result == ResidualIncomeEquityValuationModel().value(f, case())
    assert result.model_version == DATED_MODEL_VERSION


@pytest.mark.parametrize("changes", [{}, {"verified": False},
    {"scenario_inputs": {"bear": scenario()}}])
def test_dispatcher_path_preserves_v2_result_and_gate(changes):
    f = facts(**changes)
    result = ResidualIncomeContractDispatcher().value(f, case())
    assert result == ResidualIncomePathValuationModel().value(f, case())
    assert result.model_version == MODEL_VERSION


@pytest.mark.parametrize("other", [
    complete_facts().scenario_inputs["base"], {}, None,
])
def test_dispatcher_rejects_mixed_contract_even_when_unverified(other):
    f = facts(verified=False, scenario_inputs={
        "bear": scenario(), "base": other, "bull": scenario(),
    })
    with pytest.raises(ValueError, match="Mixed"):
        ResidualIncomeContractDispatcher().value(f, case())


def test_dispatcher_cannot_silently_ignore_path_or_timing_mismatch():
    f = facts()
    result = ResidualIncomeContractDispatcher().value(f, case())
    old_result = ResidualIncomeEquityValuationModel().value(f, case())
    assert result.base_value != old_result.base_value
    timing = ResidualIncomeValuationTiming(
        datetime.fromisoformat("2025-01-01T00:00:00+08:00"),
        datetime.fromisoformat("2025-06-01T00:00:00+08:00"),
        ({"id": "unsupported-path-timing"},),
    )
    with pytest.raises(ValueError, match="does not match facts"):
        ResidualIncomeContractDispatcher().value(
            replace(f, valuation_timing=timing), case())


def test_dispatcher_supported_identities_and_registry_factory():
    assert SUPPORTED_MODEL_VERSIONS == (LEGACY_VERSION, DATED_MODEL_VERSION, MODEL_VERSION)
    registration = ValuationModelRegistration(
        "residual_income_or_equity_value", "residual_income_or_equity_value",
        ResidualIncomeContractDispatcher, type(facts()),
        ("start_book_equity", "ordinary_shares", "scenario_inputs"),
    )
    assert isinstance(registration.build(), ResidualIncomeEquityValuationModel)


def test_dated_path_uses_legacy_factor_and_independent_dividends():
    from value_investment_agent.valuation_models.residual_income import valuation_time_factor
    timing = ResidualIncomeValuationTiming(
        datetime.fromisoformat("2025-01-01T00:00:00+08:00"),
        datetime.fromisoformat("2025-06-01T00:00:00+08:00"),
        ({"id": "path-timing"},),
    )
    f = facts(as_of=timing.valuation_at.date(), valuation_timing=timing)
    s = scenario()
    actual = scenario_calculation(f, s)
    origin = scenario_calculation(replace(f, valuation_timing=None), s)
    with localcontext() as ctx:
        ctx.prec = 48
        elapsed, factor = valuation_time_factor(s.cost_of_equity, timing.basis_at, timing.valuation_at)
        expected = D(origin["conditional_equity_value_cny"]) * factor
        ddm = sum(
            D(row["dividend_assumption_cny"]) / (1 + s.cost_of_equity) ** (D(row["year"]) - elapsed)
            for row in actual["forecast_years"]
        ) + D(actual["terminal_first_dividend_cny"]) / (
            s.cost_of_equity - s.terminal_growth
        ) / (1 + s.cost_of_equity) ** (D(10) - elapsed)
        assert D(actual["conditional_equity_value_cny"]) == expected
        assert abs(expected - ddm) < D("1e-40")
    model = ResidualIncomeContractDispatcher().value(f, case())
    assert model == ResidualIncomePathValuationModel().value(f, case())
    assert model.model_version == MODEL_VERSION
    assert model.status == "conditional_research_only"
    assert model.assumptions["valuation_timing"] == timing.as_policy()
    assert {"id": "path-timing"} in model.evidence_refs
    assert D(actual["per_share_value"]) == model.base_value
    assert actual["retention_policy"] == "new_typed_ignores_legacy_default"


def test_dated_constant_path_matches_old_model():
    timing = ResidualIncomeValuationTiming(
        datetime.fromisoformat("2025-01-01T00:00:00+08:00"),
        datetime.fromisoformat("2025-06-01T00:00:00+08:00"),
        ({"id": "constant-timing"},),
    )
    s = scenario(forecast_retentions=(D(".3"),) * 10)
    old = ResidualIncomeScenarioInputs(s.cost_of_equity, s.forecast_roes, s.terminal_roe, s.terminal_growth)
    f = facts(as_of=timing.valuation_at.date(), valuation_timing=timing,
              scenario_inputs={k:s for k in ("bear", "base", "bull")})
    expected = ResidualIncomeEquityValuationModel().value(
        replace(f, scenario_inputs={k:old for k in ("bear", "base", "bull")}), case())
    actual = ResidualIncomeContractDispatcher().value(f, case())
    assert abs(actual.base_value - expected.base_value) < D("1e-38")


@pytest.mark.parametrize("basis,valuation", [
    ("2026-01-01T00:00:00+08:00", "2025-06-01T00:00:00+08:00"),
    ("2025-01-01T00:00:00+08:00", "2026-01-01T00:00:00+08:00"),
    ("2025-01-01T00:00:00", "2025-06-01T00:00:00+08:00"),
])
def test_future_basis_first_payment_and_naive_timing_rejected(basis, valuation):
    with pytest.raises(ValueError):
        ResidualIncomeValuationTiming(datetime.fromisoformat(basis),
                                      datetime.fromisoformat(valuation), ({"id":"timing"},))
