"""Versioned annual D2 transport with exact consolidated pretax anchors.

This changes the request, never the frozen v2 response or its validator.
"""
from dataclasses import replace

from . import operating_horizon_draft_v2 as prior

VERSION = "operating-horizon-draft-v3"


def build_request(context, years, max_completion_tokens=4096):
    basis, plans = prior.prior.annual_plan(context, years)
    request = prior.build_request(context, years, max_completion_tokens)
    anchors = []
    for year, plan in plans.items():
        fields = basis["baselines"][plan["baseline_period"]]["fields"]
        anchor = fields["pre_tax_profit"]["evidence_id"]
        if not isinstance(anchor, str) or not anchor or anchor not in {
            row["id"] for row in context["evidence"]
        }:
            raise ValueError("CONSOLIDATED_PRETAX_ANCHOR_NOT_IN_SOURCE_CONTEXT")
        anchors.append(f"{year}: {anchor}")
    instruction = (
        " For each scenario in each listed year, other_pretax_cny.evidence_ids "
        "MUST include the exact consolidated pre_tax_profit baseline ID: "
        + "; ".join(anchors)
        + ". This is a residual accounting anchor, not a cash receipt or a "
        "claim that the residual recurs. Preserve any other genuine citations; "
        "do not invent an ID or alter the underlying numeric forecast to fit it."
    )
    return replace(request, system=request.system + " " + VERSION + instruction,
        transport_output_contract=(request.transport_output_contract or "") + instruction)


def validate_response(response, context, years, generated_at):
    result = prior.validate_response(response, context, years, generated_at)
    result["schema_version"] = VERSION
    result["prompt_version"] = VERSION
    return result
