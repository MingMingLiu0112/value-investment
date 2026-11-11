"""Offline V11 request and durable annual validation checks."""
import json
from types import SimpleNamespace

from test_operating_horizon_task_v10_live import task, NOW
from test_operating_horizon_split_v8 import split_context, _annual, _cash
from test_operating_horizon_draft_v1 import context as base_context
from value_investment_agent.application.research.agent_review import operating_horizon_task_v11_live as mod
from value_investment_agent.infrastructure.agent_runtime.provider import LLMResponse


def _service(task, mechanism):
    prior, _, _ = task
    calls = []
    def complete(request):
        calls.append(request)
        if len(calls) == 1:
            data = json.loads(_annual())
            for path in data["years"]["2027"]["operating_paths"].values():
                path["unit_cost_case"]["mechanism"] = mechanism
            return LLMResponse(json.dumps(data, ensure_ascii=False), 100, 50, "TEST_ONLY")
        return LLMResponse(_cash(), 100, 50, "TEST_ONLY")
    service = mod.OperatingHorizonTaskService(prior.root,
        source_loader=prior.source_loader,
        source_loader_version=prior.source_loader_version,
        test_provider=SimpleNamespace(complete=complete))
    return service, calls


def test_short_mechanism_fails_without_retry(task):
    service, calls = _service(task, "采购价格仍待观察")
    queued = service.create(symbol="600519", request_key="TEST_V11_SHORT", years=[2027], now=NOW)
    result = service.run(queued["task_id"], now=NOW)
    assert result["status"] == "FAILED"
    assert result["annual_status"] == "RETURNED_UNVERIFIED"
    assert result["error_code"] == "V9_ANNUAL_RESPONSE_REJECTED"
    assert result["action"] == "no_order"
    assert result["provider_requests"] == len(calls) == 1
    assert service.resume(queued["task_id"], now=NOW)["provider_requests"] == 1


def test_full_mechanism_accepted_with_shared_budget(task):
    mechanism = "原料采购单价若随长期合同调整而下降，单位成本可能改善；仍需逐季核对同口径营业成本和采购披露。"
    service, calls = _service(task, mechanism)
    queued = service.create(symbol="600519", request_key="TEST_V11_FULL", years=[2027], now=NOW)
    spec, _, _ = service._load(queued["task_id"])
    request = service._request_for_stage(spec, {}, service._context(spec), "annual")[0]
    assert "at least 30 substantive characters" in request.system
    assert "at least 30 substantive characters" in request.transport_output_contract
    assert request.output_schema["properties"]["years"]["properties"]["2027"]["properties"]["operating_paths"]["properties"]["bear"]["properties"]["unit_cost_case"]["properties"]["mechanism"]["minLength"] == 12
    result = service.run(queued["task_id"], now=NOW)
    assert result["status"] in {"SUCCEEDED", "WAITING_EVIDENCE"}, result
    assert result["annual_result"] is not None
    assert result["action"] == "no_order"
    assert result["formal_eligibility"] is False
    assert result["provider_requests"] == len(calls) == 2
    assert spec["config"]["currency"] == "CNY"
    assert spec["config"]["daily_cost_limit"] == spec["config"]["max_run_cost"] == "10"
