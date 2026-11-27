from contextlib import nullcontext
from dataclasses import replace
import json
from types import SimpleNamespace

import pytest

from value_investment_agent.application.research import parent_bear_terminal_response_v2 as wire
from value_investment_agent.infrastructure.agent_runtime.provider import LLMResponse


def term(**amount):
    return dict(evidence_anchors=["cfo"], mechanism="sealed prose", counter_evidence="counter",
                reopen_condition="reopen", **amount)


def response():
    packet = dict(cost_of_equity=term(value="0.10"),
                  policy={"new_borrowing": term(values=["14.25"])},
                  financing={"new_borrowing": "14.25"}, remaining_scheduled_events=[],
                  max_transition_years=2, rationale="rationale",
                  counter_evidence="counter", reopen_condition="reopen")
    return LLMResponse(json.dumps(packet), 100, 80, "deepseek-flash")


def test_normalizes_only_singleton_alias_and_preserves_financing_and_original():
    original = response()
    raw = json.loads(original.text)
    adjusted = wire.normalize_bear_terminal_response(original)
    result = json.loads(adjusted.text)
    assert result["cost_of_equity"] == term(values=["0.10"])
    assert result["terminal"]["policy"] == raw["policy"]
    assert result["terminal"]["financing"] == raw["financing"]
    assert replace(adjusted, text=original.text) == original
    assert json.loads(original.text)["cost_of_equity"]["value"] == "0.10"


@pytest.mark.parametrize("amount", [
    {"value": "1", "values": ["1"]}, {"values": ["1", "2"]}, {"values": [1]}, {"value": 1},
])
def test_ambiguous_or_non_string_terms_are_rejected(amount):
    original = response()
    packet = json.loads(original.text)
    packet["cost_of_equity"] = term(**amount)
    with pytest.raises(ValueError, match="PARENT_DRAFT_TERM_SOURCE_INVALID"):
        wire.normalize_bear_terminal_response(replace(original, text=json.dumps(packet)))


def test_rejects_duplicate_economic_keys_and_conflicting_prose():
    original = response()
    for raw in [original.text.replace('"value": "0.10"', '"value": "0.10", "value": "0.20"'),
                original.text.replace('"counter_evidence": "counter"',
                                      '"counter_evidence": "counter", "counter_evidence": "other"', 1)]:
        with pytest.raises(ValueError, match="CONFLICTING_JSON_KEY"):
            wire.normalize_bear_terminal_response(replace(original, text=raw))


@pytest.mark.parametrize("mismatch", [None, "request", "fingerprint", "unsettled", "wrong_task", "accepted"])
def test_sealed_diagnostic_requires_exact_failed_and_settled_response(tmp_path, mismatch):
    task_id = "rt-" + "a" * 32
    reservation = "b" * 64
    request = SimpleNamespace(user="verified request")
    directory = tmp_path / "runtime" / task_id
    binding = {"path": f"runtime/{task_id}/response-{reservation}.json", "sha256": "c" * 64}
    spec = {"source_fingerprint": "d" * 64}
    state = dict(status="FAILED", error_code="BEAR_TERMINAL_PARENT_DRAFT_TERM_SOURCE_INVALID",
                 responses={"bear.policy": {}}, returned_responses=[binding],
                 reservations={reservation: {"scenario": "bear.terminal", "status": "SETTLED"}})
    packet = dict(scenario="bear.terminal", action="no_order", source_fingerprint=spec["source_fingerprint"],
                  request_sha256=wire._hash(wire._bytes(request.__dict__)), response=response().__dict__)
    if mismatch == "request":
        packet["request_sha256"] = "f" * 64
    elif mismatch == "fingerprint":
        packet["source_fingerprint"] = "f" * 64
    elif mismatch == "unsettled":
        state["reservations"][reservation]["status"] = "RESERVED"
    elif mismatch == "wrong_task":
        binding["path"] = binding["path"].replace(task_id, "rt-" + "f" * 32)
    elif mismatch == "accepted":
        state["responses"]["bear.terminal"] = binding

    class Service:
        root = tmp_path

        def _directory(self, _):
            return directory

        def _lock(self, _):
            return nullcontext()

        def _load(self, _):
            return spec, state, {}

        def _bound(self, selected):
            assert selected == binding
            return packet

    diagnostic = wire.sealed_bear_terminal_diagnostic(Service(), task_id, wire_request=request)
    if mismatch:
        assert diagnostic is None
    else:
        assert diagnostic == dict(status="REJECTED_RESPONSE_DIAGNOSTIC_ONLY", stage="bear.terminal",
            wire_shape="FLAT_SINGLETON_TERMS", term_shape_counts={"value": 1, "values": 1},
            response_sha256="c" * 64, action="no_order", formal_eligibility=False)
