"""TEST_ONLY: V7 cash request adds bounded source anchors without promoting forecasts."""
from copy import deepcopy
import hashlib
import json

import pytest

from test_operating_horizon_draft_v2 import context, NOW
from test_operating_horizon_draft_v3 import payload
from value_investment_agent.application.research.agent_review import operating_horizon_split_v6 as old
from value_investment_agent.application.research.agent_review import operating_horizon_split_v7 as new

SOURCE = {"path": "TEST_ONLY/original.pdf", "sha256": "c" * 64}


def _parts(value):
    annual = deepcopy(value)
    cash = annual["years"]["2026"].pop("shareholder_cash_paths")
    annual_text = json.dumps(annual)
    return annual_text, json.dumps({
        "year": "2026", "annual_response_sha256": hashlib.sha256(annual_text.encode()).hexdigest(),
        "shareholder_cash_paths": cash})


def _request(ctx, annual):
    return new.build_requests(ctx, [2026], source_binding=SOURCE,
        annual_response=annual, annual_generated_at=NOW)


def test_v7_adds_same_original_parent_cash_anchor_but_leaves_v6_unchanged(context):
    annual, _ = _parts(payload())
    original = "a" * 64
    for field, scope, amount in (
        ("parent_net_profit", "parent", "10"),
        ("cfo_cny", "ISSUER_PARENT_STANDALONE", "8"),
        ("gross_capex_cny", "ISSUER_PARENT_STANDALONE", "2"),
    ):
        context["evidence"].append(dict(id="TEST_ONLY:" + field, field=field,
            scope=scope, value=amount, text="TEST_ONLY parent statement line", unit="CNY", period="2025-12-31",
            period_basis="FY", source_id="TEST_ONLY:parent", pdf_sha256=original,
            available_at="2026-01-01T00:00:00+00:00"))
    v7 = _request(context, annual)
    cash_input = json.loads(v7.cash.user)
    assert cash_input["historical_parent_cash_bridge"]["periods"][0]["cfo_less_profit_cny"] == "-2"
    assert cash_input["historical_parent_cash_bridge"]["periods"][0]["evidence_ids"] == [
        "TEST_ONLY:parent_net_profit", "TEST_ONLY:cfo_cny", "TEST_ONLY:gross_capex_cny"]
    assert "future forecast assumption need not be a disclosed future fact" in v7.cash.system
    assert json.loads(old.build_requests(context, [2026], source_binding=SOURCE,
        annual_response=annual, annual_generated_at=NOW).cash.user).get(
            "historical_parent_cash_bridge") is None
    assert v7.binding["version"] != old.VERSION


def test_v7_rejects_changed_source_and_preserves_unknown(context):
    annual, cash = _parts(payload(unknown=True))
    request = _request(context, annual)
    result = new.validate_responses(annual, cash, context=context, years=[2026],
        source_binding=SOURCE, binding=request.binding,
        annual_generated_at=NOW, cash_generated_at=NOW)
    assert result["cash_policy_appendix_status"] == "INCOMPLETE_UNKNOWN_TERMS"
    assert result["formal_eligibility"] is False and result["action"] == "no_order"
    with pytest.raises(ValueError, match="SOURCE_OR_REQUEST_CHANGED"):
        new.validate_responses(annual, cash, context=context, years=[2026],
            source_binding={**SOURCE, "sha256": "d" * 64}, binding=request.binding,
            annual_generated_at=NOW, cash_generated_at=NOW)
    malformed = json.loads(cash)
    malformed["shareholder_cash_paths"]["base"]["operating_wc_cash_cny"].update(
        classification="UNKNOWN", value="0", unit="CNY")
    with pytest.raises(ValueError, match="UNKNOWN_CASH"):
        new.validate_responses(annual, json.dumps(malformed), context=context, years=[2026],
            source_binding=SOURCE, binding=request.binding,
            annual_generated_at=NOW, cash_generated_at=NOW)
