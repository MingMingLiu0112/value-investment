"""TEST_ONLY local acknowledgements reuse real M5 transitions and atomic storage."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json

import pytest

from test_intraday_conditions import NOW, condition, observation
from test_intraday_monitor import tick
from value_investment_agent.application.hotspot import intraday_monitor as monitor


def acknowledge(path, view, *, now=NOW + timedelta(seconds=1), **changes):
    args = {"alert_id": view["alerts"][0]["alert_id"], "operation": "ACKNOWLEDGE",
            "expected_snapshot_sha256": view["snapshot_sha256"], "now": now}
    return monitor.transition_intraday_alert(path, **{**args, **changes})


def test_acknowledgement_real_m5_local_delivery_and_restart(tmp_path):
    path = tmp_path / "monitor.json"
    first = tick(path)
    assert {"ACKNOWLEDGE", "CANCEL"} <= set(first["alerts"][0]["available_operations"])
    acknowledged = acknowledge(path, first)
    alert = acknowledged["alerts"][0]
    assert alert["status"] == alert["user_status"] == "ACKNOWLEDGED"
    assert alert["delivery_channel"] == "LOCAL_TEST_ONLY"
    assert alert["available_operations"] == []
    assert acknowledged["cursor"] == first["cursor"]
    assert acknowledged["history"] == first["history"]
    assert acknowledged["engine"]["revision"] == first["engine"]["revision"]
    assert acknowledged["engine"]["outbox_revision"] == 3
    assert [(r["from_status"], r["to_status"]) for r in acknowledged["alert_transitions"]] == [
        ("PENDING", "SENT"), ("SENT", "DELIVERED"), ("DELIVERED", "ACKNOWLEDGED")]
    assert all(r["action"] == "no_order" for r in acknowledged["alert_transitions"])
    assert acknowledged["admitted"] is acknowledged["eligibility"] is False
    assert acknowledged["engine"]["acceptance_authority"] == "NONE"
    assert monitor.read_intraday_monitor(path) == acknowledged
    raw = json.loads(path.read_text())
    state = monitor.m5_event_run_state_from_payload(raw["m5_state"])
    assert state.outbox.alerts()[0].status == "ACKNOWLEDGED"
    assert state.outbox_revision == 3


def test_exact_retry_and_current_version_ack_are_no_write_noops(tmp_path):
    path = tmp_path / "monitor.json"
    first = tick(path)
    done = acknowledge(path, first)
    before = path.read_bytes()
    assert acknowledge(path, first, now=NOW + timedelta(seconds=2)) == done
    assert acknowledge(path, done, now=NOW + timedelta(seconds=2)) == done
    assert path.read_bytes() == before
    # Receipts survive later polls, so a retried accepted request stays a no-op.
    later = tick(path, now=NOW + timedelta(seconds=3))
    assert acknowledge(path, first, now=NOW + timedelta(seconds=4)) == later
    assert len(later["alerts"]) == 1 and later["engine"]["outbox_revision"] == 3


def test_stale_version_and_cross_file_alert_ids_do_not_write(tmp_path):
    path, other = tmp_path / "first.json", tmp_path / "second.json"
    first, foreign = tick(path), tick(other)
    # Identical condition/events produce identical raw M5 IDs; public IDs still
    # belong to their file, including when snapshot hashes happen to be equal.
    assert first["snapshot_sha256"] == foreign["snapshot_sha256"]
    assert first["alerts"][0]["alert_id"] != foreign["alerts"][0]["alert_id"]
    before = path.read_bytes()
    with pytest.raises(ValueError, match="does not belong"):
        acknowledge(path, foreign)
    assert path.read_bytes() == before
    tick(path, now=NOW + timedelta(seconds=1))
    before = path.read_bytes()
    with pytest.raises(ValueError, match="Stale"):
        acknowledge(path, first, now=NOW + timedelta(seconds=2))
    assert path.read_bytes() == before


@pytest.mark.parametrize("operation", ["RESET", "REARM", "SENT", "APPROVE"])
def test_unsupported_operations_are_explicit_not_terminal_failure_aliases(tmp_path, operation):
    path = tmp_path / "monitor.json"
    first = tick(path)
    before = path.read_bytes()
    assert first["unsupported_operations"] == ["RESET"]
    with pytest.raises(ValueError, match="Unsupported operation"):
        acknowledge(path, first, operation=operation)
    assert path.read_bytes() == before
    assert monitor.read_intraday_monitor(path)["alerts"][0]["status"] == "PENDING"


def test_bad_clocks_missing_monitor_and_bad_hash_fail_without_writes(tmp_path):
    absent = tmp_path / "absent" / "monitor.json"
    with pytest.raises(ValueError, match="does not exist"):
        monitor.transition_intraday_alert(absent, alert_id="fake", operation="ACKNOWLEDGE",
            expected_snapshot_sha256="a" * 64, now=NOW)
    assert not absent.parent.exists()
    path = tmp_path / "monitor.json"
    first = tick(path)
    before = path.read_bytes()
    for changes in ({"now": NOW.replace(tzinfo=None)}, {"now": NOW - timedelta(seconds=1)},
                    {"expected_snapshot_sha256": "bogus"}):
        with pytest.raises(ValueError):
            acknowledge(path, first, **changes)
        assert path.read_bytes() == before
    done = acknowledge(path, first)
    before = path.read_bytes()
    # Tick clocks must not regress behind lifecycle actions either.
    with pytest.raises(ValueError, match="clock precedes"):
        tick(path, now=NOW)
    assert path.read_bytes() == before
    assert monitor.read_intraday_monitor(path) == done


@pytest.mark.parametrize("phase", ["replace", "fsync"])
def test_ack_atomic_failure_then_retry_commits_exactly_once(tmp_path, monkeypatch, phase):
    path = tmp_path / "monitor.json"
    first = tick(path)
    before = path.read_bytes()
    def fail(*args):
        raise OSError("TEST_ONLY storage failure")
    with monkeypatch.context() as patch:
        patch.setattr(monitor.os, phase, fail)
        with pytest.raises(OSError):
            acknowledge(path, first)
    assert path.read_bytes() == before
    assert monitor.read_intraday_monitor(path) == first
    assert not list(tmp_path.glob("*.tmp"))
    done = acknowledge(path, first)
    assert done["engine"]["outbox_revision"] == 3


def test_existing_adapter_rearms_new_event_without_resetting_terminal_alert(tmp_path):
    path = tmp_path / "monitor.json"
    first = tick(path)
    acknowledge(path, first)
    # Use QUOTE for repeated true/false cycles; no fabricated completed-bar edit.
    quote_path = tmp_path / "quote.json"
    c = condition(input_kind="QUOTE", period="quote")
    def poll(now, price):
        return monitor.tick_intraday_monitor(quote_path, condition=c,
            observation={**observation(now), "price": price}, now=now, max_age=timedelta(seconds=30))
    triggered = poll(NOW, "11")
    done = acknowledge(quote_path, triggered)
    below = poll(NOW + timedelta(seconds=2), "9")
    again = poll(NOW + timedelta(seconds=3), "11")
    assert again["cursor"]["cycle"] > done["cursor"]["cycle"]
    assert again["alerts"][0]["status"] == "ACKNOWLEDGED"
    assert len(again["alerts"]) == 3
    assert again["alerts"][-1]["status"] == "PENDING"
    assert again["alerts"][-1]["alert_id"] != done["alerts"][0]["alert_id"]
    assert again["engine"]["outbox_revision"] == below["engine"]["outbox_revision"] == 3
    assert monitor.read_intraday_monitor(quote_path) == again


def test_corrupt_ack_receipt_is_rejected_even_when_envelope_hash_recomputed(tmp_path):
    path = tmp_path / "monitor.json"
    first = tick(path)
    acknowledge(path, first)
    raw = json.loads(path.read_text())
    raw["alert_action_receipts"][0]["outbox_revision"] = 1
    raw.pop("snapshot_sha256")
    raw["snapshot_sha256"] = monitor._digest(raw)
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="disagrees"):
        monitor.read_intraday_monitor(path)


def test_concurrent_same_ack_commits_one_transition_chain(tmp_path):
    path = tmp_path / "monitor.json"
    first = tick(path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: acknowledge(path, first), range(2)))
    assert results[0] == results[1]
    assert results[0]["engine"]["outbox_revision"] == 3
    assert len(results[0]["alert_transitions"]) == 3


def test_existing_m5_terminal_alert_cannot_be_acknowledged(tmp_path):
    path = tmp_path / "monitor.json"
    tick(path)
    raw = json.loads(path.read_text())
    state = monitor.m5_event_run_state_from_payload(raw["m5_state"])
    alert = state.outbox.alerts()[0]
    # This is an existing M5 terminal transport failure, not cancellation/expiry.
    state = monitor.apply_outbox_transition(state=state, alert_id=alert.alert_id,
        from_status="PENDING", to_status="FAILED_TERMINAL", occurred_at=NOW,
        error="TEST_ONLY_EXISTING_TRANSPORT_FAILURE")
    raw["m5_state"] = json.loads(state.to_json())
    raw.pop("snapshot_sha256")
    raw["snapshot_sha256"] = monitor._digest(raw)
    path.write_text(json.dumps(raw), encoding="utf-8")
    view = monitor.read_intraday_monitor(path)
    assert view["alerts"][0]["available_operations"] == []
    assert view["alerts"][0]["user_status"] == "FAILED_TERMINAL"
    before = path.read_bytes()
    with pytest.raises(ValueError, match="does not permit"):
        acknowledge(path, view)
    assert path.read_bytes() == before
