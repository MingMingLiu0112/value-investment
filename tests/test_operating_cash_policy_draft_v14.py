"""Direct offline V14 cash contract tests; no provider calls."""
import json
from copy import deepcopy

import pytest

from test_operating_horizon_split_v8 import split_context, _cash, CASH_AT
from test_operating_horizon_draft_v1 import context as base_context
from value_investment_agent.application.research.agent_review import operating_cash_policy_draft_v14 as cash


def test_v14_prompt_and_unknown_remain_bounded(split_context):
    prompt = cash.build_request(split_context, [2027])
    assert cash.VERSION in prompt.system
    assert "expired counterevidence only" in prompt.system
    result = cash.validate_response(_cash(unknown=True), split_context, [2027], CASH_AT)
    assert result["cash_policy_appendix_status"] == "INCOMPLETE_UNKNOWN_TERMS"
    assert result["action"] == "no_order" and result["formal_eligibility"] is False


def test_v14_rejects_marker_even_when_supplied_as_evidence(split_context):
    context = deepcopy(split_context)
    marker = deepcopy(context["evidence"][0])
    marker["id"] = "test:non-evidence-marker"
    context["evidence"].append(marker)
    response = json.loads(_cash(unknown=True))
    response["years"]["2027"]["shareholder_cash_paths"]["base"]["target_payout_ratio"]["evidence_ids"] = [marker["id"]]
    with pytest.raises(ValueError, match="V14_MARKER_OR_NONORDINARY_EVIDENCE_ID"):
        cash.validate_response(json.dumps(response), context, [2027], CASH_AT)


def test_v14_rejects_expired_plan_as_numeric_mechanism(split_context):
    response = json.loads(_cash())
    response["years"]["2027"]["shareholder_cash_paths"]["base"]["reserve_ratio"]["rationale"] = (
        "Mechanism: 2024-2026 dividend plan supplies the 2027 cash policy assumption.")
    with pytest.raises(ValueError, match="EXPIRED_PLAN_CANNOT|V14_EXPIRED_PLAN"):
        cash.validate_response(json.dumps(response), split_context, [2027], CASH_AT)


def test_v14_rejects_trailing_brace_and_missing_mechanism(split_context):
    with pytest.raises(ValueError):
        cash.validate_response(_cash(unknown=True) + "}", split_context, [2027], CASH_AT)
    response = json.loads(_cash())
    response["years"]["2027"]["shareholder_cash_paths"]["base"]["reserve_ratio"]["rationale"] = "Historic cash reserves are stable."
    with pytest.raises(ValueError, match="NUMERIC_CASH_HISTORY_AND_MECHANISM_REQUIRED"):
        cash.validate_response(json.dumps(response), split_context, [2027], CASH_AT)
