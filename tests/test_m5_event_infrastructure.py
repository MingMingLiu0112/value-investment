from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from value_investment_agent.investment_decision import ACTION_NO_ORDER
from value_investment_agent.m5_event_checkpoint import (
    CHECKPOINT_COMMITTED,
    CHECKPOINT_FAILED,
    CHECKPOINT_RUNNING,
    CheckpointLedger,
    checkpoint_ledger_from_payload,
)
from value_investment_agent.m5_event_core import (
    CONFIDENCE_HIGH,
    EVENT_STATUS_ACTIVE,
    EVENT_STATUS_SUPERSEDED,
    EVENT_TYPE_DIVIDEND_CHANGE,
    EVENT_TYPE_NEW_FINANCIAL_REPORT,
    EVENT_TYPE_PRICE_ATTRACTIVENESS_CHANGED,
    EVENT_TYPE_SOURCE_SCAN_FAILED,
    EVENT_TYPE_THESIS_BREAKER_TRIGGERED,
    INGEST_ACCEPTED,
    INGEST_CONFLICT_REJECTED,
    INGEST_CORRECTION_ACCEPTED,
    INGEST_DUPLICATE,
    INGEST_FUTURE_REJECTED,
    INGEST_OBSERVED_TIME_REGRESSION_REJECTED,
    NAMESPACE_SIMULATED,
    SEVERITY_CRITICAL,
    SEVERITY_HIGH,
    SEVERITY_LOW,
    ChangeEventInput,
    EventLedger,
    event_ledger_from_payload,
)
from value_investment_agent.m5_event_dependencies import (
    KIND_CURRENT_STATUS,
    KIND_DECISION_REVIEW,
    KIND_DISTRIBUTION_HISTORY,
    KIND_ENTRY_CONSISTENCY,
    KIND_FACTS,
    KIND_MODEL_VALIDITY,
    KIND_PRICE_ATTRACTIVENESS,
    KIND_PRICE_BRIDGE,
    KIND_THESIS,
    KIND_VALUATION_INPUTS,
    KIND_VALUATION_RESULT,
    DependencyGraph,
    DependencyNode,
)
from value_investment_agent.m5_event_run import (
    RUN_ATTENTION,
    run_event_batch,
)
from value_investment_agent.m5_event_outbox import (
    ALERT_ACKNOWLEDGED,
    ALERT_DELIVERED,
    ALERT_DUPLICATE,
    ALERT_ENQUEUED,
    ALERT_FAILED_RETRYABLE,
    ALERT_PENDING,
    ALERT_SENT,
    ALERT_TYPE_CRITICAL_BREAKER,
    ALERT_TYPE_REVIEW_DUE,
    ALERT_TYPE_SYSTEM_HEALTH,
    OutboxLedger,
    outbox_ledger_from_payload,
)
from value_investment_agent.m5_event_watermark import (
    LOCK_ACQUIRED,
    LOCK_ALREADY_HELD,
    LOCK_CONFLICT,
    LOCK_RENEWED,
    LOCK_RELEASED,
    LOCK_TOKEN_MISMATCH,
    SOURCE_HEALTHY,
    SOURCE_OUTAGE,
    WATERMARK_ACCEPTED,
    WATERMARK_DUPLICATE,
    WATERMARK_REGRESSION_REJECTED,
    WATERMARK_COVERAGE_COMPLETE,
    ScanWatermark,
    TaskLockStore,
    WatermarkLedger,
)


TZ = timezone(timedelta(hours=8))
OBSERVED = datetime(2026, 9, 24, 16, 0, tzinfo=TZ)
OBSERVED_LATER = OBSERVED + timedelta(minutes=10)


def _dt(hour: int, minute: int = 0, day: int = 24) -> datetime:
    return datetime(2026, 9, day, hour, minute, tzinfo=TZ)


