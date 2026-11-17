"""Offline sealed V12 -> imported V13 -> E2 using durable services and real replay."""
import json
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace

import pytest

from test_operating_horizon_task_v10_live import task, NOW  # noqa: F401
from test_operating_horizon_split_v8 import split_context, _annual, _cash  # noqa: F401
from test_operating_horizon_draft_v1 import context as base_context  # noqa: F401
from value_investment_agent.application.research import operating_horizon_cash_policy_e2_v5 as e2
from value_investment_agent.application.research.agent_review import operating_horizon_task_v12_live as v12
from value_investment_agent.application.research.agent_review import operating_horizon_task_v13_live as v13
from value_investment_agent.application.research.agent_review import operating_horizon_carryover_v13 as carryover
from value_investment_agent.infrastructure.agent_runtime.provider import LLMResponse


@pytest.fixture
def imported_chain(task, monkeypatch):
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
    # All writes are under tmp_path. The invalid endpoint and stubbed provider
    # make the sealed LIVE-mode V12 fixture entirely synthetic and offline.
    cfg_path = old.root / v12.live.CONFIG
    cfg = json.loads(cfg_path.read_bytes())
    cfg.update(model_id="deepseek-flash", api_key_env="VALUE_AGENT_TEST_ONLY_KEY")
    cfg_path.write_bytes(v12._bytes(cfg))
    monkeypatch.setenv("VALUE_AGENT_TEST_ONLY_KEY", "TEST_ONLY_NO_NETWORK")
    monkeypatch.setattr(carryover.wc_v9, "load_current", old.source_loader)
    monkeypatch.setattr(v12, "_now", lambda value=None: value or NOW)
    monkeypatch.setattr(v13, "_now", lambda value=None: value or NOW + timedelta(hours=2))
    annual_calls = []

    def annual_provider(_self, _spec):
        def complete(request):
            annual_calls.append(request)
            data = json.loads(_annual())
            for path in data["years"]["2027"]["operating_paths"].values():
                path["unit_cost_case"]["mechanism"] = (
                    "采购价格随合同和原料市场变化而调整，单位成本可能变化，需持续核对同口径成本及采购披露。")
            return LLMResponse(json.dumps(data, ensure_ascii=False), 100, 5000, "deepseek-flash")
        return SimpleNamespace(complete=complete)

    monkeypatch.setattr(v12.OperatingHorizonTaskService, "_provider", annual_provider)
    source_service = v12.OperatingHorizonTaskService(old.root,
        source_loader=old.source_loader, source_loader_version=carryover.wc_v9.VERSION)
    queued = source_service.create(symbol="600519", request_key="TEST_ONLY_V12_SOURCE",
        years=[2027], now=NOW)
    original_request = source_service._request_for_stage

    def annual_then_stop(spec, state, context, stage):
        if stage == "cash":
            raise ValueError("TEST_ONLY_STOP_BEFORE_V12_CASH_INTENT")
        return original_request(spec, state, context, stage)

    monkeypatch.setattr(source_service, "_request_for_stage", annual_then_stop)
    failed = source_service.run(queued["task_id"], now=NOW)
    assert failed["status"] == "FAILED"
    assert failed["error_code"] == "V12_TASK_EXECUTION_FAILED"
    assert failed["annual_status"] == "SETTLED_VALIDATED"
    assert set(failed["stage_responses"]) == {"annual"}
    assert set(failed["stage_intents"]) == {"annual"}
    assert len(annual_calls) == 1
    spec, state, _ = source_service._load(queued["task_id"])
    annual_packet = source_service._packet(spec, state, "annual")
    response_sha = v12._hash(annual_packet["response"]["text"].encode("utf-8"))
    budget_day = state["reservations"][state["stage_intents"]["annual"]["reservation"]]["budget_day"]
    cash_calls = []

    def cash_complete(request):
        cash_calls.append(request)
        return LLMResponse(_cash(), 100, 50, "deepseek-flash")

    cash_service = v13.OperatingHorizonTaskService(old.root,
        test_provider=SimpleNamespace(complete=cash_complete))
    imported = cash_service.create_imported(source_task_id=queued["task_id"],
        request_key="TEST_ONLY_V13_IMPORTED", expected_source_binding=spec["source_binding"],
        expected_context_sha256=spec["context_sha256"],
        expected_annual_response_sha256=response_sha, expected_budget_day=budget_day,
        now=NOW + timedelta(hours=1))
    assert imported["annual_status"] == "IMPORTED_V12"
    assert imported["stage_responses"] == {}
    completed = cash_service.run(imported["task_id"], now=NOW + timedelta(hours=2))
    assert completed["status"] == "SUCCEEDED", completed
    assert completed["cash_status"] == "SETTLED_VALIDATED"
    assert set(completed["stage_responses"]) == {"cash"}
    assert len(cash_calls) == 1
    return source_service, cash_service, queued["task_id"], imported["task_id"], source, annual_calls, cash_calls


def test_real_service_import_replays_sealed_annual_and_compiles_e2(imported_chain):
    source_service, cash_service, source_id, imported_id, _, annual_calls, cash_calls = imported_chain
    result = e2.read_v13_cash_policy_e2_input(root=cash_service.root, task_id=imported_id,
        now=NOW + timedelta(hours=3), service=cash_service)
    assert result["status"] == "TEST_ONLY_E2_CONTRACT_REPLAY"
    assert result["annual_operating_status"] == "IMPORTED_V12_COMPILED"
    assert result["annual_operating_candidates"]["2027"]["scenarios"]
    assert result["policy_years"]["2027"]["base"]["complete"] is True
    manifest = result["input_manifest"]
    assert manifest["annual_origin"] == "V12_EXTERNAL"
    assert manifest["imported_annual"]["source_task_id"] == source_id
    assert set(manifest["stage_responses"]) == {"cash"}
    assert manifest["annual_response_binding"] == source_service.read(source_id)["stage_responses"]["annual"]
    assert result["action"] == "no_order" and result["formal_eligibility"] is False
    assert result["condition_price"] is None
    assert len(annual_calls) == len(cash_calls) == 1


@pytest.mark.parametrize("target", ["source", "context", "cash"])
def test_real_service_rejects_tampered_sealed_response(imported_chain, target):
    source_service, cash_service, source_id, imported_id, source, annual_calls, cash_calls = imported_chain
    if target == "context":
        source["evidence"][0]["text"] += " TEST_ONLY_TAMPER"
    else:
        service = source_service if target == "source" else cash_service
        task_id = source_id if target == "source" else imported_id
        packet = service._directory(task_id) / ("response-annual.json" if target == "source" else "response-cash.json")
        packet.write_bytes(b"{}")
    with pytest.raises(ValueError):
        e2.read_v13_cash_policy_e2_input(root=cash_service.root, task_id=imported_id,
            now=NOW + timedelta(hours=3), service=cash_service)
    assert len(annual_calls) == len(cash_calls) == 1
