"""TEST_ONLY transport checks; no external model or financial approval."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from decimal import Decimal

import pytest

from test_operating_horizon_task_v19_generic import setup as v19_setup
from test_operating_horizon_draft_v1 import context as base_context
from test_operating_horizon_split_v8 import _annual, _cash
from value_investment_agent.application.research.agent_review import operating_horizon_task_v20_staged as task
from value_investment_agent.application.research.operating_horizon_cash_policy_e2_v12 import read_v20_cash_policy_e2_input
from value_investment_agent.infrastructure.agent_runtime.provider import LLMResponse

NOW = datetime(2026, 11, 12, 12, tzinfo=timezone.utc)


@pytest.fixture
def setup(v19_setup, monkeypatch):
    old, source, calls = v19_setup
    monkeypatch.setattr(task, "_now", lambda value=None: value or NOW)
    service = task.OperatingHorizonTaskService(old.root, source_loader=old.source_loader,
        source_loader_version=old.source_loader_version, test_provider=old.test_provider)
    whole = json.loads(_annual())
    def complete(request):
        calls.append(request)
        if len(calls) <= 3:
            scenario = task.SCENARIOS[len(calls) - 1]
            payload = deepcopy(whole)
            paths = payload["years"]["2027"]["operating_paths"]
            payload["years"]["2027"]["operating_paths"] = {scenario: paths[scenario]}
            return LLMResponse(json.dumps(payload), 100, 50, "TEST_ONLY")
        return LLMResponse(_cash(unknown=True), 100, 50, "TEST_ONLY")
    service.test_provider.complete = complete
    return service, source, calls


def test_three_scenarios_then_cash_durable_replay(setup):
    service, _, calls = setup
    created = service.create(symbol="600887", request_key="TEST_V20_STAGED", years=[2027], now=NOW)
    result = service.run(created["task_id"], now=NOW)
    assert result["status"] == "WAITING_EVIDENCE", result
    assert result["provider_requests"] == len(calls) == 4
    assert result["stage_validated"] == ["bear", "base", "bull", "cash"]
    assert result["annual_result"]["action"] == "no_order"
    assert result["formal_eligibility"] is False
    assert service.read(created["task_id"])["status"] == "WAITING_EVIDENCE"
    assert service.resume(created["task_id"], now=NOW)["provider_requests"] == 4


def test_malformed_scenario_is_sealed_and_never_retried(setup):
    service, _, calls = setup
    original = service.test_provider.complete
    def malformed(request):
        result = original(request)
        if len(calls) == 2:
            return LLMResponse(result.text + "}}}", 100, 50, "TEST_ONLY")
        return result
    service.test_provider.complete = malformed
    created = service.create(symbol="600887", request_key="TEST_V20_INVALID", years=[2027], now=NOW)
    result = service.run(created["task_id"], now=NOW)
    assert result["status"] == "FAILED"
    assert result["provider_requests"] == len(calls) == 2
    assert result["stage_validated"] == ["bear"]
    assert service.resume(created["task_id"], now=NOW)["provider_requests"] == 2


def test_cancel_before_provider(setup):
    service, _, calls = setup
    created = service.create(symbol="600887", request_key="TEST_V20_CANCEL", years=[2027], now=NOW)
    assert service.cancel(created["task_id"], now=NOW)["status"] == "CANCELLED"
    assert calls == []


def test_ambiguous_timeout_not_retried(setup):
    service, _, calls = setup
    def timeout(request):
        calls.append(request)
        raise TimeoutError("TEST_ONLY")
    service.test_provider.complete = timeout
    created = service.create(symbol="600887", request_key="TEST_V20_TIMEOUT", years=[2027], now=NOW)
    result = service.run(created["task_id"], now=NOW)
    assert result["status"] == "FAILED" and result["provider_requests"] == 1
    assert service.resume(created["task_id"], now=NOW)["provider_requests"] == 1


def test_incomplete_first_scenario_stops_before_next_call(setup):
    service, _, calls = setup
    def incomplete(request):
        calls.append(request)
        payload = json.loads(_annual())
        payload["years"]["2027"]["operating_paths"] = {}
        return LLMResponse(json.dumps(payload), 100, 50, "TEST_ONLY")
    service.test_provider.complete = incomplete
    created = service.create(symbol="600887", request_key="TEST_V20_INCOMPLETE", years=[2027], now=NOW)
    result = service.run(created["task_id"], now=NOW)
    assert result["status"] == "FAILED"
    assert result["provider_requests"] == len(calls) == 1
    assert result["stage_validated"] == []


def test_shared_budget_exhaustion_prevents_provider_call(setup):
    service, _, calls = setup
    cfg = service._configuration()
    service._daily_budget(NOW.date().isoformat(), "TEST_ONLY_OTHER_D1",
                          Decimal("10"), cfg)
    created = service.create(symbol="600887", request_key="TEST_V20_BUDGET", years=[2027], now=NOW)
    result = service.run(created["task_id"], now=NOW)
    assert result["status"] == "FAILED"
    assert result["provider_requests"] == 0 and calls == []


def test_source_change_rejects_replay(setup):
    service, source, calls = setup
    created = service.create(symbol="600887", request_key="TEST_V20_SOURCE", years=[2027], now=NOW)
    source["evidence"][0]["text"] += " changed"
    with pytest.raises(ValueError, match="V20_SOURCE_CHANGED"):
        service.read(created["task_id"])
    assert calls == []


def test_complete_staged_task_reaches_existing_e2_gate(setup):
    service, source, calls = setup
    from value_investment_agent.application.research.agent_review import operating_horizon_sources_v1 as sources
    from value_investment_agent.application.research.agent_review import operating_cash_policy_draft_v16_generic as draft
    service.source_loader_version = sources.VERSION
    for row in source["evidence"]:
        if row.get("kind") == "VERIFIED_REPORTED_FACT":
            row["kind"] = "SOURCE_BOUND_REPORTED_STATEMENT_ROW"
            row["source_id"] = "official:" + row["pdf_sha256"]
    source["evidence"].append(dict(source["evidence"][0], id="test:dividend",
        field="historical_dividend", text="TEST_ONLY dividend paid"))
    source["evidence"].append(dict(source["evidence"][0], id="test:cash-fields",
        field="historical_cash_policy",
        text="TEST_ONLY dividend parent CFO capex working capital commitment"))
    payload = json.loads(_cash())
    anchors = draft.candidates(source, source["source_binding"])
    for path in payload["years"]["2027"]["shareholder_cash_paths"].values():
        for name, term in path.items():
            if name in anchors and term["classification"] != "UNKNOWN":
                term["evidence_ids"] = anchors[name][:1]
            elif isinstance(term, dict) and not term.get("evidence_ids"):
                term["evidence_ids"] = [source["evidence"][0]["id"]]
    whole = json.loads(_annual())
    def complete(request):
        calls.append(request)
        if len(calls) <= 3:
            scenario = task.SCENARIOS[len(calls) - 1]
            row = deepcopy(whole)
            row["years"]["2027"]["operating_paths"] = {
                scenario: row["years"]["2027"]["operating_paths"][scenario]}
            return LLMResponse(json.dumps(row), 100, 50, "TEST_ONLY")
        return LLMResponse(json.dumps(payload), 100, 50, "TEST_ONLY")
    service.test_provider.complete = complete
    created = service.create(symbol="600887", request_key="TEST_V20_E2_COMPLETE", years=[2027], now=NOW)
    result = service.run(created["task_id"], now=NOW)
    assert result["status"] == "SUCCEEDED", result
    handoff = read_v20_cash_policy_e2_input(root=service.root,
        task_id=created["task_id"], now=NOW, service=service)
    assert handoff["status"] == "TEST_ONLY_E2_CONTRACT_REPLAY"
    assert set(handoff["input_manifest"]["stage_responses"]) == set(task.STAGES)
    assert handoff["input_manifest"]["source_kind_projection"]["evidence_ids"]
    assert handoff["action"] == "no_order" and handoff["formal_eligibility"] is False
