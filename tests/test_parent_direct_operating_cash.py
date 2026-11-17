"""TEST_ONLY checks for direct cash arithmetic and period boundaries."""
from copy import deepcopy
from decimal import Decimal
import pytest
from value_investment_agent.domain.valuation.parent_direct_operating_cash import (
    forecast_parent_operating_cash, combine_parent_cash_periods,
)

def inputs():
    historical = dict(symbol="600000", scope="ISSUER_PARENT_STANDALONE", currency="CNY", classification="FACT",
        period_start="2025-01-01", period_end="2025-06-30",
        revenue="100", cost="60", customer_cash="90", supplier_cash="70",
        cfo="10", source_refs=[{"test_only": True}])
    forecast = dict(symbol="600000", scope="ISSUER_PARENT_STANDALONE", currency="CNY",
        period_start="2027-01-01", period_end="2027-06-30",
        revenue="110", cost="66", other_operating_cash="-10",
        classification="FORECAST_ASSUMPTION",
        rationale="TEST_ONLY unchanged payment regime under 10% operating growth",
        counter_evidence="Supplier settlement could accelerate",
        reopen_condition="New payment terms or changes in operating taxes")
    return historical, forecast

def test_direct_cash_is_not_working_capital_or_distribution():
    h, f = inputs()
    result = forecast_parent_operating_cash(historical=h, forecast=f)
    assert Decimal(result["operating_cash"]) == 12
    assert Decimal(result["historical_other_operating_cash"]) == -10
    assert result["working_capital_cash_component"] is None
    assert result["distribution_capacity"] is None

@pytest.mark.parametrize("field,value",[
    ("scope","consolidated"), ("symbol","600001"),
    ("other_operating_cash",None), ("revenue","NaN"),
    ("period_end","2027-12-31"), ("classification","FACT"),
    ("counter_evidence",""),
])
def test_incompatible_forecasts_fail(field,value):
    h,f=inputs()
    f[field]=value
    with pytest.raises(ValueError):
        forecast_parent_operating_cash(historical=h,forecast=f)

def test_half_year_does_not_become_annual_cash():
    h,f=inputs()
    result=forecast_parent_operating_cash(historical=h,forecast=f)
    with pytest.raises(ValueError,match="INCOMPLETE_PERIOD"):
        combine_parent_cash_periods([result],period_start="2027-01-01",period_end="2027-12-31")

def test_explicit_second_half_is_required_and_can_have_negative_cash():
    h,f=inputs()
    first=forecast_parent_operating_cash(historical=h,forecast=f)
    h.update(period_start="2025-07-01",period_end="2025-12-31")
    f.update(period_start="2027-07-01",period_end="2027-12-31",other_operating_cash="-50")
    second=forecast_parent_operating_cash(historical=h,forecast=f)
    result=combine_parent_cash_periods([first,second],period_start="2027-01-01",period_end="2027-12-31")
    assert Decimal(result["operating_cash"]) == -16
    assert result["formal_eligibility"] is False
    with pytest.raises(ValueError,match="CONTIGUOUS"):
        combine_parent_cash_periods([first,first],period_start="2027-01-01",period_end="2027-12-31")


def test_regime_comparison_keeps_explicit_history_and_does_not_invent_base():
    from value_investment_agent.domain.valuation.parent_direct_operating_cash import compare_historical_payment_regimes
    h, _ = inputs()
    later = dict(h, period_start="2026-01-01", period_end="2026-06-30",
                 revenue="110", cost="66", supplier_cash="45", cfo="35")
    result = compare_historical_payment_regimes(
        observations=[h, later], period_start="2027-01-01", period_end="2027-06-30")
    assert [Decimal(x["operating_cash"]) for x in result["scenarios"]] == [12, 35]
    assert result["adopted_base"] is None
    assert not result["e2_ready"]
    assert not result["full_year_coverage"]
    with pytest.raises(ValueError, match="COMPARABLE"):
        compare_historical_payment_regimes(observations=[h, h],
            period_start="2027-01-01", period_end="2027-06-30")

def test_remaining_period_requires_same_issuer_year_and_nonnegative_flows():
    from value_investment_agent.domain.valuation.parent_direct_operating_cash import derive_remaining_period
    h1 = dict(symbol="600887", scope="ISSUER_PARENT_STANDALONE", currency="CNY", classification="FACT",
              period_start="2025-01-01", period_end="2025-06-30",
              revenue="100", cost="60", customer_cash="90", supplier_cash="70",
              cfo="-5", source_refs={"id": "h1"})
    fy = dict(h1, period_end="2025-12-31", revenue="220", cost="140",
              customer_cash="200", supplier_cash="150", cfo="20",
              source_refs={"id": "fy"})
    result = derive_remaining_period(full_year=fy, first_period=h1)
    assert result["cfo"] == "25"
    assert result["period_start"] == "2025-07-01"
    assert result["classification"] == "DERIVED_FACT"
    for patch in ({"symbol": "600519"}, {"period_end": "2024-06-30"},
                  {"customer_cash": "210"}):
        with pytest.raises(ValueError):
            derive_remaining_period(full_year=fy, first_period=dict(h1, **patch))

def test_cross_year_periods_and_prediction_as_fact_are_rejected():
    from value_investment_agent.domain.valuation.parent_direct_operating_cash import derive_remaining_period
    h, f = inputs()
    with pytest.raises(ValueError, match="SINGLE_YEAR"):
        forecast_parent_operating_cash(historical=h, forecast=dict(f, period_start="2026-01-01"))
    with pytest.raises(ValueError, match="HISTORICAL_FACT"):
        forecast_parent_operating_cash(historical=dict(h, classification="FORECAST_ASSUMPTION"), forecast=f)
    with pytest.raises(ValueError, match="SINGLE_YEAR"):
        derive_remaining_period(full_year=dict(h,period_end="2026-12-31"),first_period=h)


def test_arithmetic_is_independent_of_ambient_decimal_precision():
    from decimal import localcontext
    from value_investment_agent.domain.valuation.parent_direct_operating_cash import derive_remaining_period, compare_historical_payment_regimes
    h, f = inputs()
    fy = dict(h, period_end="2025-12-31", revenue="220",cost="150",
              customer_cash="200",supplier_cash="150",cfo="10041373127.94")
    expected=derive_remaining_period(full_year=fy,first_period=h)
    later=dict(h,period_start="2026-01-01",period_end="2026-06-30",revenue="111.111",cost="69.123")
    kwargs=dict(observations=[h,later],period_start="2027-01-01",period_end="2027-06-30")
    comparison=compare_historical_payment_regimes(**kwargs)
    with localcontext() as ctx:
        ctx.prec=6
        assert derive_remaining_period(full_year=fy,first_period=h)==expected
        assert compare_historical_payment_regimes(**kwargs)==comparison
