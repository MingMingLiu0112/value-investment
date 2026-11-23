"""Numbered-report operating history for the V3 cash sufficiency preflight.

The existing V2 stage/response schema remains in force. Only the historical
parent-company observation source changes; no model response is repaired.
"""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal, localcontext
import json
from pathlib import Path

from .direct_owner_cash_agent_draft_v1 import _load_spec
from .direct_owner_cash_agent_draft_v2 import VERSION as DRAFT_VERSION_V2
from .direct_owner_cash_staged_v2 import (
    merge_staged_parent_cash, staged_parent_cash_request,
)
from .parent_direct_owner_cash_sources_v2 import read_parent_direct_owner_cash_sources_v2
from .parent_direct_owner_cash_unnumbered_v1 import (
    VERSION as UNNUMBERED_SOURCE, FINANCING_VERSION, UNNUMBERED_VERSIONS,
    read_unnumbered_parent_cash, read_unnumbered_parent_financing,
)
from ...domain.valuation.parent_direct_operating_cash import (
    SCOPE, forecast_parent_operating_cash,
)

VERSION = "direct-owner-cash-staged-v3"


def staged_parent_cash_request_v3(**kwargs):
    """Keep old stage schemas; state the existing terminal economic invariant.

    Old sealed requests and responses remain historical. This V3-only prompt
    correction never edits a model response or relaxes the deterministic cash
    compiler, which still rejects an unsupported stationary tail.
    """
    request = staged_parent_cash_request(**kwargs)
    if kwargs["stage"] == "policy":
        payload = json.loads(request.user)
        context = payload["source_context"]
        floors = []
        for observation in context.get("historical_financing_observations", []):
            cash = observation["financing_cash_flows"]
            period = cash["period_end"]
            year = int(period[:4])
            if (year not in payload["required_years"] or
                    cash["period_start"] != f"{year}-01-01" or period == f"{year}-12-31"):
                continue
            for observed_field, forecast_field in (
                ("borrowings_received_cny", "new_borrowing"),
                ("debt_repayments_paid_cny", "debt_repayment"),
            ):
                movement = cash["components"][observed_field]
                if movement["classification"] == "FACT":
                    floors.append(dict(year=year, field=forecast_field,
                                       minimum_cny=movement["value_cny"], observed_through=period))
        history = [
            row for row in context.get("parent_operating_cash_observations", [])
            if row["period_end"] == context["valuation_date"]
            and row["scope"] == SCOPE and row["symbol"] == context["symbol"]
        ]
        if history:
            if len(history) != 1 or not context["valuation_date"].endswith("-12-31"):
                raise ValueError("PARENT_V3_UNIQUE_ANNUAL_OPERATING_HISTORY_REQUIRED")
            historical = dict(history[0], currency="CNY", classification="FACT",
                              period_start=context["valuation_date"][:4] + "-01-01")
            operating = kwargs["prior_drafts"]["operating"]
            with localcontext() as arithmetic:
                arithmetic.prec = 48
                payload["derived_annual_operating_cash_path"] = [
                    dict(year=year, operating_cash_cny=str(_annual_operating_cash(
                        historical, context, operating, index, year)))
                    for index, year in enumerate(operating["years"])
                ]
        if floors or history:
            payload["realised_annual_financing_floors"] = floors
            return replace(request, user=json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                                    separators=(",", ":")),
                           transport_output_contract=request.transport_output_contract +
                           " For each realised_annual_financing_floors row, the stated policy series "
                           "field in that year must be at least minimum_cny. These are gross realised "
                           "parent cash amounts, not net financing or future refinancing forecasts."
                           " If derived_annual_operating_cash_path is present, use that cash path to "
                           "check yearly liquidity and mandatory payments before modelling payout. "
                           "It is derived from the submitted operating forecast, not a historical fact. "
                           "Supplier payments, working-capital movements and other operating "
                           "cash adjustments are already included in this path. "
                           "For other_mandatory_cash, identify distinct cash payments outside "
                           "operating cash and the separately forecast capex, commitments, debt "
                           "repayment and interest lines. Do not deduct an operating cash or "
                           "working-capital residual again as other_mandatory_cash. "
                           "A reported closing cash balance is a point-in-time observation, "
                           "not a minimum operating reserve. Explain the basis and uncertainty "
                           "of each cash_floor assumption independently of the observed balance. "
                           "Do not invent financing or other receipts to close a funding gap.")
    if kwargs["stage"] != "terminal":
        return request
    payload = json.loads(request.user)
    if kwargs.get("verified_context") is not None and kwargs.get("prior_drafts") is not None:
        # This is a forecast arithmetic check, never evidence of future lending.
        spec = _load_spec(Path(kwargs["root"]), kwargs["spec_binding"])
        opening_debt = spec["opening"]["debt"]
        facts = kwargs["verified_context"]["facts"]
        def amount(term):
            if "linear_terms" in term:
                return sum(Decimal(facts[row["anchor"]]["value_cny"]) *
                           Decimal(row["factor"]) for row in term["linear_terms"])
            if "anchor" in term:
                factor = Decimal(term.get("factor", "1"))
                return Decimal(facts[term["anchor"]]["value_cny"]) * factor
            return Decimal(term["value"])
        # Expose only the verified field identity and the spec classification.
        # Free-form spec prose is not promoted into a model instruction.
        anchor = opening_debt.get("anchor")
        field = facts[anchor]["field"] if anchor is not None else None
        upper_bound = (opening_debt["classification"] == "FORECAST_ASSUMPTION"
                       and field == "liabilities_cny")
        payload["opening_debt_basis"] = dict(
            amount_cny=str(amount(opening_debt)),
            classification=opening_debt["classification"],
            fact_field=field,
            scope=("ALL_PARENT_LIABILITIES_UPPER_BOUND_NOT_FINANCING_FACT"
                   if upper_bound else "SPECIFIED_OPENING_DEBT_BASIS"))
        policy = kwargs["prior_drafts"]["policy"]["series"]
        debt = amount(opening_debt)
        debt_path = []
        years = kwargs["prior_drafts"]["policy"].get("years")
        borrowings = policy["new_borrowing"]["values"]
        repayments = policy["debt_repayment"]["values"]
        if years is not None and len(years) != len(borrowings):
            raise ValueError("PARENT_V3_FORECAST_DEBT_YEARS_INVALID")
        for index, (borrowing, repayment) in enumerate(
                zip(borrowings, repayments, strict=True)):
            debt += Decimal(borrowing) - Decimal(repayment)
            if debt < 0:
                raise ValueError("PARENT_V3_FORECAST_DEBT_NEGATIVE")
            debt_path.append(dict(year=years[index] if years is not None else index + 1,
                                  closing_debt_cny=str(debt)))
        payload["forecast_closing_debt_after_annual_years"] = dict(
            value_cny=str(debt),
            annual_path=debt_path,
            classification="DERIVED_FORECAST_ASSUMPTION_NOT_FACT",
            method="opening debt assumption plus ten annual new_borrowing minus debt_repayment",
            refinancing_guaranteed=False)
    rule = (
        " For the stationary tail, calculate net distributable cash before payout as "
        "operating_cash + investment_cash_received - maintenance_capex - growth_capex "
        "- interest_outside_cfo - other_mandatory_cash + new_borrowing - debt_repayment. "
        "This stationary net must be between zero and parent_profit inclusive. "
        " The stationary terminal policy field commitments_outside_capex must be zero. "
        "Allocate supported finite obligations to their finite forecast years. "
        "If any obligation remains after the forecast or its settlement cannot be supported, "
        "do not assert a stationary terminal or claim that the obligation disappeared. "
        "A one-time return of investment principal is not a recurring terminal receipt. "
        "Explain the recurring source of investment_cash_received; if it cannot be "
        "supported, leave the terminal economically unassessable rather than inventing "
        "a sustainable amount. Do not adjust values to match a market price."
        " Express cost_of_equity as a decimal fraction strictly between zero and one: "
        "12 percent must be 0.12, never 12.00. Do not silently convert an "
        "unsupported rate or infer one from the current share price."
        " If forecast_closing_debt_after_annual_years.value_cny is positive, "
        "terminal.financing cannot be null; an equal borrowing/repayment rollover "
        "is only a conditional assumption and must include cash interest. "
        "Use the forecast_closing_debt_after_annual_years amount as the maximum "
        "gross terminal repayment under constant-debt rollover; do not claim "
        "debt was fully repaid when that amount remains positive. Its annual_path "
        "is forecast arithmetic, not evidence of future lender approval."
        " The opening_debt_basis classification and scope are binding: an all-parent-"
        "liabilities upper bound is not an observed interest-bearing debt balance or"
        " a dated maturity schedule. Do not claim the upper bound must be repaid"
        " or refinanced as a verified financing obligation."
    )
    if "forecast_closing_debt_after_annual_years" in payload:
        exact_cap = payload["forecast_closing_debt_after_annual_years"]["value_cny"]
        rule += (
            " The exact forecast terminal opening debt is " + exact_cap +
            " CNY. Any terminal annual gross debt_repayment must be no greater"
            " than this exact amount. Do not round the amount upward to a"
            " convenient billion; equal gross new_borrowing does not relax"
            " this bound. A feasible arithmetic assumption is still not"
            " evidence of available refinancing."
        )
    return replace(request, user=json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                             separators=(",", ":")),
                   transport_output_contract=request.transport_output_contract + rule)


