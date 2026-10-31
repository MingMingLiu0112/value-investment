"""F1 economic acceptance for the exact-tail v4 owner-cash contract."""
from copy import deepcopy
from decimal import Decimal as D

import pytest

from value_investment_agent.domain.valuation.joint_capital_cash_path_v4 import (
    SCOPE,
    compile_joint_capital_cash_path,
    value_terminal_economic_contract,
)
from value_investment_agent.valuation_models.residual_income_path_v4 import (
    ResidualIncomePathScenarioInputs,
    scenario_calculation,
)


def stable_case(*, terminal_payout="0.85"):
    historical = dict(scope=SCOPE, currency="CNY", revenue="100", cost="80",
        surcharges="0", selling="0", admin="0", research="0",
        pre_tax_profit="20", tax="0", parent_profit="20", nonrecurring="0",
        da="0", opening_cash="20", opening_distribution_capacity="100",
        cash_floor="10")
    years = [dict(year=year, revenue_growth="0", cost_ratio="0.8",
        target_payout_ratio="0.85", accessible_profit_ratio="0.95",
        net_maintenance_cash_cny="2", operating_wc_cash_cny="1",
        commitment_cash_cny="0", reserve_ratio="0.1")
        for year in range(1, 11)]
    drivers = dict(years=years, operating_allocation="0",
        new_operating_return="0", new_liquidity_return="0")
    terminal = dict(net_maintenance_cash_cny="2", operating_wc_cash_cny="1",
        commitment_cash_cny="0", accessible_profit_ratio="0.95",
        target_payout_ratio=terminal_payout, reserve_ratio="0.1",
        profit_scale="1", rationale="Stable owner-cash acceptance case.",
        terminal_mechanism="recursive_capital_use_and_owner_distribution_v2",
        terminal_start_year=11,
        first_distribution_timing="end_of_terminal_year_1",
        legacy_profit_dynamics="constant_after_profit_scale_transition",
        commitment_occurrences=0, restricted_cash_release_cny="0",
        restricted_cash_release_year=None,
        convergence_tolerance_cny="0.01", max_tail_years=2000)
    return dict(start_book="100", historical=historical, drivers=drivers,
        terminal_policy=terminal)


def value(args, cost="0.08"):
    path = compile_joint_capital_cash_path(**args)
    return path, value_terminal_economic_contract(
        path["terminal_economic_contract"], D(cost))


def consume(path, cost="0.08"):
    scenario = ResidualIncomePathScenarioInputs(
        cost_of_equity=D(cost), forecast_roes=path["forecast_roe"],
        forecast_retentions=path["forecast_retentions"],
        terminal_roe=path["terminal_roe"],
        terminal_growth=path["terminal_growth"],
        terminal_economic_contract=path["terminal_economic_contract"],
    )
    facts = type("Facts", (), {"operating_inputs": {
        "start_book_equity": D("100"), "ordinary_shares": D("10")},
        "valuation_timing": None})()
    return scenario_calculation(facts, scenario)


def test_t01_low_payout_diagnostic_growth_above_cost_reaches_candidate_consumption():
    path, tail = value(stable_case(terminal_payout="0.4"))
    assert path["terminal_growth"] > D("0.08")
    assert tail["equity_value"] == D("100")
    calculated = consume(path)
    assert calculated["model_version"] == "residual-income-equity-path-v4"
    assert D(calculated["terminal_economic_value_cny"]) == D("100")
    assert D(calculated["terminal_value_error_bound_cny"]) == 0
    assert calculated["terminal_value_error_kind"] == (
        "ANALYTICAL_TAIL_TRUNCATION_ONLY"
    )
    assert calculated["terminal_value_error_scope"] == (
        "TOTAL_EQUITY_AT_YEAR_10_END"
    )
    assert D(calculated["terminal_value_error_bound_basis_cny"]) == 0
    assert D(calculated["terminal_value_error_bound_basis_per_share"]) == 0
    assert D(calculated["terminal_bridge_arithmetic_tolerance_cny"]) > 0
    assert calculated["terminal_economic_uncertainty_status"] == (
        "NOT_QUANTIFIED_BY_NUMERIC_ERROR_BOUND"
    )
    assert abs(D(calculated["dividend_crosscheck_difference_cny"])) < D("0.01")


