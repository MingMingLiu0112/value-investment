"""V11 annual transport instruction; the V3 validator remains authoritative."""
from dataclasses import replace

from . import operating_horizon_split_v8 as split

VERSION = "operating-horizon-request-v11"
INSTRUCTION = (
    " For every bear, base, and bull scenario, unit_cost_case.mechanism MUST "
    "contain at least 30 substantive characters explaining the scenario-specific "
    "unit-cost mechanism and its link to the cited source anchors. Avoid generic "
    "labels or repeated filler. Keep all original evidence IDs, contrary evidence, "
    "reopen conditions, source citations, point-in-time boundaries, and numbers."
)


def build_annual_request(context, years, *, source_binding, max_completion_tokens=4096):
    request = split.build_annual_request(context, years,
        source_binding=source_binding, max_completion_tokens=max_completion_tokens)
    return replace(request, system=request.system + " " + VERSION + INSTRUCTION,
        transport_output_contract=(request.transport_output_contract or "") + INSTRUCTION)