def preflight_terminal_forecast_debt_v3(*, request, parsed_stage):
    """Reject a terminal debt contradiction before requesting another scenario."""
    projected = json.loads(request.user).get("forecast_closing_debt_after_annual_years")
    if projected is None:
        return  # Older TEST_ONLY requests have no source-bound debt projection.
    debt = Decimal(projected["value_cny"])
    terminal = parsed_stage["terminal"]
    commitment = terminal.get("policy", {}).get("commitments_outside_capex")
    if commitment is not None and Decimal(commitment["values"][0]) != 0:
        raise ValueError("PARENT_V3_FINITE_COMMITMENT_IN_TERMINAL")
    financing = terminal["financing"]
    if debt > 0 and financing is None:
        raise ValueError("PARENT_V3_TERMINAL_DEBT_POLICY_UNSUPPORTED")
    if financing is not None:
        policy = terminal["policy"]
        repayment = Decimal(policy["debt_repayment"]["values"][0])
        borrowing = Decimal(policy["new_borrowing"]["values"][0])
        if debt <= 0 or repayment > debt or borrowing != repayment:
            raise ValueError("PARENT_V3_TERMINAL_REFINANCING_ARITHMETIC_INVALID")
        interest = Decimal(policy["interest_outside_cfo"]["values"][0])
        if interest <= 0:
            raise ValueError("PARENT_V3_TERMINAL_CASH_INTEREST_REQUIRED")
    policy = terminal.get("policy", {})
    cash_fields = ("operating_cash", "investment_cash_received", "new_borrowing",
                   "maintenance_capex", "growth_capex", "interest_outside_cfo",
                   "other_mandatory_cash", "debt_repayment", "parent_profit")
    if all(field in policy for field in cash_fields):
        with localcontext() as arithmetic:
            arithmetic.prec = 48
            amounts = {field: Decimal(policy[field]["values"][0]) for field in cash_fields}
            net = (amounts["operating_cash"] + amounts["investment_cash_received"]
                   + amounts["new_borrowing"] - sum(amounts[field] for field in cash_fields[3:-1]))
        if not 0 <= net <= amounts["parent_profit"]:
            raise ValueError("PARENT_V3_UNSUPPORTED_STATIONARY_CASH_CONVERSION")


