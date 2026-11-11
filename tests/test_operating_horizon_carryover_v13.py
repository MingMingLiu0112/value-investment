"""Offline admission checks for the read-only V12 to V13 boundary."""
import pytest

from value_investment_agent.application.research.agent_review import operating_horizon_carryover_v13 as carry


def test_rejects_missing_sealed_task_without_provider_call(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises((FileNotFoundError, ValueError)):
        carry.prepare_cash(tmp_path, "rt-" + "0" * 32,
            expected_source_binding={"pinned": True},
            expected_context_sha256="a" * 64,
            expected_annual_response_sha256="b" * 64,
            expected_budget_day="2026-11-12")


@pytest.mark.parametrize("change", ["source", "context", "annual", "calls"])
def test_rejects_unbound_or_unvalidated_annual_before_request(monkeypatch, change):
    spec = {"mode": "LIVE_OPERATING", "years": [2027],
            "source_binding": {"source": "pinned"}, "context_sha256": "a" * 64}
    state = {"action": "no_order", "stage_validated": ["annual"], "new_llm_calls": 1}
    if change == "source":
        spec["source_binding"] = {"source": "different"}
    elif change == "context":
        spec["context_sha256"] = "c" * 64
    elif change == "annual":
        state["stage_validated"] = []
    else:
        state["new_llm_calls"] = 0

    class Service:
        def __init__(self, root):
            pass

        def _load(self, task_id):
            return spec, state, {"sha256": "pinned"}

        def _context(self, spec):
            pytest.fail("invalid admission reached source replay")

    monkeypatch.setattr(carry.v12, "OperatingHorizonTaskService", Service)
    with pytest.raises(ValueError, match="V13_CARRYOVER_SOURCE_MISMATCH"):
        carry.prepare_cash("unused", "rt-source",
            expected_source_binding={"source": "pinned"},
            expected_context_sha256="a" * 64,
            expected_annual_response_sha256="b" * 64,
            expected_budget_day="2026-11-12")
