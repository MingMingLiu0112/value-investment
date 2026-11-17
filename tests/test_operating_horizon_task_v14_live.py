"""Offline V14 task/provider contract; no paid model calls."""
import json
from copy import deepcopy
from types import SimpleNamespace
import pytest

from test_operating_horizon_task_v10_live import task, NOW
from test_operating_horizon_split_v8 import split_context, _annual, _cash
from test_operating_horizon_draft_v1 import context as base_context
from value_investment_agent.application.research.agent_review import operating_horizon_task_v13_live as v13
from value_investment_agent.application.research.agent_review import operating_horizon_task_v14_live as v14
from value_investment_agent.infrastructure.agent_runtime.provider import LLMRequest, LLMResponse


def _service(task, cash_text=None):
    old, _, _ = task
    calls = []
    def complete(request):
        calls.append(request)
        if len(calls) == 1:
            data = json.loads(_annual())
            for path in data["years"]["2027"]["operating_paths"].values():
                path["unit_cost_case"]["mechanism"] = (
                    "采购价格随合同和原料市场变化而调整，单位成本可能变化，需持续核对同口径成本及采购披露。")
            return LLMResponse(json.dumps(data, ensure_ascii=False), 100, 5000, "TEST_ONLY")
        return LLMResponse(cash_text or _cash(unknown=True), 100, 50, "TEST_ONLY")
    return v14.OperatingHorizonTaskService(old.root,
        source_loader=old.source_loader, source_loader_version=old.source_loader_version,
        test_provider=SimpleNamespace(complete=complete)), calls


def test_v14_isolated_cash_request_and_unknown_result(task):
    service, calls = _service(task)
    queued = service.create(symbol="600519", request_key="TEST_V14_VALID", years=[2027], now=NOW)
    spec, _, _ = service._load(queued["task_id"])
    assert spec["task_contract"] == v14.CONTRACT
    assert service.base != v13.OperatingHorizonTaskService(service.root,
        source_loader=service.source_loader, source_loader_version=service.source_loader_version,
        test_provider=service.test_provider).base
    assert spec["config"]["model_id"] == "TEST_ONLY"
    assert spec["config"]["daily_cost_limit"] == spec["config"]["max_run_cost"] == "10"
    result = service.run(queued["task_id"], now=NOW)
    assert result["status"] in {"SUCCEEDED", "WAITING_EVIDENCE"}, result
    assert len(calls) == result["provider_requests"] == 2
    assert all(call.max_completion_tokens == 8192 for call in calls)
    assert v14.cash_v14.VERSION in calls[1].system
    assert result["action"] == "no_order" and result["formal_eligibility"] is False
    if result["status"] == "SUCCEEDED":
        assert result["research_result"]["cash_policy_v14"]["cash_policy_appendix_status"] == "INCOMPLETE_UNKNOWN_TERMS"
        assert result["research_result"]["cash_policy_v14"]["action"] == "no_order"
    assert service.read(queued["task_id"])["provider_requests"] == 2


def test_v14_rejects_cash_marker_after_settlement_without_retry(task):
    bad = json.loads(_cash(unknown=True))
    bad["years"]["2027"]["shareholder_cash_paths"]["base"]["target_payout_ratio"]["evidence_ids"] = ["test:marker"]
    service, calls = _service(task, json.dumps(bad))
    # The response must be sealed and settled before a strict rejection.
    queued = service.create(symbol="600519", request_key="TEST_V14_MARKER", years=[2027], now=NOW)
    result = service.run(queued["task_id"], now=NOW)
    assert result["status"] == "FAILED"
    assert result["error_code"] == "V14_CASH_RESPONSE_REJECTED"
    assert result["settled_cost"] != "0" and result["reserved_cost"] == "0"
    assert set(result["stage_responses"]) == {"annual", "cash"}
    assert service.resume(queued["task_id"], now=NOW)["provider_requests"] == len(calls) == 2


def test_v14_budget_blocks_provider_before_intent(task):
    service, calls = _service(task)
    path = service.root / v14.live.CONFIG
    cfg = json.loads(path.read_bytes())
    cfg["max_run_cost"] = "0.001"
    path.write_bytes(v14._bytes(cfg))
    queued = service.create(symbol="600519", request_key="TEST_V14_BUDGET", years=[2027], now=NOW)
    failed = service.run(queued["task_id"], now=NOW)
    assert failed["status"] == "FAILED"
    assert failed["error_code"] == "V14_TASK_EXECUTION_FAILED"
    assert failed["provider_requests"] == 0 and failed["stage_intents"] == {}
    assert calls == []


def test_v14_daily_cap_and_live_model_gate_prevent_paid_call(task):
    service, calls = _service(task)
    path = service.root / v14.live.CONFIG
    cfg = json.loads(path.read_bytes())
    cfg["daily_cost_limit"] = "0.001"
    path.write_bytes(v14._bytes(cfg))
    with pytest.raises(ValueError, match="TASK_LIMIT_EXCEEDS_DAILY_LIMIT"):
        service.create(symbol="600519", request_key="TEST_V14_DAILY", years=[2027], now=NOW)
    assert calls == []
    cfg["daily_cost_limit"] = "10"
    path.write_bytes(v14._bytes(cfg))
    live_service = v14.OperatingHorizonTaskService(service.root,
        source_loader=service.source_loader, source_loader_version=service.source_loader_version)
    with pytest.raises(PermissionError, match="EXACT_MODEL_REQUIRED"):
        live_service.create(symbol="600519", request_key="TEST_V14_LIVE", years=[2027], now=NOW)


def test_v14_imported_cash_is_distinct_and_pinned(task, monkeypatch):
    service, calls = _service(task)
    context = task[0].source_loader(root=service.root, symbol="600519", now=NOW)
    original = LLMRequest(role="cash", system="cash", user="pinned annual",
        output_schema={"type": "object"}, max_completion_tokens=8192)
    lineage = dict(action="no_order", source_task_id="rt-v12-source",
        source_record_binding={"path": "v12/current.json", "sha256": "a" * 64},
        source_binding=context["source_binding"], source_context_sha256="b" * 64,
        source_annual_response_sha256="c" * 64, source_budget_day="2026-11-12",
        source_annual_result_sha256="d" * 64, v13_cash_binding={"source": "v12"},
        v13_cash_request_sha256=v14._hash(v14._bytes(original.__dict__)))
    monkeypatch.setattr(v14.carryover, "replay_cash", lambda *args, **kwargs:
        (original, deepcopy(lineage), deepcopy(context), {"response": {}, "generated_at": NOW.isoformat()}))
    queued = service.create_imported(source_task_id=lineage["source_task_id"],
        request_key="TEST_V14_IMPORT", expected_source_binding=lineage["source_binding"],
        expected_context_sha256=lineage["source_context_sha256"],
        expected_annual_response_sha256=lineage["source_annual_response_sha256"],
        expected_budget_day=lineage["source_budget_day"], now=NOW)
    spec, state, _ = service._load(queued["task_id"])
    request, binding = service._request_for_stage(spec, state, context, "cash")
    assert spec["cash_request_sha256"] == v14._hash(v14._bytes(request.__dict__))
    assert spec["cash_request_sha256"] != lineage["v13_cash_request_sha256"]
    assert v14.cash_v14.VERSION in request.system
    assert binding == lineage["v13_cash_binding"]
    assert queued["provider_requests"] == 0 and calls == []
