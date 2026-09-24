from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from value_investment_agent.m5_event_core import (
    CONFIDENCE_HIGH,
    EVENT_TYPE_NEW_FINANCIAL_REPORT,
    EVENT_STATUS_SUPERSEDED,
    NAMESPACE_SIMULATED,
    SEVERITY_HIGH,
    ChangeEventInput,
    _digest,
    _state_digest,
    event_ledger_from_payload,
)
from value_investment_agent.m5_event_dependencies import (
    KIND_FACTS,
    DependencyGraph,
    DependencyNode,
)
from value_investment_agent.m5_event_outbox import (
    ALERT_ACKNOWLEDGED,
    ALERT_DELIVERED,
    ALERT_FAILED_RETRYABLE,
    ALERT_PENDING,
    ALERT_SENT,
)
from value_investment_agent.m5_event_outbox_state import apply_outbox_transition
from value_investment_agent.m5_event_outbox_transition import (
    outbox_transition_id,
    replay_outbox_transitions,
)
from value_investment_agent.m5_event_run import (
    run_event_batch,
    run_event_batch_persisted,
)
from value_investment_agent.m5_event_run_state import (
    M5_RUN_STATE_SCHEMA_V1,
    M5EventRunState,
    m5_event_run_state_from_payload,
)
from value_investment_agent.m5_event_state_store import (
    InMemoryM5EventRunStateStore,
    JsonM5EventRunStateStore,
    M5StateStoreConflict,
)
from value_investment_agent.m5_event_watermark import (
    SOURCE_HEALTHY,
    WATERMARK_COVERAGE_COMPLETE,
    ScanWatermark,
)


TZ = timezone(timedelta(hours=8))
OBSERVED = datetime(2026, 9, 24, 16, 0, tzinfo=TZ)


def test_outbox_transition_id_canonicalizes_equivalent_instants() -> None:
    shanghai = datetime(2026, 9, 24, 16, 6, tzinfo=TZ)
    utc = datetime(2026, 9, 24, 8, 6, tzinfo=timezone.utc)

    assert shanghai == utc
    assert outbox_transition_id(
        alert_id="alert-1",
        from_status=ALERT_PENDING,
        to_status=ALERT_SENT,
        occurred_at=shanghai,
        error=None,
    ) == outbox_transition_id(
        alert_id="alert-1",
        from_status=ALERT_PENDING,
        to_status=ALERT_SENT,
        occurred_at=utc,
        error=None,
    )


def _event(*, source_event_id: str, at: datetime) -> ChangeEventInput:
    available_at = at - timedelta(minutes=5)
    return ChangeEventInput(
        source_event_id=source_event_id,
        source_id="cninfo",
        symbol="600519",
        event_type=EVENT_TYPE_NEW_FINANCIAL_REPORT,
        detected_at=available_at,
        available_at=available_at,
        effective_at=available_at,
        previous_state={},
        current_state={"value": source_event_id},
        severity=SEVERITY_HIGH,
        reason="synthetic M5 outbox transition fixture",
        evidence_refs=({"id": f"evidence-{source_event_id}"},),
        confidence=CONFIDENCE_HIGH,
        requires_human_review=True,
        namespace=NAMESPACE_SIMULATED,
    )


def _watermark(*, watermark_id: str, at: datetime) -> ScanWatermark:
    return ScanWatermark(
        watermark_id=watermark_id,
        scope="ALL",
        source="cninfo",
        coverage_through=at,
        retrieved_at=at,
        parser_version="outbox-transition-v1",
        coverage_status=WATERMARK_COVERAGE_COMPLETE,
        source_health=SOURCE_HEALTHY,
        evidence_refs=({"id": f"scan-{watermark_id}"},),
    )


def _graph() -> DependencyGraph:
    return DependencyGraph(
        (
            DependencyNode(
                node_id="facts",
                kind=KIND_FACTS,
                symbol="*",
                inputs=(),
                version="outbox-transition-v1",
                evidence_refs=({"id": "dependency-facts"},),
            ),
        )
    )


