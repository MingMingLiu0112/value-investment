"""V13 import runner tests use a fake provider and no external API."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from test_operating_horizon_task_v10_live import task, NOW
from test_operating_horizon_split_v8 import split_context
from test_operating_horizon_draft_v1 import context as base_context
from value_investment_agent.application.research.agent_review import operating_horizon_task_v13_live as mod


def _import_service(task, monkeypatch):
    old, _, _ = task
    calls = []

    def complete(request):
        calls.append(request)
        raise ValueError("LLM response incomplete: completion token cap reached")

    service = mod.OperatingHorizonTaskService(old.root,
        source_loader=old.source_loader,
        source_loader_version=old.source_loader_version,
        test_provider=SimpleNamespace(complete=complete))
    context = old.source_loader(root=old.root, symbol="600519", now=NOW)
    request = SimpleNamespace(system="cash", user="pinned V12 annual", max_completion_tokens=8192)
    lineage = dict(version="test-external", action="no_order", source_task_id="rt-v12-source",
        source_record_binding={"path": "v12/current.json", "sha256": "a" * 64},
        source_binding=context["source_binding"], source_context_sha256="b" * 64,
        source_annual_response_sha256="c" * 64, source_budget_day="2026-11-12",
        source_annual_result_sha256="d" * 64, v13_cash_binding={"source": "v12"},
        v13_cash_request_sha256=mod._hash(mod._bytes(request.__dict__)))

    def replay(root, task_id, **expected):
        assert task_id == lineage["source_task_id"]
        assert expected["expected_source_binding"] == lineage["source_binding"]
        return request, deepcopy(lineage), deepcopy(context), {"response": {}, "generated_at": NOW.isoformat()}

    monkeypatch.setattr(mod.carryover, "replay_cash", replay)
    return service, calls, lineage


def test_import_creates_distinct_cash_only_task_and_reserves_only_cash(task, monkeypatch):
    service, calls, source = _import_service(task, monkeypatch)
    queued = service.create_imported(source_task_id=source["source_task_id"],
        request_key="TEST_V13_IMPORT", expected_source_binding=source["source_binding"],
        expected_context_sha256=source["source_context_sha256"],
        expected_annual_response_sha256=source["source_annual_response_sha256"],
        expected_budget_day=source["source_budget_day"], now=NOW)
    assert queued["task_id"] != source["source_task_id"]
    assert queued["annual_result"] is None
    assert queued["annual_status"] == "IMPORTED_V12"
    assert queued["provider_requests"] == queued["new_llm_calls"] == 0
    assert queued["stage_validated"] == ["annual"]
    assert queued["stage_responses"] == queued["stage_intents"] == {}
    failed = service.run(queued["task_id"], now=NOW)
    assert failed["error_code"] == "V13_CASH_COMPLETION_CAP_REJECTED"
    assert failed["provider_requests"] == len(calls) == 1
    assert set(failed["stage_intents"]) == {"cash"}
    assert failed["settled_cost"] == "0"
    assert service.resume(queued["task_id"], now=NOW)["provider_requests"] == 1


def test_import_replay_failure_closes_read_without_provider(task, monkeypatch):
    service, calls, source = _import_service(task, monkeypatch)
    queued = service.create_imported(source_task_id=source["source_task_id"],
        request_key="TEST_V13_TAMPER", expected_source_binding=source["source_binding"],
        expected_context_sha256=source["source_context_sha256"],
        expected_annual_response_sha256=source["source_annual_response_sha256"],
        expected_budget_day=source["source_budget_day"], now=NOW)
    monkeypatch.setattr(mod.carryover, "replay_cash", lambda *args, **kwargs:
        (_ for _ in ()).throw(ValueError("V12_BUDGET_CHANGED")))
    with pytest.raises(ValueError, match="V12_BUDGET_CHANGED"):
        service.read(queued["task_id"])
    assert calls == []


@pytest.mark.parametrize("field", ["source_record_binding", "source_budget_day",
                                   "source_annual_response_sha256", "v13_cash_request_sha256"])
def test_import_rejects_changed_external_lineage_on_read(task, monkeypatch, field):
    service, calls, source = _import_service(task, monkeypatch)
    queued = service.create_imported(source_task_id=source["source_task_id"],
        request_key="TEST_V13_LINEAGE", expected_source_binding=source["source_binding"],
        expected_context_sha256=source["source_context_sha256"],
        expected_annual_response_sha256=source["source_annual_response_sha256"],
        expected_budget_day=source["source_budget_day"], now=NOW)
    original = mod.carryover.replay_cash

    def changed(*args, **kwargs):
        request, lineage, context, packet = original(*args, **kwargs)
        lineage[field] = "changed"
        return request, lineage, context, packet

    monkeypatch.setattr(mod.carryover, "replay_cash", changed)
    with pytest.raises(ValueError, match="V13_IMPORTED_LINEAGE_CHANGED"):
        service.read(queued["task_id"])
    assert calls == []


def test_import_rejects_local_annual_response_even_with_external_pin(task, monkeypatch):
    service, calls, source = _import_service(task, monkeypatch)
    queued = service.create_imported(source_task_id=source["source_task_id"],
        request_key="TEST_V13_LOCAL_ANNUAL", expected_source_binding=source["source_binding"],
        expected_context_sha256=source["source_context_sha256"],
        expected_annual_response_sha256=source["source_annual_response_sha256"],
        expected_budget_day=source["source_budget_day"], now=NOW)
    spec, state, _ = service._load(queued["task_id"])
    state["stage_responses"]["annual"] = {"path": "forged.json", "sha256": "0" * 64}
    service._save(spec, state, service._load(queued["task_id"])[2], NOW)
    with pytest.raises(ValueError, match="V8_TASK_BINDING_INVALID"):
        service.read(queued["task_id"])
    assert calls == []