def _event(
    *,
    source_event_id: str,
    symbol: str = "600519",
    event_type: str = EVENT_TYPE_NEW_FINANCIAL_REPORT,
    detected_at: datetime = OBSERVED,
    available_at: datetime = OBSERVED,
    severity: str = SEVERITY_HIGH,
    previous_state: dict | None = None,
    current_state: dict | None = None,
    correction_of_event_id: str | None = None,
    supersedes_event_id: str | None = None,
) -> ChangeEventInput:
    return ChangeEventInput(
        source_event_id=source_event_id,
        symbol=symbol,
        event_type=event_type,
        detected_at=detected_at,
        available_at=available_at,
        effective_at=available_at,
        previous_state=previous_state or {},
        current_state=current_state or {"value": "1.0"},
        severity=severity,
        reason="synthetic M5 fixture",
        evidence_refs=({"id": f"evidence-{source_event_id}"},),
        confidence=CONFIDENCE_HIGH,
        requires_human_review=True,
        correction_of_event_id=correction_of_event_id,
        supersedes_event_id=supersedes_event_id,
        namespace=NAMESPACE_SIMULATED,
    )


def _ledger() -> EventLedger:
    return EventLedger(namespace=NAMESPACE_SIMULATED)


def _watermark(
    *,
    watermark_id: str = "scan-20260924",
    coverage_through: datetime = OBSERVED,
    retrieved_at: datetime = OBSERVED,
    source_health: str = SOURCE_HEALTHY,
) -> ScanWatermark:
    return ScanWatermark(
        watermark_id=watermark_id,
        scope="ALL",
        source="cninfo",
        coverage_through=coverage_through,
        retrieved_at=retrieved_at,
        parser_version="fixture-v1",
        coverage_status=WATERMARK_COVERAGE_COMPLETE,
        source_health=source_health,
        evidence_refs=({"id": f"scan-{watermark_id}"},),
    )


def test_event_acceptance_has_deterministic_identity_and_round_trip():
    ledger = _ledger()
    event = _event(source_event_id="600519-report-001")
    result = ledger.append(event, observed_at=OBSERVED)

    assert result.status == INGEST_ACCEPTED
    assert result.event is not None
    assert result.event.event_id.startswith("m5-")
    assert result.event.sequence == 1
    assert result.event.status == EVENT_STATUS_ACTIVE

    restored = event_ledger_from_payload(ledger.as_policy())
    assert len(restored) == 1
    assert restored.events()[0] == result.event
    assert restored.events()[0].source_fingerprint == event.source_fingerprint


def test_legacy_event_id_fallback_requires_source_id_to_be_absent():
    ledger = _ledger()
    ledger.append(
        _event(source_event_id="600519-report-legacy"),
        observed_at=OBSERVED,
    )
    payload = ledger.as_policy()
    raw = payload["events"][0]
    raw.pop("source_id")
    raw["event_id"] = "m5-0ce1fd855cc78a903589a628b7b44135"

    restored = event_ledger_from_payload(payload)
    assert restored.events()[0].source_id == "unspecified-source"
    assert restored.events()[0].event_id == raw["event_id"]

    raw["source_id"] = "cninfo"
    with pytest.raises(ValueError, match="id does not match"):
        event_ledger_from_payload(payload)


def test_exact_duplicate_is_ignored_without_new_sequence():
    ledger = _ledger()
    event = _event(source_event_id="600519-report-001")
    ledger.append(event, observed_at=OBSERVED)
    duplicate = ledger.append(event, observed_at=OBSERVED_LATER)

    assert duplicate.status == INGEST_DUPLICATE
    assert duplicate.duplicate_event_id == ledger.events()[0].event_id
    assert len(ledger) == 1


def test_changed_source_without_correction_fails_closed():
    ledger = _ledger()
    ledger.append(
        _event(source_event_id="600519-report-001"),
        observed_at=OBSERVED,
    )
    changed = _event(
        source_event_id="600519-report-001",
        current_state={"value": "2.0"},
    )
    result = ledger.append(changed, observed_at=OBSERVED_LATER)

    assert result.status == INGEST_CONFLICT_REJECTED
    assert result.event is None
    assert len(ledger) == 1


