"""Parent FY-minus-9M Q4 history and 9M-fact-plus-Q4-forecast arithmetic.

No owner distribution, capital policy, valuation, or current-price conclusion is
implied. The source loader must authenticate the supplied source references.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import localcontext

from .parent_cash_policy import _number, _period, _symbol
from .parent_direct_operating_cash import FIELDS, SCOPE, _observation

VERSION = "parent-remaining-year-cash-v1"


def _nine_months(row, *, as_of):
    _symbol(row["symbol"])
    start, end = _period(row)
    if ((start.month, start.day, end.month, end.day) != (1, 1, 9, 30)
            or start.year != end.year or end > as_of
            or row.get("classification") != "FACT"
            or row.get("scope") != SCOPE or row.get("currency") != "CNY"
            or not row.get("source_refs")):
        raise ValueError("REMAINING_YEAR_DATED_PARENT_9M_FACT_REQUIRED")
    values = {field: _number(row[field]) for field in FIELDS}
    if (min(values["revenue"], values["cost"]) <= 0
            or min(values["customer_cash"], values["supplier_cash"]) < 0):
        raise ValueError("REMAINING_YEAR_INVALID_9M_DRIVERS")
    return start, end, values


def build_parent_remaining_year_cash(*, historical_full_year, historical_nine_months,
                                     current_nine_months, q4_forecast, as_of: date):
    """Keep five full-year flows and their fact/assumption components explicit.

    The old shared forecast helper supports H2 but not Q4. This module applies
    its explicit direct-cash ratios to the real October-to-December period.
    """
    if type(as_of) is not date:
        raise ValueError("REMAINING_YEAR_EXPLICIT_AS_OF_REQUIRED")
    with localcontext() as arithmetic:
        arithmetic.prec = 48
        fy_start, fy_end, full = _observation(historical_full_year)
        old_start, old_end, old_nine = _nine_months(historical_nine_months, as_of=as_of)
        current_start, current_end, current = _nine_months(current_nine_months, as_of=as_of)
        symbols = {row["symbol"] for row in
                   (historical_full_year, historical_nine_months, current_nine_months, q4_forecast)}
        if (len(symbols) != 1 or historical_full_year.get("classification") != "FACT"
                or fy_start != old_start or fy_end.year != old_end.year
                or (fy_start.month, fy_start.day, fy_end.month, fy_end.day) != (1, 1, 12, 31)
                or current_start.year != fy_start.year + 1 or fy_end >= current_start
                or fy_end > as_of or q4_forecast.get("scope") != SCOPE
                or q4_forecast.get("currency") != "CNY"
                or q4_forecast.get("classification") != "FORECAST_ASSUMPTION"
                or q4_forecast.get("period_start") != f"{current_end.year}-10-01"
                or q4_forecast.get("period_end") != f"{current_end.year}-12-31"
                or not q4_forecast.get("source_refs")):
            raise ValueError("REMAINING_YEAR_SAME_ISSUER_PERIOD_CHAIN_REQUIRED")
        # _period rejects malformed dates; Q4 must immediately follow the 9M fact.
        forecast_start, forecast_end = _period(q4_forecast)
        if forecast_start != current_end + timedelta(days=1):
            raise ValueError("REMAINING_YEAR_OVERLAPPING_OR_GAPPED_PERIODS")
        q4_values = {field: full[field] - old_nine[field] for field in FIELDS}
        if (min(q4_values["revenue"], q4_values["cost"]) <= 0
                or min(q4_values["customer_cash"], q4_values["supplier_cash"]) < 0):
            raise ValueError("REMAINING_YEAR_NEGATIVE_DERIVED_Q4_DRIVERS")
        for field in ("rationale", "counter_evidence", "reopen_condition"):
            if not isinstance(q4_forecast.get(field), str) or not q4_forecast[field].strip():
                raise ValueError("REMAINING_YEAR_EXPLAINED_Q4_ASSUMPTIONS_REQUIRED")
        revenue = _number(q4_forecast["revenue"])
        cost = _number(q4_forecast["cost"])
        other = _number(q4_forecast["other_operating_cash"])
        if min(revenue, cost) < 0:
            raise ValueError("REMAINING_YEAR_NEGATIVE_Q4_FORECAST_DRIVERS")
        collected = revenue * q4_values["customer_cash"] / q4_values["revenue"]
        paid = cost * q4_values["supplier_cash"] / q4_values["cost"]
        forecast_values = dict(revenue=revenue, cost=cost, customer_cash=collected,
                               supplier_cash=paid, cfo=collected - paid + other)
        history_sources = {"full_year": historical_full_year["source_refs"],
                           "nine_months": historical_nine_months["source_refs"]}
        result = {}
        for field in FIELDS:
            result[field] = dict(total=str(current[field] + forecast_values[field]),
                fact_9m=str(current[field]), forecast_q4=str(forecast_values[field]),
                fact_classification="FACT", forecast_classification="FORECAST_ASSUMPTION")
        return dict(schema_version=VERSION, action="no_order", formal_eligibility=False,
            symbol=historical_full_year["symbol"], scope=SCOPE, currency="CNY",
            period_start=current_start.isoformat(), period_end=forecast_end.isoformat(),
            classification="FACT_PLUS_FORECAST_ASSUMPTION_NOT_ADOPTED_OWNER_CASH",
            historical_q4=dict(period_start=f"{fy_end.year}-10-01", period_end=fy_end.isoformat(),
                classification="DERIVED_FACT", derivation="same-year FY minus same-year 9M flows",
                source_refs=history_sources, **{k: str(v) for k, v in q4_values.items()}),
            current_nine_months=dict(period_start=current_start.isoformat(),
                period_end=current_end.isoformat(), classification="FACT",
                source_refs=current_nine_months["source_refs"],
                **{k: str(v) for k, v in current.items()}),
            conditional_q4=dict(period_start=forecast_start.isoformat(),
                period_end=forecast_end.isoformat(), classification="FORECAST_ASSUMPTION",
                source_refs=q4_forecast["source_refs"], historical_source_refs=history_sources,
                rationale=q4_forecast["rationale"], counter_evidence=q4_forecast["counter_evidence"],
                reopen_condition=q4_forecast["reopen_condition"],
                coefficients=dict(customer_cash_to_revenue=str(q4_values["customer_cash"] / q4_values["revenue"]),
                                  supplier_cash_to_cost=str(q4_values["supplier_cash"] / q4_values["cost"])),
                other_operating_cash=str(other),
                **{k: str(v) for k, v in forecast_values.items()}),
            full_year=result, annualized_nine_months=False,
            investment_income=None, debt_policy=None, capital_policy=None,
            distribution_capacity=None, automatic_dividend=None,
            owner_model_followup="Investment income, debt and capital policy require the existing owner model; no automatic dividend.")
