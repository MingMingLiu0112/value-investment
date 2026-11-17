"""Real V12/V14 services, fake providers, and V14 E2 cold read."""
from copy import deepcopy
from datetime import timedelta
import hashlib
import json
from types import SimpleNamespace

import pytest

from test_operating_horizon_task_v10_live import task, NOW, e2_read_time
from test_operating_horizon_split_v8 import split_context, _annual, _cash
from test_operating_horizon_draft_v1 import context as base_context
from value_investment_agent.application.research.agent_review import operating_horizon_task_v12_live as v12
from value_investment_agent.application.research.agent_review import operating_horizon_task_v14_live as v14
from value_investment_agent.application.research.operating_horizon_cash_policy_e2_v6 import read_v14_cash_policy_e2_input
from value_investment_agent.infrastructure.agent_runtime.provider import LLMResponse


def _annual_text():
    data = json.loads(_annual())
    for path in data["years"]["2027"]["operating_paths"].values():
        path["unit_cost_case"]["mechanism"] = (
            "采购价格随合同和原料市场变化而调整，单位成本可能变化，需持续核对同口径成本及采购披露。")
    return json.dumps(data, ensure_ascii=False)


@pytest.fixture
def chain(task, monkeypatch):
    old, source, _ = task
    pbt = next(row for row in source["evidence"] if row.get("field") == "pre_tax_profit")
    for row in source["evidence"]:
        if row.get("unit") == "CNY":
            row.update(kind="VERIFIED_REPORTED_FACT", physical_page=1)
    for field, amount, scope in (("tax", "91", "consolidated"),
                                 ("parent_profit", "346", "consolidated_parent")):
        row = deepcopy(pbt)
        row.update(id="TEST_ONLY:" + field, field=field, value=amount, scope=scope)
        source["evidence"].append(row)
    annual_calls, cash_calls = [], []
    def annual_complete(request):
        annual_calls.append(request)
        return LLMResponse(_annual_text(), 100, 5000, "TEST_ONLY")
    source_service = v12.OperatingHorizonTaskService(old.root,
        source_loader=old.source_loader, source_loader_version=old.source_loader_version,
        test_provider=SimpleNamespace(complete=annual_complete))
    original_request = source_service._request_for_stage
    def stop_before_cash(spec, state, context, stage):
        if stage == "cash":
            raise ValueError("TEST_ONLY_STOP_V12_AFTER_ANNUAL")
        return original_request(spec, state, context, stage)
    monkeypatch.setattr(source_service, "_request_for_stage", stop_before_cash)
    source_id = source_service.create(symbol="600519", request_key="TEST_V12_TO_V14", years=[2027], now=NOW)["task_id"]
    source_result = source_service.run(source_id, now=NOW)
    assert source_result["error_code"] == "V12_TASK_EXECUTION_FAILED"
    assert source_result["stage_validated"] == ["annual"]
    assert set(source_result["stage_responses"]) == {"annual"}
    assert len(annual_calls) == 1
    spec, state, _ = source_service._load(source_id)
    annual_packet = source_service._packet(spec, state, "annual")
    intent = state["stage_intents"]["annual"]
    def cash_complete(request):
        cash_calls.append(request)
        return LLMResponse(_cash(), 100, 50, "TEST_ONLY")
    service = v14.OperatingHorizonTaskService(old.root,
        source_loader=old.source_loader, source_loader_version=old.source_loader_version,
        test_provider=SimpleNamespace(complete=cash_complete), test_v12_service=source_service)
    queued = service.create_imported(source_task_id=source_id,
        request_key="TEST_V14_FROM_V12", expected_source_binding=spec["source_binding"],
        expected_context_sha256=spec["context_sha256"],
        expected_annual_response_sha256=hashlib.sha256(annual_packet["response"]["text"].encode()).hexdigest(),
        expected_budget_day=state["reservations"][intent["reservation"]]["budget_day"], now=NOW)
    result = service.run(queued["task_id"], now=NOW)
    assert len(cash_calls) == 1
    return service, queued["task_id"], result, source_service, source_id, cash_calls


def test_real_services_offline_v12_v14_e2_cold_read(chain):
    service, task_id, result, _, _, calls = chain
    assert result["status"] == "SUCCEEDED", result
    admitted = read_v14_cash_policy_e2_input(root=service.root, task_id=task_id,
        now=e2_read_time(), service=service)
    assert admitted["status"] == "TEST_ONLY_E2_CONTRACT_REPLAY"
    assert admitted["annual_operating_status"] == "VERIFIED_V12_ANNUAL_COMPILED"
    assert admitted["input_manifest"]["imported_annual"]["source_task_id"]
    assert admitted["input_manifest"]["task_contract"] == v14.CONTRACT
    assert admitted["action"] == "no_order" and admitted["formal_eligibility"] is False
    assert admitted["condition_price"] is None and len(calls) == 1
    assert service.read(task_id)["provider_requests"] == 1


def test_v14_e2_cold_read_rejects_tampered_v12_or_v14_packet(chain):
    service, task_id, result, source, source_id, calls = chain
    assert result["status"] == "SUCCEEDED", result
    source_packet = source._directory(source_id) / "response-annual.json"
    source_packet.write_text("{}", encoding="utf-8")
    with pytest.raises((ValueError, OSError)):
        read_v14_cash_policy_e2_input(root=service.root, task_id=task_id,
            now=e2_read_time(), service=service)
    assert len(calls) == 1


def test_v14_e2_cold_read_rejects_tampered_local_cash(chain):
    service, task_id, result, _, _, calls = chain
    assert result["status"] == "SUCCEEDED", result
    cash_packet = service._directory(task_id) / "response-cash.json"
    cash_packet.write_text("{}", encoding="utf-8")
    with pytest.raises((ValueError, OSError)):
        read_v14_cash_policy_e2_input(root=service.root, task_id=task_id,
            now=e2_read_time(), service=service)
    assert len(calls) == 1


def test_v14_e2_cold_read_rejects_source_replay_change(chain):
    service, task_id, result, source, _, calls = chain
    assert result["status"] == "SUCCEEDED", result
    original = source.source_loader
    def changed(**kwargs):
        context = deepcopy(original(**kwargs))
        context["snapshot_fingerprint"] = "0" * 64
        return context
    source.source_loader = changed
    with pytest.raises((ValueError, OSError)):
        read_v14_cash_policy_e2_input(root=service.root, task_id=task_id,
            now=e2_read_time(), service=service)
    assert len(calls) == 1
