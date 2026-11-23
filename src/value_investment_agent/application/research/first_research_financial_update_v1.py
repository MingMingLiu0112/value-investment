"""Identify a newer, source-bound financial period before E1 recompilation.

This only compares reported YTD facts. It cannot infer shareholder cash,
replace assumptions, or make an existing E2/F1 candidate current.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from decimal import Decimal, InvalidOperation

from ...domain.valuation.joint_capital_cash_path_v4 import HISTORICAL_FIELDS


_SOURCE_FINANCIAL_FIELDS = HISTORICAL_FIELDS - {
    "scope", "currency", "opening_cash", "opening_distribution_capacity", "cash_floor"
}
_OPERATING_SCOPES = {"revenue": "consolidated", "parent_profit": "consolidated_parent"}


def compare_first_input_financial_update(*, symbol: str, financial_basis: str,
                                         native_facts: dict, q3_read_model: dict,
                                         income_read_model: dict | None = None) -> dict | None:
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
        if (period.year != basis.year or (period.month, period.day) != (9, 30)
                or (basis.month, basis.day) != (6, 30)):
            raise ValueError("FINANCIAL_UPDATE_NONCOMPARABLE_PERIODS")
        facts = native_facts["facts"]
        def h1(field: str) -> Decimal:
            rows = [row for row in facts if row.get("field") == field
                    and row.get("period_end") == financial_basis]
            if len(rows) != 1 or rows[0].get("unit") != "CNY":
                raise ValueError("FINANCIAL_UPDATE_UNIQUE_H1_FACT_REQUIRED:" + field)
            if rows[0].get("scope") != _OPERATING_SCOPES[field]:
                raise ValueError("FINANCIAL_UPDATE_H1_SCOPE_MISMATCH:" + field)
            return Decimal(rows[0]["value"])
        q3 = observation["facts"]
        revenue_9m, profit_9m = (Decimal(q3[key]) for key in
            ("revenue_ytd_cny", "attributable_profit_ytd_cny"))
        revenue_h1, profit_h1 = h1("revenue"), h1("parent_profit")
        if (not all(value.is_finite() for value in
                    (revenue_9m, profit_9m, revenue_h1, profit_h1))
                or revenue_9m < revenue_h1 or revenue_h1 < 0):
            raise ValueError("FINANCIAL_UPDATE_INVALID_REPORTED_VALUES")
        verified_fields = set(_OPERATING_SCOPES)
        income = None
        if income_read_model and income_read_model.get("status") == "VERIFIED_REPORTED_Q3_INCOME_FACTS_ONLY":
            if (income_read_model.get("symbol") != symbol or
                    income_read_model.get("report_period") != period.isoformat() or
                    income_read_model.get("currency") != "CNY" or
                    income_read_model.get("unit") != "yuan" or
                    income_read_model.get("period_basis") != "YTD_9M"):
                raise ValueError("FINANCIAL_UPDATE_INCOME_SCOPE_MISMATCH")
            income = income_read_model
            current = income["facts"][str(period.year)]
            if Decimal(current["revenue"]) != revenue_9m or Decimal(current["parent_profit"]) != profit_9m:
                raise ValueError("FINANCIAL_UPDATE_INCOME_FACT_CONFLICT")
            verified_fields.update(current)
        return {**base, "status": "SOURCE_BOUND_NEW_FINANCIAL_FACT_REQUIRES_E1_RECOMPILE",
                "reason": "Newer reported profit and revenue require a new economic and cash review; the old valuation remains historical.",
                "reported_period": period.isoformat(),
                "source_bindings": q3_read_model["source_bindings"],
                "verified_income_observation": income,
                "income_observation_status": (income_read_model or {}).get("status", "NOT_STARTED"),
                "reported_ytd_9m_cny": {"revenue": str(revenue_9m),
                                         "attributable_profit": str(profit_9m)},
                "reported_h1_ytd_cny": {"revenue": str(revenue_h1),
                                        "attributable_profit": str(profit_h1)},
                "derived_q3_quarter_cny": {"revenue": str(revenue_9m - revenue_h1),
                                            "attributable_profit": str(profit_9m - profit_h1)},
                "e1_recompile_requirements": {
                    "current_ytd_source_fields_missing": sorted(_SOURCE_FINANCIAL_FIELDS - verified_fields),
                    "prior_year_comparative_required": True,
                    "ordinary_shares_at_new_basis": "UNVERIFIED",
                    "parent_accessible_cash_at_new_basis": "UNVERIFIED",
                    "forecast_cash_policy_reunderwriting_required": True,
                },
                "fact_classification": "REPORTED_YTD_AND_DERIVED_QUARTER_NOT_FORECAST"}
    except (ValueError, KeyError, TypeError, InvalidOperation) as error:
        return {**base, "reason": str(error)}



def _read_aligned_operating_income(root, now, native_facts, observation):
    from ..product.common import require_inside, sha256_file
    from ...infrastructure.filings.pdf_text import extract_pages
    from ...infrastructure.filings.quarterly_operating_facts_v1 import FIELDS, parse_quarterly_operating_facts

    basis = native_facts["financial_basis"]
    revenue_rows = [row for row in native_facts["facts"] if row["field"] == "revenue"
                    and row["period_end"] == basis and row["scope"] == "consolidated"]
    if len(revenue_rows) != 1:
        raise ValueError("Q3_CURRENCY_BASIS_UNVERIFIED")
    source, = (row for row in native_facts["sources"] if row["id"] == revenue_rows[0]["source_id"]
               and row["symbol"] == observation["symbol"] and row["report_period"] == basis)
    current = observation["source_bindings"]["original"]
    def reopen(binding):
        path = require_inside(root, root / binding["path"], "quarter operating original")
        if datetime.fromisoformat(binding["available_at"]) > now or sha256_file(path) != binding["sha256"]:
            raise ValueError("Q3_OPERATING_ORIGINAL_BINDING_INVALID")
        return extract_pages(path, limit=80)

    currency_refs = [dict(path=source["path"], sha256=source["sha256"], physical_page=n, excerpt=line.strip())
                     for n, page in enumerate(reopen(source), 1) for line in page.splitlines()
                     if "以人民币为记账本位币" in line]
    parsed = parse_quarterly_operating_facts(reopen(current), symbol=observation["symbol"],
                                            currency_basis={"currency": "CNY", "evidence_refs": currency_refs})
    if parsed["period_end"] != observation["ytd_9m_observation"]["report_period"]:
        raise ValueError("Q3_OPERATING_REPORT_PERIOD_MISMATCH")
    return dict(status="VERIFIED_REPORTED_Q3_INCOME_FACTS_ONLY", symbol=parsed["symbol"],
                report_period=parsed["period_end"], period_basis="YTD_9M", currency="CNY", unit="yuan",
                facts={parsed[period][:4]: {name: parsed["fields"][name][column] for name in FIELDS}
                       for period, column in (("period_end", "current"), ("comparative_end", "comparative"))},
                source_bindings={"original": current, "currency_basis": currency_refs},
                original_rows={name: parsed["fields"][name] for name in FIELDS}, action="no_order")


def compare_aligned_quarter_update(*, symbol: str, financial_basis: str,
                                   native_facts: dict, alignment: dict,
                                   root: Path | None = None, now: datetime | None = None) -> dict | None:
    """Consume only the quarterly facts already reopened by the same candidate's F2."""
    check, = (row for row in alignment["checks"] if row["id"] == "financial_updates")
    candidates = {}
    for event in check["details"].get("financial_update_research", ()):
        if event.get("status") != "SOURCE_TERMS_VERIFIED_REQUIRES_CANDIDATE_REVIEW":
            continue
        for fact in event["facts"]:
            update = fact["terms"]["financial_update"]
            if (update.get("status") != "VERIFIED"
                    or update.get("period_basis") != "YEAR_TO_DATE_9M_NOT_SINGLE_QUARTER"
                    or update.get("action") != "no_order"
                    or update["period_start"] != financial_basis[:4] + "-01-01"
                    or update["period_end"] != financial_basis[:4] + "-09-30"):
                continue
            revenue = update["fields"]["revenue_cny"]
            profit = update["fields"]["parent_profit_cny"]
            if (revenue["scope"], profit["scope"], revenue["unit"], profit["unit"]) != (
                    "consolidated", "consolidated_parent", "CNY", "CNY"):
                continue
            binding = fact["binding"]
            observation = {
                "status": "VERIFIED_OBSERVATION_ONLY", "symbol": symbol,
                "source_bindings": {"original": {**binding, "source_url": fact["source_url"],
                                                    "available_at": fact["source_available_at"]}},
                "ytd_9m_observation": {
                    "symbol": symbol, "status": "VERIFIED_REPORTED_Q3_UNAUDITED_OBSERVATION",
                    "report_period": update["period_end"], "period_basis": "YTD_9M",
                    "unit": "yuan", "currency": "CNY",
                    "facts": {"revenue_ytd_cny": revenue["value"],
                              "attributable_profit_ytd_cny": profit["value"]},
                },
            }
            previous = candidates.setdefault(binding["sha256"], observation)
            if (previous["ytd_9m_observation"] != observation["ytd_9m_observation"]
                    or previous["source_bindings"]["original"]["source_url"] != fact["source_url"]):
                return compare_first_input_financial_update(
                    symbol=symbol, financial_basis=financial_basis, native_facts=native_facts,
                    q3_read_model={"status": "UNASSESSABLE",
                                   "reason": "CONFLICTING_BOUND_QUARTER_FINANCIAL_FACTS"},
                )
    if len(candidates) != 1:
        return None
    observation = next(iter(candidates.values()))
    income = None
    if root is not None and now is not None:
        try:
            income = _read_aligned_operating_income(root, now, native_facts, observation)
        except (OSError, ValueError, KeyError, TypeError) as error:
            income = {"status": "UNASSESSABLE", "reason": str(error)}
    return compare_first_input_financial_update(
        symbol=symbol, financial_basis=financial_basis, native_facts=native_facts,
        q3_read_model=observation, income_read_model=income,
    )