def test_explicit_correction_supersedes_previous_event():
    ledger = _ledger()
    original = ledger.append(
        _event(source_event_id="600519-report-001"),
        observed_at=OBSERVED,
    ).event
    assert original is not None
    correction = _event(
        source_event_id="600519-report-001",
        current_state={"value": "2.0"},
        correction_of_event_id=original.event_id,
    )
    result = ledger.append(correction, observed_at=OBSERVED_LATER)

    assert result.status == INGEST_CORRECTION_ACCEPTED
    assert result.superseded_event_ids == (original.event_id,)
    assert ledger.get(original.event_id).status == EVENT_STATUS_SUPERSEDED
    assert ledger.active_events()[0].current_state == {"value": "2.0"}


def test_explicit_correction_requires_same_source_event_identity():
    ledger = _ledger()
    original = ledger.append(
        _event(source_event_id="600519-report-001"),
        observed_at=OBSERVED,
    ).event
    assert original is not None
    correction = _event(
        source_event_id="600519-report-002",
        current_state={"value": "2.0"},
        correction_of_event_id=original.event_id,
    )

    result = ledger.append(correction, observed_at=OBSERVED_LATER)

    assert result.status == INGEST_CONFLICT_REJECTED
    assert result.event is None
    assert len(ledger) == 1
    assert ledger.get(original.event_id).status == EVENT_STATUS_ACTIVE


def test_serialized_ledger_rejects_superseded_event_without_successor():
    ledger = _ledger()
    original = ledger.append(
        _event(source_event_id="600519-report-001"),
        observed_at=OBSERVED,
    ).event
    assert original is not None
    ledger.append(
        _event(
            source_event_id="600519-report-001",
            current_state={"value": "2.0"},
            correction_of_event_id=original.event_id,
        ),
        observed_at=OBSERVED_LATER,
    )
    payload = ledger.as_policy()
    payload["events"] = payload["events"][:1]

    with pytest.raises(ValueError, match="missing a successor"):
        event_ledger_from_payload(payload)


def test_serialized_ledger_rejects_active_correction_target():
    ledger = _ledger()
    original = ledger.append(
        _event(source_event_id="600519-report-001"),
        observed_at=OBSERVED,
    ).event
    assert original is not None
    ledger.append(
        _event(
            source_event_id="600519-report-001",
            current_state={"value": "2.0"},
            correction_of_event_id=original.event_id,
        ),
        observed_at=OBSERVED_LATER,
    )
    payload = ledger.as_policy()
    payload["events"][0]["status"] = EVENT_STATUS_ACTIVE

    with pytest.raises(ValueError, match="target status is not superseded"):
        event_ledger_from_payload(payload)


def test_serialized_ledger_rejects_missing_or_mismatched_last_observed_at():
    ledger = _ledger()
    ledger.append(
        _event(source_event_id="600519-report-001"),
        observed_at=OBSERVED,
    )
    payload = ledger.as_policy()

    missing = dict(payload)
    missing.pop("last_observed_at")
    with pytest.raises(ValueError, match="must record last_observed_at"):
        event_ledger_from_payload(missing)

    mismatched = dict(payload)
    mismatched["last_observed_at"] = OBSERVED_LATER.isoformat()
    with pytest.raises(ValueError, match="does not match the final accepted event"):
        event_ledger_from_payload(mismatched)


def test_late_event_is_accepted_without_reordering_history():
    ledger = _ledger()
    event = _event(
        source_event_id="600519-late-001",
        available_at=_dt(9, 0, day=23),
        detected_at=_dt(9, 1, day=23),
    )
    result = ledger.append(
        event,
        observed_at=OBSERVED,
        coverage_watermark=_watermark(coverage_through=OBSERVED),
    )

    assert result.status == INGEST_ACCEPTED
    assert result.is_late is True
    assert ledger.ordered_by_available_at()[0].available_at == event.available_at


def test_future_event_is_rejected_at_replay_boundary():
    future = _event(
        source_event_id="600519-future-001",
        detected_at=OBSERVED_LATER,
        available_at=OBSERVED_LATER,
    )
    result = _ledger().append(future, observed_at=OBSERVED)

    assert result.status == INGEST_FUTURE_REJECTED
    assert result.event is None


