import json

import pytest

from value_investment_agent.application.research.agent_review.parent_cash_financing_wire import (
    FINANCING_FIELDS, conditional_no_refinance_terms, financing_policy_request,
    merge_financing_policy_response,
)
from value_investment_agent.infrastructure.agent_runtime.provider import LLMRequest, LLMResponse


def test_no_refinance_rolls_principal_to_zero_and_separates_interest():
    schedule = {"period_end": "2026-09-30",
        "reported_ytd_cny": {"borrowings_received_cny": "100", "debt_repayments_paid_cny": "80"},
        "later_issuance_proceeds_at_issue_price_cny": "40",
        "scheduled_face_principal_by_maturity_cny": {"2026-12-30": "30", "2027-11-12": "20"}}
    calendar = {"issues": [{"maturity": "2026-12-30", "conditional_act365_cash_cny": "2"},
                            {"maturity": "2027-11-12", "conditional_act365_cash_cny": "1"}]}
    kwargs = dict(years=[2026, 2027, 2028], opening_principal="20", schedule=schedule,
                  calendar=calendar, paid_interest={"year": 2026, "minimum_cny": "3"},
                  residual_stress_rate="0.03", anchors=["cash"])
    terms = conditional_no_refinance_terms(**kwargs)
    assert terms["new_borrowing"]["values"] == ["140.00", "0.00", "0.00"]
    assert terms["debt_repayment"]["values"] == ["110.00", "50.00", "0.00"]
    assert terms["interest_outside_cfo"]["values"] == ["5.90", "1.90", "0.00"]
    schedule["scheduled_face_principal_by_maturity_cny"]["2028-01-01"] = "1"
    with pytest.raises(ValueError, match="NO_REFINANCE_WINDOW_UNSUPPORTED"):
        conditional_no_refinance_terms(**kwargs)


def test_policy_contract_keeps_financing_outside_provider_response():
    terms = {field: {"values": ["10"]} for field in FINANCING_FIELDS}
    fields = sorted(FINANCING_FIELDS | {"parent_profit"})
    request = LLMRequest(role="FUNDAMENTAL", system="test",
        user=json.dumps({"stage": "policy", "required_fields": fields,
                         "required_years": [2026], "source_context": {"facts": {"cash": {}}}}),
        output_schema={"properties": {"series": {"required": fields,
            "properties": {name: {} for name in fields}}}}, max_completion_tokens=1024)
    wire = financing_policy_request(request, terms)
    assert wire.output_schema["properties"]["series"]["required"] == ["parent_profit"]
    assert request.output_schema["properties"]["series"]["required"] == fields
    payload = {"years": [2026], "series": {"parent_profit": {"values": ["15"]}}}
    raw = LLMResponse(json.dumps(payload), 100, 100, "deepseek-flash")
    merged = merge_financing_policy_response(raw, wire)
    assert json.loads(merged.text)["series"] == {**payload["series"], **terms}
    assert json.loads(raw.text) == payload
    payload["series"]["new_borrowing"] = terms["new_borrowing"]
    with pytest.raises(ValueError, match="FINANCING_WIRE_RESPONSE_INVALID"):
        merge_financing_policy_response(LLMResponse(json.dumps(payload), 100, 100,
                                                    "deepseek-flash"), wire)
