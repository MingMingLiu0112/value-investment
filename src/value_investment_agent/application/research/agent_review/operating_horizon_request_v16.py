"""V16 source-bound annual pretax citation instruction; V13 transport is retained."""
from dataclasses import replace

from . import operating_horizon_request_v13 as prior
from . import operating_horizon_split_v13 as split
from . import operating_horizon_draft_v1 as annual_plan

VERSION = "operating-horizon-request-v16-annual-pretax-citation"


def build_annual_request(context, years, *, source_binding):
    request = prior.build_annual_request(context, years, source_binding=source_binding)
    projected = split._annual_context(split._project(context, source_binding))
    basis, plans = annual_plan.annual_plan(projected, years)
    instructions = []
    for year, plan in sorted(plans.items()):
        period = plan["baseline_period"]
        try:
            anchor = basis["baselines"][period]["fields"]["pre_tax_profit"]["evidence_id"]
        except (KeyError, TypeError) as error:
            raise ValueError("V16_FY_PRETAX_ANCHOR_REQUIRED") from error
        ids = {row["id"] for row in projected["evidence"]}
        if not isinstance(anchor, str) or not anchor or anchor not in ids:
            raise ValueError("V16_FY_PRETAX_ANCHOR_REQUIRED")
        instructions.append(
            f"For year {year}, baseline {period}, the consolidated FY pre_tax_profit "
            f"source-bound evidence ID is {anchor}. Include exactly this ID in "
            f"years[{year}].operating_paths.bear.drivers.other_pretax_cny.evidence_ids, "
            f"years[{year}].operating_paths.base.drivers.other_pretax_cny.evidence_ids, "
            f"and years[{year}].operating_paths.bull.drivers.other_pretax_cny.evidence_ids. "
            "Keep any other valid interim comparative citations; do not substitute them "
            "for the FY consolidated pre-tax residual anchor.")
    delta = " " + VERSION + ": " + " ".join(instructions)
    return replace(request, system=request.system + delta,
                   transport_output_contract=(request.transport_output_contract or "") + delta)