"""V12 transport-only cap extension; frozen V8 validators remain authoritative."""
from dataclasses import replace

from . import operating_horizon_request_v11 as annual_v11
from . import operating_horizon_split_v8 as split

VERSION = "operating-horizon-request-v12"
COMPLETION_CAP = 8192


def build_annual_request(context, years, *, source_binding):
    # Frozen request construction stays at 4096; only transport cap changes.
    request = annual_v11.build_annual_request(
        context, years, source_binding=source_binding)
    return replace(request, max_completion_tokens=COMPLETION_CAP,
                   system=request.system + " " + VERSION)


def build_cash_request(context, years, *, source_binding, annual_response,
                       annual_generated_at):
    # The V8 binding/validator hash the original requests. Keep that source
    # binding; the actual V12 transport request has a separate packet hash.
    requests = split.build_requests(
        context, years, source_binding=source_binding,
        annual_response=annual_response, annual_generated_at=annual_generated_at)
    return replace(requests.cash, max_completion_tokens=COMPLETION_CAP,
                   system=requests.cash.system + " " + VERSION), requests.binding
