"""The compact D2 cash-policy follow-up remains source bound and no-order."""
from types import SimpleNamespace
from datetime import datetime, timezone
import json
import pytest

import test_operating_horizon_task_v2 as v2_tests
from test_operating_horizon_sources_v1 import source_env
from test_operating_horizon_draft_v1 import NOW, context
from test_operating_horizon_draft_v3 import payload
from value_investment_agent.application.research.agent_review import operating_cash_policy_task_v1 as mod
from value_investment_agent.application.research import operating_horizon_cash_policy_e2_v1 as e2
from value_investment_agent.infrastructure.agent_runtime.provider import LLMResponse


def test_policy_only_task_uses_existing_source_task_engine(source_env, monkeypatch):
    base = v2_tests.env.__wrapped__(source_env, monkeypatch)
    monkeypatch.setattr(mod, "_now", lambda value=None: value or NOW)
    accepted = payload()["years"]
    response = {"years": {"2026": {"shareholder_cash_paths":
        accepted["2026"]["shareholder_cash_paths"]}}}
    calls = []
    provider = SimpleNamespace(complete=lambda request: (
        calls.append(request) or LLMResponse(json.dumps(response), 100, 50, "TEST_ONLY")))
    service = mod.OperatingCashPolicyTaskService(base.root, test_provider=provider)
    task = service.create(symbol="123456", request_key="TEST_POLICY_ONLY", years=[2026])
    result = service.run(task["task_id"])
    assert result["status"] == "SUCCEEDED", result
    assert result["research_result"]["cash_policy_appendix_status"] == "COMPLETE_UNAPPROVED"
    assert result["scope"] == "SOURCE_BOUND_CASH_POLICY_ONLY_NOT_VALUATION_OR_PRICE"
    assert result["action"] == "no_order" and result["formal_eligibility"] is False
    assert len(calls) == 1 and "Do not repeat operating forecasts" in calls[0].system
    assert "need not be an issuer-announced forward policy" in calls[0].system
    assert "UNKNOWN is required when even a conditional bound lacks an economic mechanism" in calls[0].system
    assert "FORECAST_ASSUMPTION" in calls[0].system
    assert "historical evidence anchors" in calls[0].transport_output_contract
    assert "1-240 characters" in calls[0].transport_output_contract
    assert calls[0].max_completion_tokens == 4096
    handoff = e2.read_d2_cash_policy_e2_input(root=base.root, task_id=task["task_id"], now=datetime.now(timezone.utc),
        service=service)
    assert handoff["status"] == "SOURCE_BOUND_D2_V4_CASH_POLICY_READY_FOR_E2"
    assert handoff["input_manifest"]["task_contract"] == mod.CONTRACT


def test_cash_policy_exact_one_extra_brace_uses_verified_transport_view(source_env, monkeypatch):
    base = v2_tests.env.__wrapped__(source_env, monkeypatch)
    monkeypatch.setattr(mod, "_now", lambda value=None: value or NOW)
    response = {"years": {"2026": {"shareholder_cash_paths":
        payload()["years"]["2026"]["shareholder_cash_paths"]}}}
    calls = []
    provider = SimpleNamespace(complete=lambda request: (
        calls.append(request) or LLMResponse(json.dumps(response) + "}", 100, 50, "TEST_ONLY")))
    service = mod.OperatingCashPolicyTaskService(base.root, test_provider=provider)
    task = service.create(symbol="123456", request_key="TEST_POLICY_ONE_BRACE", years=[2026])
    result = service.run(task["task_id"])
    assert result["status"] == "SUCCEEDED", result
    assert result["research_result"]["cash_policy_appendix_status"] == "COMPLETE_UNAPPROVED"
    assert result["response_binding"] != result["normalized_response_binding"]
    assert service._bound(result["response_binding"])["response"]["text"].endswith("}}")
    assert service.read(task["task_id"])["research_result"] == result["research_result"]
    assert len(calls) == 1 and result["action"] == "no_order"