def merge_staged_parent_cash_v3(**kwargs):
    """Preserve verified V2 stage values while tagging the new draft contract."""
    merged = merge_staged_parent_cash(**kwargs)
    merged["schema_version"] = DRAFT_VERSION_V2
    return merged


def _historical_parent_operating_cash(*, root, spec, evaluated_at):
    if (spec.get("source_adapter_version") not in {"NUMBERED_CNINFO_V2", *UNNUMBERED_VERSIONS}
            or spec.get("operating_sources") != []):
        raise ValueError("PARENT_V3_NUMBERED_SOURCE_REQUIRED")
    reader = {
        UNNUMBERED_SOURCE: read_unnumbered_parent_cash,
        FINANCING_VERSION: read_unnumbered_parent_financing,
        "NUMBERED_CNINFO_V2": read_parent_direct_owner_cash_sources_v2,
    }[spec["source_adapter_version"]]
    evidence = reader(
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


def _annual_operating_cash(historical, context, operating, index, year):
    forecast = dict(symbol=context["symbol"], scope=SCOPE, currency="CNY",
                    classification="FORECAST_ASSUMPTION", period_start=f"{year}-01-01",
                    period_end=f"{year}-12-31",
                    rationale="Source-bound conditional parent operating cash forecast",
                    counter_evidence="Collection and payment conversion may weaken",
                    reopen_condition="Reopen after new parent-company filing",
                    **{field: operating["series"][field]["values"][index]
                       for field in ("revenue", "cost", "other_operating_cash")})
    return Decimal(forecast_parent_operating_cash(
        historical=historical, forecast=forecast)["operating_cash"])

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
    # Annual forecasts cover the full calendar year. A known interim parent
    # cash movement within that year is a hard floor, not a future estimate.
    for observation in context.get("historical_financing_observations", []):
        cash = observation["financing_cash_flows"]
        period = cash["period_end"]
        year = int(period[:4])
        if (year not in policy["years"] or cash["period_start"] != f"{year}-01-01"
                or period == f"{year}-12-31"):
            continue
        index = policy["years"].index(year)
        for observed_field, forecast_field in (
            ("borrowings_received_cny", "new_borrowing"),
            ("debt_repayments_paid_cny", "debt_repayment"),
        ):
            movement = cash["components"][observed_field]
            if (movement["classification"] == "FACT"
                    and Decimal(policy["series"][forecast_field]["values"][index])
                    < Decimal(movement["value_cny"])):
                raise ValueError(
                    f"PARENT_V3_ANNUAL_FINANCING_BELOW_REALISED_CASH:{year}:{forecast_field}")
    mandatory = ("maintenance_capex", "growth_capex", "commitments_outside_capex",
                 "debt_repayment", "interest_outside_cfo", "other_mandatory_cash")
    with localcontext() as arithmetic:
        arithmetic.prec = 48
        cash = Decimal(opening["value_cny"])
        for index, year in enumerate(operating["years"]):
            cfo = _annual_operating_cash(historical, context, operating, index, year)
            amounts = {field: Decimal(term["values"][index])
                       for field, term in policy["series"].items()}
            if any(value < 0 for value in amounts.values()):
                raise ValueError("PARENT_V3_NEGATIVE_POLICY_AMOUNT")
            cash += (cfo + amounts["investment_cash_received"]
                     + amounts["new_borrowing"]
                     - sum(amounts[field] for field in mandatory))
            if cash < amounts["cash_floor"]:
                raise ValueError(f"DIRECT_OWNER_UNFUNDED_CASH_REQUIREMENT:{year}")
