"""Run-once M5 event ingestion coordinator.

This is a pure domain/application boundary helper.  It advances a simulated or
offline run from ingestion through bounded invalidation and outbox bookkeeping,
but does not schedule a service, notify a human or touch production state.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any, Mapping, Sequence

from .investment_decision import ACTION_NO_ORDER
from .m5_event_checkpoint import (
    CHECKPOINT_COMMITTED,
    CheckpointLedger,
    TaskCheckpoint,
)
from .m5_event_core import (
    M5_EVENT_SCHEMA,
    NAMESPACE_SIMULATED,
    _digest,
    _required_datetime,
    _required_int,
    _required_text,
    ChangeEvent,
    ChangeEventInput,
    EventIngestResult,
    EventLedger,
    INGEST_ACCEPTED,
    INGEST_CORRECTION_ACCEPTED,
    INGEST_DUPLICATE,
    INGEST_CONFLICT_REJECTED,
    INGEST_FUTURE_REJECTED,
    INGEST_OBSERVED_TIME_REGRESSION_REJECTED,
    INGEST_SUPERSEDES_ACCEPTED,
    SEVERITY_CRITICAL,
    _state_digest,
)
from .m5_event_dependencies import DependencyGraph, DependencyInvalidation
from .m5_event_outbox import (
    EventAlert,
    OutboxLedger,
    alert_type_for_event_type,
)
from .m5_event_watermark import (
    LOCK_ACQUIRED,
    LOCK_REPLACED_EXPIRED,
    SOURCE_HEALTHY,
    SOURCE_DEGRADED,
    SOURCE_OUTAGE,
    WATERMARK_COVERAGE_COMPLETE,
    WATERMARK_COVERAGE_INCOMPLETE,
    WATERMARK_REGRESSION_REJECTED,
    ScanWatermark,
    TaskLockStore,
    WatermarkLedger,
)
from .m5_event_run_state import M5EventBatchRecord, M5EventRunState
from .m5_event_state_store import M5EventRunStateStore, M5StateStoreConflict


RUN_HEALTHY = "HEALTHY"
RUN_ATTENTION = "ATTENTION"
RUN_HEALTH_STATUSES = frozenset({RUN_HEALTHY, RUN_ATTENTION})
DEFAULT_MAX_WATERMARK_AGE = timedelta(minutes=15)

_ACCEPTED_INGEST_STATUSES = frozenset(
    {
        INGEST_ACCEPTED,
        INGEST_CORRECTION_ACCEPTED,
        INGEST_SUPERSEDES_ACCEPTED,
    }
)
_REJECTED_INGEST_STATUSES = frozenset(
    {
        INGEST_FUTURE_REJECTED,
        INGEST_CONFLICT_REJECTED,
        INGEST_OBSERVED_TIME_REGRESSION_REJECTED,
    }
)

@dataclass(frozen=True)
class M5EventRunReceipt:
    receipt_id: str
    run_id: str
    batch_id: str
    stream_id: str
    namespace: str
    generated_at: datetime
    ingest_results: tuple[EventIngestResult, ...]
    invalidations: tuple[DependencyInvalidation, ...]
    alerts: tuple[EventAlert, ...]
    checkpoint: TaskCheckpoint
    health_status: str
    silent_ok: bool
    review_due: tuple[str, ...]
    state: M5EventRunState
    state_sha256: str
    idempotent_noop: bool = False
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "receipt_id",
            _required_text(self.receipt_id, "receipt_id"),
        )
        object.__setattr__(self, "run_id", _required_text(self.run_id, "run_id"))
        object.__setattr__(
            self,
            "batch_id",
            _required_text(self.batch_id, "batch_id"),
        )
        object.__setattr__(
            self,
            "stream_id",
            _required_text(self.stream_id, "stream_id"),
        )
        object.__setattr__(self, "namespace", _required_text(self.namespace, "namespace"))
        object.__setattr__(
            self,
            "generated_at",
            _required_datetime(self.generated_at, "generated_at"),
        )
        object.__setattr__(
            self,
            "ingest_results",
            tuple(
                item
                if isinstance(item, EventIngestResult)
                else EventIngestResult(**item)
                for item in self.ingest_results
            ),
        )
        object.__setattr__(
            self,
            "invalidations",
            tuple(
                item
                if isinstance(item, DependencyInvalidation)
                else DependencyInvalidation(**item)
                for item in self.invalidations
            ),
        )
        object.__setattr__(
            self,
            "alerts",
            tuple(
                item if isinstance(item, EventAlert) else EventAlert(**item)
                for item in self.alerts
            ),
        )
        if not isinstance(self.checkpoint, TaskCheckpoint):
            raise ValueError("checkpoint must be a TaskCheckpoint")
        if not isinstance(self.state, M5EventRunState):
            raise ValueError("state must be an M5EventRunState")
        if self.stream_id != self.state.state_key:
            raise ValueError("Receipt stream_id must match its run state")
        if self.namespace != self.state.namespace:
            raise ValueError("Receipt namespace must match its run state")
        object.__setattr__(
            self,
            "state_sha256",
            _required_text(self.state_sha256, "state_sha256").lower(),
        )
        if self.state_sha256 != self.state.state_sha256():
            raise ValueError("Receipt state hash does not match its run state")
        if self.health_status not in RUN_HEALTH_STATUSES:
            raise ValueError("Unknown event run health status")
        if self.checkpoint.status != CHECKPOINT_COMMITTED:
            raise ValueError("Event run receipt requires a committed checkpoint")
        matching_checkpoints = tuple(
            item
            for item in self.state.checkpoints.checkpoints()
            if item.checkpoint_id == self.checkpoint.checkpoint_id
        )
        if matching_checkpoints != (self.checkpoint,):
            raise ValueError("Receipt checkpoint must belong to its run state")
        expected_receipt_id = "m5-run-" + _digest(
            "run-receipt",
            self.run_id,
            self.batch_id,
            self.generated_at.isoformat(),
        )[:32]
        if self.receipt_id != expected_receipt_id:
            raise ValueError("Receipt id does not match its immutable payload")
        object.__setattr__(
            self,
            "review_due",
            tuple(_required_text(item, "review_due") for item in self.review_due),
        )
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Event run receipt must remain no_order")

    def verify(self) -> None:
        if self.state_sha256 != self.state.state_sha256():
            raise ValueError("Receipt state hash no longer matches its run state")
        if self.namespace != self.state.namespace:
            raise ValueError("Receipt namespace no longer matches its run state")
        matching_checkpoints = tuple(
            item
            for item in self.state.checkpoints.checkpoints()
            if item.checkpoint_id == self.checkpoint.checkpoint_id
        )
        if matching_checkpoints != (self.checkpoint,):
            raise ValueError("Receipt checkpoint no longer matches its run state")

    @property
    def active_events(self) -> tuple[ChangeEvent, ...]:
        active: list[ChangeEvent] = []
        seen: set[str] = set()
        for result in self.ingest_results:
            event = result.event
            if (
                event is not None
                and event.status == "ACTIVE"
                and event.event_id not in seen
            ):
                seen.add(event.event_id)
                active.append(event)
        return tuple(active)

    @property
    def critical_alert_count(self) -> int:
        return sum(item.severity == SEVERITY_CRITICAL for item in self.alerts)

    @property
    def accepted_event_count(self) -> int:
        return sum(
            result.status
            in {
                INGEST_ACCEPTED,
                INGEST_CORRECTION_ACCEPTED,
                INGEST_SUPERSEDES_ACCEPTED,
            }
            for result in self.ingest_results
        )

    def as_policy(self) -> dict[str, Any]:
        self.verify()
        return {
            "receipt_id": self.receipt_id,
            "run_id": self.run_id,
            "batch_id": self.batch_id,
            "stream_id": self.stream_id,
            "namespace": self.namespace,
            "generated_at": self.generated_at.isoformat(),
            "ingest_results": [item.as_policy() for item in self.ingest_results],
            "invalidations": [item.as_policy() for item in self.invalidations],
            "alerts": [item.as_policy() for item in self.alerts],
            "checkpoint": self.checkpoint.as_policy(),
            "health_status": self.health_status,
            "silent_ok": self.silent_ok,
            "review_due": list(self.review_due),
            "state": self.state.as_policy(),
            "state_sha256": self.state_sha256,
            "idempotent_noop": self.idempotent_noop,
            "action": self.action,
        }


def _batch_request_fingerprint(
    *,
    events: Sequence[ChangeEventInput],
    observed_times: Sequence[datetime],
    watermark: ScanWatermark,
    graph: DependencyGraph,
    direct_kinds_by_source_event_id: Mapping[str, Sequence[str]],
) -> str:
    return _state_digest(
        {
            "events": [event.as_policy() for event in events],
            "observed_times": [item.isoformat() for item in observed_times],
            "watermark": watermark.as_policy(),
            "dependency_graph": graph.as_policy(),
            "direct_kinds_by_source_event_id": {
                key: list(value)
                for key, value in sorted(direct_kinds_by_source_event_id.items())
            },
        }
    )


def _checkpoint_for_replay(state: M5EventRunState, checkpoint_id: str) -> TaskCheckpoint:
    for checkpoint in state.checkpoints.checkpoints():
        if checkpoint.checkpoint_id == checkpoint_id:
            if checkpoint.status != CHECKPOINT_COMMITTED:
                raise ValueError("Recorded batch checkpoint is not committed")
            return checkpoint
    raise ValueError("Recorded batch checkpoint is missing")


def _replayed_batch(
    *,
    state: M5EventRunState,
    checkpoint: TaskCheckpoint,
    events: Sequence[ChangeEventInput],
    observed_times: Sequence[datetime],
    watermark: ScanWatermark,
    graph: DependencyGraph,
    direct_kinds_by_source_event_id: Mapping[str, Sequence[str]],
) -> tuple[tuple[EventIngestResult, ...], tuple[DependencyInvalidation, ...]]:
    """Replay the recorded batch from its durable checkpoint prefix.

    The aggregate does not store receipt snapshots. Replaying the original
    request against the checkpoint prefix therefore reconstructs the original
    ingest verdicts and dependency invalidations without trusting later state.
    """

    ledger = EventLedger(namespace=state.namespace)
    prefix_end = checkpoint.last_sequence - len(checkpoint.ingested_event_ids)
    if prefix_end < 0:
        raise ValueError("Recorded batch checkpoint prefix is invalid")
    for previous in state.event_ledger.events():
        if previous.sequence > prefix_end:
            break
        restored = ledger.append(
            previous.input,
            observed_at=previous.ingested_at,
            coverage_watermark=watermark,
        )
        if restored.status not in _ACCEPTED_INGEST_STATUSES:
            raise ValueError("Recorded batch prefix cannot be replayed")
        if restored.event is None or restored.event.event_id != previous.event_id:
            raise ValueError("Recorded batch prefix event identity changed")

    results: list[EventIngestResult] = []
    invalidations: list[DependencyInvalidation] = []
    for event, observed_at in zip(events, observed_times):
        result = ledger.append(
            event,
            observed_at=observed_at,
            coverage_watermark=watermark,
        )
        results.append(result)
        if result.event is None or result.status not in _ACCEPTED_INGEST_STATUSES:
            continue
        custom_kinds = direct_kinds_by_source_event_id.get(
            result.event.source_event_id
        )
        invalidations.append(
            graph.invalidate(
                result.event,
                direct_kinds=tuple(custom_kinds) if custom_kinds else None,
            )
        )
    replayed_event_ids = tuple(
        result.event.event_id
        for result in results
        if result.event is not None
        and result.status in _ACCEPTED_INGEST_STATUSES
    )
    if replayed_event_ids != checkpoint.ingested_event_ids:
        raise ValueError("Replayed batch does not match its committed checkpoint")
    return tuple(results), tuple(invalidations)


def _alerts_for_batch(
    state: M5EventRunState,
    checkpoint: TaskCheckpoint,
) -> tuple[EventAlert, ...]:
    event_ids = set(checkpoint.ingested_event_ids)
    return tuple(
        alert
        for alert in state.outbox.alerts()
        if alert.event_id in event_ids
    )


def _active_alerts(state: M5EventRunState) -> tuple[EventAlert, ...]:
    terminal = {"ACKNOWLEDGED", "FAILED_TERMINAL"}
    return tuple(
        item for item in state.outbox.alerts() if item.status not in terminal
    )


def _receipt_health(
    *,
    state: M5EventRunState,
    scan_watermark: ScanWatermark,
    persisted_watermark: ScanWatermark,
    ingest_results: Sequence[EventIngestResult],
    generated_at: datetime,
    max_watermark_age: timedelta,
) -> tuple[str, bool, tuple[str, ...]]:
    source_health_ok = all(
        watermark.source_health not in {SOURCE_OUTAGE, SOURCE_DEGRADED}
        for watermark in (scan_watermark, persisted_watermark)
    )
    coverage_ok = all(
        watermark.coverage_status == WATERMARK_COVERAGE_COMPLETE
        for watermark in (scan_watermark, persisted_watermark)
    )
    freshness_ok = (
        generated_at - scan_watermark.retrieved_at <= max_watermark_age
        and generated_at - persisted_watermark.retrieved_at <= max_watermark_age
    )
    rejected_ingest = any(
        result.status in _REJECTED_INGEST_STATUSES for result in ingest_results
    )
    active_alerts = _active_alerts(state)
    review_due = tuple(
        sorted(
            {
                item.alert_type
                for item in active_alerts
                if item.requires_human_review
            }
        )
    )
    has_attention = (
        not source_health_ok
        or not coverage_ok
        or not freshness_ok
        or rejected_ingest
        or bool(active_alerts)
    )
    return (
        RUN_ATTENTION if has_attention else RUN_HEALTHY,
        not active_alerts
        and source_health_ok
        and coverage_ok
        and freshness_ok
        and not rejected_ingest,
        review_due,
    )


def _unaccepted_coverage_mark(
    watermark: ScanWatermark,
    previous: ScanWatermark | None,
) -> ScanWatermark:
    """Persist a scan boundary without claiming complete coverage."""
    return replace(
        watermark,
        coverage_through=(
            previous.coverage_through
            if previous is not None
            else watermark.coverage_through
        ),
        coverage_status=WATERMARK_COVERAGE_INCOMPLETE,
    )


def _validate_run_clock(
    *,
    generated_at: datetime,
    observed_times: Sequence[datetime],
    watermark: ScanWatermark,
    max_watermark_age: object,
) -> timedelta:
    if not isinstance(max_watermark_age, timedelta):
        raise ValueError("max_watermark_age must be a timedelta")
    if max_watermark_age < timedelta(0):
        raise ValueError("max_watermark_age cannot be negative")
    if any(observed_at > generated_at for observed_at in observed_times):
        raise ValueError("generated_at cannot precede an observed event time")
    if watermark.retrieved_at > generated_at:
        raise ValueError("Watermark retrieval cannot follow generated_at")
    if generated_at - watermark.retrieved_at > max_watermark_age:
        raise ValueError("Watermark is stale relative to the run clock")
    return max_watermark_age


def run_event_batch(
    *,
    events: Sequence[ChangeEventInput],
    observed_times: Sequence[datetime],
    watermark: ScanWatermark,
    graph: DependencyGraph,
    run_id: str,
    generated_at: datetime,
    namespace: str = NAMESPACE_SIMULATED,
    lock_owner: str = "offline-m5-runner",
    lock_token: str = "m5-offline-token",
    lease_seconds: int = 120,
    direct_kinds_by_source_event_id: Mapping[str, Sequence[str]] | None = None,
    state: M5EventRunState | None = None,
    batch_id: str | None = None,
    expected_revision: int | None = None,
    lock_store: TaskLockStore | None = None,
    max_watermark_age: timedelta = DEFAULT_MAX_WATERMARK_AGE,
) -> M5EventRunReceipt:
    """Ingest one bounded batch and return an atomically exportable next state."""

    if len(events) != len(observed_times):
        raise ValueError("Every event requires one observed_at timestamp")
    run_id = _required_text(run_id, "run_id")
    batch_id = _required_text(batch_id or run_id, "batch_id")
    generated_at = _required_datetime(generated_at, "generated_at")
    observed_times = tuple(
        _required_datetime(item, "observed_at") for item in observed_times
    )
    if namespace != NAMESPACE_SIMULATED:
        raise ValueError("Public run-once coordinator accepts SIMULATED only")
    if state is not None and not isinstance(state, M5EventRunState):
        raise ValueError("state must be an M5EventRunState")
    if expected_revision is not None:
        expected_revision = _required_int(expected_revision, "expected_revision")
        if expected_revision < 0:
            raise ValueError("expected_revision cannot be negative")
    if any(not isinstance(event, ChangeEventInput) for event in events):
        raise ValueError("events must contain ChangeEventInput objects")
    if any(event.namespace != namespace for event in events):
        raise ValueError("All events must use the requested namespace")
    max_watermark_age = _validate_run_clock(
        generated_at=generated_at,
        observed_times=observed_times,
        watermark=watermark,
        max_watermark_age=max_watermark_age,
    )
    direct_kinds_by_source_event_id = {
        _required_text(key, "direct dependency source_event_id"): tuple(
            _required_text(item, "direct dependency kind")
            for item in value
        )
        for key, value in dict(direct_kinds_by_source_event_id or {}).items()
    }
    event_source_ids = {event.source_event_id for event in events}
    if any(
        source_event_id not in event_source_ids
        for source_event_id in direct_kinds_by_source_event_id
    ):
        raise ValueError("Every custom dependency policy must match an event")

    working = (
        state.clone()
        if state is not None
        else M5EventRunState.empty(state_key=run_id, namespace=namespace)
    )
    if expected_revision is not None and working.revision != expected_revision:
        raise ValueError(
            "M5 run state revision does not match expected_revision"
        )
    request_fingerprint = _batch_request_fingerprint(
        events=events,
        observed_times=observed_times,
        watermark=watermark,
        graph=graph,
        direct_kinds_by_source_event_id=direct_kinds_by_source_event_id,
    )
    existing_record = next(
        (
            item
            for item in working.batch_records
            if item.batch_id == batch_id
        ),
        None,
    )
    if existing_record is not None:
        if existing_record.request_fingerprint != request_fingerprint:
            raise ValueError("Batch id was already used with different inputs")
        if existing_record.run_id != run_id:
            raise ValueError("Batch id was already used by a different run_id")
        if existing_record.namespace != namespace:
            raise ValueError("Batch id was already used in a different namespace")
        generated_at = existing_record.generated_at
        checkpoint = _checkpoint_for_replay(
            working,
            existing_record.checkpoint_id,
        )
        current_watermark = working.watermarks.current(
            scope=watermark.scope,
            source=watermark.source,
        )
        effective_watermark = current_watermark or watermark
        replayed_results, replayed_invalidations = _replayed_batch(
            state=working,
            checkpoint=checkpoint,
            events=events,
            observed_times=observed_times,
            watermark=watermark,
            graph=graph,
            direct_kinds_by_source_event_id=direct_kinds_by_source_event_id,
        )
        health_status, silent_ok, review_due = _receipt_health(
            state=working,
            scan_watermark=watermark,
            persisted_watermark=watermark,
            ingest_results=replayed_results,
            generated_at=generated_at,
            max_watermark_age=max_watermark_age,
        )
        return M5EventRunReceipt(
            receipt_id=existing_record.receipt_id,
            run_id=run_id,
            batch_id=batch_id,
            stream_id=working.state_key,
            namespace=namespace,
            generated_at=generated_at,
            ingest_results=replayed_results,
            invalidations=replayed_invalidations,
            alerts=_alerts_for_batch(working, checkpoint),
            checkpoint=checkpoint,
            health_status=health_status,
            silent_ok=silent_ok,
            review_due=review_due,
            state=working,
            state_sha256=working.state_sha256(),
            idempotent_noop=True,
        )

    effective_lock_owner = f"{lock_owner}:run:{run_id}"
    effective_lock_token = f"{lock_token}:batch:{batch_id}"
    locks = lock_store or TaskLockStore()
    lock_result = locks.acquire(
        scope=f"M5:state:{working.state_key}",
        owner=effective_lock_owner,
        token=effective_lock_token,
        now=generated_at,
        lease_seconds=lease_seconds,
    )
    if (
        lock_result.lock is None
        or lock_result.status not in {LOCK_ACQUIRED, LOCK_REPLACED_EXPIRED}
    ):
        raise ValueError(
            f"Could not acquire the M5 state lock: {lock_result.status}"
        )
    lock_acquired = True
    try:
        current_watermark = working.watermarks.current(
            scope=watermark.scope,
            source=watermark.source,
        )
        if (
            current_watermark is not None
            and watermark.coverage_through < current_watermark.coverage_through
        ):
            raise ValueError("Watermark regresses the run state")
        effective_watermark = current_watermark or watermark
        ingest_results: list[EventIngestResult] = []
        invalidations: list[DependencyInvalidation] = []
        new_alerts: list[EventAlert] = []
        for event, observed_at in zip(events, observed_times):
            result = working.event_ledger.append(
                event,
                observed_at=observed_at,
                coverage_watermark=watermark,
            )
            ingest_results.append(result)
            if result.event is None or result.status not in _ACCEPTED_INGEST_STATUSES:
                continue
            custom_kinds = direct_kinds_by_source_event_id.get(
                result.event.source_event_id
            )
            invalidations.append(
                graph.invalidate(
                    result.event,
                    direct_kinds=tuple(custom_kinds) if custom_kinds else None,
                )
            )
            alert_type = alert_type_for_event_type(result.event.event_type)
            enqueued = working.outbox.enqueue_for_event(
                event=result.event,
                alert_type=alert_type,
                now=observed_at,
            )
            if enqueued.alert is not None:
                new_alerts.append(enqueued.alert)

        coverage_safe_to_advance = (
            watermark.coverage_status == WATERMARK_COVERAGE_COMPLETE
            and watermark.source_health == SOURCE_HEALTHY
            and not any(
                result.status in _REJECTED_INGEST_STATUSES
                for result in ingest_results
            )
        )
        persisted_watermark = (
            watermark
            if coverage_safe_to_advance
            else _unaccepted_coverage_mark(watermark, current_watermark)
        )
        watermark_result = working.watermarks.advance(persisted_watermark)
        if watermark_result.status == WATERMARK_REGRESSION_REJECTED:
            raise ValueError("Watermark regresses the run state")
        effective_watermark = watermark_result.watermark or persisted_watermark

        checkpoint_result = working.checkpoints.start(
            run_id=working.state_key,
            scope="ALL",
            started_at=generated_at,
            evidence_refs=(
                {"id": f"batch:{batch_id}"},
                {"id": effective_watermark.watermark_id},
            ),
        )
        if checkpoint_result.checkpoint is None:
            raise ValueError("Could not start the M5 run checkpoint")
        prior_committed = [
            item
            for item in working.checkpoints.checkpoints()
            if item.status == CHECKPOINT_COMMITTED
        ]
        prior_sequence = prior_committed[-1].last_sequence if prior_committed else 0
        ingested_event_ids = tuple(
            event.event_id
            for event in working.event_ledger.events()[prior_sequence:]
        )
        committed = working.checkpoints.commit(
            checkpoint_id=checkpoint_result.checkpoint.checkpoint_id,
            completed_at=generated_at,
            last_sequence=len(working.event_ledger),
            watermark_ids=tuple(
                sorted(
                    item.watermark_id
                    for item in working.watermarks.watermarks()
                )
            ),
            ingested_event_ids=ingested_event_ids,
        )
        if committed.checkpoint is None:
            raise ValueError("Could not commit the M5 run checkpoint")

        receipt_id = "m5-run-" + _digest(
            "run-receipt",
            run_id,
            batch_id,
            generated_at.isoformat(),
        )[:32]
        next_revision = working.revision + 1
        record = M5EventBatchRecord(
            batch_id=batch_id,
            run_id=run_id,
            namespace=namespace,
            generated_at=generated_at,
            request_fingerprint=request_fingerprint,
            receipt_id=receipt_id,
            checkpoint_id=committed.checkpoint.checkpoint_id,
            state_revision=next_revision,
        )
        next_state = M5EventRunState(
            state_key=working.state_key,
            namespace=working.namespace,
            revision=next_revision,
            event_ledger=working.event_ledger,
            watermarks=working.watermarks,
            checkpoints=working.checkpoints,
            outbox=working.outbox,
            batch_records=working.batch_records + (record,),
            outbox_revision=working.outbox_revision,
            outbox_transitions=working.outbox_transitions,
        )
        health_status, silent_ok, review_due = _receipt_health(
            state=next_state,
            scan_watermark=watermark,
            persisted_watermark=effective_watermark,
            ingest_results=ingest_results,
            generated_at=generated_at,
            max_watermark_age=max_watermark_age,
        )
        return M5EventRunReceipt(
            receipt_id=receipt_id,
            run_id=run_id,
            batch_id=batch_id,
            stream_id=next_state.state_key,
            namespace=namespace,
            generated_at=generated_at,
            ingest_results=tuple(ingest_results),
            invalidations=tuple(invalidations),
            alerts=tuple(new_alerts),
            checkpoint=committed.checkpoint,
            health_status=health_status,
            silent_ok=silent_ok,
            review_due=review_due,
            state=next_state,
            state_sha256=next_state.state_sha256(),
        )
    finally:
        if lock_acquired:
            locks.release(
                scope=lock_result.lock.scope,
                owner=effective_lock_owner,
                token=effective_lock_token,
                now=generated_at,
            )


def run_event_batch_persisted(
    *,
    events: Sequence[ChangeEventInput],
    observed_times: Sequence[datetime],
    watermark: ScanWatermark,
    graph: DependencyGraph,
    run_id: str,
    generated_at: datetime,
    store: M5EventRunStateStore,
    namespace: str = NAMESPACE_SIMULATED,
    lock_owner: str = "offline-m5-runner",
    lock_token: str = "m5-offline-token",
    lease_seconds: int = 120,
    direct_kinds_by_source_event_id: Mapping[str, Sequence[str]] | None = None,
    state: M5EventRunState | None = None,
    batch_id: str | None = None,
    lock_store: TaskLockStore | None = None,
) -> M5EventRunReceipt:
    """Run one batch and persist its next state with revision/digest CAS."""

    if not isinstance(store, M5EventRunStateStore):
        raise ValueError("store must implement M5EventRunStateStore")
    run_id = _required_text(run_id, "run_id")
    state_key = state.state_key if state is not None else run_id
    current = store.load(state_key=state_key)
    if current is None:
        if state is not None and state.revision != 0:
            raise M5StateStoreConflict(
                "Cannot seed a persisted run from a non-empty snapshot"
            )
        working = (
            state.clone()
            if state is not None
            else M5EventRunState.empty(state_key=state_key, namespace=namespace)
        )
    else:
        if state is not None and state.state_sha256() != current.state_sha256():
            raise M5StateStoreConflict(
                "Provided M5 state snapshot is stale relative to the store"
            )
        working = current

    receipt = run_event_batch(
        events=events,
        observed_times=observed_times,
        watermark=watermark,
        graph=graph,
        run_id=run_id,
        generated_at=generated_at,
        namespace=namespace,
        lock_owner=lock_owner,
        lock_token=lock_token,
        lease_seconds=lease_seconds,
        direct_kinds_by_source_event_id=direct_kinds_by_source_event_id,
        state=working,
        batch_id=batch_id,
        expected_revision=working.revision,
        lock_store=lock_store,
    )
    store.commit(
        expected_revision=working.revision,
        expected_sha256=(
            None if current is None else current.state_sha256()
        ),
        state=receipt.state,
    )
    return receipt
