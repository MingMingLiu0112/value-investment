"""V14 2027 cash boundary; V3 remains frozen and authoritative."""
from dataclasses import replace
import re

from value_investment_agent.application.research.agent_review import operating_cash_policy_draft_v3 as prior
from value_investment_agent.application.research.agent_review import operating_horizon_draft_v3 as full
from value_investment_agent.application.research.agent_review.operating_driver_draft_v2 import _payload

VERSION = "operating-cash-policy-draft-v14-2027-expired-plan-boundary"
_PLAN = re.compile(r"2024\s*[-－—–]\s*2026|75\s*%|0[.]75|issuer.?plan|dividend.?plan|分红规划|分红计划", re.I)
_MARKER = re.compile(r"marker|non.?evidence|issuer.?plan|dividend.?plan|分红规划|分红计划", re.I)


def build_request(context, years, max_completion_tokens=2048):
    request = prior.build_request(context, years, max_completion_tokens)
    return replace(request, system=request.system + " " + VERSION + ": The 2024-2026 plan is expired counterevidence only. "
        "Never put its binding, label, or marker in evidence_ids. For a 2027 numeric cash term cite an ordinary "
        "sealed historical source and explain the economic mechanism; UNKNOWN/null is valid. Return one JSON object only.")


def validate_response(response, context, years, generated_at):
    # First retain every frozen schema, time, source and economic gate.
    result = prior.validate_response(response, context, years, generated_at)
    payload = _payload(response.text if hasattr(response, "text") else response)
    ordinary = {row["id"] for row in context["evidence"] if row.get("period", "") < "2027-01-01"
        and not _MARKER.search(row["id"])}
    for path in payload["years"]["2027"]["shareholder_cash_paths"].values():
        for name in full.TERMS:
            term = path[name]
            ids = term["evidence_ids"]
            if any(id not in ordinary for id in ids):
                raise ValueError("V14_MARKER_OR_NONORDINARY_EVIDENCE_ID")
            if term["classification"] != "UNKNOWN" and _PLAN.search(term["rationale"]):
                raise ValueError("V14_EXPIRED_PLAN_CANNOT_SUPPORT_2027_TERM")
    return {**result, "schema_version": VERSION, "prompt_version": VERSION}