def test_new_request_key_cannot_repeat_paid_incomplete_research(source_env, monkeypatch):
    base = v2_tests.env.__wrapped__(source_env, monkeypatch)
    monkeypatch.setattr(mod, "_now", lambda value=None: value or NOW)
    response = {"years": {"2026": {"shareholder_cash_paths":
        payload()["years"]["2026"]["shareholder_cash_paths"]}}}
    response["years"]["2026"]["shareholder_cash_paths"]["base"]["reserve_ratio"] = {
        "classification": "UNKNOWN", "value": None, "unit": "not_quantified",
        "rationale": "Source does not establish future reserve needs.",
        "evidence_ids": ["test:pre_tax_profit"],
    }
    calls = []
    provider = SimpleNamespace(complete=lambda request: (
        calls.append(request) or LLMResponse(json.dumps(response), 100, 50, "TEST_ONLY")))
    service = mod.OperatingCashPolicyTaskService(base.root, test_provider=provider)
    first = service.create(symbol="123456", request_key="INCOMPLETE_FIRST", years=[2026])
    assert service.run(first["task_id"])["research_result"]["cash_policy_appendix_status"] == "INCOMPLETE_UNKNOWN_TERMS"
    with pytest.raises(PermissionError, match="CASH_POLICY_UNCHANGED_SOURCE_ALREADY_RESEARCHED"):
        service.create(symbol="123456", request_key="INCOMPLETE_SECOND", years=[2026])
    assert len(calls) == 1


def test_policy_only_task_rejects_missing_policy_segment(source_env, monkeypatch):
    base = v2_tests.env.__wrapped__(source_env, monkeypatch)
    monkeypatch.setattr(mod, "_now", lambda value=None: value or NOW)
    provider = SimpleNamespace(complete=lambda request: LLMResponse('{"years":{"2026":{}}}', 100, 50, "TEST_ONLY"))
    service = mod.OperatingCashPolicyTaskService(base.root, test_provider=provider)
    task = service.create(symbol="123456", request_key="TEST_POLICY_MISSING", years=[2026])
    result = service.run(task["task_id"])
    assert result["status"] == "FAILED"
    assert result["error_code"] == "HORIZON_EXACT_FIELDS_REQUIRED"


def test_same_model_and_source_cannot_repeat_a_schema_failure(source_env, monkeypatch):
    base = v2_tests.env.__wrapped__(source_env, monkeypatch)
    monkeypatch.setattr(mod, "_now", lambda value=None: value or NOW)
    provider = SimpleNamespace(complete=lambda request: LLMResponse('{"years":{"2026":{}}}', 100, 50, "TEST_ONLY"))
    service = mod.OperatingCashPolicyTaskService(base.root, test_provider=provider)
    failed = service.create(symbol="123456", request_key="TEST_POLICY_FAIL_ONCE", years=[2026])
    assert service.run(failed["task_id"])["status"] == "FAILED"
    with pytest.raises(PermissionError, match="CASH_POLICY_PROVIDER_SCHEMA_FAILURE"):
        service.create(symbol="123456", request_key="TEST_POLICY_FAIL_TWICE", years=[2026])


def test_explicitly_changed_authorization_allows_one_new_schema_retry(source_env, monkeypatch):
    base = v2_tests.env.__wrapped__(source_env, monkeypatch)
    monkeypatch.setattr(mod, "_now", lambda value=None: value or NOW)
    provider = SimpleNamespace(complete=lambda request: LLMResponse(
        '{"years":{"2026":{}}}', 100, 50, "TEST_ONLY"))
    service = mod.OperatingCashPolicyTaskService(base.root, test_provider=provider)
    failed = service.create(symbol="123456", request_key="TEST_POLICY_AUTH_FAIL", years=[2026])
    assert service.run(failed["task_id"])["status"] == "FAILED"
    config = base.root / "config" / "agent-research-provider.local.json"
    value = json.loads(config.read_text(encoding="utf-8"))
    value["authorization_reference"] += " Retry separately authorized."
    config.write_text(json.dumps(value), encoding="utf-8")
    retry = service.create(symbol="123456", request_key="TEST_POLICY_AUTH_RETRY", years=[2026])
    assert retry["status"] == "QUEUED"
