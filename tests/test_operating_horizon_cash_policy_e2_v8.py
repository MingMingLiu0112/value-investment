"""V16 native D2 result reaches the unchanged deterministic E2 compiler."""
from copy import deepcopy
from datetime import timedelta
import hashlib
import json
from types import SimpleNamespace

import pytest

from test_operating_horizon_task_v10_live import task, NOW
from test_operating_horizon_split_v8 import split_context, _annual, _cash
from test_operating_horizon_draft_v1 import context as base_context
from test_operating_horizon_cash_policy_e2_v7 import chain
from value_investment_agent.application.research.agent_review import operating_horizon_task_v16_live as v16
from value_investment_agent.application.research.operating_horizon_cash_policy_e2_v8 import read_v16_cash_policy_e2_input
from value_investment_agent.infrastructure.agent_runtime.provider import LLMResponse


@pytest.fixture
def native(task):
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
    calls = []

    def complete(request):
        calls.append(request)
        if len(calls) == 1:
            value = json.loads(_annual())
            for path in value["years"]["2027"]["operating_paths"].values():
                path["unit_cost_case"]["mechanism"] = (
                    "采购价格随合同和原料市场变化而调整，单位成本可能变化，需持续核对同口径成本及采购披露。")
            return LLMResponse(json.dumps(value, ensure_ascii=False), 100, 5000, "TEST_ONLY")
        return LLMResponse(_cash(), 100, 50, "TEST_ONLY")

    service = v16.OperatingHorizonTaskService(old.root,
        source_loader=old.source_loader, source_loader_version=old.source_loader_version,
        test_provider=SimpleNamespace(complete=complete))
    created = service.create(symbol="600519", request_key="TEST_V16_NATIVE_E2", years=[2027], now=NOW)
    return service, created["task_id"], calls


def test_native_v16_compiles_to_e2_without_new_provider_call(native):
    service, task_id, calls = native
    result = service.run(task_id, now=NOW)
    assert result["status"] == "SUCCEEDED", result
    assert len(calls) == 2
    admitted = read_v16_cash_policy_e2_input(root=service.root, task_id=task_id,
        now=NOW + timedelta(hours=1), service=service)
    assert admitted["status"] == "TEST_ONLY_E2_CONTRACT_REPLAY"
    assert admitted["input_manifest"]["task_contract"] == v16.CONTRACT
    assert admitted["action"] == "no_order" and admitted["formal_eligibility"] is False
    assert admitted["condition_price"] is None and len(calls) == 2


def test_native_v16_rejects_changed_sealed_cash_response(native):
    service, task_id, calls = native
    assert service.run(task_id, now=NOW)["status"] == "SUCCEEDED"
    packet = service._directory(task_id) / "response-cash.json"
    packet.write_text("{}", encoding="utf-8")
    with pytest.raises((ValueError, OSError)):
        read_v16_cash_policy_e2_input(root=service.root, task_id=task_id,
            now=NOW + timedelta(hours=1), service=service)
    assert len(calls) == 2


def test_imported_v12_v16_cash_stays_separate_from_old_v15(chain):
    old_service, old_task_id, _, annual_service, annual_task_id, old_calls = chain
    annual_spec, annual_state, _ = annual_service._load(annual_task_id)
    annual_packet = annual_service._packet(annual_spec, annual_state, "annual")
    intent = annual_state["stage_intents"]["annual"]
    cash_calls = []

    def complete(request):
        cash_calls.append(request)
        return LLMResponse(_cash(), 100, 50, "TEST_ONLY")

    service = v16.OperatingHorizonTaskService(annual_service.root,
        source_loader=annual_service.source_loader,
        source_loader_version=annual_service.source_loader_version,
        test_provider=SimpleNamespace(complete=complete), test_v12_service=annual_service)
    created = service.create_imported(source_task_id=annual_task_id,
        request_key="TEST_V16_FROM_V12", expected_source_binding=annual_spec["source_binding"],
        expected_context_sha256=annual_spec["context_sha256"],
        expected_annual_response_sha256=hashlib.sha256(
            annual_packet["response"]["text"].encode()).hexdigest(),
        expected_budget_day=annual_state["reservations"][intent["reservation"]]["budget_day"],
        now=NOW)
    assert service.base != old_service.base and created["task_id"] != old_task_id
    result = service.run(created["task_id"], now=NOW)
    assert result["status"] == "SUCCEEDED", result
    admitted = read_v16_cash_policy_e2_input(root=service.root, task_id=created["task_id"],
        now=NOW + timedelta(hours=1), service=service)
    assert admitted["status"] == "TEST_ONLY_E2_CONTRACT_REPLAY"
    assert admitted["input_manifest"]["imported_annual"]["source_task_id"] == annual_task_id
    assert admitted["action"] == "no_order" and admitted["formal_eligibility"] is False
    assert len(cash_calls) == 1 and len(old_calls) == 1