def test_observed_processing_time_cannot_move_backwards():
    ledger = _ledger()
    ledger.append(_event(source_event_id="600519-a"), observed_at=OBSERVED_LATER)
    result = ledger.append(
        _event(source_event_id="600519-b"),
        observed_at=OBSERVED,
    )

    assert result.status == INGEST_OBSERVED_TIME_REGRESSION_REJECTED
    assert len(ledger) == 1


def test_out_of_order_available_dates_are_exposed_in_pit_order():
    ledger = _ledger()
    ledger.append(
        _event(
            source_event_id="600519-later",
            available_at=_dt(15),
            detected_at=_dt(15),
        ),
        observed_at=OBSERVED_LATER,
    )
    ledger.append(
        _event(
            source_event_id="600519-earlier",
            available_at=_dt(9),
            detected_at=_dt(9),
        ),
        observed_at=OBSERVED_LATER,
    )

    ordered = ledger.ordered_by_available_at()
    assert [item.source_event_id for item in ordered] == [
        "600519-earlier",
        "600519-later",
    ]


def test_system_health_event_requires_system_symbol():
    with pytest.raises(ValueError, match="SYSTEM"):
        _event(
            source_event_id="cninfo-outage",
            event_type=EVENT_TYPE_SOURCE_SCAN_FAILED,
        )

    system = _event(
        source_event_id="cninfo-outage",
        symbol="SYSTEM",
        event_type=EVENT_TYPE_SOURCE_SCAN_FAILED,
        severity=SEVERITY_CRITICAL,
    )
    assert system.symbol == "SYSTEM"


def test_watermark_advance_is_monotonic_and_rejects_regression():
    store = WatermarkLedger()
    first = _watermark(coverage_through=_dt(15, day=23))
    later = _watermark(
        watermark_id="scan-20260924-later",
        coverage_through=OBSERVED,
        retrieved_at=OBSERVED,
    )

    assert store.advance(first).status == WATERMARK_ACCEPTED
    assert store.advance(later).status == WATERMARK_ACCEPTED
    assert store.current(scope="ALL", source="cninfo") == later

    earlier = _watermark(
        watermark_id="scan-20260924-earlier",
        coverage_through=_dt(9, day=23),
        retrieved_at=_dt(9, day=23),
    )
    result = store.advance(earlier)
    assert result.status == WATERMARK_REGRESSION_REJECTED
    assert result.watermark is None


def test_equal_watermark_is_duplicate_and_covers_boundary():
    store = WatermarkLedger()
    first = _watermark()
    assert store.advance(first).status == WATERMARK_ACCEPTED
    duplicate = _watermark(watermark_id="same-coverage")
    result = store.advance(duplicate)
    assert result.status == WATERMARK_DUPLICATE
    assert result.watermark == first
    assert first.covers(OBSERVED) is True


def test_task_lock_blocks_second_owner_and_renews_with_token():
    store = TaskLockStore()
    acquired = store.acquire(
        scope="M5-scan",
        owner="worker-a",
        token="token-a",
        now=OBSERVED,
        lease_seconds=60,
    )
    assert acquired.status == LOCK_ACQUIRED
    assert acquired.lock is not None

    conflict = store.acquire(
        scope="M5-scan",
        owner="worker-b",
        token="token-b",
        now=OBSERVED + timedelta(seconds=5),
        lease_seconds=60,
    )
    assert conflict.status == LOCK_CONFLICT
    assert conflict.conflicting_lock == acquired.lock

    same_owner = store.acquire(
        scope="M5-scan",
        owner="worker-a",
        token="token-a",
        now=OBSERVED + timedelta(seconds=5),
        lease_seconds=60,
    )
    assert same_owner.status == LOCK_ALREADY_HELD

    renewed = store.renew(
        scope="M5-scan",
        owner="worker-a",
        token="token-a",
        now=OBSERVED + timedelta(seconds=30),
        lease_seconds=120,
    )
    assert renewed.status == LOCK_RENEWED
    assert renewed.lock.expires_at == OBSERVED + timedelta(seconds=150)

    wrong = store.release(
        scope="M5-scan",
        owner="worker-a",
        token="wrong",
        now=OBSERVED + timedelta(seconds=40),
    )
    assert wrong.status == LOCK_TOKEN_MISMATCH

    released = store.release(
        scope="M5-scan",
        owner="worker-a",
        token="token-a",
        now=OBSERVED + timedelta(seconds=40),
    )
    assert released.status == LOCK_RELEASED


