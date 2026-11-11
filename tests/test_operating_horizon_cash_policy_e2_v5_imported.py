"""Offline E2 admission for an external annual checkpoint and local cash response."""
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace

import pytest

from test_operating_horizon_task_v10_live import task, NOW  # noqa: F401
from test_operating_horizon_split_v8 import split_context  # noqa: F401
from test_operating_horizon_draft_v1 import context as base_context  # noqa: F401
from value_investment_agent.application.research import operating_horizon_cash_policy_e2_v5 as e2
from value_investment_agent.application.research.agent_review import operating_horizon_carryover_v13 as carryover
from value_investment_agent.application.research.agent_review.task_execution_v1 import _bytes, _hash


def test_imported_v13_e2_uses_external_annual_and_local_cash(task, monkeypatch):
    original_service, source, _ = task
    pbt = next(row for row in source["evidence"] if row.get("field") == "pre_tax_profit")
    for row in source["evidence"]:
        if row.get("unit") == "CNY":
            row.update(kind="VERIFIED_REPORTED_FACT", physical_page=1)
    for field, amount, scope in (("tax", "91", "consolidated"),
                                 ("parent_profit", "346", "consolidated_parent")):
        row = deepcopy(pbt)
        row.update(id="TEST_ONLY:" + field, field=field, value=amount, scope=scope)
        source["evidence"].append(row)
    created = original_service.create(symbol="600519", request_key="TEST_IMPORTED_E2", years=[2027], now=NOW)
    completed = original_service.run(created["task_id"], now=NOW)
    assert completed["status"] == "SUCCEEDED"
    source_spec, source_state, _ = original_service._load(created["task_id"])
    context = original_service._context(source_spec)
    annual_packet = original_service._packet(source_spec, source_state, "annual")
    cash_packet = original_service._packet(source_spec, source_state, "cash")
    lineage = dict(source_task_id="external-v12", source_binding=deepcopy(completed["source_binding"]),
        source_context_sha256=_hash(_bytes(context)), source_annual_response_sha256=
        _hash(annual_packet["response"]["text"].encode("utf-8")), source_budget_day="2026-11-12",
        source_annual_result_sha256="a" * 64,
        source_annual_response_binding=deepcopy(completed["stage_responses"]["annual"]))
    spec = dict(source_spec, task_contract=e2.CONTRACT, imported_annual=deepcopy(lineage),
        context_sha256=_hash(_bytes(context)))
    spec.pop("context_fingerprint")
    state = deepcopy(source_state)
    state["stage_responses"].pop("annual")
    state["stage_intents"].pop("annual")
    view = deepcopy(completed)
    view.update(workflow=e2.CONTRACT, annual_status="IMPORTED_V12",
        imported_annual={"source_annual_result_sha256": lineage["source_annual_result_sha256"]},
        stage_responses=deepcopy(state["stage_responses"]))
    service = SimpleNamespace(root=original_service.root, read=lambda _: view,
        _load=lambda _: (spec, state, None), _context=lambda _: context,
        _packet=lambda _spec, _state, stage: cash_packet if stage == "cash" else None)
    def replay(_root, _task_id, **pins):
        assert _task_id == lineage["source_task_id"]
        assert pins["expected_context_sha256"] == lineage["source_context_sha256"]
        return None, deepcopy(lineage), deepcopy(context), deepcopy(annual_packet)
    monkeypatch.setattr(carryover, "replay_cash", replay)
    cutoff = NOW + timedelta(hours=1)
    result = e2.read_v13_cash_policy_e2_input(root=service.root, task_id=created["task_id"],
        now=cutoff, service=service)
    assert result["status"] == "TEST_ONLY_E2_CONTRACT_REPLAY"
    assert result["annual_operating_status"] == "IMPORTED_V12_COMPILED"
    assert result["annual_operating_candidates"]["2027"]["scenarios"]
    assert result["policy_years"]["2027"]["base"]["complete"] is True
    assert result["input_manifest"]["annual_origin"] == "V12_EXTERNAL"
    assert set(result["input_manifest"]["stage_responses"]) == {"cash"}
    assert result["input_manifest"]["annual_response_binding"] == lineage["source_annual_response_binding"]
    assert result["action"] == "no_order" and result["condition_price"] is None
    assert result["formal_eligibility"] is False

    view["annual_status"] = "SETTLED_VALIDATED"
    with pytest.raises(ValueError, match="SUCCEEDED_TWO_STAGE"):
        e2.read_v13_cash_policy_e2_input(root=service.root, task_id=created["task_id"], now=cutoff, service=service)
    view["annual_status"] = "IMPORTED_V12"
    view["stage_responses"]["annual"] = lineage["source_annual_response_binding"]
    with pytest.raises(ValueError, match="RESPONSE_PINS_REQUIRED"):
        e2.read_v13_cash_policy_e2_input(root=service.root, task_id=created["task_id"], now=cutoff, service=service)
    view["stage_responses"].pop("annual")
    state["stage_responses"]["annual"] = lineage["source_annual_response_binding"]
    with pytest.raises(ValueError, match="TASK_PINS_CHANGED"):
        e2.read_v13_cash_policy_e2_input(root=service.root, task_id=created["task_id"], now=cutoff, service=service)
    state["stage_responses"].pop("annual")
    view["research_result"]["years"]["2027"]["shareholder_cash_paths"]["base"]["terms"]["operating_wc_cash_cny"]["classification"] = "UNKNOWN"
    with pytest.raises(ValueError, match="UNKNOWN_CASH_TERM"):
        e2.read_v13_cash_policy_e2_input(root=service.root, task_id=created["task_id"], now=cutoff, service=service)
    view["research_result"] = deepcopy(completed["research_result"])
    def changed(_root, _task_id, **pins):
        bad = deepcopy(lineage)
        bad["source_annual_response_sha256"] = "0" * 64
        return None, bad, deepcopy(context), deepcopy(annual_packet)
    monkeypatch.setattr(carryover, "replay_cash", changed)
    with pytest.raises(ValueError, match="IMPORTED_LINEAGE_CHANGED"):
        e2.read_v13_cash_policy_e2_input(root=service.root, task_id=created["task_id"], now=cutoff, service=service)
    monkeypatch.setattr(carryover, "replay_cash", lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("V12_TAMPER")))
    with pytest.raises(ValueError, match="V12_TAMPER"):
        e2.read_v13_cash_policy_e2_input(root=service.root, task_id=created["task_id"], now=cutoff, service=service)
