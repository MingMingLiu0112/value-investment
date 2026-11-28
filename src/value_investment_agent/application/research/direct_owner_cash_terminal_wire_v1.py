"""Give terminal research the preceding cash bridge without changing its output."""
from dataclasses import replace
from decimal import localcontext
import json

from .direct_owner_cash_staged_v3 import _annual_operating_cash
from ...domain.valuation.parent_direct_operating_cash import SCOPE


def terminal_wire_request(request):
    payload = json.loads(request.user)
    context = payload["source_context"]
    previous = payload["prior_forecast_assumptions_not_facts"]
    year = payload["terminal_reference_year"]
    matches = [row for row in context.get("parent_operating_cash_observations", [])
               if row["period_end"] == context["valuation_date"]
               and row["scope"] == SCOPE and row["symbol"] == context["symbol"]]
    if len(matches) == 1:
        historical = dict(matches[0], currency="CNY", classification="FACT",
                          period_start=context["valuation_date"][:4] + "-01-01")
        last = dict(series={name: {"values": [value]}
                            for name, value in previous["operating"].items()})
        with localcontext() as arithmetic:
            arithmetic.prec = 48
            operating_cash = _annual_operating_cash(historical, context, last, 0, year)
        payload["terminal_transition_reference"] = {
            "year": year,
            "classification": "DERIVED_FORECAST_ASSUMPTION_NOT_FACT",
            "operating_cash_cny": str(operating_cash),
            "policy_cash_inputs_cny": previous["policy"],
        }
    return replace(request, user=json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                             separators=(",", ":")),
        transport_output_contract=request.transport_output_contract +
        " Reconcile terminal operating cash to terminal_transition_reference and the "
        "issuer's parent-only cash conversion. Identify which differences are recurring "
        "and which are finite. For the same terminal period and parent scope, recompute "
        "the full net cash equation using the exact values you will return. If cash "
        "exceeds parent_profit, identify the economic source of the mismatch first. "
        "Do not inflate profit, invent outflows, or clip cash merely to pass the check. "
        "Any change from the last year must be justified with the existing evidence, "
        "including capex and financing. If the stationary case cannot be supported, "
        "do not assert one.")
