"""TEST_ONLY lifecycle transitions through the existing M5 replay/store contracts."""
from copy import deepcopy
from datetime import timedelta, timezone

import pytest

from test_m5_outbox_transition import OBSERVED, _initial_state, _kwargs, _legacy_run_state_payload
from value_investment_agent.m5_event_core import M5_EVENT_SCHEMA, _digest
from value_investment_agent.m5_event_outbox import (
    ALERT_CANCELLED, ALERT_EXPIRED, ALERT_PENDING, ALERT_SENT, ALERT_DELIVERED,
    ALERT_FAILED_RETRYABLE, ALERT_FAILED_TERMINAL, ALERT_ACKNOWLEDGED,
    ALERT_TERMINAL_DUPLICATE, OUTBOX_SCHEMA_V2,
)
from value_investment_agent.m5_event_outbox_state import apply_outbox_transition
from value_investment_agent.m5_event_outbox_transition import (
    OUTBOX_TRANSITION_SCHEMA, OUTBOX_TRANSITION_SCHEMA_V2, OutboxTransitionRecord,
    outbox_transition_id,
)
from value_investment_agent.m5_event_run import RUN_ATTENTION, run_event_batch
from value_investment_agent.m5_event_run_state import m5_event_run_state_from_payload
from value_investment_agent.m5_event_state_store import JsonM5EventRunStateStore, M5StateStoreConflict


def terminate(state, status=ALERT_CANCELLED, **overrides):
    alert = state.outbox.alerts()[0]
    kwargs = dict(state=state, alert_id=alert.alert_id, from_status=alert.status,
                  to_status=status, occurred_at=OBSERVED + timedelta(minutes=10),
                  reason="TEST_ONLY condition cycle invalidated", evidence_refs=("TEST_ONLY:cycle-v2",))
    if status == ALERT_EXPIRED:
        kwargs["expires_at"] = OBSERVED + timedelta(minutes=5)
    kwargs.update(overrides)
    return apply_outbox_transition(**kwargs)


def advance(state, status, minute=1):
    alert = state.outbox.alerts()[0]
    return apply_outbox_transition(state=state, alert_id=alert.alert_id,
                                  from_status=alert.status, to_status=status,
                                  occurred_at=OBSERVED + timedelta(minutes=minute),
                                  error="TEST_ONLY failure" if status in {ALERT_FAILED_RETRYABLE, ALERT_FAILED_TERMINAL} else None)


@pytest.mark.parametrize("terminal", [ALERT_CANCELLED, ALERT_EXPIRED])
@pytest.mark.parametrize("path", [(), (ALERT_SENT,), (ALERT_SENT, ALERT_DELIVERED), (ALERT_FAILED_RETRYABLE,)])
def test_lifecycle_persist_replay_dedupe_and_review(tmp_path, terminal, path):
    initial = _initial_state()
    store = JsonM5EventRunStateStore(tmp_path / "TEST_ONLY")
    store.commit(expected_revision=0, expected_sha256=None, state=initial)
    state = initial
    for minute, status in enumerate(path, 1):
        next_state = advance(state, status, minute)
        store.commit(expected_revision=state.revision, expected_sha256=state.state_sha256(), state=next_state)
        state = next_state
    before = state.to_json()
    result = terminate(state, terminal)
    assert state.to_json() == before
    assert result.revision == state.revision
    assert result.outbox_revision == state.outbox_revision + 1
    assert result.is_outbox_transition_successor_of(state)
    assert result.outbox.schema_version == OUTBOX_SCHEMA_V2
    assert result.as_policy()["outbox_transitions"]["schema_version"] == OUTBOX_TRANSITION_SCHEMA_V2
    old, alert = state.outbox.alerts()[0], result.outbox.alerts()[0]
    assert alert.status == terminal and alert.next_attempt_at is None
    assert (alert.attempts, alert.last_error, alert.sent_at, alert.delivered_at) == (old.attempts, old.last_error, old.sent_at, old.delivered_at)
    assert alert.requires_human_review and alert.action == "no_order"
    assert not result.outbox.pending(OBSERVED + timedelta(days=1))
    store.commit(expected_revision=state.revision, expected_sha256=state.state_sha256(), state=result)
    restored = store.load(state_key=result.state_key)
    assert restored.to_json() == result.to_json()
    assert terminate(state, terminal).to_json() == result.to_json()
    assert terminate(result, terminal, from_status=old.status).to_json() == result.to_json()
    with pytest.raises(M5StateStoreConflict):
        store.commit(expected_revision=state.revision, expected_sha256=state.state_sha256(), state=terminate(state, terminal, reason="TEST_ONLY stale writer"))
    replay = run_event_batch(**_kwargs(batch_id="batch-1", event_id="event-1"), state=restored)
    assert replay.health_status == RUN_ATTENTION and replay.silent_ok is False and replay.review_due
    enqueued = restored.outbox.enqueue_for_event(event=restored.event_ledger.events()[0], alert_type=alert.alert_type, now=OBSERVED)
    assert enqueued.status == ALERT_TERMINAL_DUPLICATE
    follow = run_event_batch(**_kwargs(batch_id="batch-2", event_id="event-2", at=OBSERVED + timedelta(hours=1)), state=result).state
    assert follow.clone().to_json() == follow.to_json()
    assert follow.outbox.alerts()[0].status == terminal


