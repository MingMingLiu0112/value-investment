"""Source-bound direct-cash alternative research; no source reclassification."""
from decimal import Decimal, localcontext

from .parent_direct_cash_research import read_parent_direct_cash_research
from ...domain.valuation.parent_direct_operating_cash import (
    derive_remaining_period, compare_historical_payment_regimes,
    forecast_parent_operating_cash, combine_parent_cash_periods,
)


def replay_direct_cash_alternative(*, root, interim_binding, annual_binding,
                                  evaluated_at, forecast_year):
    """Recompute a full-year sensitivity using explicit seasonal components.

    Holding observed scale is a research assumption, not adopted business
    guidance. The full-year assembly never doubles H1 or manufactures WC.
    """
    if type(forecast_year) is not int or not 1 <= forecast_year <= 9999:
        raise ValueError("DIRECT_CASH_FORECAST_YEAR_REQUIRED")
    interim = read_parent_direct_cash_research(
        root=root, receipt_binding=interim_binding, evaluated_at=evaluated_at)
    annual = read_parent_direct_cash_research(
        root=root, receipt_binding=annual_binding, evaluated_at=evaluated_at)
    if len(annual["observed"]) != 1:
        raise ValueError("DIRECT_CASH_ONE_ANNUAL_BASIS_REQUIRED")
    fy = annual["observed"][0]
    matches = [row for row in interim["observed"]
               if row["period_start"] == fy["period_start"]
               and row["symbol"] == fy["symbol"]]
    if len(matches) != 1:
        raise ValueError("DIRECT_CASH_MATCHED_ANNUAL_INTERIM_REQUIRED")
    h2 = derive_remaining_period(full_year=fy, first_period=matches[0])
    h1_results = compare_historical_payment_regimes(
        observations=interim["observed"],
        period_start=f"{forecast_year}-01-01", period_end=f"{forecast_year}-06-30")
    with localcontext() as arithmetic:
        arithmetic.prec = 48
        other = Decimal(h2["cfo"]) - Decimal(h2["customer_cash"]) + Decimal(h2["supplier_cash"])
    h2_forecast = dict(
        symbol=h2["symbol"], scope=h2["scope"], currency=h2["currency"],
        period_start=f"{forecast_year}-07-01", period_end=f"{forecast_year}-12-31",
        revenue=h2["revenue"], cost=h2["cost"],
        other_operating_cash=str(other),
        classification="FORECAST_ASSUMPTION",
        rationale="Hold the separately derived historical H2 operating scale and collection/payment regime; do not annualise H1.",
        counter_evidence="This older H2 regime can change with sales, credit, settlement and taxes; no persistence is established.",
        reopen_condition="Reopen on new parent annual/H2 reports or changed operating/settlement conditions.")
    h2_result = forecast_parent_operating_cash(historical=h2, forecast=h2_forecast)
    paths = [combine_parent_cash_periods(
        [first, h2_result], period_start=f"{forecast_year}-01-01",
        period_end=f"{forecast_year}-12-31") for first in h1_results["scenarios"]]
    return dict(
        schema_version="parent-direct-cash-alternative-v1", symbol=fy["symbol"],
        evaluated_at=evaluated_at.isoformat(), observed=interim["observed"] + [fy],
        derived_h2=h2, first_half_sensitivity=h1_results,
        annual_cash_scenarios=paths, adopted_base=None,
        status="SOURCE_BOUND_FULL_YEAR_CASH_SENSITIVITY",
        e2_ready=False,
        missing=["ADOPTED_OPERATING_FORECAST", "OWNER_CASH_AND_DISTRIBUTION_BRIDGE",
                 "CONTINUING_CAPITAL_AND_TERMINAL_POLICY"],
        working_capital_cash_component=None, formal_eligibility=False,
        action="no_order")
