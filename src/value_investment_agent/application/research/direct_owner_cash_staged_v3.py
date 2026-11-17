"""Numbered-report operating history for the V3 cash sufficiency preflight.

The existing V2 stage/response schema remains in force. Only the historical
parent-company observation source changes; no model response is repaired.
"""
from __future__ import annotations

from decimal import Decimal, localcontext
from pathlib import Path

from .direct_owner_cash_agent_draft_v1 import _load_spec
from .direct_owner_cash_agent_draft_v2 import VERSION as DRAFT_VERSION_V2
from .direct_owner_cash_staged_v2 import merge_staged_parent_cash
from .parent_direct_owner_cash_sources_v2 import read_parent_direct_owner_cash_sources_v2
from ...domain.valuation.parent_direct_operating_cash import (
    SCOPE, forecast_parent_operating_cash,
)

VERSION = "direct-owner-cash-staged-v3"


def merge_staged_parent_cash_v3(**kwargs):
    """Preserve verified V2 stage values while tagging the new draft contract."""
    merged = merge_staged_parent_cash(**kwargs)
    merged["schema_version"] = DRAFT_VERSION_V2
    return merged


def _historical_parent_operating_cash(*, root, spec, evaluated_at):
    if (spec.get("source_adapter_version") != "NUMBERED_CNINFO_V2"
            or spec.get("operating_sources") != []):
        raise ValueError("PARENT_V3_NUMBERED_SOURCE_REQUIRED")
    evidence = read_parent_direct_owner_cash_sources_v2(
        root=root, symbol=spec["symbol"], issuer_name=spec["issuer_name"],
        sources=spec["owner_sources"], evaluated_at=evaluated_at,
        constraint_binding=spec.get("constraint_binding"),
        fund_selection=spec.get("fund_selection"))
    basis = spec["valuation_date"]
    matches = [row for row in evidence["statements"]
               if row["period_end"] == basis and row["period_basis"] == "FY"]
    if len(matches) != 1:
        raise ValueError("PARENT_V3_UNIQUE_ANNUAL_OPERATING_HISTORY_REQUIRED")
    statement = matches[0]
    fields = {
        "revenue": ("income", "revenue"),
        "cost": ("income", "cost"),
        "customer_cash": ("cash_flow", "customer_cash_cny"),
        "supplier_cash": ("cash_flow", "supplier_cash_cny"),
        "cfo": ("cash_flow", "cfo_cny"),
    }
    observed = dict(symbol=spec["symbol"], scope=SCOPE, currency="CNY",
                    classification="FACT", period_start=basis[:4] + "-01-01",
                    period_end=basis, source_refs=[])
    for name, (section, field) in fields.items():
        try:
            item = statement[section][field]
            observed[name] = item["current"]
            observed["source_refs"].append(item["source_refs"])
        except (KeyError, TypeError) as error:
            raise ValueError("PARENT_V3_OPERATING_FACT_MISSING:" + name) from error
    return observed


def preflight_annual_cash_upper_bound_v3(*, root: Path, spec_binding: dict,
                                         evaluated_at, context: dict,
                                         operating: dict, policy: dict) -> None:
    """Reject a deficit even with zero shareholder payout, using real FY cash.

    This necessary check does not establish refinancing, legal distributability,
    executable price or formal investment qualification.
    """
    spec = _load_spec(Path(root).resolve(), spec_binding)
    basis = context["valuation_date"]
    if basis != spec["valuation_date"] or context["symbol"] != spec["symbol"]:
        raise ValueError("PARENT_V3_CONTEXT_IDENTITY_MISMATCH")
    historical = _historical_parent_operating_cash(
        root=root, spec=spec, evaluated_at=evaluated_at)
    opening_id = context["opening_fact_anchors"]["cash"]
    if spec.get("opening", {}).get("cash") != {
            "classification": "FACT", "anchor": opening_id}:
        raise ValueError("PARENT_V3_OPENING_CASH_SCOPE_INVALID")
    opening = context["facts"][opening_id]
    if (opening.get("field") != "closing_cash_and_equivalents_cny"
            or opening.get("period_end") != basis or opening.get("scope") != SCOPE):
        raise ValueError("PARENT_V3_OPENING_CASH_SCOPE_INVALID")
    if operating["years"] != policy["years"]:
        raise ValueError("PARENT_V3_YEAR_MISMATCH")
    mandatory = ("maintenance_capex", "growth_capex", "commitments_outside_capex",
                 "debt_repayment", "interest_outside_cfo", "other_mandatory_cash")
    with localcontext() as arithmetic:
        arithmetic.prec = 48
        cash = Decimal(opening["value_cny"])
        for index, year in enumerate(operating["years"]):
            forecast = dict(symbol=context["symbol"], scope=SCOPE, currency="CNY",
                classification="FORECAST_ASSUMPTION", period_start=f"{year}-01-01",
                period_end=f"{year}-12-31",
                rationale="Source-bound conditional parent operating cash forecast",
                counter_evidence="Collection and payment conversion may weaken",
                reopen_condition="Reopen after new parent-company filing",
                **{field: operating["series"][field]["values"][index]
                   for field in ("revenue", "cost", "other_operating_cash")})
            cfo = Decimal(forecast_parent_operating_cash(
                historical=historical, forecast=forecast)["operating_cash"])
            amounts = {field: Decimal(term["values"][index])
                       for field, term in policy["series"].items()}
            if any(value < 0 for value in amounts.values()):
                raise ValueError("PARENT_V3_NEGATIVE_POLICY_AMOUNT")
            cash += (cfo + amounts["investment_cash_received"]
                     + amounts["new_borrowing"]
                     - sum(amounts[field] for field in mandatory))
            if cash < amounts["cash_floor"]:
                raise ValueError(f"DIRECT_OWNER_UNFUNDED_CASH_REQUIREMENT:{year}")
