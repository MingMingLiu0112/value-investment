"""Conditional forecast instructions preserve the admitted V14 source gates."""
import json

import pytest

from test_operating_horizon_split_v8 import split_context, _cash, CASH_AT
from test_operating_horizon_draft_v1 import context as base_context
from value_investment_agent.application.research.agent_review import operating_cash_policy_draft_v15 as cash


def test_v15_requests_contestable_scenarios_without_upgrading_unknown(split_context):
    request = cash.build_request(split_context, [2027])
    assert cash.VERSION in request.system
    assert "FORECAST_ASSUMPTION, never FACT" in request.system
    assert "unpaid commitment" in request.system
    assert "expired 2024-2026 dividend plan" in request.system
    result = cash.validate_response(_cash(unknown=True), split_context, [2027], CASH_AT)
    assert result["cash_policy_appendix_status"] == "INCOMPLETE_UNKNOWN_TERMS"
    assert result["action"] == "no_order" and result["formal_eligibility"] is False


def test_v15_keeps_v14_expired_plan_and_transport_rejections(split_context):
    response = json.loads(_cash())
    response["years"]["2027"]["shareholder_cash_paths"]["base"]["reserve_ratio"]["rationale"] = (
        "Mechanism: 2024-2026 dividend plan proves the 2027 ratio.")
    with pytest.raises(ValueError, match="EXPIRED_PLAN_CANNOT"):
        cash.validate_response(json.dumps(response), split_context, [2027], CASH_AT)
    with pytest.raises(ValueError):
        cash.validate_response(_cash(unknown=True) + "}", split_context, [2027], CASH_AT)