@pytest.mark.parametrize("overrides", [
    {"reason": None}, {"reason": " "}, {"evidence_refs": ()},
    {"evidence_refs": ("x", "x")}, {"evidence_refs": "x"},
    {"occurred_at": OBSERVED.replace(tzinfo=None)},
    {"occurred_at": OBSERVED - timedelta(seconds=1)},
    {"expires_at": OBSERVED},
])
def test_cancel_rejects_invalid_contract(overrides):
    with pytest.raises(ValueError):
        terminate(_initial_state(), **overrides)


@pytest.mark.parametrize("deadline", [None, OBSERVED.replace(tzinfo=None), OBSERVED - timedelta(seconds=1), OBSERVED + timedelta(hours=1)])
def test_expiry_rejects_missing_naive_precreation_or_unelapsed_deadline(deadline):
    with pytest.raises(ValueError):
        terminate(_initial_state(), ALERT_EXPIRED, expires_at=deadline)


def test_exact_deadline_and_timezone_identity_binding():
    state = _initial_state()
    deadline = OBSERVED + timedelta(minutes=10)
    result = terminate(state, ALERT_EXPIRED, expires_at=deadline)
    equivalent = terminate(state, ALERT_EXPIRED, expires_at=deadline.astimezone(timezone.utc), occurred_at=deadline.astimezone(timezone.utc))
    record = result.outbox_transitions[-1]
    assert record.transition_id == equivalent.outbox_transitions[-1].transition_id
    for overrides in ({"reason": "different"}, {"evidence_refs": ("different",)}, {"expires_at": deadline - timedelta(seconds=1)}):
        assert terminate(state, ALERT_EXPIRED, expires_at=overrides.get("expires_at", deadline), **{k:v for k,v in overrides.items() if k != "expires_at"}).outbox_transitions[-1].transition_id != record.transition_id


@pytest.mark.parametrize("terminal", [ALERT_CANCELLED, ALERT_EXPIRED, ALERT_FAILED_TERMINAL, ALERT_ACKNOWLEDGED])
def test_terminals_cannot_be_reopened(terminal):
    state = _initial_state()
    if terminal == ALERT_ACKNOWLEDGED:
        for minute, status in enumerate((ALERT_SENT, ALERT_DELIVERED, ALERT_ACKNOWLEDGED), 1):
            state = advance(state, status, minute)
    elif terminal == ALERT_FAILED_TERMINAL:
        state = advance(state, terminal)
    else:
        state = terminate(state, terminal)
    with pytest.raises(ValueError):
        terminate(state)
    with pytest.raises(ValueError):
        advance(state, ALERT_SENT, 20)


