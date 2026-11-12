"""TEST_ONLY V8 annual task lifecycle; no public call or cash admission."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
import shutil
from types import SimpleNamespace

import pytest

from test_operating_horizon_draft_v2 import context, valid
from value_investment_agent.application.research.agent_review import operating_horizon_task_v8_annual as mod
from value_investment_agent.application.research.agent_review import operating_horizon_task_v7_split as old
from value_investment_agent.infrastructure.agent_runtime.provider import LLMResponse

NOW = datetime(2026, 11, 11, 12, tzinfo=timezone.utc)


@pytest.fixture
def task(tmp_path, context, monkeypatch):
    def link(source, target):
        with open(source, "rb") as incoming, open(target, "xb") as outgoing:
            shutil.copyfileobj(incoming, outgoing)
    monkeypatch.setattr(os, "link", link)
    monkeypatch.setattr(mod, "_now", lambda value=None: value or NOW)
    context["symbol"] = "600519"
    context["as_of"] = "2026-11-11"
    context["evidence"] = [row for row in context["evidence"] if row["field"] not in {"revenue", "cost"}]
    for period, basis in (("2024-12-31", "FY"), ("2025-12-31", "FY"),
                          ("2025-06-30", "H1"), ("2026-06-30", "H1")):
        for field, value in (("revenue", "1000"), ("cost", "100")):
            context["evidence"].append(dict(id=(f"test:{field}" if period == "2025-12-31" else f"test:{period}:{field}"),
                source_id=f"test:{period}", pdf_sha256="b" * 64,
                available_at="2026-07-01T00:00:00+00:00", period=period,
                period_basis=basis, scope="consolidated", unit="CNY", field=field,
                value=value, text="TEST_ONLY statement row"))
    pin = dict(path="runtime/test-only-sealed.json", sha256="a" * 64)
    context["source_binding"] = pin
    def source_loader(*, root, symbol, now, binding=None):
        if symbol != "600519" or binding not in (None, pin):
            raise ValueError("TEST_ONLY_SOURCE_CHANGED")
        return deepcopy(context)
    cfg = dict(endpoint="https://test-only.invalid/v1/chat/completions", model_id="TEST_ONLY",
        api_key_env="VALUE_AGENT_TEST_ONLY_KEY", timeout_seconds=1, max_completion_tokens_cap=4096,
        max_run_cost="10", input_cost_per_million="1", output_cost_per_million="2",
        authorized=True, authorization_reference="TEST_ONLY", currency="CNY", daily_cost_limit="10")
    path = tmp_path / mod.live.CONFIG
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(mod._bytes(cfg))
    proposal = valid()
    for case in proposal["years"]["2026"]["operating_paths"].values():
        case["unit_cost_case"] = dict(mechanism="条件性投入价格下降，尚待采购合同确认",
            source_anchor_ids=["test:cost"], contrary_evidence_ids=["test:2026-06-30:cost"],
            reopen_condition="下期同口径营业成本率继续上升时重新估计")
    calls = []
    def complete(request):
        calls.append(request)
        return LLMResponse(json.dumps(proposal, ensure_ascii=False), 100, 50, "TEST_ONLY")
    service = mod.OperatingHorizonTaskService(tmp_path, source_loader=source_loader,
        source_loader_version="test-only-source-v8", test_provider=SimpleNamespace(complete=complete))
    return service, context, calls


def test_distinct_store_and_explicit_loader(task):
    service, _, calls = task
    assert service.base.name == mod.STORE != old.STORE
    assert mod.CONTRACT != old.CONTRACT
    with pytest.raises(ValueError, match="EXPLICIT_SOURCE_LOADER"):
        mod.OperatingHorizonTaskService(service.root, source_loader=None,
            source_loader_version="", test_provider=object())
    assert calls == []


def test_annual_settlement_replay_and_cash_stop(task):
    service, _, calls = task
    queued = service.create(symbol="600519", request_key="TEST_V8_ANNUAL", years=[2026], now=NOW)
    assert queued["status"] == "QUEUED" and queued["cash_status"] == "WAITING_FOR_CASH_V2"
    result = service.run(queued["task_id"], now=NOW)
    assert result["status"] == "WAITING_EVIDENCE"
    assert result["annual_status"] == "SETTLED_VALIDATED"
    assert result["research_result"] is None and result["condition_price"] is None
    assert result["annual_result"]["action"] == "no_order"
    assert result["new_llm_calls"] == 0 and len(calls) == 1
    assert service.read(queued["task_id"])["annual_result"] == result["annual_result"]
    assert service.run(queued["task_id"], now=NOW)["status"] == "WAITING_EVIDENCE"
    assert len(calls) == 1
    spec, state, _ = service._load(queued["task_id"])
    with pytest.raises(ValueError, match="CASH_V2_CONTRACT_REQUIRED"):
        service._request_for_stage(spec, state, service._context(spec), "cash")


def test_source_binding_change_fails_replay(task):
    service, source, _ = task
    queued = service.create(symbol="600519", request_key="TEST_V8_BINDING", years=[2026], now=NOW)
    source["snapshot_fingerprint"] = "c" * 64
    assert service.read(queued["task_id"])["status"] == "FAILED"


def test_response_binding_change_cannot_replay(task):
    service, _, calls = task
    queued = service.create(symbol="600519", request_key="TEST_V8_RESPONSE", years=[2026], now=NOW)
    service.run(queued["task_id"], now=NOW)
    response = service._directory(queued["task_id"]) / "response-annual.json"
    response.write_text("{}", encoding="utf-8")
    replay = service.read(queued["task_id"])
    assert replay["status"] == "FAILED" and replay["annual_result"] is None
    assert len(calls) == 1


def test_invalid_citation_after_return_keeps_settlement_and_never_retries(task):
    service, _, _ = task
    proposal = valid()
    for path in proposal["years"]["2026"]["operating_paths"].values():
        path["unit_cost_case"] = dict(mechanism="条件性投入价格下降，尚待采购合同确认",
            source_anchor_ids=["test:cost"], contrary_evidence_ids=["test:2026-06-30:cost"],
            reopen_condition="下期同口径营业成本率继续上升时重新估计")
    proposal["years"]["2026"]["operating_paths"]["bull"]["unit_cost_case"]["source_anchor_ids"] = ["fabricated"]
    calls = []
    def invalid_response(request):
        calls.append(request)
        return LLMResponse(json.dumps(proposal, ensure_ascii=False), 100, 50, "TEST_ONLY")
    service.test_provider.complete = invalid_response
    queued = service.create(symbol="600519", request_key="TEST_V8_BAD_CITE", years=[2026], now=NOW)
    failed = service.run(queued["task_id"], now=NOW)
    assert failed["status"] == "FAILED"
    assert failed["error_code"] == "V8_ANNUAL_RESPONSE_REJECTED"
    assert failed["annual_status"] == "RETURNED_UNVERIFIED"
    assert failed["research_result"] is None and failed["annual_result"] is None
    assert failed["stage_responses"]["annual"]
    assert next(iter(failed["reservations"].values()))["status"] == "SETTLED"
    assert service.read(queued["task_id"])["status"] == "FAILED"
    assert service.run(queued["task_id"], now=NOW)["status"] == "FAILED"
    assert len(calls) == 1


def test_provider_failure_is_persisted_as_ambiguous(task):
    service, _, _ = task
    calls = []
    def timeout(request):
        calls.append(request)
        raise TimeoutError("TEST_ONLY provider interruption")
    service.test_provider.complete = timeout
    queued = service.create(symbol="600519", request_key="TEST_V8_TIMEOUT", years=[2026], now=NOW)
    failed = service.run(queued["task_id"], now=NOW)
    assert failed["status"] == "FAILED"
    assert failed["error_code"] == "V8_ANNUAL_PROVIDER_AMBIGUOUS"
    assert failed["annual_status"] == "AMBIGUOUS_CALL_NO_RETRY"
    assert failed["stage_responses"] == {}
    assert service.resume(queued["task_id"], now=NOW)["status"] == "FAILED"
    assert len(calls) == 1
