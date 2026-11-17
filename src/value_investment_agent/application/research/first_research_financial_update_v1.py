"""Identify a newer, source-bound financial period before E1 recompilation.

This only compares reported YTD facts. It cannot infer shareholder cash,
replace assumptions, or make an existing E2/F1 candidate current.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation


def compare_first_input_financial_update(*, symbol: str, financial_basis: str,
                                         native_facts: dict, q3_read_model: dict) -> dict | None:
    if q3_read_model.get("status") == "NOT_SUPPORTED":
        return None
    base = {"schema_version": "first-input-financial-update-v1", "symbol": symbol,
            "status": "UNASSESSABLE", "action": "no_order", "formal_eligibility": False,
            "valuation_recomputed": False, "price_admitted": False,
            "financial_basis": financial_basis, "reported_period": None}
    if q3_read_model.get("status") != "VERIFIED_OBSERVATION_ONLY":
        return {**base, "reason": q3_read_model.get("reason") or "Q3_SOURCE_NOT_VERIFIED"}
    observation = q3_read_model.get("ytd_9m_observation") or {}
    try:
        if (q3_read_model.get("symbol") != symbol or observation.get("symbol") != symbol
                or observation.get("status") != "VERIFIED_REPORTED_Q3_UNAUDITED_OBSERVATION"
                or observation.get("currency") != "CNY" or observation.get("unit") != "yuan"
                or observation.get("period_basis") != "YTD_9M"
                or native_facts.get("symbol") != symbol
                or native_facts.get("financial_basis") != financial_basis):
            raise ValueError("FINANCIAL_UPDATE_SOURCE_IDENTITY_OR_SCOPE_MISMATCH")
        period = date.fromisoformat(observation["report_period"])
        basis = date.fromisoformat(financial_basis)
        if period <= basis:
            return {**base, "status": "NO_NEWER_FINANCIAL_PERIOD",
                    "reported_period": period.isoformat(), "reason": None}
        if (period.year != basis.year or period.month != 9 or basis.month != 6):
            raise ValueError("FINANCIAL_UPDATE_NONCOMPARABLE_PERIODS")
        facts = native_facts["facts"]
        def h1(field: str) -> Decimal:
            rows = [row for row in facts if row.get("field") == field
                    and row.get("period_end") == financial_basis]
            if len(rows) != 1 or rows[0].get("unit") != "CNY":
                raise ValueError("FINANCIAL_UPDATE_UNIQUE_H1_FACT_REQUIRED:" + field)
            return Decimal(rows[0]["value"])
        q3 = observation["facts"]
        revenue_9m, profit_9m = (Decimal(q3[key]) for key in
            ("revenue_ytd_cny", "attributable_profit_ytd_cny"))
        revenue_h1, profit_h1 = h1("revenue"), h1("parent_profit")
        if (not all(value.is_finite() for value in
                    (revenue_9m, profit_9m, revenue_h1, profit_h1))
                or revenue_9m < revenue_h1 or revenue_h1 < 0):
            raise ValueError("FINANCIAL_UPDATE_INVALID_REPORTED_VALUES")
        return {**base, "status": "SOURCE_BOUND_NEW_FINANCIAL_FACT_REQUIRES_E1_RECOMPILE",
                "reason": "Newer reported profit and revenue require a new economic and cash review; the old valuation remains historical.",
                "reported_period": period.isoformat(),
                "source_bindings": q3_read_model["source_bindings"],
                "reported_ytd_9m_cny": {"revenue": str(revenue_9m),
                                         "attributable_profit": str(profit_9m)},
                "reported_h1_ytd_cny": {"revenue": str(revenue_h1),
                                        "attributable_profit": str(profit_h1)},
                "derived_q3_quarter_cny": {"revenue": str(revenue_9m - revenue_h1),
                                            "attributable_profit": str(profit_9m - profit_h1)},
                "fact_classification": "REPORTED_YTD_AND_DERIVED_QUARTER_NOT_FORECAST"}
    except (ValueError, KeyError, TypeError, InvalidOperation) as error:
        return {**base, "reason": str(error)}