def test_retry_failure_transition_clock_cannot_be_backdated():
    state = advance(_initial_state(), ALERT_FAILED_RETRYABLE, 8)
    with pytest.raises(ValueError):
        terminate(state, occurred_at=OBSERVED + timedelta(minutes=7))


def test_evidence_boundaries_are_unambiguous_and_inputs_are_frozen():
    state = _initial_state()
    refs = ["TEST_ONLY:a", "TEST_ONLY:b"]
    result = terminate(state, evidence_refs=refs)
    refs.append("TEST_ONLY:later mutation")
    assert result.outbox_transitions[-1].evidence_refs == ("TEST_ONLY:a", "TEST_ONLY:b")
    joined = terminate(state, evidence_refs=("TEST_ONLY:a|TEST_ONLY:b",))
    assert joined.outbox_transitions[-1].transition_id != result.outbox_transitions[-1].transition_id


def test_v2_requires_lifecycle_history_and_v1_cannot_smuggle_new_metadata():
    state = _initial_state()
    payload = state.as_policy()
    payload["outbox_transitions"]["schema_version"] = OUTBOX_TRANSITION_SCHEMA_V2
    with pytest.raises(ValueError):
        m5_event_run_state_from_payload(payload)
    payload = advance(state, ALERT_SENT).as_policy()
    payload["outbox_transitions"]["transitions"][0]["reason"] = None
    with pytest.raises(ValueError):
        m5_event_run_state_from_payload(payload)


@pytest.mark.parametrize("field,value", [("reason", "forged"), ("evidence_refs", ["forged"]), ("expires_at", "2026-09-24T16:01:00+08:00")])
def test_immutable_metadata_tamper_rejected(field, value):
    payload = terminate(_initial_state(), ALERT_EXPIRED).as_policy()
    payload["outbox_transitions"]["transitions"][-1][field] = value
    with pytest.raises(ValueError):
        m5_event_run_state_from_payload(payload)


@pytest.mark.parametrize("target", ["outbox", "outbox_transitions"])
def test_schema_downgrade_rejected(target):
    payload = terminate(_initial_state()).as_policy()
    payload[target]["schema_version"] = M5_EVENT_SCHEMA if target == "outbox" else OUTBOX_TRANSITION_SCHEMA
    with pytest.raises(ValueError):
        m5_event_run_state_from_payload(payload)


def test_snapshot_cannot_clear_review_or_rewrite_attempts():
    original = terminate(_initial_state()).as_policy()
    for field, value in (("requires_human_review", False), ("attempts", 2), ("last_error", "forged")):
        payload = deepcopy(original)
        payload["outbox"]["alerts"][0][field] = value
        with pytest.raises(ValueError):
            m5_event_run_state_from_payload(payload)


def test_v1_serialization_and_ids_unchanged():
    state = _initial_state()
    payload = state.as_policy()
    assert payload["outbox"]["schema_version"] == M5_EVENT_SCHEMA
    assert payload["outbox_transitions"] == {"schema_version": OUTBOX_TRANSITION_SCHEMA, "transitions": []}
    assert state.clone().to_json() == state.to_json()
    old = m5_event_run_state_from_payload(_legacy_run_state_payload(state))
    assert old.clone().to_json() == old.to_json()
    sent = advance(state, ALERT_SENT)
    record = sent.outbox_transitions[-1]
    expected = "m5-outbox-" + _digest("outbox-transition", record.alert_id, ALERT_PENDING, ALERT_SENT, record.occurred_at.astimezone(timezone.utc).isoformat(), "")[:32]
    assert record.transition_id == expected == outbox_transition_id(alert_id=record.alert_id, from_status=ALERT_PENDING, to_status=ALERT_SENT, occurred_at=record.occurred_at, error=None)
    assert set(record.as_policy()) == {"outbox_revision", "transition_id", "alert_id", "from_status", "to_status", "occurred_at", "error", "action"}
    with pytest.raises(ValueError):
        OutboxTransitionRecord(outbox_revision=1, alert_id=record.alert_id, from_status=ALERT_PENDING, to_status=ALERT_SENT, occurred_at=OBSERVED, reason="must not silently enter v1")
