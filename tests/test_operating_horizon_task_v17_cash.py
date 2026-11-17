"""Direct offline V17 admission and derived-packet tests; no provider calls."""

from copy import deepcopy
import hashlib
import json

import pytest

from test_operating_horizon_annual_v3 import _response
from value_investment_agent.application.research.agent_review import operating_horizon_task_v17_cash as mod
from value_investment_agent.application.research.agent_review import operating_horizon_v17_source as source


def test_derived_packet_moves_only_declared_fields():
    payload = _response()
    year = payload["years"]["2026"]
    for field in ("counter_evidence", "reopen_condition"):
        year["operating_paths"][field] = year.pop(field)
    packet = {"response": {"text": json.dumps(payload, ensure_ascii=False)}}
    before = deepcopy(packet)
    expected = deepcopy(payload)
    for field in ("counter_evidence", "reopen_condition"):
        expected["years"]["2026"][field] = expected["years"]["2026"]["operating_paths"].pop(field)
    text = mod.source.repair.common._canonical(expected)
    normalized = {"derived_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "relocations": [{"from": f"/years/2026/operating_paths/{field}",
                         "to": f"/years/2026/{field}"}
                        for field in ("counter_evidence", "reopen_condition")]}
    assert mod.OperatingHorizonTaskService._derived_text(packet, normalized) == text
    assert packet == before
    normalized["derived_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="V17_DERIVED_HASH_CHANGED"):
        mod.OperatingHorizonTaskService._derived_text(packet, normalized)


def test_source_identity_fails_before_read():
    with pytest.raises(ValueError, match="V17_EXACT_V16_SOURCE_REQUIRED"):
        source.replay(object(), "rt-synthetic-source")


@pytest.mark.parametrize("status,error,stages", [
    ("SUCCEEDED", "V16_ANNUAL_RESPONSE_REJECTED", {"annual": {}}),
    ("FAILED", "V16_CASH_RESPONSE_REJECTED", {"annual": {}}),
    ("FAILED", "V16_ANNUAL_RESPONSE_REJECTED", {"annual": {}, "cash": {}}),
])
def test_source_rejects_wrong_state_before_context(monkeypatch, status, error, stages):
    service = object.__new__(source.v16.OperatingHorizonTaskService)
    spec = {"task_contract": source.v16.CONTRACT, "years": [2027]}
    state = {"status": status, "error_code": error, "stage_intents": stages,
             "stage_responses": {"annual": {}}, "stage_validated": [], "provider_requests": 1}
    monkeypatch.setattr(service, "_load", lambda task_id: (spec, state, {}))
    monkeypatch.setattr(service, "_context", lambda spec: pytest.fail("context loaded before state check"))
    with pytest.raises(ValueError, match="V17_SOURCE_STATE_INVALID"):
        source.replay(service, "rt-synthetic-source")


def test_synthetic_task_id_replays_without_source_constant(monkeypatch):
    service = object.__new__(source.v16.OperatingHorizonTaskService)
    synthetic_id = "rt-synthetic-fixture-123"
    request = type("Request", (), {})()
    request.__dict__["sample"] = "annual"
    request_sha = source._hash(source._bytes(request.__dict__))
    spec = {"task_contract": source.v16.CONTRACT, "years": [2027],
            "source_loader_binding": {"version": "synthetic-v9"},
            "annual_request_sha256": request_sha, "config": {"model_id": "mock"},
            "source_binding": {"source": "synthetic"}, "context_sha256": "c" * 64,
            "implementation_sha256": {"version": "synthetic"}}
    state = {"status": "FAILED", "error_code": "V16_ANNUAL_RESPONSE_REJECTED",
             "stage_intents": {"annual": {"reservation": "r"}},
             "stage_responses": {"annual": {"sha256": "p"}},
             "stage_validated": [], "provider_requests": 1,
             "reservations": {"r": {"budget_day": "2026-11-12"}}}
    packet = {"request_sha256": request_sha, "generated_at": "2026-11-12T00:00:00+08:00",
              "response": {"text": "{}", "prompt_tokens": 1, "completion_tokens": 1, "model_id": "mock"}}
    monkeypatch.setattr(service, "_load", lambda task_id: (spec, state, {"sha256": "head"}) if task_id == synthetic_id else pytest.fail("wrong id"))
    monkeypatch.setattr(service, "_loader_binding", lambda: spec["source_loader_binding"])
    monkeypatch.setattr(service, "_context", lambda _spec: {"symbol": "600519"})
    monkeypatch.setattr(service, "_packet", lambda *_: packet)
    monkeypatch.setattr(service, "_request_for_stage", lambda *_: (request, None))
    monkeypatch.setattr(service, "_usage", lambda *_: None)
    monkeypatch.setattr(service, "_verify_stage_settlement", lambda *_: None)
    monkeypatch.setattr(source.split, "_project", lambda context, binding: context)
    monkeypatch.setattr(source.split, "_annual_context", lambda context: context)
    monkeypatch.setattr(source.repair, "normalize_response", lambda *_: {
        "version": "synthetic-repair", "raw_sha256": "a" * 64,
        "derived_sha256": "b" * 64, "relocations": [],
        "validated_result": {"response_sha256": "b" * 64}})
    _, _, _, lineage = source.replay(service, synthetic_id)
    assert lineage["source_task_id"] == synthetic_id
    assert lineage["source_loader_binding"] == spec["source_loader_binding"]


def test_distinct_contract_and_cash_only_stage_rejection():
    assert mod.CONTRACT != mod.v16.CONTRACT
    assert mod.STORE != mod.v16.STORE
    service = object.__new__(mod.OperatingHorizonTaskService)
    with pytest.raises(ValueError, match="V17_ANNUAL_PROVIDER_FORBIDDEN"):
        service._request_for_stage({}, {}, {}, "annual")