def test_task_lock_rejects_cross_owner_token_and_time_regression():
    store = TaskLockStore()
    store.acquire(
        scope="M5-scan",
        owner="worker-a",
        token="shared-token",
        now=OBSERVED,
        lease_seconds=60,
    )

    cross_owner = store.acquire(
        scope="M5-scan",
        owner="worker-b",
        token="shared-token",
        now=OBSERVED + timedelta(seconds=5),
        lease_seconds=60,
    )
    assert cross_owner.status == LOCK_CONFLICT

    with pytest.raises(ValueError, match="renewal time cannot precede"):
        store.renew(
            scope="M5-scan",
            owner="worker-a",
            token="shared-token",
            now=OBSERVED - timedelta(seconds=1),
            lease_seconds=60,
        )
    with pytest.raises(ValueError, match="release time cannot precede"):
        store.release(
            scope="M5-scan",
            owner="worker-a",
            token="shared-token",
            now=OBSERVED - timedelta(seconds=1),
        )


def test_checkpoint_commit_and_failure_are_recorded():
    store = CheckpointLedger()
    started = store.start(
        run_id="M5-20260924",
        scope="ALL",
        started_at=OBSERVED,
        evidence_refs=({"id": "checkpoint-fixture"},),
    )
    assert started.status == CHECKPOINT_RUNNING
    checkpoint = started.checkpoint
    assert checkpoint is not None

    duplicate = store.start(
        run_id="M5-20260924",
        scope="ALL",
        started_at=OBSERVED_LATER,
        evidence_refs=({"id": "checkpoint-fixture"},),
    )
    assert duplicate.status == LOCK_CONFLICT

    committed = store.commit(
        checkpoint_id=checkpoint.checkpoint_id,
        completed_at=OBSERVED_LATER,
        last_sequence=2,
        watermark_ids=("scan-20260924",),
        ingested_event_ids=("m5-event-a", "m5-event-b"),
    )
    assert committed.status == CHECKPOINT_COMMITTED
    assert committed.checkpoint.last_sequence == 2

    failed_start = store.start(
        run_id="M5-20260924-failed",
        scope="ALL",
        started_at=OBSERVED,
        evidence_refs=({"id": "checkpoint-fixture"},),
    )
    failed = store.fail(
        checkpoint_id=failed_start.checkpoint.checkpoint_id,
        completed_at=OBSERVED_LATER,
        error="fixture scan interruption",
    )
    assert failed.status == CHECKPOINT_FAILED
    assert failed.checkpoint.error == "fixture scan interruption"


def test_checkpoint_ledger_round_trip_and_rejects_regression():
    store = CheckpointLedger()
    first = store.start(
        run_id="M5-round-trip",
        scope="ALL",
        started_at=OBSERVED,
        evidence_refs=({"id": "checkpoint-round-trip"},),
    ).checkpoint
    assert first is not None
    store.commit(
        checkpoint_id=first.checkpoint_id,
        completed_at=OBSERVED_LATER,
        last_sequence=2,
        watermark_ids=("scan-1",),
        ingested_event_ids=("event-1", "event-2"),
    )
    second_started = OBSERVED_LATER + timedelta(minutes=10)
    second = store.start(
        run_id="M5-round-trip",
        scope="ALL",
        started_at=second_started,
        evidence_refs=({"id": "checkpoint-round-trip-2"},),
    ).checkpoint
    assert second is not None
    store.commit(
        checkpoint_id=second.checkpoint_id,
        completed_at=second_started + timedelta(minutes=5),
        last_sequence=3,
        watermark_ids=("scan-2",),
        ingested_event_ids=("event-3",),
    )

    restored = checkpoint_ledger_from_payload(store.as_policy())
    assert restored.as_policy() == store.as_policy()

    payload = store.as_policy()
    payload["checkpoints"][1]["last_sequence"] = 1
    with pytest.raises(ValueError, match="sequence cannot regress"):
        checkpoint_ledger_from_payload(payload)

    with pytest.raises(ValueError, match="prior terminal checkpoint"):
        store.start(
            run_id="M5-round-trip",
            scope="ALL",
            started_at=OBSERVED,
            evidence_refs=({"id": "checkpoint-regression"},),
        )


