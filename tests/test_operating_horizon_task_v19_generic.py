"""TEST_ONLY durable generic task, with no paid provider."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
import shutil
from decimal import Decimal
from types import SimpleNamespace

import pytest

from test_operating_horizon_draft_v1 import context as base_context
from test_operating_horizon_annual_v3 import paired
from test_operating_horizon_split_v8 import _annual, _cash
from value_investment_agent.application.research.agent_review import operating_horizon_task_v19_generic as task
from value_investment_agent.application.research.operating_horizon_cash_policy_e2_v11 import read_v19_cash_policy_e2_input
from value_investment_agent.infrastructure.agent_runtime.provider import LLMResponse

NOW = datetime(2026, 11, 12, 12, tzinfo=timezone.utc)
PIN = {"path": "TEST_ONLY/600887-source.json", "sha256": "c" * 64}


@pytest.fixture
def setup(tmp_path, base_context, monkeypatch):
    old_link = os.link
    def link(source, target):
        with open(source, "rb") as incoming, open(target, "xb") as outgoing:
            shutil.copyfileobj(incoming, outgoing)
    monkeypatch.setattr(os, "link", link)
    monkeypatch.setattr(task, "_now", lambda value=None: value or NOW)
    source = deepcopy(paired.__wrapped__(base_context))
    source.update(symbol="600887", schema_version="operating-horizon-sources-v1",
        source_binding=PIN, snapshot_fingerprint="f" * 64,
        as_of="2026-11-11T22:00:00+08:00", action="no_order", formal_eligibility=False)
    for row in source["evidence"]:
        if "field" in row and "value" in row:
            row.setdefault("kind", "VERIFIED_REPORTED_FACT")
            row.setdefault("physical_page", 2)
    for row in list(source["evidence"]):
        if row.get("field") != "pre_tax_profit" or row.get("scope") != "consolidated":
            continue
        for field, ratio, scope in (("tax", ".2", "consolidated"),
                                     ("parent_profit", ".7", "consolidated_parent")):
            if any(item.get("field") == field and item.get("period") == row["period"]
                   for item in source["evidence"]):
                continue
            source["evidence"].append(dict(row, id="TEST_ONLY:" + field + ":" + row["period"],
                field=field, scope=scope,
                value=str(Decimal(row["value"]) * Decimal(ratio))))
    def loader(*, root, symbol, now, binding=None):
        if symbol != "600887" or binding not in (None, PIN):
            raise ValueError("TEST_SOURCE_CHANGED")
        return deepcopy(source)
    config = dict(endpoint="https://test-only.invalid/v1/chat/completions", model_id="TEST_ONLY",
        api_key_env="VALUE_AGENT_TEST_ONLY_KEY", timeout_seconds=1,
        max_completion_tokens_cap=4096, max_run_cost="10", input_cost_per_million="0.01",
        output_cost_per_million="0.02", authorized=True, authorization_reference="TEST_ONLY",
        currency="CNY", daily_cost_limit="10")
    path = tmp_path / task.live.CONFIG
    path.parent.mkdir(parents=True)
    path.write_bytes(task._bytes(config))
    calls = []
    def complete(request):
        calls.append(request)
        return LLMResponse(_annual() if len(calls) == 1 else _cash(unknown=True),
                           100, 50, "TEST_ONLY")
    service = task.OperatingHorizonTaskService(tmp_path, source_loader=loader,
        source_loader_version="TEST_ONLY_GENERIC_SOURCE", test_provider=SimpleNamespace(complete=complete))
    return service, source, calls


def test_incomplete_and_replay(setup):
    service, _, calls = setup
    queued = service.create(symbol="600887", request_key="TEST_V19_VALID", years=[2027], now=NOW)
    result = service.run(queued["task_id"], now=NOW)
    assert result["status"] == "WAITING_EVIDENCE", result
    assert result["research_result"]["reason"] == "CASH_POLICY_INCOMPLETE"
    assert result["action"] == "no_order" and result["formal_eligibility"] is False
    assert result["provider_requests"] == len(calls) == 2
    assert service.read(queued["task_id"])["status"] == "WAITING_EVIDENCE"
    assert service.resume(queued["task_id"], now=NOW)["provider_requests"] == 2


def test_cancel_before_provider(setup):
    service, _, calls = setup
    queued = service.create(symbol="600887", request_key="TEST_V19_CANCEL", years=[2027], now=NOW)
    assert service.cancel(queued["task_id"], now=NOW)["status"] == "CANCELLED"
    assert service.run(queued["task_id"], now=NOW)["status"] == "CANCELLED"
    assert calls == []


def test_ambiguous_provider_never_retried(setup):
    service, _, calls = setup
    def interrupted(request):
        calls.append(request)
        raise TimeoutError("TEST_ONLY interruption")
    service.test_provider.complete = interrupted
    queued = service.create(symbol="600887", request_key="TEST_V19_RECOVERY", years=[2027], now=NOW)
    result = service.run(queued["task_id"], now=NOW)
    assert result["status"] == "FAILED"
    assert result["provider_requests"] == len(calls) == 1
    assert service.resume(queued["task_id"], now=NOW)["provider_requests"] == 1
    assert len(calls) == 1


def test_cash_interruption_preserves_annual_and_never_retries(setup):
    service, _, calls = setup
    def interrupted(request):
        calls.append(request)
        if len(calls) == 2:
            raise TimeoutError("TEST_ONLY cash interruption")
        return LLMResponse(_annual(), 100, 50, "TEST_ONLY")
    service.test_provider.complete = interrupted
    queued = service.create(symbol="600887", request_key="TEST_V19_CASH_INTERRUPTED", years=[2027], now=NOW)
    result = service.run(queued["task_id"], now=NOW)
    assert result["status"] == "FAILED"
    assert result["stage_validated"] == ["annual"]
    assert set(result["stage_intents"]) == {"annual", "cash"}
    assert set(result["stage_responses"]) == {"annual"}
    assert result["provider_requests"] == len(calls) == 2
    assert service.resume(queued["task_id"], now=NOW)["provider_requests"] == 2
    assert len(calls) == 2


def test_exact_source_reloaded(setup):
    service, source, calls = setup
    queued = service.create(symbol="600887", request_key="TEST_V19_SOURCE", years=[2027], now=NOW)
    source["evidence"][0]["text"] += " changed"
    with pytest.raises(ValueError, match="V19_SOURCE_CHANGED"):
        service.read(queued["task_id"])
    assert calls == []


def test_complete_cash_path(setup):
    service, source, calls = setup
    from value_investment_agent.application.research.agent_review import operating_horizon_sources_v1 as generic_sources
    service.source_loader_version = generic_sources.VERSION
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
    from value_investment_agent.application.research.agent_review import operating_cash_policy_draft_v16_generic as draft
    anchors = draft.candidates(source, PIN)
    for path in payload["years"]["2027"]["shareholder_cash_paths"].values():
        for name, term in path.items():
            if name in anchors and term["classification"] != "UNKNOWN":
                term["evidence_ids"] = anchors[name][:1]
            elif isinstance(term, dict) and not term.get("evidence_ids"):
                term["evidence_ids"] = [source["evidence"][0]["id"]]
    def complete(request):
        calls.append(request)
        return LLMResponse(_annual() if len(calls) == 1 else json.dumps(payload),
                           100, 50, "TEST_ONLY")
    service.test_provider.complete = complete
    queued = service.create(symbol="600887", request_key="TEST_V19_COMPLETE", years=[2027], now=NOW)
    result = service.run(queued["task_id"], now=NOW)
    assert result["status"] == "SUCCEEDED", result
    assert result["research_result"]["action"] == "no_order"
    assert result["research_result"]["formal_eligibility"] is False
    assert result["provider_requests"] == len(calls) == 2
    handoff = read_v19_cash_policy_e2_input(root=service.root,
        task_id=queued["task_id"], now=NOW, service=service)
    assert handoff["status"] == "TEST_ONLY_E2_CONTRACT_REPLAY"
    assert handoff["action"] == "no_order" and handoff["formal_eligibility"] is False
    assert handoff["input_manifest"]["source_kind_projection"]["evidence_ids"]


def test_existing_d1_budget_blocks_new_v19_provider(setup):
    service, _, calls = setup
    day = NOW.date().isoformat()
    cfg = service._configuration()
    legacy = task.live.LiveOperatingTaskService(service.root)
    assert service._budget_service.base == legacy.base
    legacy._daily_budget(day, "TEST_ONLY_EXISTING_D1_RESERVATION", Decimal("10"), cfg)
    queued = service.create(symbol="600887", request_key="TEST_V19_SHARED_BUDGET", years=[2027], now=NOW)
    result = service.run(queued["task_id"], now=NOW)
    assert result["status"] == "FAILED"
    assert result["provider_requests"] == 0
    assert result["error_code"] == "V19_TASK_EXECUTION_FAILED"
    assert calls == []


def test_live_budget_uses_explicit_shared_root_without_model_call(tmp_path, monkeypatch):
    def loader(*, root, symbol, now, binding=None):
        raise AssertionError("NO_SOURCE_OR_PROVIDER_CALL_EXPECTED")
    code_root = tmp_path / "code"
    shared_root = tmp_path / "shared"
    code_root.mkdir()
    config_path = shared_root / task.live.CONFIG
    config_path.parent.mkdir(parents=True)
    config = dict(endpoint="https://test-only.invalid/v1/chat/completions",
        model_id="deepseek-flash", api_key_env="VALUE_AGENT_TEST_ONLY_KEY",
        timeout_seconds=1, max_completion_tokens_cap=4096,
        max_run_cost="10", input_cost_per_million="0.01",
        output_cost_per_million="0.02", authorized=True,
        authorization_reference="TEST_ONLY_NO_LIVE_CALL", currency="CNY",
        daily_cost_limit="10")
    config_path.write_bytes(task._bytes(config))
    monkeypatch.delenv("VALUE_AGENT_SHARED_RESEARCH_ROOT", raising=False)
    service = task.OperatingHorizonTaskService(code_root, source_loader=loader,
        source_loader_version="TEST_ONLY_SOURCE")
    with pytest.raises(PermissionError, match="V19_SHARED_BUDGET_ROOT_REQUIRED"):
        service._configuration()
    monkeypatch.setenv("VALUE_AGENT_SHARED_RESEARCH_ROOT", str(shared_root))
    service = task.OperatingHorizonTaskService(code_root, source_loader=loader,
        source_loader_version="TEST_ONLY_SOURCE")
    cfg = service._configuration()
    assert cfg["model_id"] == "deepseek-flash"
    service._daily_budget("2026-11-12", "TEST_ONLY_SHARED_RESERVATION", Decimal("10"), cfg)
    existing = task.live.LiveOperatingTaskService(shared_root)
    with pytest.raises(ValueError, match="DAILY_BUDGET_EXHAUSTED_BEFORE_CALL"):
        existing._daily_budget("2026-11-12", "TEST_ONLY_NEXT_RESERVATION", Decimal(".01"), cfg)
