"""Synthetic public observations, real adapter/M5 engines and local persistence."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json

import pytest

from test_intraday_conditions import NOW, condition, observation
from value_investment_agent.application.hotspot import intraday_monitor as monitor


def tick(path, *, now=NOW, previous_price="11", **kwargs):
    return monitor.tick_intraday_monitor(path, condition=condition(),
        observation={**observation(now), "price": previous_price}, now=now,
        max_age=timedelta(seconds=30), **kwargs)


def test_missing_read_has_no_filesystem_effect(tmp_path):
    parent = tmp_path / "absent"
    result = monitor.read_intraday_monitor(parent / "monitor.json")
    assert not parent.exists()
    assert result["status"] == "NOT_INITIALIZED"
    assert result["namespace"] == "SIMULATED" and result["test_only"]
    assert result["action"] == "no_order"
    assert result["alerts"] == result["history"] == []


def test_restart_unchanged_polls_preserve_outbox_and_cursor(tmp_path):
    path = tmp_path / "monitor.json"
    first = tick(path)
    assert first["status"] == "CONDITION_REVIEW"
    assert len(first["history"]) == len(first["alerts"]) == 1
    initial = path.read_bytes()
    assert tick(path) == first
    assert path.read_bytes() == initial
    later = tick(path, now=NOW + timedelta(seconds=2))
    assert later["cursor"]["checked_at"] > first["cursor"]["checked_at"]
    assert later["history"] == first["history"]
    assert later["alerts"] == first["alerts"]
    assert monitor.read_intraday_monitor(path) == later
    assert later["engine"]["revision"] == 1
    assert later["engine"]["whole_source_coverage"] is False
    assert later["eligibility"] is later["admitted"] is False
    raw = json.loads(path.read_text())
    state = monitor.m5_event_run_state_from_payload(raw["m5_state"])
    assert all(w.coverage_status == "INCOMPLETE" and w.scope.startswith(monitor.SCOPE + ":")
               for w in state.watermarks.watermarks())
    assert all(node["current_state"]["binding"] == later["cursor"]["binding"] for node in later["history"])


def test_failure_recovery_history_is_atomic_and_deduplicated(tmp_path):
    path = tmp_path / "monitor.json"
    tick(path)
    failed_at = NOW + timedelta(seconds=1)
    failed = monitor.tick_intraday_monitor(path, condition=condition(), observation=None,
        now=failed_at, max_age=timedelta(seconds=30))
    assert failed["status"] == "STALE_OR_UNAVAILABLE"
    assert len(failed["history"]) == 2
    assert failed["history"][-1]["event_type"] == "SOURCE_SCAN_FAILED"
    restored = tick(path, now=NOW + timedelta(seconds=3))
    assert len(restored["history"]) == len(restored["alerts"]) == 4
    assert [event["event_type"] for event in restored["history"][-2:]] == [
        "SOURCE_SCAN_RECOVERED", "PRICE_ATTRACTIVENESS_CHANGED"]
    assert monitor.read_intraday_monitor(path) == restored


def test_rehashed_cursor_and_older_event_snapshot_cannot_be_recombined(tmp_path):
    path = tmp_path / "monitor.json"
    tick(path)
    first = json.loads(path.read_text())
    monitor.tick_intraday_monitor(path, condition=condition(), observation=None,
        now=NOW + timedelta(seconds=1), max_age=timedelta(seconds=30))
    failed = json.loads(path.read_text())
    failed["m5_state"] = first["m5_state"]
    failed["snapshot_sha256"] = monitor._digest({key: value for key, value in failed.items()
        if key != "snapshot_sha256"})
    path.write_text(json.dumps(failed), encoding="utf-8")
    with pytest.raises(ValueError, match="Cursor disagrees"):
        monitor.read_intraday_monitor(path)


def test_not_triggered_initial_cursor_needs_no_fake_event(tmp_path):
    path = tmp_path / "monitor.json"
    result = tick(path, previous_price="9")
    assert result["status"] == "NOT_TRIGGERED"
    assert result["history"] == result["alerts"] == []
    assert monitor.read_intraday_monitor(path) == result
    later = NOW.replace(hour=14, minute=0)
    triggered = monitor.tick_intraday_monitor(path, condition=condition(),
        observation={**observation(later), "bar_end": later.replace(second=0).isoformat()},
        now=later, max_age=timedelta(seconds=30))
    assert triggered["status"] == "CONDITION_REVIEW"
    assert [event["event_type"] for event in triggered["history"]] == ["PRICE_ATTRACTIVENESS_CHANGED"]


def test_clock_regression_rejected_and_source_regression_cannot_advance_cursor(tmp_path):
    path = tmp_path / "monitor.json"
    first = tick(path)
    before = path.read_bytes()
    with pytest.raises(ValueError, match="Prior state"):
        tick(path, now=NOW - timedelta(seconds=1))
    assert path.read_bytes() == before
    result = monitor.tick_intraday_monitor(path, condition=condition(),
        observation=observation(NOW - timedelta(seconds=1)), now=NOW + timedelta(seconds=1),
        max_age=timedelta(seconds=30))
    assert result["status"] == "STALE_OR_UNAVAILABLE"
    assert result["cursor"]["last_source_at"] == first["cursor"]["last_source_at"]
    assert result["cursor"]["last_received_at"] == first["cursor"]["last_received_at"]


@pytest.mark.parametrize("phase", ["replace", "fsync"])
def test_atomic_failure_retains_both_old_cursor_and_m5(tmp_path, monkeypatch, phase):
    path = tmp_path / "monitor.json"
    first = tick(path)
    before = path.read_bytes()
    def fail(*args):
        raise OSError("TEST_ONLY simulated disk failure")
    with monkeypatch.context() as patch:
        patch.setattr(monitor.os, phase, fail)
        with pytest.raises(OSError):
            monitor.tick_intraday_monitor(path, condition=condition(), observation=None,
                now=NOW + timedelta(seconds=1), max_age=timedelta(seconds=30))
    assert path.read_bytes() == before
    assert monitor.read_intraday_monitor(path) == first
    assert not list(tmp_path.glob("*.tmp"))
    retried = monitor.tick_intraday_monitor(path, condition=condition(), observation=None,
        now=NOW + timedelta(seconds=1), max_age=timedelta(seconds=30))
    assert len(retried["history"]) == len(retried["alerts"]) == 2
    assert retried["cursor"]["cycle"] == first["cursor"]["cycle"] + 1
    assert monitor.tick_intraday_monitor(path, condition=condition(), observation=None,
        now=NOW + timedelta(seconds=1), max_age=timedelta(seconds=30)) == retried


def test_cross_condition_namespace_and_corrupt_state_fail_closed(tmp_path):
    path = tmp_path / "monitor.json"
    tick(path)
    before = path.read_bytes()
    with pytest.raises(ValueError, match="different condition"):
        monitor.tick_intraday_monitor(path, condition=condition(threshold="12"),
            observation=observation(), now=NOW, max_age=timedelta(seconds=30))
    assert path.read_bytes() == before
    absent = tmp_path / "actual" / "monitor.json"
    with pytest.raises(ValueError, match="ACTUAL authorization"):
        tick(absent, namespace="ACTUAL")
    assert not absent.parent.exists()
    raw = json.loads(before)
    raw["cursor"]["cycle"] += 1
    path.write_text(json.dumps(raw), encoding="utf-8")
    corrupt = path.read_bytes()
    with pytest.raises(ValueError, match="Corrupt"):
        monitor.read_intraday_monitor(path)
    with pytest.raises(ValueError, match="Corrupt"):
        tick(path)
    assert path.read_bytes() == corrupt


def test_cross_condition_m5_even_with_recomputed_envelope_hash_rejected(tmp_path):
    first, second = tmp_path / "first.json", tmp_path / "second.json"
    tick(first)
    monitor.tick_intraday_monitor(second, condition=condition(condition_id="OTHER_TEST_ONLY"),
        observation=observation(), now=NOW, max_age=timedelta(seconds=30))
    raw = json.loads(first.read_text())
    raw["m5_state"] = json.loads(second.read_text())["m5_state"]
    raw.pop("snapshot_sha256")
    raw["snapshot_sha256"] = monitor._digest(raw)
    first.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="Foreign M5"):
        monitor.read_intraday_monitor(first)


def test_two_local_writers_do_not_duplicate_events(tmp_path):
    path = tmp_path / "monitor.json"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: tick(path), range(2)))
    assert results[0] == results[1]
    assert len(monitor.read_intraday_monitor(path)["alerts"]) == 1