def test_outbox_deduplicates_normal_alerts_but_retains_critical_events():
    outbox = OutboxLedger()
    ledger = _ledger()
    first = ledger.append(
        _event(
            source_event_id="600519-thesis",
            event_type=EVENT_TYPE_THESIS_BREAKER_TRIGGERED,
            severity=SEVERITY_CRITICAL,
        ),
        observed_at=OBSERVED,
    ).event
    second = ledger.append(
        _event(
            source_event_id="600519-thesis-2",
            event_type=EVENT_TYPE_THESIS_BREAKER_TRIGGERED,
            severity=SEVERITY_CRITICAL,
        ),
        observed_at=OBSERVED_LATER,
    ).event

    first_alert = outbox.enqueue_for_event(
        event=first,
        alert_type=ALERT_TYPE_CRITICAL_BREAKER,
        now=OBSERVED_LATER,
    )
    duplicate = outbox.enqueue_for_event(
        event=first,
        alert_type=ALERT_TYPE_CRITICAL_BREAKER,
        now=OBSERVED_LATER,
    )
    second_alert = outbox.enqueue_for_event(
        event=second,
        alert_type=ALERT_TYPE_CRITICAL_BREAKER,
        now=OBSERVED_LATER,
    )

    assert first_alert.status == ALERT_ENQUEUED
    assert duplicate.status == ALERT_DUPLICATE
    assert second_alert.status == ALERT_ENQUEUED
    assert len(outbox.alerts()) == 2


def test_outbox_transitions_retry_and_recovery_without_network():
    outbox = OutboxLedger()
    event = _ledger().append(
        _event(
            source_event_id="600519-review",
            severity=SEVERITY_LOW,
        ),
        observed_at=OBSERVED,
    ).event
    queued = outbox.enqueue_for_event(
        event=event,
        alert_type=ALERT_TYPE_REVIEW_DUE,
        now=OBSERVED,
    )
    alert = queued.alert
    assert alert.status == ALERT_PENDING

    sent = outbox.mark_sent(alert_id=alert.alert_id, now=OBSERVED_LATER)
    assert sent.status == ALERT_SENT
    failed = outbox.mark_failed(
        alert_id=alert.alert_id,
        now=OBSERVED_LATER,
        error="fixture delivery failure",
    )
    assert failed.status == ALERT_FAILED_RETRYABLE
    assert failed.attempts == 2
    assert failed.next_attempt_at > OBSERVED_LATER

    retry_time = failed.next_attempt_at + timedelta(seconds=1)
    assert outbox.pending(retry_time)[0].alert_id == alert.alert_id
    resent = outbox.mark_sent(alert_id=alert.alert_id, now=retry_time)
    delivered = outbox.mark_delivered(alert_id=alert.alert_id, now=retry_time)
    acknowledged = outbox.mark_acknowledged(alert_id=alert.alert_id, now=retry_time)
    assert delivered.status == ALERT_DELIVERED
    assert acknowledged.status == ALERT_ACKNOWLEDGED
    assert resent.attempts == 3


def test_outbox_ledger_round_trip_and_rejects_duplicate_dedupe_key():
    outbox = OutboxLedger()
    event = _ledger().append(
        _event(source_event_id="600519-outbox-round-trip"),
        observed_at=OBSERVED,
    ).event
    queued = outbox.enqueue_for_event(
        event=event,
        alert_type=ALERT_TYPE_REVIEW_DUE,
        now=OBSERVED,
    )
    outbox.mark_sent(alert_id=queued.alert.alert_id, now=OBSERVED_LATER)
    outbox.mark_failed(
        alert_id=queued.alert.alert_id,
        now=OBSERVED_LATER,
        error="fixture retry",
    )

    restored = outbox_ledger_from_payload(outbox.as_policy())
    assert restored.as_policy() == outbox.as_policy()

    payload = outbox.as_policy()
    duplicate = dict(payload["alerts"][0])
    duplicate["alert_id"] = "m5-alert-duplicate-dedupe"
    payload["alerts"].append(duplicate)
    with pytest.raises(ValueError, match="duplicate dedupe key"):
        outbox_ledger_from_payload(payload)


