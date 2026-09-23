"""Run-once M5 event ingestion coordinator.

This is a pure domain/application boundary helper.  It advances a simulated or
offline run from ingestion through bounded invalidation and outbox bookkeeping,
but does not schedule a service, notify a human or touch production state.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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
    _required_text,
    ChangeEvent,
    ChangeEventInput,
    EventIngestResult,
    EventLedger,
    EVENT_TYPE_DIVIDEND_CHANGE,
    EVENT_TYPE_MODEL_STALE,
    EVENT_TYPE_POSITION_RISK_CHANGED,
    EVENT_TYPE_SOURCE_SCAN_FAILED,
    EVENT_TYPE_SOURCE_SCAN_RECOVERED,
    EVENT_TYPE_THESIS_BREAKER_TRIGGERED,
    EVENT_TYPE_THESIS_WEAKENED,
    INGEST_ACCEPTED,
    INGEST_CORRECTION_ACCEPTED,
    INGEST_SUPERSEDES_ACCEPTED,
    SEVERITY_CRITICAL,
)
from .m5_event_dependencies import DependencyGraph, DependencyInvalidation
from .m5_event_outbox import (
    ALERT_TYPE_CRITICAL_BREAKER,
    ALERT_TYPE_DIVIDEND_ALERT,
    ALERT_TYPE_MODEL_STALE,
    ALERT_TYPE_POSITION_RISK,
    ALERT_TYPE_REVIEW_DUE,
    ALERT_TYPE_SYSTEM_HEALTH,
    ALERT_TYPE_THESIS_ALERT,
    EventAlert,
    OutboxLedger,
)
from .m5_event_watermark import (
    SOURCE_DEGRADED,
    SOURCE_OUTAGE,
    ScanWatermark,
    TaskLockStore,
    WatermarkLedger,
)


RUN_HEALTHY = "HEALTHY"
RUN_ATTENTION = "ATTENTION"
RUN_HEALTH_STATUSES = frozenset({RUN_HEALTHY, RUN_ATTENTION})

_ALERT_BY_EVENT_TYPE = {
    EVENT_TYPE_THESIS_BREAKER_TRIGGERED: ALERT_TYPE_CRITICAL_BREAKER,
    EVENT_TYPE_THESIS_WEAKENED: ALERT_TYPE_THESIS_ALERT,
    EVENT_TYPE_MODEL_STALE: ALERT_TYPE_MODEL_STALE,
    EVENT_TYPE_DIVIDEND_CHANGE: ALERT_TYPE_DIVIDEND_ALERT,
    EVENT_TYPE_POSITION_RISK_CHANGED: ALERT_TYPE_POSITION_RISK,
    EVENT_TYPE_SOURCE_SCAN_FAILED: ALERT_TYPE_SYSTEM_HEALTH,
    EVENT_TYPE_SOURCE_SCAN_RECOVERED: ALERT_TYPE_SYSTEM_HEALTH,
}


@dataclass(frozen=True)
class M5EventRunReceipt:
    receipt_id: str
    run_id: str
    namespace: str
    generated_at: datetime
    ingest_results: tuple[EventIngestResult, ...]
    invalidations: tuple[DependencyInvalidation, ...]
    alerts: tuple[EventAlert, ...]
    checkpoint: TaskCheckpoint
    health_status: str
    silent_ok: bool
    review_due: tuple[str, ...]
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "receipt_id",
            _required_text(self.receipt_id, "receipt_id"),
        )
        object.__setattr__(self, "run_id", _required_text(self.run_id, "run_id"))
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
        if self.health_status not in RUN_HEALTH_STATUSES:
            raise ValueError("Unknown event run health status")
        if self.checkpoint.status != CHECKPOINT_COMMITTED:
            raise ValueError("Event run receipt requires a committed checkpoint")
        object.__setattr__(
            self,
            "review_due",
            tuple(_required_text(item, "review_due") for item in self.review_due),
        )
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Event run receipt must remain no_order")

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
        return {
            "receipt_id": self.receipt_id,
            "run_id": self.run_id,
            "namespace": self.namespace,
            "generated_at": self.generated_at.isoformat(),
            "ingest_results": [item.as_policy() for item in self.ingest_results],
            "invalidations": [item.as_policy() for item in self.invalidations],
            "alerts": [item.as_policy() for item in self.alerts],
            "checkpoint": self.checkpoint.as_policy(),
            "health_status": self.health_status,
            "silent_ok": self.silent_ok,
            "review_due": list(self.review_due),
            "action": self.action,
        }


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
) -> M5EventRunReceipt:
    """Ingest one bounded batch and return a fail-closed run receipt."""

    if len(events) != len(observed_times):
        raise ValueError("Every event requires one observed_at timestamp")
    run_id = _required_text(run_id, "run_id")
    generated_at = _required_datetime(generated_at, "generated_at")
    if namespace not in {NAMESPACE_SIMULATED}:
        raise ValueError("Public run-once coordinator accepts SIMULATED only")
    if any(event.namespace != namespace for event in events):
        raise ValueError("All events must use the requested namespace")
    direct_kinds_by_source_event_id = dict(
        direct_kinds_by_source_event_id or {}
    )
    event_source_ids = {event.source_event_id for event in events}
    if any(
        source_event_id not in event_source_ids
        for source_event_id in direct_kinds_by_source_event_id
    ):
        raise ValueError("Every custom dependency policy must match an event")

    ledger = EventLedger(namespace=namespace)
    watermarks = WatermarkLedger()
    watermarks.advance(watermark)
    locks = TaskLockStore()
    lock_result = locks.acquire(
        scope=f"M5:{run_id}",
        owner=lock_owner,
        token=lock_token,
        now=generated_at,
        lease_seconds=lease_seconds,
    )
    if lock_result.lock is None:
        raise ValueError("Could not acquire the M5 run lock")

    checkpoints = CheckpointLedger()
    checkpoint_result = checkpoints.start(
        run_id=run_id,
        scope="ALL",
        started_at=generated_at,
        evidence_refs=(
            {"id": "m5-run-start"},
            {"id": watermark.watermark_id},
        ),
    )
    if checkpoint_result.checkpoint is None:
        locks.release(scope=lock_result.lock.scope, token=lock_token, now=generated_at)
        raise ValueError("Could not start the M5 run checkpoint")

    outbox = OutboxLedger()
    ingest_results: list[EventIngestResult] = []
    invalidations: list[DependencyInvalidation] = []
    for event, observed_at in zip(events, observed_times):
        result = ledger.append(
            event,
            observed_at=observed_at,
            coverage_watermark=watermark,
        )
        ingest_results.append(result)
        if result.event is None or result.status not in {
            INGEST_ACCEPTED,
            INGEST_CORRECTION_ACCEPTED,
            INGEST_SUPERSEDES_ACCEPTED,
        }:
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
        alert_type = _ALERT_BY_EVENT_TYPE.get(
            result.event.event_type,
            ALERT_TYPE_REVIEW_DUE,
        )
        outbox.enqueue_for_event(
            event=result.event,
            alert_type=alert_type,
            now=observed_at,
        )

    committed = checkpoints.commit(
        checkpoint_id=checkpoint_result.checkpoint.checkpoint_id,
        completed_at=generated_at,
        last_sequence=len(ledger),
        watermark_ids=(watermark.watermark_id,),
        ingested_event_ids=tuple(
            result.event.event_id
            for result in ingest_results
            if result.event is not None
        ),
    )
    if committed.checkpoint is None:
        raise ValueError("Could not commit the M5 run checkpoint")
    locks.release(scope=lock_result.lock.scope, token=lock_token, now=generated_at)

    alerts = outbox.alerts()
    source_health_ok = watermark.source_health not in {SOURCE_OUTAGE, SOURCE_DEGRADED}
    has_attention = not source_health_ok or any(
        item.requires_human_review for item in alerts
    )
    review_due = tuple(
        sorted({item.alert_type for item in alerts if item.requires_human_review})
    )
    return M5EventRunReceipt(
        receipt_id="m5-run-" + _digest("run-receipt", run_id, generated_at.isoformat())[
            :32
        ],
        run_id=run_id,
        namespace=namespace,
        generated_at=generated_at,
        ingest_results=tuple(ingest_results),
        invalidations=tuple(invalidations),
        alerts=alerts,
        checkpoint=committed.checkpoint,
        health_status=RUN_ATTENTION if has_attention else RUN_HEALTHY,
        silent_ok=not alerts and source_health_ok,
        review_due=review_due,
    )
