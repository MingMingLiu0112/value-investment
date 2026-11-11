"""TEST_ONLY 2027 cash durability checks."""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import os
import shutil
from types import SimpleNamespace

import pytest

from test_operating_horizon_split_v8 import split_context, _annual, _cash, SOURCE
from test_operating_horizon_draft_v1 import context as base_context
from value_investment_agent.application.research.agent_review import operating_horizon_task_v10_live as mod
from value_investment_agent.infrastructure.agent_runtime.provider import LLMResponse

NOW = datetime(2026, 11, 12, 12, tzinfo=timezone.utc)


@pytest.fixture
def task(tmp_path_factory, split_context, monkeypatch):
    tmp_path = tmp_path_factory.mktemp("v")
    def link(source, target):
        with open(source, "rb") as incoming, open(target, "xb") as outgoing:
            shutil.copyfileobj(incoming, outgoing)
    monkeypatch.setattr(os, "link", link)
    monkeypatch.setattr(mod, "_now", lambda value=None: value or NOW)
    source = deepcopy(split_context)
    source.update(source_binding=SOURCE, snapshot_fingerprint="f" * 64,
                  schema_version=mod.official.VERSION, action="no_order",
                  formal_eligibility=False, as_of="2026-11-11T22:00:00+08:00")
    def loader(*, root, symbol, now, binding=None):
        if symbol != "600519" or binding not in (None, SOURCE):
            raise ValueError("TEST_SOURCE_CHANGED")
        return deepcopy(source)
    cfg = dict(endpoint="https://test-only.invalid/v1/chat/completions", model_id="TEST_ONLY",
        api_key_env="VALUE_AGENT_TEST_ONLY_KEY", timeout_seconds=1, max_completion_tokens_cap=4096,
        max_run_cost="10", input_cost_per_million="1", output_cost_per_million="2",
        authorized=True, authorization_reference="TEST_ONLY", currency="CNY", daily_cost_limit="10")
    path = tmp_path / mod.live.CONFIG
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(mod._bytes(cfg))
    calls = []
    def complete(request):
        calls.append(request)
        return LLMResponse(_annual() if len(calls) == 1 else _cash(), 100, 50, "TEST_ONLY")
    service = mod.OperatingHorizonTaskService(tmp_path, source_loader=loader,
        source_loader_version="TEST_ONLY_OFFICIAL_2027", test_provider=SimpleNamespace(complete=complete))
    return service, source, calls


def test_cash_stage_and_duplicate_intent(task):
    service, _, calls = task
    queued = service.create(symbol="600519", request_key="TEST_V10_CASH", years=[2027], now=NOW)
    result = service.run(queued["task_id"], now=NOW)
    assert result["status"] in {"SUCCEEDED", "WAITING_EVIDENCE"}
    assert result["cash_status"] == "SETTLED_VALIDATED"
    assert len(calls) == 2
    assert set(result["stage_responses"]) == {"annual", "cash"}
    assert result["cash_binding"]["year"] == "2027"
    assert result["action"] == "no_order"
    assert service.read(queued["task_id"])["status"] == result["status"]
    assert service.run(queued["task_id"], now=NOW)["provider_requests"] == 2
    assert len(calls) == 2


def test_source_and_response_tamper(task):
    service, source, calls = task
    queued = service.create(symbol="600519", request_key="TEST_V10_TAMPER", years=[2027], now=NOW)
    service.run(queued["task_id"], now=NOW)
    source["snapshot_fingerprint"] = "a" * 64
    assert service.read(queued["task_id"])["status"] == "FAILED"
    source["snapshot_fingerprint"] = "f" * 64
    packet = service._directory(queued["task_id"]) / "response-cash.json"
    packet.write_text("{}", encoding="utf-8")
    assert service.read(queued["task_id"])["status"] == "FAILED"
    assert len(calls) == 2


def test_missing_cash_and_cancellation(task):
    service, _, calls = task
    queued = service.create(symbol="600519", request_key="TEST_V10_MISSING", years=[2027], now=NOW)
    spec, state, _ = service._load(queued["task_id"])
    assert service._result(spec, state, service._context(spec)) is None
    assert service.cancel(queued["task_id"], now=NOW)["status"] == "CANCELLED"
    service.run(queued["task_id"], now=NOW)
    assert calls == []