def test_outbox_ledger_rejects_acknowledgement_without_delivery():
    outbox = OutboxLedger()
    event = _ledger().append(
        _event(source_event_id="600519-outbox-ack"),
        observed_at=OBSERVED,
    ).event
    queued = outbox.enqueue_for_event(
        event=event,
        alert_type=ALERT_TYPE_REVIEW_DUE,
        now=OBSERVED,
    )
    payload = outbox.as_policy()
    payload["alerts"][0]["status"] = ALERT_ACKNOWLEDGED
    payload["alerts"][0]["attempts"] = 1
    payload["alerts"][0]["next_attempt_at"] = None
    payload["alerts"][0]["delivered_at"] = None

    with pytest.raises(ValueError, match="requires delivered_at"):
        outbox_ledger_from_payload(payload)


def test_source_health_alert_is_explicit_and_not_a_normal_day():
    outbox = OutboxLedger()
    system_event = _ledger().append(
        _event(
            source_event_id="cninfo-outage",
            symbol="SYSTEM",
            event_type=EVENT_TYPE_SOURCE_SCAN_FAILED,
            severity=SEVERITY_CRITICAL,
        ),
        observed_at=OBSERVED,
    ).event
    result = outbox.enqueue_system_health(event=system_event, now=OBSERVED)

    assert result.status == ALERT_ENQUEUED
    assert result.alert.alert_type == ALERT_TYPE_SYSTEM_HEALTH
    assert result.alert.requires_human_review is True
    assert result.alert.action == ACTION_NO_ORDER


def _node(
    node_id: str,
    *,
    kind: str,
    symbol: str = "600519",
    inputs: tuple[str, ...] = (),
) -> DependencyNode:
    return DependencyNode(
        node_id=node_id,
        kind=kind,
        symbol=symbol,
        inputs=inputs,
        version="fixture-v1",
        evidence_refs=({"id": f"node-{node_id}"},),
    )


def _graph() -> DependencyGraph:
    return DependencyGraph(
        (
            _node("facts", kind=KIND_FACTS),
            _node("valuation-inputs", kind=KIND_VALUATION_INPUTS),
            _node("distribution", kind=KIND_DISTRIBUTION_HISTORY),
            _node("model-validity", kind=KIND_MODEL_VALIDITY),
            _node("valuation-result", kind=KIND_VALUATION_RESULT, inputs=("facts", "valuation-inputs")),
            _node("thesis", kind=KIND_THESIS),
            _node("decision-review", kind=KIND_DECISION_REVIEW, inputs=("thesis", "valuation-result")),
            _node("entry-consistency", kind=KIND_ENTRY_CONSISTENCY, inputs=("thesis", "decision-review")),
            _node("price-attractiveness", kind=KIND_PRICE_ATTRACTIVENESS),
            _node("price-bridge", kind=KIND_PRICE_BRIDGE, inputs=("price-attractiveness", "model-validity")),
            _node("current-status", kind=KIND_CURRENT_STATUS, inputs=("price-attractiveness", "valuation-result", "decision-review")),
        )
    )


def test_new_financial_report_invalidates_facts_valuation_and_downstream_only():
    graph = _graph()
    event = _ledger().append(
        _event(
            source_event_id="600519-financial-report",
            event_type=EVENT_TYPE_NEW_FINANCIAL_REPORT,
        ),
        observed_at=OBSERVED,
    ).event
    invalidation = graph.invalidate(event)

    kinds = invalidation.affected_kinds()
    assert KIND_FACTS in kinds
    assert KIND_VALUATION_INPUTS in kinds
    assert KIND_DISTRIBUTION_HISTORY in kinds
    assert KIND_MODEL_VALIDITY in kinds
    assert KIND_VALUATION_RESULT in kinds
    assert KIND_PRICE_BRIDGE in kinds
    assert invalidation.truncated is False
    assert invalidation.action == ACTION_NO_ORDER


