"""The v2 overlay accepts replayable M2 research only, never trade admission."""
from __future__ import annotations

import json

import pytest

from test_value_research_queue import _hash, _inputs
from value_investment_agent.application.research.value_research_queue import build_value_research_queue
from value_investment_agent.presentation.daily_product_discovery_v2 import verify_discovery_bindings


def _bindings(tmp_path):
    inputs = _inputs(tmp_path)
    queue = build_value_research_queue(**inputs, budget=1)
    path = tmp_path / "runtime" / "queue.json"
    path.write_text(json.dumps(queue, ensure_ascii=False), encoding="utf-8")
    return {
        "value_discovery_report": {"path": "runtime/value-discovery-report.json",
                                   "sha256": _hash(inputs["report_path"])},
        "value_research_queue": {"path": "runtime/queue.json", "sha256": _hash(path)},
    }


def test_v2_overlay_requires_replayable_research_queue(tmp_path):
    bindings = _bindings(tmp_path)
    verify_discovery_bindings(tmp_path, bindings)
    with pytest.raises(ValueError, match="together"):
        verify_discovery_bindings(tmp_path, {"value_discovery_report": bindings["value_discovery_report"]})
    path = tmp_path / bindings["value_research_queue"]["path"]
    queue = json.loads(path.read_text(encoding="utf-8"))
    queue["entries"][0]["research_state"] = "BUY_CANDIDATE"
    path.write_text(json.dumps(queue, ensure_ascii=False), encoding="utf-8")
    bindings["value_research_queue"]["sha256"] = _hash(path)
    with pytest.raises(ValueError, match="not a replay"):
        verify_discovery_bindings(tmp_path, bindings)


def test_v2_overlay_rejects_unbound_pending_admission(tmp_path):
    bindings = _bindings(tmp_path)
    pending_path = tmp_path / "runtime" / "pending.json"
    pending_path.write_text(json.dumps({
        "schema_version": "m2-pending-research-intake-v1", "action": "no_order",
        "symbol": "000001", "decision_admitted": True, "quote_admitted": False,
        "m2_queue_binding": bindings["value_research_queue"],
    }), encoding="utf-8")
    bindings["m2_pending_research"] = {"path": "runtime/pending.json", "sha256": _hash(pending_path)}
    with pytest.raises(ValueError, match="not bound"):
        verify_discovery_bindings(tmp_path, bindings)
