"""TEST_ONLY request boundary; no model service or paid calls."""
import json
from datetime import datetime, timezone

import pytest

from value_investment_agent.application.research import direct_owner_cash_agent_request_v1 as target
from value_investment_agent.infrastructure.agent_runtime.provider import LLMResponse


def test_source_only_request_excludes_old_forecast(monkeypatch, tmp_path):
    context = dict(symbol="600887", valuation_date="2025-12-31",
        input_fingerprint="a" * 64, facts={"profit": {"value_cny": "100"}},
        unresolved=["TEST_ONLY debt schedule unknown"], action="no_order",
        formal_eligibility=False, forecast_scenarios_present=False)
    monkeypatch.setattr(target, "read_parent_cash_agent_facts", lambda **kw: context)
    request = target.parent_cash_request(root=tmp_path, spec_binding={},
        scenario="bear", generated_at=datetime.now(timezone.utc))
    payload = json.loads(request.user)
    assert payload["source_context"]["facts"]["profit"]["value_cny"] == "100"
    assert payload["source_context"]["forecast_scenarios_present"] is False
    assert "scenarios" not in payload["source_context"]
    assert payload["required_years"] == list(range(2026, 2036))
    assert request.output_schema["properties"]["scenario"]["const"] == "bear"
    assert request.output_schema["properties"]["series"]["required"]


@pytest.mark.parametrize("raw,code", [
    ('{', "INVALID_JSON"),
    ('{"scenario":"bear","scenario":"bull"}', "DUPLICATE_JSON_KEY"),
    ('{"schema_version":"wrong","scenario":"bear","source_fingerprint":"x"}',
     "RESPONSE_BINDING_INVALID"),
])
def test_response_rejects_invalid_or_unbound_json(raw, code):
    response = LLMResponse(text=raw, prompt_tokens=1, completion_tokens=1,
                           model_id="TEST_ONLY")
    with pytest.raises(ValueError, match=code):
        target.parse_parent_cash_response(response, scenario="bear",
                                          source_fingerprint="a" * 64)


def test_tool_call_is_rejected():
    response = LLMResponse(text="{}", prompt_tokens=1, completion_tokens=1,
                           model_id="TEST_ONLY", tool_calls=1)
    with pytest.raises(ValueError, match="UNAUTHORIZED_TOOL"):
        target.parse_parent_cash_response(response, scenario="bear",
                                          source_fingerprint="a" * 64)
