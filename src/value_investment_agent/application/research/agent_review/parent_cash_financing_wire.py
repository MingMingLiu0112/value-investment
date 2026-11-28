"""Keep source-bound financing inputs outside the model's response schema."""

import json
from copy import deepcopy
from dataclasses import replace
from datetime import date
from decimal import Decimal

from ..direct_owner_cash_staged_v2 import _identical_prose_duplicate_only
from ..parent_financing_schedule_v1 import disclosed_financing_limits

FINANCING_FIELDS = frozenset(("new_borrowing", "debt_repayment", "interest_outside_cfo"))


def conditional_no_refinance_terms(*, years, opening_principal, schedule, calendar,
                                   paid_interest, residual_stress_rate, anchors):
    """Model full disclosed proceeds, next-year payoff and no further borrowing."""
    year, ceiling, minimum = disclosed_financing_limits(schedule)
    if (len(years) < 2 or years != list(range(year, year + len(years)))
            or not {year, year + 1} <= minimum.keys()
            or any(value > 0 for key, value in minimum.items() if key > year + 1)
            or paid_interest["year"] != year):
        raise ValueError("PARENT_V3_NO_REFINANCE_WINDOW_UNSUPPORTED")
    opening = Decimal(opening_principal)
    rate = Decimal(residual_stress_rate)
    if not opening.is_finite() or opening < 0 or not rate.is_finite() or not 0 < rate < 1:
        raise ValueError("PARENT_V3_NO_REFINANCE_ASSUMPTIONS_INVALID")
    payoff = opening + ceiling - minimum[year]
    residual = payoff - minimum[year + 1]
    if residual < 0:
        raise ValueError("PARENT_V3_NO_REFINANCE_PRINCIPAL_UNFUNDED")
    coupons = {key: Decimal(0) for key in years[:2]}
    for issue in calendar["issues"]:
        due = date.fromisoformat(issue["maturity"]).year
        if due not in coupons:
            raise ValueError("PARENT_V3_NO_REFINANCE_WINDOW_UNSUPPORTED")
        coupons[due] += Decimal(issue["conditional_act365_cash_cny"])
    stress = (residual * rate).quantize(Decimal(".01"))
    interest = [Decimal(paid_interest["minimum_cny"]) + coupons[year] + stress,
                coupons[year + 1] + stress]
    if interest[0] <= 0 or payoff > 0 and interest[1] <= 0:
        raise ValueError("PARENT_V3_NO_REFINANCE_INTEREST_UNSUPPORTED")
    values = {
        "new_borrowing": [ceiling, Decimal(0)],
        "debt_repayment": [minimum[year], payoff],
        "interest_outside_cfo": interest,
    }
    mechanisms = {
        "new_borrowing": "Conditional full disclosed gross proceeds, with no new borrowing thereafter.",
        "debt_repayment": "Disclosed first-year maturity floor and conditional full payoff in the next year.",
        "interest_outside_cfo": (
            f"Realised note interest and conditional ACT/365 coupons, plus {rate:.2%} "
            "annual stress on residual principal for both financing years."),
    }
    return {
        name: dict(
            values=[format(amount, ".2f") for amount in amounts]
            + ["0.00"] * (len(years) - 2),
            evidence_anchors=list(anchors), mechanism=mechanisms[name],
            counter_evidence="Gross issuance is not verified net cash; residual interest and payoff timing are conditional.",
            reopen_condition="Reopen on confirmed cash receipts, loan terms or changes to dated maturities.",
        )
        for name, amounts in values.items()
    }


def financing_policy_request(request, financing_terms):
    payload = json.loads(request.user)
    schema = deepcopy(request.output_schema)
    series = schema["properties"]["series"]
    required = series["required"]
    if (payload["stage"] != "policy" or set(financing_terms) != FINANCING_FIELDS
            or set(payload["required_fields"]) != set(required)
            or not FINANCING_FIELDS <= set(required)):
        raise ValueError("PARENT_V3_FINANCING_WIRE_INVALID")
    remaining = [field for field in required if field not in FINANCING_FIELDS]
    payload["required_fields"] = series["required"] = remaining
    for field in FINANCING_FIELDS:
        del series["properties"][field]
    payload["fixed_conditional_financing_not_facts"] = financing_terms
    anchors = ", ".join(sorted(payload["source_context"]["facts"]))
    return replace(request, user=json.dumps(payload, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")), output_schema=schema, transport_output_contract=(
            "Return one JSON object with exactly years and series. Copy required_years "
            "exactly. In series use only these fields: " + ", ".join(remaining) + ". "
            "Each term has exactly values, evidence_anchors, mechanism, counter_evidence, "
            "and reopen_condition. Values are arrays of decimal strings. Evidence IDs: "
            + anchors + ". The application supplies financing cash amounts from "
            "fixed_conditional_financing_not_facts. Do not echo or replace those terms. "
            "Explain how operating policy responds to that conditional financing path. "
            "Keep paid interest separate from operating cash and avoid double counting."))


def merge_financing_policy_response(response, wire_request):
    if response.tool_calls:
        raise ValueError("PARENT_V3_FINANCING_WIRE_TOOL_CALL_FORBIDDEN")
    data = json.loads(response.text, object_pairs_hook=_identical_prose_duplicate_only)
    payload = json.loads(wire_request.user)
    terms = payload["fixed_conditional_financing_not_facts"]
    if (not isinstance(data, dict) or set(data) != {"years", "series"}
            or data["years"] != payload["required_years"]
            or not isinstance(data["series"], dict)
            or set(data["series"]) != set(payload["required_fields"])
            or set(terms) != FINANCING_FIELDS or FINANCING_FIELDS & data["series"].keys()):
        raise ValueError("PARENT_V3_FINANCING_WIRE_RESPONSE_INVALID")
    data["series"].update(terms)
    # The caller retains the untouched provider response and passes this derived
    # view through the existing strict policy and economic validators.
    return replace(response, text=json.dumps(data, ensure_ascii=False, sort_keys=True,
                                             separators=(",", ":")))