def test_price_change_does_not_invalidate_intrinsic_value():
    graph = _graph()
    event = _ledger().append(
        _event(
            source_event_id="600519-price-zone",
            event_type=EVENT_TYPE_PRICE_ATTRACTIVENESS_CHANGED,
        ),
        observed_at=OBSERVED,
    ).event
    invalidation = graph.invalidate(event)

    kinds = invalidation.affected_kinds()
    assert KIND_PRICE_ATTRACTIVENESS in kinds
    assert KIND_PRICE_BRIDGE in kinds
    assert KIND_CURRENT_STATUS in kinds
    assert KIND_VALUATION_RESULT not in kinds
    assert KIND_FACTS not in kinds


def test_thesis_breaker_invalidates_decision_and_entry_consistency():
    graph = _graph()
    event = _ledger().append(
        _event(
            source_event_id="600519-thesis-breaker",
            event_type=EVENT_TYPE_THESIS_BREAKER_TRIGGERED,
            severity=SEVERITY_CRITICAL,
        ),
        observed_at=OBSERVED,
    ).event
    invalidation = graph.invalidate(event)

    kinds = invalidation.affected_kinds()
    assert KIND_THESIS in kinds
    assert KIND_DECISION_REVIEW in kinds
    assert KIND_ENTRY_CONSISTENCY in kinds
    assert KIND_CURRENT_STATUS in kinds


def test_bounded_recalculation_records_deferred_nodes():
    chain = DependencyGraph(
        tuple(
            _node(f"n{index}", kind=KIND_FACTS, inputs=() if index == 0 else (f"n{index - 1}",))
            for index in range(6)
        )
    )
    event = _ledger().append(
        _event(source_event_id="600519-bounded", event_type=EVENT_TYPE_NEW_FINANCIAL_REPORT),
        observed_at=OBSERVED,
    ).event
    invalidation = chain.invalidate(event, max_depth=5, max_nodes=2)

    assert invalidation.truncated is True
    assert len(invalidation.affected_nodes) == 2
    assert len(invalidation.deferred_node_ids) == 4
    assert len(invalidation.recalculation_queue()) == 2


def test_dependency_graph_rejects_cycles_and_unknown_inputs():
    with pytest.raises(ValueError, match="cycle"):
        DependencyGraph(
            (
                _node("a", kind=KIND_FACTS, inputs=("b",)),
                _node("b", kind=KIND_FACTS, inputs=("a",)),
            )
        )
    with pytest.raises(ValueError, match="does not exist"):
        DependencyGraph((_node("a", kind=KIND_FACTS, inputs=("missing",)),))


def test_run_event_batch_produces_committed_simulated_receipt():
    graph = _graph()
    watermark = _watermark(
        coverage_through=OBSERVED_LATER,
        retrieved_at=OBSERVED_LATER,
    )
    events = (
        _event(
            source_event_id="600519-report-run",
            event_type=EVENT_TYPE_NEW_FINANCIAL_REPORT,
        ),
        _event(
            source_event_id="600519-thesis-run",
            event_type=EVENT_TYPE_THESIS_BREAKER_TRIGGERED,
            severity=SEVERITY_CRITICAL,
        ),
    )
    receipt = run_event_batch(
        events=events,
        observed_times=(OBSERVED_LATER, OBSERVED_LATER),
        watermark=watermark,
        graph=graph,
        run_id="M5-fixture-20260924",
        generated_at=OBSERVED_LATER,
    )

    assert receipt.namespace == NAMESPACE_SIMULATED
    assert receipt.accepted_event_count == 2
    assert len(receipt.active_events) == 2
    assert len(receipt.invalidations) == 2
    assert receipt.critical_alert_count == 1
    assert receipt.health_status == RUN_ATTENTION
    assert receipt.silent_ok is False
    assert receipt.checkpoint.status == CHECKPOINT_COMMITTED
    assert receipt.checkpoint.last_sequence == 2
    assert receipt.action == ACTION_NO_ORDER
