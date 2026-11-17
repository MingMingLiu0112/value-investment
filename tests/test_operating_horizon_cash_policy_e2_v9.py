"""Direct V17 E2 reader admission and fail-closed gates."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib

import pytest

from value_investment_agent.application.research import operating_horizon_cash_policy_e2_v9 as e2


def _fixture(tmp_path, monkeypatch):
    service = object.__new__(e2.OperatingHorizonTaskService)
    service.root = tmp_path
    annual = {"response": {"text": "derived annual"}}
    cash = {"response": {"text": "cash"}}
    lineage = {"source_task_id": "rt-source", "source_context_sha256": "c" * 64,
               "source_binding": {"id": "source"},
               "source_packet_binding": {"path": "response-annual.json", "sha256": "a" * 64}}
    pins = {"cash": {"path": "response-cash.json", "sha256": "b" * 64}}
    spec = {"task_contract": e2.CONTRACT, "imported_annual": deepcopy(lineage),
            "context_sha256": "c" * 64, "source_binding": {"id": "source"},
            "config": {"max_completion_tokens_cap": 100}}
    state = {"stage_responses": deepcopy(pins), "stage_validated": ["annual", "cash"]}
    task = {"workflow": e2.CONTRACT, "status": "SUCCEEDED", "annual_status": "IMPORTED_REPAIRED_V16",
            "cash_status": "SETTLED_VALIDATED", "action": "no_order", "formal_eligibility": False,
            "stage_responses": deepcopy(pins), "imported_annual": deepcopy(lineage), "symbol": "600519",
            "research_result": {"cash_policy_v15": {"cash_policy_appendix_status": "COMPLETE_UNAPPROVED",
                                                    "action": "no_order"},
                                "split_response_sha256": {"annual": hashlib.sha256(b"derived annual").hexdigest(),
                                                          "cash": hashlib.sha256(b"cash").hexdigest()}}}
    monkeypatch.setattr(service, "read", lambda _: deepcopy(task))
    monkeypatch.setattr(service, "_load", lambda _: (deepcopy(spec), deepcopy(state), None))
    monkeypatch.setattr(service, "_imported", lambda _: (type("Request", (), {"max_completion_tokens": 100})(),
                                                   deepcopy(lineage), {"symbol": "600519", "snapshot_fingerprint": "f"},
                                                   deepcopy(annual)))
    monkeypatch.setattr(service, "_packet", lambda *_: deepcopy(cash))
    monkeypatch.setattr(service, "_context", lambda _: {"symbol": "600519", "snapshot_fingerprint": "f"})
    return service, task, spec, lineage


def test_v17_repaired_annual_reaches_e2_with_cash_only_durable_pins(tmp_path, monkeypatch):
    service, _, _, lineage = _fixture(tmp_path, monkeypatch)

    def compile_input(**kwargs):
        replay = kwargs["service"]
        task = replay.read("rt-v17")
        spec, state, _ = replay._load("rt-v17")
        assert kwargs["contract"] == e2.CONTRACT and kwargs["version"] == e2.VERSION
        assert task["stage_responses"]["annual"] == lineage["source_packet_binding"]
        assert set(state["stage_responses"]) == {"annual", "cash"}
        assert spec["context_fingerprint"] == "f"
        assert replay._packet(spec, state, "annual")["response"]["text"] == "derived annual"
        return {"input_manifest": {"schema_version": kwargs["version"]}, "action": "no_order"}

    monkeypatch.setattr(e2, "_read_bound_cash_policy_e2_input", compile_input)
    result = e2.read_v17_cash_policy_e2_input(tmp_path, "rt-v17", datetime.now(timezone.utc), service)
    assert result["input_manifest"]["imported_annual"] == lineage
    assert result["input_manifest"]["annual_origin"] == "V16_REPAIRED"
    assert result["annual_operating_status"] == "VERIFIED_REPAIRED_V16_ANNUAL_COMPILED"
    assert len(result["input_fingerprint"]) == 64


@pytest.mark.parametrize("change,error", [
    ("unknown", "V17_E2_CASH_POLICY_INCOMPLETE"),
    ("lineage", "V17_E2_LINEAGE_INVALID"),
    ("hash", "V17_E2_RESPONSE_HASH_CHANGED"),
])
def test_v17_fails_closed_before_compiler(tmp_path, monkeypatch, change, error):
    service, task, spec, lineage = _fixture(tmp_path, monkeypatch)
    if change == "unknown":
        task["research_result"]["cash_policy_v15"]["cash_policy_appendix_status"] = "INCOMPLETE_UNKNOWN_TERMS"
        monkeypatch.setattr(service, "read", lambda _: deepcopy(task))
    elif change == "lineage":
        lineage["source_context_sha256"] = "0" * 64
        monkeypatch.setattr(service, "_imported", lambda _: (type("Request", (), {"max_completion_tokens": 100})(),
                                                       deepcopy(lineage), {"symbol": "600519"}, {}))
    else:
        task["research_result"]["split_response_sha256"]["annual"] = "0" * 64
        monkeypatch.setattr(service, "read", lambda _: deepcopy(task))
    monkeypatch.setattr(e2, "_read_bound_cash_policy_e2_input", lambda **_: pytest.fail("compiler reached"))
    with pytest.raises(ValueError, match=error):
        e2.read_v17_cash_policy_e2_input(tmp_path, "rt-v17", datetime.now(timezone.utc), service)
