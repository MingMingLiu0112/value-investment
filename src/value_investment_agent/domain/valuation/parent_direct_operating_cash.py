"""Conditional parent operating-cash forecasts from explicit historical cash drivers.

The input loader authenticates source references. This arithmetic keeps direct
operating cash separate from pure working-capital adjustments and dividends.
"""
from decimal import Decimal, localcontext
from functools import wraps

from .parent_cash_policy import _number, _period, _symbol

VERSION = "parent-direct-operating-cash-v1"
SCOPE = "ISSUER_PARENT_STANDALONE"
FIELDS = ("revenue", "cost", "customer_cash", "supplier_cash", "cfo")


def _precise(function):
    @wraps(function)
    def calculate(*args, **kwargs):
        with localcontext() as arithmetic:
            arithmetic.prec = 48
            return function(*args, **kwargs)
    return calculate


def _calendar_period(row):
    start, end = _period(row)
    if (start.year != end.year or
            (start.month, start.day, end.month, end.day) not in {
                (1, 1, 6, 30), (7, 1, 12, 31), (1, 1, 12, 31)}):
        raise ValueError("DIRECT_CASH_SINGLE_YEAR_CALENDAR_PERIOD_REQUIRED")
    return start, end


def _observation(row):
    _symbol(row["symbol"])
    start, end = _calendar_period(row)
    if row.get("classification") not in {"FACT", "DERIVED_FACT"}:
        raise ValueError("DIRECT_CASH_HISTORICAL_FACT_REQUIRED")
    if row.get("scope") != SCOPE or row.get("currency") != "CNY":
        raise ValueError("DIRECT_CASH_PARENT_CNY_REQUIRED")
    values = {field: _number(row[field]) for field in FIELDS}
    if (min(values["revenue"], values["cost"]) <= 0
            or min(values["customer_cash"], values["supplier_cash"]) < 0):
        raise ValueError("DIRECT_CASH_POSITIVE_DRIVER_BASE_REQUIRED")
    if not row.get("source_refs"):
        raise ValueError("DIRECT_CASH_SOURCE_REFERENCES_REQUIRED")
    return start, end, values


def forecast_parent_operating_cash(*, historical, forecast):
    """Use one same-season historical payment regime under stated assumptions.

    Supplier cash divided by cost is an empirical payment coefficient. It is
    neither purchases nor payable turnover. Other operating cash is a signed
    aggregate including payroll, taxes and other operating flows.
    """
    start, end, values = _observation(historical)
    target_start, target_end = _calendar_period(forecast)
    if (forecast.get("symbol") != historical["symbol"]
            or forecast.get("scope") != SCOPE or forecast.get("currency") != "CNY"
            or forecast.get("classification") != "FORECAST_ASSUMPTION"):
        raise ValueError("DIRECT_CASH_FORECAST_IDENTITY_REQUIRED")
    if ((start.month, start.day, end.month, end.day) !=
            (target_start.month, target_start.day, target_end.month, target_end.day)
            or end >= target_start):
        raise ValueError("DIRECT_CASH_SAME_SEASON_FORWARD_PERIOD_REQUIRED")
    for field in ("rationale", "counter_evidence", "reopen_condition"):
        if not isinstance(forecast.get(field), str) or not forecast[field].strip():
            raise ValueError("DIRECT_CASH_EXPLAINED_ASSUMPTIONS_REQUIRED")
    with localcontext() as arithmetic:
        arithmetic.prec = 48
        revenue = _number(forecast["revenue"])
        cost = _number(forecast["cost"])
        other = _number(forecast["other_operating_cash"])
        if min(revenue, cost) < 0:
            raise ValueError("DIRECT_CASH_NONNEGATIVE_FORECAST_DRIVERS_REQUIRED")
        collected = revenue * values["customer_cash"] / values["revenue"]
        paid = cost * values["supplier_cash"] / values["cost"]
        historical_other = values["cfo"] - values["customer_cash"] + values["supplier_cash"]
        cfo = collected - paid + other
        return dict(
            schema_version=VERSION, symbol=historical["symbol"], scope=SCOPE,
            currency="CNY", period_start=target_start.isoformat(), period_end=target_end.isoformat(),
            classification="FORECAST_ASSUMPTION",
            historical_period=[start.isoformat(), end.isoformat()],
            source_refs=historical["source_refs"],
            assumptions={**forecast},
            coefficients=dict(
                customer_cash_to_revenue=str(values["customer_cash"] / values["revenue"]),
                supplier_cash_to_cost=str(values["supplier_cash"] / values["cost"]),
            ),
            historical_other_operating_cash=str(historical_other),
            customer_cash=str(collected), supplier_cash=str(paid),
            other_operating_cash=str(other), operating_cash=str(cfo),
            formula="revenue * historical_customer_cash / historical_revenue - cost * historical_supplier_cash / historical_cost + other_operating_cash",
            working_capital_cash_component=None,
            distribution_capacity=None,
            formal_eligibility=False, action="no_order",
        )