def _kwargs(*, batch_id: str, event_id: str, at: datetime = OBSERVED):
    return {
        "events": (_event(source_event_id=event_id, at=at),),
        "observed_times": (at,),
        "watermark": _watermark(watermark_id=f"scan-{batch_id}", at=at),
        "graph": _graph(),
        "run_id": "m5-outbox-transition-run",
        "generated_at": at,
        "batch_id": batch_id,
    }


def _legacy_event_id(payload) -> str:
    refs = tuple(dict(item) for item in payload["evidence_refs"])
    fingerprint = _digest(
        "event",
        payload["namespace"],
        payload["symbol"],
        payload["source_event_id"],
        payload["event_type"],
        _state_digest(payload["previous_state"]),
        _state_digest(payload["current_state"]),
        payload["severity"],
        payload["reason"],
        _state_digest({"refs": refs}),
        payload["confidence"],
        payload.get("correction_of_event_id") or "",
        payload.get("supersedes_event_id") or "",
    )
    return "m5-" + _digest("event-id", fingerprint)[:32]


def _initial_state() -> M5EventRunState:
    return run_event_batch(
        **_kwargs(batch_id="batch-1", event_id="event-1"),
        state=None,
    ).state


def _legacy_run_state_payload(state: M5EventRunState) -> dict:
    payload = state.as_policy()
    event = payload["event_ledger"]["events"][0]
    event.pop("source_id")
    event.pop("event_identity_version", None)
    legacy_event_id = _legacy_event_id(event)
    event["event_id"] = legacy_event_id
    payload["checkpoints"]["checkpoints"][0]["ingested_event_ids"] = [
        legacy_event_id
    ]
    alert = payload["outbox"]["alerts"][0]
    alert["event_id"] = legacy_event_id
    alert["dedupe_key"] = f"event:{legacy_event_id}:{alert['alert_type']}"
    alert["alert_id"] = "m5-alert-" + _digest(
        "alert",
        alert["alert_type"],
        legacy_event_id,
        alert["dedupe_key"],
        alert["created_at"],
    )[:32]
    payload["schema_version"] = M5_RUN_STATE_SCHEMA_V1
    payload.pop("outbox_revision")
    payload.pop("outbox_transitions")
    return payload


def test_legacy_run_state_round_trips_and_persists(tmp_path) -> None:
    legacy_payload = _legacy_run_state_payload(_initial_state())
    legacy_state = m5_event_run_state_from_payload(legacy_payload)
    assert "source_id" not in legacy_state.event_ledger.as_policy()["events"][0]
    assert legacy_state.clone().to_json() == legacy_state.to_json()

    store = JsonM5EventRunStateStore(tmp_path / "m5-state")
    store.commit(
        expected_revision=0,
        expected_sha256=None,
        state=legacy_state,
    )
    restored = store.load(state_key=legacy_state.state_key)
    assert restored is not None
    assert restored.to_json() == legacy_state.to_json()


def test_outbox_transitions_persist_without_advancing_batch_revision(tmp_path) -> None:
    store = JsonM5EventRunStateStore(tmp_path / "m5-state")
    initial = _initial_state()
    store.commit(expected_revision=0, expected_sha256=None, state=initial)
    alert_id = initial.outbox.alerts()[0].alert_id

    current = store.load(state_key=initial.state_key)
    assert current is not None
    for offset, to_status in enumerate(
        (ALERT_SENT, ALERT_DELIVERED, ALERT_ACKNOWLEDGED),
        start=1,
    ):
        next_state = apply_outbox_transition(
            state=current,
            alert_id=alert_id,
            from_status=current.outbox.alerts()[0].status,
            to_status=to_status,
            occurred_at=OBSERVED + timedelta(minutes=offset),
        )
        store.commit(
            expected_revision=current.revision,
            expected_sha256=current.state_sha256(),
            state=next_state,
        )
        current = store.load(state_key=initial.state_key)
        assert current is not None

    assert current.revision == 1
    assert current.outbox_revision == 3
    assert current.outbox.alerts()[0].status == ALERT_ACKNOWLEDGED
    assert tuple(item.to_status for item in current.outbox_transitions) == (
        ALERT_SENT,
        ALERT_DELIVERED,
        ALERT_ACKNOWLEDGED,
    )

    restored = JsonM5EventRunStateStore(tmp_path / "m5-state").load(
        state_key=initial.state_key
    )
    assert restored is not None
    assert restored.to_json() == current.to_json()