def test_t02_full_distribution_independent_analytical_benchmark_and_scale():
    args = stable_case(terminal_payout="1")
    args["historical"].update(cost="20", pre_tax_profit="80", parent_profit="80")
    for row in args["drivers"]["years"]:
        row.update(cost_ratio="0.2", target_payout_ratio="1",
            accessible_profit_ratio="1", net_maintenance_cash_cny="0",
            operating_wc_cash_cny="0", reserve_ratio="0")
    args["terminal_policy"].update(accessible_profit_ratio="1",
        net_maintenance_cash_cny="0", operating_wc_cash_cny="0",
        reserve_ratio="0")
    path, tail = value(args)
    assert path["terminal_distribution"] == D("80")
    assert tail["equity_value"] == D("1000")
    assert tail["absolute_error_bound_cny"] == 0

    scaled = deepcopy(args)
    scaled["historical"].update(revenue="250", cost="50",
        pre_tax_profit="200", parent_profit="200")
    scaled_path, scaled_tail = value(scaled, cost="0.10")
    assert scaled_path["terminal_distribution"] == D("200")
    assert scaled_tail["equity_value"] == D("2000")


def test_t03_stable_sixteen_distribution_values_at_200_not_325():
    path, tail = value(stable_case())
    assert path["terminal_distribution"] == D("16")
    assert tail["equity_value"] == D("200")
    assert tail["valuation_method"] == "exact_static_owner_distribution_perpetuity"


def test_t04_only_productive_or_liquidity_mechanisms_create_new_profit():
    idle_path, idle = value(stable_case(), cost="0.12")
    productive_args = stable_case()
    productive_args["drivers"].update(
        operating_allocation="0.5", new_operating_return="0.08")
    productive_path, productive = value(productive_args, cost="0.12")
    assert productive["equity_value"] > idle["equity_value"]
    assert productive_path["terminal"]["new_operating_profit"] > 0
    assert idle_path["terminal"]["new_operating_profit"] == 0
    assert idle_path["terminal"]["new_liquidity_profit"] == 0


def test_t05_higher_recurring_needs_cannot_raise_value():
    _, base = value(stable_case())
    higher = stable_case()
    higher["terminal_policy"].update(
        net_maintenance_cash_cny="3", operating_wc_cash_cny="2")
    _, stressed = value(higher)
    assert stressed["equity_value"] < base["equity_value"]


def test_t06_events_are_consumed_before_exact_tail_and_one_time_only():
    args = stable_case()
    for row in args["drivers"]["years"]:
        row["accessible_profit_ratio"] = "0.5"
    args["terminal_policy"].update(accessible_profit_ratio="0.5",
        commitment_cash_cny="1", commitment_occurrences=12,
        restricted_cash_release_cny="20", restricted_cash_release_year=15)
    path, tail = value(args)
    assert tail["years_evaluated"] >= 15
    assert tail["last_scheduled_event_year"] == 15
    assert tail["restricted_cash_release_consumed_cny"] == D("20")
    assert tail["commitment_occurrences_consumed"] == 12
    assert tail["analytical_first_row"]["restricted_cash_release_cny"] == 0
    assert path["terminal_economic_contract"].commitment_occurrences == 12


def test_t07_unfunded_unsupported_and_nonconvergent_fail_closed():
    unfunded = stable_case()
    unfunded["terminal_policy"]["net_maintenance_cash_cny"] = "100000"
    with pytest.raises(ValueError, match="unfunded"):
        value(unfunded)

    invalid_release = stable_case()
    invalid_release["terminal_policy"].update(
        restricted_cash_release_cny="1000", restricted_cash_release_year=2)
    with pytest.raises(ValueError, match="exceeds"):
        value(invalid_release)

    explosive = stable_case()
    explosive["drivers"].update(
        operating_allocation="1", new_operating_return="0.5")
    explosive["terminal_policy"].update(
        target_payout_ratio="0", max_tail_years=40)
    with pytest.raises(ValueError, match="exact tail|value-convergent"):
        value(explosive)


def test_v4_rejects_permanent_negative_working_capital_release():
    args = stable_case()
    args["terminal_policy"]["operating_wc_cash_cny"] = "-1"
    with pytest.raises(ValueError, match="nonnegative"):
        compile_joint_capital_cash_path(**args)