@_precise
def combine_parent_cash_periods(results, *, period_start, period_end):
    """Sum explicit consecutive component forecasts without annualisation."""
    start, end = _calendar_period(dict(period_start=period_start, period_end=period_end))
    if not results:
        raise ValueError("DIRECT_CASH_PERIODS_REQUIRED")
    from datetime import timedelta

    next_start = start
    symbol = results[0]["symbol"]
    total = Decimal(0)
    for result in results:
        current_start, current_end = _calendar_period(result)
        if (result.get("schema_version") != VERSION or result.get("scope") != SCOPE
                or result.get("currency") != "CNY" or result["symbol"] != symbol
                or result.get("classification") != "FORECAST_ASSUMPTION"
                or current_start != next_start or current_end > end):
            raise ValueError("DIRECT_CASH_CONTIGUOUS_SAME_ISSUER_PERIODS_REQUIRED")
        total += _number(result["operating_cash"])
        next_start = current_end + timedelta(days=1)
    if next_start != end + timedelta(days=1):
        raise ValueError("DIRECT_CASH_INCOMPLETE_PERIOD_COVERAGE")
    return dict(schema_version=VERSION, symbol=symbol, scope=SCOPE, currency="CNY",
                period_start=period_start, period_end=period_end,
                operating_cash=str(total), component_periods=results,
                classification="FORECAST_ASSUMPTION", working_capital_cash_component=None,
                distribution_capacity=None, formal_eligibility=False, action="no_order")


@_precise
def compare_historical_payment_regimes(*, observations, period_start, period_end):
    """Hold operating scale at the latest observed season under each cash regime.

    This is an explicit constant-scale sensitivity, not an adopted annual
    business forecast. No average or preferred Base is inferred.
    """
    if len(observations) < 2:
        raise ValueError("DIRECT_CASH_TWO_COMPARABLE_OBSERVATIONS_REQUIRED")
    parsed = [_observation(row) for row in observations]
    symbol = observations[0]["symbol"]
    seasons = {(start.month, start.day, end.month, end.day) for start, end, _ in parsed}
    if (len(seasons) != 1 or any(row["symbol"] != symbol for row in observations)
            or len({end for _, end, _ in parsed}) != len(parsed)):
        raise ValueError("DIRECT_CASH_COMPARABLE_SAME_ISSUER_HISTORY_REQUIRED")
    latest_index = max(range(len(parsed)), key=lambda i: parsed[i][1])
    latest = observations[latest_index]
    results = []
    for observed, (_, end, amounts) in zip(observations, parsed):
        other = amounts["cfo"] - amounts["customer_cash"] + amounts["supplier_cash"]
        forecast = dict(
            symbol=symbol, scope=SCOPE, currency="CNY", period_start=period_start,
            period_end=period_end, revenue=latest["revenue"], cost=latest["cost"],
            other_operating_cash=str(other), classification="FORECAST_ASSUMPTION",
            rationale="Hold revenue and cost at the latest same-season observed scale; apply the selected historical collection/payment ratios and other operating cash.",
            counter_evidence="Supplier credit, bill settlement, taxes and other operating receipts/payments may differ. Historical cash highs may be temporary.",
            reopen_condition="Recompute on new same-scope statements, changed credit terms or evidence of settlement obligations.",
            operating_scale_source_refs=latest["source_refs"],
        )
        result = forecast_parent_operating_cash(historical=observed, forecast=forecast)
        results.append(dict(result, regime_period_end=end.isoformat()))
    return dict(
        schema_version=VERSION, method="DIRECT_OPERATING_CASH",
        symbol=symbol, scope=SCOPE, currency="CNY",
        period_start=period_start, period_end=period_end,
        classification="CONDITIONAL_CONSTANT_SCALE_SENSITIVITY",
        scenarios=results,
        range_cny=[str(min(Decimal(r["operating_cash"]) for r in results)),
                   str(max(Decimal(r["operating_cash"]) for r in results))],
        adopted_base=None, full_year_coverage=period_start.endswith("-01-01") and period_end.endswith("-12-31"),
        e2_ready=False,
        e2_gaps=["ADOPTED_ANNUAL_OPERATING_CASH_FORECAST_REQUIRED",
                 "PARENT_TO_OWNER_CASH_AND_DISTRIBUTION_BRIDGE_REQUIRED"],
        action="no_order", formal_eligibility=False,
    )

@_precise
def derive_remaining_period(*, full_year, first_period):
    """Derive H2 flows from reconciled same-issuer FY and H1 observations."""
    start, end, annual = _observation(full_year)
    sub_start, sub_end, first = _observation(first_period)
    if (full_year["symbol"] != first_period["symbol"] or start != sub_start
            or (start.month, start.day, end.month, end.day) != (1, 1, 12, 31)
            or (sub_end.month, sub_end.day) != (6, 30) or sub_end.year != end.year):
        raise ValueError("DIRECT_CASH_FY_H1_SAME_BASIS_REQUIRED")
    amounts = {key: str(annual[key] - first[key]) for key in FIELDS}
    result = dict(
        symbol=full_year["symbol"], scope=SCOPE, currency="CNY",
        period_start=f"{end.year}-07-01", period_end=end.isoformat(),
        classification="DERIVED_FACT", derivation="FY minus same-year H1 flows",
        source_refs={"full_year": full_year["source_refs"],
                     "first_period": first_period["source_refs"]}, **amounts,
    )
    _observation(result)  # Negative derived receipts/payments require review.
    return result
