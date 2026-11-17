"""Direct TEST_ONLY V16 annual-citation and durable replay checks."""
import json
from types import SimpleNamespace

from test_operating_horizon_task_v10_live import task, NOW
from test_operating_horizon_split_v8 import split_context, _annual, _cash
from test_operating_horizon_draft_v1 import context as base_context
from value_investment_agent.application.research.agent_review import operating_horizon_task_v15_live as v15
from value_investment_agent.application.research.agent_review import operating_horizon_task_v16_live as v16
from value_investment_agent.application.research.agent_review import operating_horizon_request_v16 as request_v16
from value_investment_agent.infrastructure.agent_runtime.provider import LLMResponse


def _service(task, *, missing=False):
    old, source, _ = task
    calls = []
    def complete(request):
        calls.append(request)
        if len(calls) == 1:
            data = json.loads(_annual())
            for path in data["years"]["2027"]["operating_paths"].values():
                path["unit_cost_case"]["mechanism"] = (
                    "采购价格随合同和原料市场变化而调整，单位成本可能变化，需持续核对同口径成本及采购披露。")
                if missing:
                    path["drivers"]["other_pretax_cny"]["evidence_ids"] = ["test:revenue"]
            return LLMResponse(json.dumps(data, ensure_ascii=False), 100, 5000, "TEST_ONLY")
        return LLMResponse(_cash(unknown=True), 100, 50, "TEST_ONLY")
    service = v16.OperatingHorizonTaskService(old.root,
        source_loader=old.source_loader, source_loader_version=old.source_loader_version,
        test_provider=SimpleNamespace(complete=complete))
    return service, source, calls


def test_v16_request_names_source_bound_fy_anchor_for_every_scenario(task):
    service, source, calls = _service(task)
    request = request_v16.build_annual_request(source, [2027],
        source_binding=source["source_binding"])
    for name in ("bear", "base", "bull"):
        clause = f"years[2027].operating_paths.{name}.drivers.other_pretax_cny.evidence_ids"
        assert clause in request.system and clause in request.transport_output_contract
    assert "test:pre_tax_profit" in request.system
    assert request.max_completion_tokens == 8192
    assert calls == []


def test_v16_test_only_valid_response_and_replay(task):
    service, _, calls = _service(task)
    queued = service.create(symbol="600519", request_key="TEST_V16_VALID", years=[2027], now=NOW)
    spec, _, _ = service._load(queued["task_id"])
    assert spec["task_contract"] == v16.CONTRACT
    assert spec["action"] == "no_order"
    assert service.base != v15.OperatingHorizonTaskService(service.root,
        source_loader=service.source_loader, source_loader_version=service.source_loader_version,
        test_provider=service.test_provider).base
    result = service.run(queued["task_id"], now=NOW)
    assert result["status"] in {"SUCCEEDED", "WAITING_EVIDENCE"}, result
    assert result["provider_requests"] == len(calls) == 2
    assert result["action"] == "no_order" and result["formal_eligibility"] is False
    assert service.read(queued["task_id"])["provider_requests"] == 2
    assert service.resume(queued["task_id"], now=NOW)["provider_requests"] == 2


def test_v16_missing_fy_anchor_rejected_after_settlement_without_retry(task):
    service, _, calls = _service(task, missing=True)
    queued = service.create(symbol="600519", request_key="TEST_V16_MISSING", years=[2027], now=NOW)
    result = service.run(queued["task_id"], now=NOW)
    assert result["status"] == "FAILED", result
    assert result["error_code"] == "V16_ANNUAL_RESPONSE_REJECTED"
    assert result["provider_requests"] == len(calls) == 1
    assert set(result["stage_responses"]) == {"annual"}
    assert result["settled_cost"] != "0" and result["reserved_cost"] == "0"
    assert service.resume(queued["task_id"], now=NOW)["provider_requests"] == 1