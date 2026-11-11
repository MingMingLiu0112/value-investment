"""2027 conditional cash hypotheses; V14 evidence gates remain authoritative."""
from dataclasses import replace

from . import operating_cash_policy_draft_v14 as prior


VERSION = "operating-cash-policy-draft-v15-2027-conditional-hypotheses"


def build_request(context, years, max_completion_tokens=2048):
    request = prior.build_request(context, years, max_completion_tokens)
    return replace(request, system=request.system + " " + VERSION + ": "
        "A future conditional assumption does not require an already published 2027 plan. "
        "For bear/base/bull, examine each of the six shareholder-cash terms separately. "
        "Where an ordinary sealed historical issuer source provides a relevant anchor, "
        "propose a numerically explicit, contestable 2027 scenario only if its rationale "
        "starts 'Mechanism:' and explains the historical anchor, the change from that "
        "anchor, parent-versus-group scope, the economic reason for the scenario, and "
        "what would overturn it. Treat its value as FORECAST_ASSUMPTION, never FACT. "
        "Use different economic conditions for bear/base/bull; do not choose values to "
        "match the market price. Historical parent CFO is not accessible profit; gross "
        "capital expenditure is not proven maintenance spending; an unpaid commitment "
        "has no proven payment year. If the source cannot bound a term defensibly, "
        "leave that term UNKNOWN/null and say which missing mechanism prevents a bound. "
        "The expired 2024-2026 dividend plan is counterevidence only, never the "
        "2027 payout target or a numeric support citation. Return exactly one JSON "
        "object without markdown or trailing characters.")


def validate_response(response, context, years, generated_at):
    result = prior.validate_response(response, context, years, generated_at)
    return {**result, "schema_version": VERSION, "prompt_version": VERSION}