def test_cash_intent_is_never_repeated_after_provider_timeout(task):
    service, _, calls = task
    original = service.test_provider.complete
    def timeout_on_cash(request):
        if len(calls) == 1:
            calls.append(request)
            raise TimeoutError("TEST_ONLY cash interruption")
        return original(request)
    service.test_provider.complete = timeout_on_cash
    queued = service.create(symbol="600519", request_key="TEST_V10_TIMEOUT", years=[2027], now=NOW)
    failed = service.run(queued["task_id"], now=NOW)
    assert failed["status"] == "FAILED"
    assert failed["cash_status"] == "AMBIGUOUS_CALL_NO_RETRY"
    assert service.resume(queued["task_id"], now=NOW)["status"] == "FAILED"
    assert len(calls) == 2


def test_second_stage_run_budget_stops_before_cash_call(task, monkeypatch):
    service, _, calls = task
    monkeypatch.setattr(service, "_cost", lambda *args: Decimal("6"))
    queued = service.create(symbol="600519", request_key="TEST_V10_BUDGET", years=[2027], now=NOW)
    failed = service.run(queued["task_id"], now=NOW)
    assert failed["status"] == "FAILED"
    assert failed["cash_status"] == "PENDING"
    assert len(calls) == 1


def test_unknown_cash_does_not_become_capacity(task):
    service, _, calls = task
    original = service.test_provider.complete
    def unknown_on_cash(request):
        if len(calls) == 1:
            calls.append(request)
            return LLMResponse(_cash(unknown=True), 100, 50, "TEST_ONLY")
        return original(request)
    service.test_provider.complete = unknown_on_cash
    queued = service.create(symbol="600519", request_key="TEST_V10_UNKNOWN", years=[2027], now=NOW)
    result = service.run(queued["task_id"], now=NOW)
    assert result["action"] == "no_order"
    assert result["formal_eligibility"] is False
    assert result["condition_price"] is None
    assert len(calls) == 2


def test_live_preflight_requires_exact_model_and_credential(task, monkeypatch):
    service, _, calls = task
    live_service = mod.OperatingHorizonTaskService(service.root,
        source_loader=service.source_loader,
        source_loader_version=service.source_loader_version)
    with pytest.raises(PermissionError, match="V10_EXACT_MODEL_REQUIRED"):
        live_service.create(symbol="600519", request_key="TEST_V10_PREFLIGHT", years=[2027], now=NOW)
    cfg_path = service.root / mod.live.CONFIG
    cfg = mod.live.model_configuration(service.root)
    cfg["model_id"] = "deepseek-flash"
    cfg_path.write_bytes(mod._bytes(cfg))
    monkeypatch.delenv(cfg["api_key_env"], raising=False)
    with pytest.raises(PermissionError, match="MODEL_CREDENTIAL_REQUIRED"):
        live_service.create(symbol="600519", request_key="TEST_V10_PREFLIGHT", years=[2027], now=NOW)
    assert calls == []
    assert not live_service.base.exists()


def test_live_create_and_shared_budget_rejection_never_call_provider(task, monkeypatch):
    service, _, calls = task
    cfg_path = service.root / mod.live.CONFIG
    cfg = mod.live.model_configuration(service.root)
    cfg["model_id"] = "deepseek-flash"
    cfg_path.write_bytes(mod._bytes(cfg))
    monkeypatch.setenv(cfg["api_key_env"], "offline-test-placeholder")
    live_service = mod.OperatingHorizonTaskService(service.root,
        source_loader=service.source_loader,
        source_loader_version=service.source_loader_version)
    queued = live_service.create(symbol="600519", request_key="TEST_V10_LIVE", years=[2027], now=NOW)
    assert queued["execution_mode"] == "LIVE_OPERATING"
    assert queued["action"] == "no_order"
    provider_calls = []
    monkeypatch.setattr(live_service, "_provider", lambda spec: SimpleNamespace(
        complete=lambda request: provider_calls.append(request)))
    def exhausted(*args, **kwargs):
        raise ValueError("DAILY_BUDGET_EXHAUSTED_BEFORE_CALL")
    monkeypatch.setattr(live_service, "_daily_budget", exhausted)
    failed = live_service.run(queued["task_id"], now=NOW)
    assert failed["status"] == "FAILED"
    assert failed["annual_status"] == "AMBIGUOUS_CALL_NO_RETRY"
    assert live_service.resume(queued["task_id"], now=NOW)["status"] == "FAILED"
    assert provider_calls == calls == []

