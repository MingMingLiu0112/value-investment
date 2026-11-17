"""TEST_ONLY cross-sleeve history must never borrow another strategy's thesis."""
from copy import deepcopy

import pytest

from value_investment_agent.application.portfolio import judgment_snapshot


@pytest.mark.parametrize("decision,sleeve", [
    ("600887", "HOTSPOT_SATELLITE"),
    ("hotspot-600887", "CORE_VALUE"),
])
def test_cross_sleeve_fill_has_no_borrowed_judgment(tmp_path, monkeypatch, decision, sleeve):
    plan = {"symbol": "600887", "research_version": "TEST_ONLY", "action": "no_order"}
    packet = {"publication_id": "TEST_ONLY", "content_sha256": "a" * 64,
        "value_price_conditions": {"600887": deepcopy(plan)},
        "price_conditions": {"items": [{"symbol": "600887", "price_action_plan": deepcopy(plan)}]}}
    monkeypatch.setattr(judgment_snapshot, "load_current_packet", lambda root: (packet, None))
    fill = {"symbol": "600887", "decision_id": decision, "sleeve": sleeve,
        "research_version": "TEST_ONLY"}
    before = deepcopy(packet)
    assert judgment_snapshot.capture_judgment_snapshot(tmp_path, fill) is None
    assert packet == before


@pytest.mark.parametrize("decision,sleeve", [
    ("600887", "CORE_VALUE"), ("hotspot-600887", "HOTSPOT_SATELLITE"),
])
def test_matched_strategy_keeps_detached_recording_history(tmp_path, monkeypatch, decision, sleeve):
    plan = {"symbol": "600887", "research_version": "TEST_ONLY", "action": "no_order"}
    packet = {"publication_id": "TEST_ONLY", "content_sha256": "a" * 64,
        "value_price_conditions": {"600887": plan},
        "price_conditions": {"items": [{"symbol": "600887", "price_action_plan": plan}]}}
    monkeypatch.setattr(judgment_snapshot, "load_current_packet", lambda root: (packet, None))
    snapshot = judgment_snapshot.capture_judgment_snapshot(tmp_path,
        {"symbol": "600887", "decision_id": decision, "sleeve": sleeve, "research_version": "TEST_ONLY"})
    assert snapshot["plan"] == plan
    plan["research_version"] = "CHANGED"
    assert snapshot["plan"]["research_version"] == "TEST_ONLY"
    assert snapshot["action"] == "no_order"
    assert snapshot["trade_time_availability_proven"] is False
