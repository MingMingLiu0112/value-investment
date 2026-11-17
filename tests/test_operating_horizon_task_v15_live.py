"""Offline V15 task/provider contract; no paid model calls."""
import json
from copy import deepcopy
from types import SimpleNamespace
import pytest

from test_operating_horizon_task_v10_live import task, NOW
from test_operating_horizon_split_v8 import split_context, _annual, _cash
from test_operating_horizon_draft_v1 import context as base_context
from value_investment_agent.application.research.agent_review import operating_horizon_task_v13_live as v13
from value_investment_agent.application.research.agent_review import operating_horizon_task_v15_live as v15
from value_investment_agent.application.research.agent_review import operating_horizon_task_v12_live as v12
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
    return v15.OperatingHorizonTaskService(old.root,
        source_loader=old.source_loader, source_loader_version=old.source_loader_version,
        test_provider=SimpleNamespace(complete=complete)), calls


def test_v15_isolated_cash_request_and_unknown_result(task):
    service, calls = _service(task)
    queued = service.create(symbol="600519", request_key="TEST_V15_VALID", years=[2027], now=NOW)
    spec, _, _ = service._load(queued["task_id"])
    assert spec["task_contract"] == v15.CONTRACT
    assert service.base != v13.OperatingHorizonTaskService(service.root,
        source_loader=service.source_loader, source_loader_version=service.source_loader_version,
        test_provider=service.test_provider).base
    assert spec["config"]["model_id"] == "TEST_ONLY"
    assert spec["config"]["daily_cost_limit"] == spec["config"]["max_run_cost"] == "10"
    result = service.run(queued["task_id"], now=NOW)
    assert result["status"] in {"SUCCEEDED", "WAITING_EVIDENCE"}, result
    assert len(calls) == result["provider_requests"] == 2
    assert all(call.max_completion_tokens == 8192 for call in calls)
    assert v15.cash_v15.VERSION in calls[1].system
    assert result["action"] == "no_order" and result["formal_eligibility"] is False
    if result["status"] == "SUCCEEDED":
        assert result["research_result"]["cash_policy_v15"]["cash_policy_appendix_status"] == "INCOMPLETE_UNKNOWN_TERMS"
        assert result["research_result"]["cash_policy_v15"]["action"] == "no_order"
    assert service.read(queued["task_id"])["provider_requests"] == 2


def test_v15_rejects_cash_marker_after_settlement_without_retry(task):
    bad = json.loads(_cash(unknown=True))
    bad["years"]["2027"]["shareholder_cash_paths"]["base"]["target_payout_ratio"]["evidence_ids"] = ["test:marker"]
    service, calls = _service(task, json.dumps(bad))
    # The response must be sealed and settled before a strict rejection.
    queued = service.create(symbol="600519", request_key="TEST_V15_MARKER", years=[2027], now=NOW)
    result = service.run(queued["task_id"], now=NOW)
    assert result["status"] == "FAILED"
    assert result["error_code"] == "V15_CASH_RESPONSE_REJECTED"
    assert result["settled_cost"] != "0" and result["reserved_cost"] == "0"
    assert set(result["stage_responses"]) == {"annual", "cash"}
    assert service.resume(queued["task_id"], now=NOW)["provider_requests"] == len(calls) == 2


def test_v15_budget_blocks_provider_before_intent(task):
    service, calls = _service(task)
    path = service.root / v15.live.CONFIG
    cfg = json.loads(path.read_bytes())
    cfg["max_run_cost"] = "0.001"
    path.write_bytes(v15._bytes(cfg))
    queued = service.create(symbol="600519", request_key="TEST_V15_BUDGET", years=[2027], now=NOW)
    failed = service.run(queued["task_id"], now=NOW)
    assert failed["status"] == "FAILED"
    assert failed["error_code"] == "V15_TASK_EXECUTION_FAILED"
    assert failed["provider_requests"] == 0 and failed["stage_intents"] == {}
    assert calls == []


def test_v15_daily_cap_and_live_model_gate_prevent_paid_call(task):
    service, calls = _service(task)
    path = service.root / v15.live.CONFIG
    cfg = json.loads(path.read_bytes())
    cfg["daily_cost_limit"] = "0.001"
    path.write_bytes(v15._bytes(cfg))
    with pytest.raises(ValueError, match="TASK_LIMIT_EXCEEDS_DAILY_LIMIT"):
        service.create(symbol="600519", request_key="TEST_V15_DAILY", years=[2027], now=NOW)
    assert calls == []
    cfg["daily_cost_limit"] = "10"
    path.write_bytes(v15._bytes(cfg))
    live_service = v15.OperatingHorizonTaskService(service.root,
        source_loader=service.source_loader, source_loader_version=service.source_loader_version)
    with pytest.raises(PermissionError, match="EXACT_MODEL_REQUIRED"):
        live_service.create(symbol="600519", request_key="TEST_V15_LIVE", years=[2027], now=NOW)


