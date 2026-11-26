"""Opt-in financing revision request projections."""
import json

import pytest

from value_investment_agent.application.research import direct_owner_cash_staged_v3 as staged
from value_investment_agent.application.research.direct_owner_cash_financing_rows_v1 import staged_financing_request_v1
from value_investment_agent.infrastructure.agent_runtime.provider import LLMRequest


@pytest.mark.parametrize("repayment", ["12", "7"])
def test_terminal_debt_bridge_separates_principal_and_interest(monkeypatch, tmp_path, repayment):
    old = LLMRequest(role="FUNDAMENTAL", system="", user="{}", output_schema={}, transport_output_contract="old")
    monkeypatch.setattr(staged, "staged_parent_cash_request", lambda **kwargs: old)
    monkeypatch.setattr(staged, "_load_spec", lambda *args: {
        "opening": {"debt": {"value": "20", "classification": "FORECAST_ASSUMPTION"}}})
    issue = dict(classification="FACT", scope="ISSUER_FINANCING_DISCLOSURE",
                 currency="CNY", code="TEST_ONLY", maturity="2027-04-15", principal_cny="8")
    kwargs = dict(stage="terminal", root=tmp_path, spec_binding={},
                  verified_context={"facts": {}, "constraints": {"issued_financing": [issue]}},
                  prior_drafts={"policy": {"years": [2027], "series": {
                      "new_borrowing": {"values": ["0"]}, "debt_repayment": {"values": [repayment]},
                      "interest_outside_cfo": {"values": ["2"]}}}})
    if repayment == "7":
        with pytest.raises(ValueError, match="REPAYMENT_BELOW_CONTRACTUAL_FLOOR:2027"):
            staged_financing_request_v1(**kwargs)
        return
    result = json.loads(staged_financing_request_v1(**kwargs).user)
    row, = result["forecast_closing_debt_after_annual_years"]["annual_path"]
    assert row == dict(year=2027, closing_debt_cny="8", disclosed_unsettled_maturities_cny="8",
                       other_forecast_principal_payments_cny="4", forecast_interest_outside_cfo_cny="2",
                       undated_outstanding_principal_cny=None)
