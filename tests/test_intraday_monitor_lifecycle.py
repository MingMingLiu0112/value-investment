"""Notification termination never changes condition or risk-review facts."""
from datetime import datetime, timedelta

import pytest

from test_intraday_monitor import tick
from test_intraday_conditions import NOW, condition, observation
from value_investment_agent.application.hotspot import intraday_monitor as monitor


def terminate(path, current, operation, now):
    return monitor.transition_intraday_alert(path,
        alert_id=current["alerts"][-1]["alert_id"], operation=operation,
        expected_snapshot_sha256=current["snapshot_sha256"], now=now)


@pytest.mark.parametrize("operation,status", [("CANCEL", "CANCELLED"), ("EXPIRE", "EXPIRED")])
def test_termination_replays_and_preserves_original_review(tmp_path, operation, status):
    path = tmp_path / "monitor.json"
    initial = tick(path)
    deadline = datetime.fromisoformat(initial["alerts"][0]["expiry_at"])
    now = deadline + timedelta(seconds=1)
    result = terminate(path, initial, operation, now)
    assert result["alerts"][0]["status"] == status
    assert result["alerts"][0]["attempts"] == 0
    assert result["alerts"][0]["requires_human_review"] is True
    assert result["alerts"][0]["available_operations"] == []
    assert result["history"] == initial["history"]
    assert result["cursor"] == initial["cursor"]
    assert result["eligibility"] is result["admitted"] is False
    assert result["engine"]["whole_source_coverage"] is False
    assert monitor.read_intraday_monitor(path) == result
    before = path.read_bytes()
    assert terminate(path, initial, operation, now + timedelta(seconds=1)) == result
    assert path.read_bytes() == before
    record = result["alert_transitions"][-1]
    assert record["reason"]
    assert record["evidence_refs"]
    if operation == "EXPIRE":
        assert datetime.fromisoformat(record["expires_at"]) == deadline


def test_expiry_before_declared_close_is_rejected_without_mutation(tmp_path):
    path = tmp_path / "monitor.json"
    initial = tick(path)
    before = path.read_bytes()
    with pytest.raises(ValueError, match="not expired"):
        terminate(path, initial, "EXPIRE", NOW + timedelta(seconds=1))
    assert path.read_bytes() == before


def test_source_failure_cannot_be_hidden_as_expired_price_observation(tmp_path):
    path = tmp_path / "monitor.json"
    initial = monitor.tick_intraday_monitor(path, condition=condition(), observation=None,
        now=NOW, max_age=timedelta(seconds=30))
    assert initial["alerts"][0]["expiry_at"] is None
    before = path.read_bytes()
    with pytest.raises(ValueError, match="not expired"):
        terminate(path, initial, "EXPIRE", NOW + timedelta(days=1))
    assert path.read_bytes() == before


def test_new_condition_cycle_can_alert_after_cancel_without_reopening_old_alert(tmp_path):
    path = tmp_path / "monitor.json"
    def quote_tick(now, price="11"):
        return monitor.tick_intraday_monitor(path,
            condition=condition(input_kind="QUOTE", period="quote"),
            observation={**observation(now), "price": price}, now=now,
            max_age=timedelta(seconds=30))
    initial = quote_tick(NOW)
    cancelled = terminate(path, initial, "CANCEL", NOW + timedelta(seconds=1))
    unchanged = quote_tick(NOW + timedelta(seconds=2))
    assert unchanged["alerts"] == cancelled["alerts"]
    quote_tick(NOW + timedelta(seconds=3), "9")
    renewed = quote_tick(NOW + timedelta(seconds=4))
    assert len(renewed["alerts"]) == 3
    assert renewed["alerts"][0]["status"] == "CANCELLED"
    assert renewed["alerts"][-1]["status"] == "PENDING"
    assert renewed["alerts"][-1]["alert_id"] != initial["alerts"][0]["alert_id"]
