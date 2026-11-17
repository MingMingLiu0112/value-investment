"""Offline V13 transport and durable budget regression; never calls a paid API."""
import json
from copy import deepcopy
from types import SimpleNamespace


from test_operating_horizon_task_v10_live import task, NOW
from test_operating_horizon_split_v8 import split_context, _annual, _cash
from test_operating_horizon_draft_v1 import context as base_context
from value_investment_agent.application.research.agent_review import operating_horizon_task_v11_live as v11
from value_investment_agent.application.research.agent_review import operating_horizon_task_v13_live as mod
from value_investment_agent.infrastructure.agent_runtime.provider import LLMResponse


def _service(task, behavior="valid"):
    old, _, _ = task
    calls = []

    def complete(request):
        calls.append(request)
        if behavior == "cap":
            raise ValueError("LLM response incomplete: completion token cap reached")
        if behavior == "network":
            raise TimeoutError("TEST_ONLY unknown network outcome")
        if len(calls) == 1:
            data = json.loads(_annual())
            for path in data["years"]["2027"]["operating_paths"].values():
                path["unit_cost_case"]["mechanism"] = (
                    "采购价格随合同和原料市场变化而调整，单位成本可能变化，需持续核对同口径成本及采购披露。")
            return LLMResponse(json.dumps(data, ensure_ascii=False), 100, 5000, "TEST_ONLY")
        return LLMResponse(_cash(), 100, 50, "TEST_ONLY")

    service = mod.OperatingHorizonTaskService(old.root,
        source_loader=old.source_loader,
        source_loader_version=old.source_loader_version,
        test_provider=SimpleNamespace(complete=complete))
    return service, calls


def test_v13_uses_new_identity_8192_cap_and_frozen_validators(task):
    service, calls = _service(task)
    queued = service.create(symbol="600519", request_key="TEST_V13_VALID", years=[2027], now=NOW)
    spec, _, _ = service._load(queued["task_id"])
    request, _ = service._request_for_stage(spec, {}, service._context(spec), "annual")
    assert spec["task_contract"] == mod.CONTRACT
    assert spec["config"]["max_completion_tokens_cap"] == request.max_completion_tokens == 8192
    assert "at least 30 substantive characters" in request.system
    assert spec["config"]["daily_cost_limit"] == spec["config"]["max_run_cost"] == "10"
    assert service.base != v11.OperatingHorizonTaskService(service.root,
        source_loader=service.source_loader,
        source_loader_version=service.source_loader_version,
        test_provider=service.test_provider).base
    result = service.run(queued["task_id"], now=NOW)
    assert result["status"] in {"SUCCEEDED", "WAITING_EVIDENCE"}, result
    assert result["annual_result"] is not None
    assert result["provider_requests"] == len(calls) == 2
    assert [call.max_completion_tokens for call in calls] == [8192, 8192]
    assert result["action"] == "no_order" and result["formal_eligibility"] is False


def test_explicit_cap_rejection_keeps_reservation_and_never_retries(task):
    service, calls = _service(task, "cap")
    queued = service.create(symbol="600519", request_key="TEST_V13_CAP", years=[2027], now=NOW)
    result = service.run(queued["task_id"], now=NOW)
    assert result["status"] == "FAILED"
    assert result["error_code"] == "V13_ANNUAL_COMPLETION_CAP_REJECTED"
    assert result["reserved_cost"] != "0" and result["settled_cost"] == "0"
    assert list(result["reservations"].values())[0]["status"] == "RESERVED"
    assert service.resume(queued["task_id"], now=NOW)["provider_requests"] == 1
    assert len(calls) == 1


def test_unknown_preseal_network_outcome_remains_ambiguous(task):
    service, calls = _service(task, "network")
    queued = service.create(symbol="600519", request_key="TEST_V13_NET", years=[2027], now=NOW)
    result = service.run(queued["task_id"], now=NOW)
    assert result["error_code"] == "V13_ANNUAL_PROVIDER_AMBIGUOUS"
    assert result["reserved_cost"] != "0"
    assert not result["stage_responses"]
    assert service.resume(queued["task_id"], now=NOW)["provider_requests"] == len(calls) == 1


def test_source_hash_change_invalidates_read_without_new_call(task):
    service, calls = _service(task)
    queued = service.create(symbol="600519", request_key="TEST_V13_SOURCE", years=[2027], now=NOW)
    service.run(queued["task_id"], now=NOW)
    old_loader = service.source_loader

    def changed_loader(**kwargs):
        context = deepcopy(old_loader(**kwargs))
        context["snapshot_fingerprint"] = "a" * 64
        return context

    service.source_loader = changed_loader
    assert service.read(queued["task_id"])["status"] == "FAILED"
    assert len(calls) == 2


def test_8192_reservation_obeys_same_daily_budget(task):
    service, calls = _service(task)
    cfg_path = service.root / mod.live.CONFIG
    cfg = json.loads(cfg_path.read_bytes())
    cfg["max_run_cost"] = "0.001"
    cfg_path.write_bytes(mod._bytes(cfg))
    queued = service.create(symbol="600519", request_key="TEST_V13_BUDGET", years=[2027], now=NOW)
    failed = service.run(queued["task_id"], now=NOW)
    assert failed["status"] == "FAILED"
    assert failed["provider_requests"] == 0
    assert not failed["stage_intents"]
    assert calls == []
    assert failed["error_code"] == "V13_TASK_EXECUTION_FAILED"