def test_outbox_transition_replay_is_idempotent(tmp_path) -> None:
    store = JsonM5EventRunStateStore(tmp_path / "m5-state")
    initial = _initial_state()
    store.commit(expected_revision=0, expected_sha256=None, state=initial)
    current = store.load(state_key=initial.state_key)
    assert current is not None
    alert_id = current.outbox.alerts()[0].alert_id
    occurred_at = OBSERVED + timedelta(minutes=1)

    transitioned = apply_outbox_transition(
        state=current,
        alert_id=alert_id,
        from_status=ALERT_PENDING,
        to_status=ALERT_SENT,
        occurred_at=occurred_at,
    )
    replayed = apply_outbox_transition(
        state=transitioned,
        alert_id=alert_id,
        from_status=ALERT_PENDING,
        to_status=ALERT_SENT,
        occurred_at=occurred_at,
    )

    assert replayed.to_json() == transitioned.to_json()
    assert replayed.outbox_revision == 1
    assert len(replayed.outbox_transitions) == 1


def test_outbox_transition_stale_writer_cannot_overwrite(tmp_path) -> None:
    store = JsonM5EventRunStateStore(tmp_path / "m5-state")
    initial = _initial_state()
    store.commit(expected_revision=0, expected_sha256=None, state=initial)
    stale = store.load(state_key=initial.state_key)
    assert stale is not None
    alert_id = stale.outbox.alerts()[0].alert_id
    sent = apply_outbox_transition(
        state=stale,
        alert_id=alert_id,
        from_status=ALERT_PENDING,
        to_status=ALERT_SENT,
        occurred_at=OBSERVED + timedelta(minutes=1),
    )
    failed = apply_outbox_transition(
        state=stale,
        alert_id=alert_id,
        from_status=ALERT_PENDING,
        to_status=ALERT_FAILED_RETRYABLE,
        occurred_at=OBSERVED + timedelta(minutes=1),
        error="synthetic transport failure",
    )
    store.commit(
        expected_revision=stale.revision,
        expected_sha256=stale.state_sha256(),
        state=sent,
    )

    with pytest.raises(M5StateStoreConflict, match="digest changed"):
        store.commit(
            expected_revision=stale.revision,
            expected_sha256=stale.state_sha256(),
            state=failed,
        )

    persisted = store.load(state_key=initial.state_key)
    assert persisted is not None
    assert persisted.outbox.alerts()[0].status == ALERT_SENT