def test_v15_imported_cash_is_distinct_and_pinned(task, monkeypatch):
    service, calls = _service(task)
    context = task[0].source_loader(root=service.root, symbol="600519", now=NOW)
    original = LLMRequest(role="cash", system="cash", user="pinned annual",
        output_schema={"type": "object"}, max_completion_tokens=8192)
    lineage = dict(action="no_order", source_task_id="rt-v12-source",
        source_record_binding={"path": "v12/current.json", "sha256": "a" * 64},
        source_binding=context["source_binding"], source_context_sha256="b" * 64,
        source_annual_response_sha256="c" * 64, source_budget_day="2026-11-12",
        source_annual_result_sha256="d" * 64, v13_cash_binding={"source": "v12"},
        v13_cash_request_sha256=v15._hash(v15._bytes(original.__dict__)))
    monkeypatch.setattr(v15.carryover, "replay_cash", lambda *args, **kwargs:
        (original, deepcopy(lineage), deepcopy(context), {"response": {}, "generated_at": NOW.isoformat()}))
    queued = service.create_imported(source_task_id=lineage["source_task_id"],
        request_key="TEST_V15_IMPORT", expected_source_binding=lineage["source_binding"],
        expected_context_sha256=lineage["source_context_sha256"],
        expected_annual_response_sha256=lineage["source_annual_response_sha256"],
        expected_budget_day=lineage["source_budget_day"], now=NOW)
    spec, state, _ = service._load(queued["task_id"])
    request, binding = service._request_for_stage(spec, state, context, "cash")
    assert spec["cash_request_sha256"] == v15._hash(v15._bytes(request.__dict__))
    assert spec["cash_request_sha256"] != lineage["v13_cash_request_sha256"]
    assert v15.cash_v15.VERSION in request.system
    assert binding == lineage["v13_cash_binding"]
    assert queued["provider_requests"] == 0 and calls == []


@pytest.mark.parametrize("bad_text", [
    lambda: _cash(unknown=True) + "}",
    lambda: _expired_cash(),
])
def test_v15_rejects_repeated_or_expired_cash_after_settlement(task, bad_text):
    service, calls = _service(task, bad_text())
    queued = service.create(symbol="600519", request_key="TEST_V15_REJECT", years=[2027], now=NOW)
    result = service.run(queued["task_id"], now=NOW)
    assert result["status"] == "FAILED"
    assert result["error_code"] == "V15_CASH_RESPONSE_REJECTED"
    assert result["settled_cost"] != "0" and result["reserved_cost"] == "0"
    assert service.resume(queued["task_id"], now=NOW)["provider_requests"] == len(calls) == 2


def _expired_cash():
    data = json.loads(_cash())
    data["years"]["2027"]["shareholder_cash_paths"]["base"]["reserve_ratio"]["rationale"] = (
        "Mechanism: 2024-2026 dividend plan proves the 2027 ratio.")
    return json.dumps(data)


def test_v15_real_v12_annual_import_and_lineage_pin(task, monkeypatch):
    old, _, _ = task
    annual_calls = []
    def annual_then_fail(request):
        annual_calls.append(request)
        data = json.loads(_annual())
        for path in data["years"]["2027"]["operating_paths"].values():
            path["unit_cost_case"]["mechanism"] = (
                "采购价格随合同和原料市场变化而调整，单位成本可能变化，需持续核对同口径成本及采购披露。")
        return LLMResponse(json.dumps(data, ensure_ascii=False), 100, 5000, "TEST_ONLY")
    source = v12.OperatingHorizonTaskService(old.root,
        source_loader=old.source_loader, source_loader_version=old.source_loader_version,
        test_provider=SimpleNamespace(complete=annual_then_fail))
    original = source._request_for_stage
    def fail_cash(spec, state, context, stage):
        if stage == "cash":
            raise ValueError("TEST_CASH_PREINTENT_FAILURE")
        return original(spec, state, context, stage)
    monkeypatch.setattr(source, "_request_for_stage", fail_cash)
    queued = source.create(symbol="600519", request_key="TEST_V12_IMPORT", years=[2027], now=NOW)
    failed = source.run(queued["task_id"], now=NOW)
    assert failed["error_code"] == "V12_TASK_EXECUTION_FAILED"
    assert failed["stage_validated"] == ["annual"] and len(annual_calls) == 1
    source_spec, source_state, _ = source._load(queued["task_id"])
    source_packet = source._packet(source_spec, source_state, "annual")
    settlement = next(iter(source_state["reservations"].values()))
    service, calls = _service(task)
    service.test_v12_service = source
    def cash_only(request):
        calls.append(request)
        return LLMResponse(_cash(unknown=True), 100, 50, "TEST_ONLY")
    service.test_provider = SimpleNamespace(complete=cash_only)
    with pytest.raises(ValueError, match="V15_TEST_V12_PIN_INVALID"):
        service.create_imported(source_task_id=queued["task_id"],
            request_key="TEST_V15_BAD_PIN",
            expected_source_binding=source_spec["source_binding"],
            expected_context_sha256=source_spec["context_sha256"],
            expected_annual_response_sha256=v15._hash(source_packet["response"]["text"].encode("utf-8")),
            expected_budget_day="1999-01-01", now=NOW)
    assert calls == []
    imported = service.create_imported(source_task_id=queued["task_id"],
        request_key="TEST_V15_IMPORT_REAL",
        expected_source_binding=source_spec["source_binding"],
        expected_context_sha256=source_spec["context_sha256"],
        expected_annual_response_sha256=v15._hash(source_packet["response"]["text"].encode("utf-8")),
        expected_budget_day=settlement["budget_day"], now=NOW)
    assert imported["annual_status"] == "IMPORTED_V12"
    assert imported["provider_requests"] == 0
    result = service.run(imported["task_id"], now=NOW)
    assert result["status"] in {"SUCCEEDED", "WAITING_EVIDENCE"}, result
    assert result["provider_requests"] == len(calls) == 1
    assert v15.cash_v15.VERSION in calls[0].system
    assert result["action"] == "no_order"
    if result["status"] == "SUCCEEDED":
        assert result["research_result"]["cash_policy_v15"]["cash_policy_appendix_status"] == "INCOMPLETE_UNKNOWN_TERMS"