def test_event_batch_successor_cannot_rewrite_prior_event_history(tmp_path) -> None:
    store = JsonM5EventRunStateStore(tmp_path / "m5-state")
    initial = _initial_state()
    store.commit(expected_revision=0, expected_sha256=None, state=initial)
    current = store.load(state_key=initial.state_key)
    assert current is not None
    alert_id = current.outbox.alerts()[0].alert_id
    sent = apply_outbox_transition(
        state=current,
        alert_id=alert_id,
        from_status=ALERT_PENDING,
        to_status=ALERT_SENT,
        occurred_at=OBSERVED + timedelta(minutes=1),
    )
    store.commit(
        expected_revision=current.revision,
        expected_sha256=current.state_sha256(),
        state=sent,
    )
    run_event_batch_persisted(
        store=store,
        **_kwargs(
            batch_id="batch-2",
            event_id="event-2",
            at=OBSERVED + timedelta(minutes=10),
        ),
    )
    persisted = store.load(state_key=initial.state_key)
    assert persisted is not None

    third = run_event_batch(
        **_kwargs(
            batch_id="batch-3",
            event_id="event-3",
            at=OBSERVED + timedelta(minutes=20),
        ),
        state=persisted,
    ).state
    forged_event_payload = third.event_ledger.as_policy()
    rewritten_ingested_at = OBSERVED + timedelta(minutes=7)
    forged_event_payload["events"][-2][
        "ingested_at"
    ] = rewritten_ingested_at.isoformat()
    forged_event_ledger = event_ledger_from_payload(forged_event_payload)
    forged_outbox = replay_outbox_transitions(
        events=forged_event_ledger.events(),
        transitions=third.outbox_transitions,
    )
    forged = replace(
        third,
        event_ledger=forged_event_ledger,
        outbox=forged_outbox,
    )

    assert forged.is_event_batch_successor_of(persisted) is False
    with pytest.raises(
        M5StateStoreConflict,
        match="round-trip|Event batch successor",
    ):
        store.commit(
            expected_revision=persisted.revision,
            expected_sha256=persisted.state_sha256(),
            state=forged,
        )

    reloaded = store.load(state_key=initial.state_key)
    assert reloaded is not None
    assert reloaded.to_json() == persisted.to_json()


def test_event_batch_successor_requires_explicit_new_supersede_target(
    tmp_path,
) -> None:
    store = JsonM5EventRunStateStore(tmp_path / "m5-state")
    initial = _initial_state()
    store.commit(expected_revision=0, expected_sha256=None, state=initial)
    run_event_batch_persisted(
        store=store,
        **_kwargs(
            batch_id="batch-2",
            event_id="event-2",
            at=OBSERVED + timedelta(minutes=10),
        ),
    )
    persisted = store.load(state_key=initial.state_key)
    assert persisted is not None
    third = run_event_batch(
        **_kwargs(
            batch_id="batch-3",
            event_id="event-3",
            at=OBSERVED + timedelta(minutes=20),
        ),
        state=persisted,
    ).state
    forged_event = third.event_ledger.events()[-2]
    third.event_ledger._events[forged_event.event_id] = replace(
        forged_event,
        status=EVENT_STATUS_SUPERSEDED,
    )

    assert third.is_event_batch_successor_of(persisted) is False
    with pytest.raises(
        M5StateStoreConflict,
        match="round-trip|Event batch successor",
    ):
        store.commit(
            expected_revision=persisted.revision,
            expected_sha256=persisted.state_sha256(),
            state=third,
        )

    reloaded = store.load(state_key=initial.state_key)
    assert reloaded is not None
    assert reloaded.to_json() == persisted.to_json()


def test_store_rejects_invalid_successor_that_fails_round_trip(tmp_path) -> None:
    store = JsonM5EventRunStateStore(tmp_path / "m5-state")
    initial = _initial_state()
    store.commit(expected_revision=0, expected_sha256=None, state=initial)
    run_event_batch_persisted(
        store=store,
        **_kwargs(
            batch_id="batch-2",
            event_id="event-2",
            at=OBSERVED + timedelta(minutes=10),
        ),
    )
    persisted = store.load(state_key=initial.state_key)
    assert persisted is not None
    third = run_event_batch(
        **_kwargs(
            batch_id="batch-3",
            event_id="event-3",
            at=OBSERVED + timedelta(minutes=20),
        ),
        state=persisted,
    ).state
    target = third.event_ledger.events()[0]
    successor = third.event_ledger.events()[-1]
    third.event_ledger._events[target.event_id] = replace(
        target,
        status=EVENT_STATUS_SUPERSEDED,
    )
    third.event_ledger._events[successor.event_id] = replace(
        successor,
        correction_of_event_id=target.event_id,
        source_id="different-source",
    )

    assert third.is_event_batch_successor_of(persisted) is True
    with pytest.raises(M5StateStoreConflict, match="round-trip"):
        store.commit(
            expected_revision=persisted.revision,
            expected_sha256=persisted.state_sha256(),
            state=third,
        )

    reloaded = store.load(state_key=initial.state_key)
    assert reloaded is not None
    assert reloaded.to_json() == persisted.to_json()


def test_failed_transition_retry_and_follow_on_batch_preserve_history(tmp_path) -> None:
    store = JsonM5EventRunStateStore(tmp_path / "m5-state")
    initial = _initial_state()
    store.commit(expected_revision=0, expected_sha256=None, state=initial)
    current = store.load(state_key=initial.state_key)
    assert current is not None
    alert_id = current.outbox.alerts()[0].alert_id

    failed = apply_outbox_transition(
        state=current,
        alert_id=alert_id,
        from_status=ALERT_PENDING,
        to_status=ALERT_FAILED_RETRYABLE,
        occurred_at=OBSERVED + timedelta(minutes=1),
        error="synthetic transport failure",
    )
    store.commit(
        expected_revision=current.revision,
        expected_sha256=current.state_sha256(),
        state=failed,
    )
    persisted_failed = store.load(state_key=initial.state_key)
    assert persisted_failed is not None
    retry_at = failed.outbox.alerts()[0].next_attempt_at
    assert retry_at is not None
    retried = apply_outbox_transition(
        state=persisted_failed,
        alert_id=alert_id,
        from_status=ALERT_FAILED_RETRYABLE,
        to_status=ALERT_SENT,
        occurred_at=retry_at,
    )
    store.commit(
        expected_revision=persisted_failed.revision,
        expected_sha256=persisted_failed.state_sha256(),
        state=retried,
    )

    next_batch = run_event_batch_persisted(
        store=store,
        **_kwargs(
            batch_id="batch-2",
            event_id="event-2",
            at=OBSERVED + timedelta(minutes=10),
        ),
    )

    assert next_batch.state.revision == 2
    assert next_batch.state.outbox_revision == 2
    assert len(next_batch.state.outbox_transitions) == 2
    assert next_batch.state.outbox_transitions == retried.outbox_transitions
    assert len(next_batch.state.outbox.alerts()) == 2


def test_transition_history_tampering_fails_closed() -> None:
    state = _initial_state()
    alert_id = state.outbox.alerts()[0].alert_id
    transitioned = apply_outbox_transition(
        state=state,
        alert_id=alert_id,
        from_status=ALERT_PENDING,
        to_status=ALERT_SENT,
        occurred_at=OBSERVED + timedelta(minutes=1),
    )

    with pytest.raises(ValueError, match="transition history"):
        M5EventRunState(
            state_key=transitioned.state_key,
            namespace=transitioned.namespace,
            revision=transitioned.revision,
            event_ledger=transitioned.event_ledger,
            watermarks=transitioned.watermarks,
            checkpoints=transitioned.checkpoints,
            outbox=transitioned.outbox,
            batch_records=transitioned.batch_records,
            outbox_revision=0,
            outbox_transitions=(),
        )

    forged_transition = transitioned.as_policy()
    forged_transition["outbox_transitions"]["transitions"][0][
        "occurred_at"
    ] = (OBSERVED + timedelta(minutes=2)).isoformat()
    with pytest.raises(ValueError, match="transition id"):
        m5_event_run_state_from_payload(forged_transition)


def test_legacy_v1_state_without_transitions_remains_readable() -> None:
    state = _initial_state()
    payload = state.as_policy()
    payload["schema_version"] = M5_RUN_STATE_SCHEMA_V1
    payload.pop("outbox_revision")
    payload.pop("outbox_transitions")

    restored = m5_event_run_state_from_payload(payload)
    assert restored.outbox_revision == 0
    assert restored.outbox_transitions == ()
    assert restored.outbox.alerts()[0].status == ALERT_PENDING
