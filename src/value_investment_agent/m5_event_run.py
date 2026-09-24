"""Run-once M5 event ingestion coordinator.

This is a pure domain/application boundary helper.  It advances a simulated or
offline run from ingestion through bounded invalidation and outbox bookkeeping,
but does not schedule a service, notify a human or touch production state.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
import json
from typing import Any, Mapping, Sequence

from .investment_decision import ACTION_NO_ORDER
from .m5_actual_offline_authorization import (
    M5ActualOfflineAuthorization,
    require_actual_offline_authorization,
)
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
    event_ingest_result_from_payload,
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
from .m5_event_dependencies import (
    DependencyGraph,
    DependencyInvalidation,
    dependency_invalidation_from_payload,
)
from .m5_event_outbox import (
    ALERT_ACKNOWLEDGED,
    EventAlert,
    OutboxLedger,
    alert_type_for_event_type,
    event_alert_from_payload,
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
from .m5_event_run_state import (
    M5EventBatchRecord,
    M5EventRunState,
    m5_event_run_state_from_payload,
)
from .m5_event_state_store import (
    M5EventRunReceiptStore,
    M5EventRunStateStore,
    M5ReceiptPublication,
    M5StateStoreConflict,
)
from .m5_run_request import M5EventRunRequest, batch_request_fingerprint


RUN_HEALTHY = "HEALTHY"
RUN_ATTENTION = "ATTENTION"
RUN_HEALTH_STATUSES = frozenset({RUN_HEALTHY, RUN_ATTENTION})
DEFAULT_MAX_WATERMARK_AGE = timedelta(minutes=15)
M5_EVENT_RUN_RECEIPT_SCHEMA = "m5-event-run-receipt-v1"
RUN_RECEIPT_ARTIFACT_KEYS = frozenset(
    {
        "schema_version",
        "receipt",
        "receipt_sha256",
        "audit_fingerprint",
    }
)

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


def _receipt_audit_fingerprint(
    *,
    receipt_id: str,
    run_id: str,
    batch_id: str,
    stream_id: str,
    namespace: str,
    generated_at: datetime,
    ingest_results: Sequence[EventIngestResult],
    invalidations: Sequence[DependencyInvalidation],
    checkpoint: TaskCheckpoint,
    action: str,
) -> str:
    return _state_digest(
        {
            "receipt_id": receipt_id,
            "run_id": run_id,
            "batch_id": batch_id,
            "stream_id": stream_id,
            "namespace": namespace,
            "generated_at": generated_at.isoformat(),
            "ingest_results": [
                item.as_policy() for item in ingest_results
            ],
            "invalidations": [
                item.as_policy() for item in invalidations
            ],
            "checkpoint": checkpoint.as_policy(),
            "action": action,
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
        matching_batch_records = tuple(
            item
            for item in self.state.batch_records
            if item.receipt_id == self.receipt_id
        )
        if len(matching_batch_records) != 1:
            raise ValueError("Receipt is missing its unique run-state batch record")
        matching_record = matching_batch_records[0]
        if (
            matching_record.batch_id != self.batch_id
            or matching_record.run_id != self.run_id
            or matching_record.namespace != self.namespace
            or matching_record.generated_at != self.generated_at
            or matching_record.checkpoint_id != self.checkpoint.checkpoint_id
            or matching_record.state_revision > self.state.revision
        ):
            raise ValueError("Receipt does not match its run-state batch record")
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
        matching_batch_records = tuple(
            item
            for item in self.state.batch_records
            if item.receipt_id == self.receipt_id
        )
        if len(matching_batch_records) != 1:
            raise ValueError("Receipt is missing its unique run-state batch record")
        matching_record = matching_batch_records[0]
        if (
            matching_record.receipt_audit_fingerprint is not None
            and matching_record.receipt_audit_fingerprint
            != self.audit_fingerprint()
        ):
            raise ValueError(
                "Receipt audit fingerprint does not match its run-state batch record"
            )
        self._verify_evidence_binding()

    def _verify_evidence_binding(self) -> None:
        """Require every verdict and alert to exist in the receipt state."""

        recorded_events = {
            item.event_id: item.as_policy()
            for item in self.state.event_ledger.events()
        }
        for result in self.ingest_results:
            event = result.event
            if event is None or result.status not in _ACCEPTED_INGEST_STATUSES:
                continue
            recorded = recorded_events.get(event.event_id)
            if recorded is None:
                raise ValueError(
                    "Receipt ingest verdict is missing from its run state"
                )
            if _without_mutable_status(recorded) != _without_mutable_status(
                event.as_policy()
            ):
                raise ValueError(
                    "Receipt ingest verdict no longer matches its run state"
                )
        recorded_alerts = {
            item.alert_id: item.as_policy()
            for item in self.state.outbox.alerts()
        }
        for alert in self.alerts:
            recorded = recorded_alerts.get(alert.alert_id)
            if recorded is None:
                raise ValueError("Receipt alert is missing from its run state")
            if recorded != alert.as_policy():
                raise ValueError(
                    "Receipt alert no longer matches its run state"
                )
        for invalidation in self.invalidations:
            if invalidation.event_id not in recorded_events:
                raise ValueError(
                    "Receipt invalidation is missing from its run state"
                )

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

    def audit_fingerprint(self) -> str:
        """Hash the batch facts a retry must reproduce.

        Call-level observations, the ambient run state and mutable outbox
        delivery fields are deliberately excluded: retrying one request after
        later batches ran must reproduce the same verdicts, not the same
        surrounding state.
        """

        return _receipt_audit_fingerprint(
            receipt_id=self.receipt_id,
            run_id=self.run_id,
            batch_id=self.batch_id,
            stream_id=self.stream_id,
            namespace=self.namespace,
            generated_at=self.generated_at,
            ingest_results=self.ingest_results,
            invalidations=self.invalidations,
            checkpoint=self.checkpoint,
            action=self.action,
        )

    def to_artifact_payload(self) -> dict[str, Any]:
        payload = self.as_policy()
        return {
            "schema_version": M5_EVENT_RUN_RECEIPT_SCHEMA,
            "receipt": payload,
            "receipt_sha256": _state_digest(payload),
            "audit_fingerprint": self.audit_fingerprint(),
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_artifact_payload(),
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        )

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "M5EventRunReceipt":
        """Parse a durable receipt artifact fail-closed."""

        if not isinstance(payload, Mapping):
            raise ValueError("M5 run receipt artifact must be an object")
        data = dict(payload)
        if data.get("schema_version") != M5_EVENT_RUN_RECEIPT_SCHEMA:
            raise ValueError("Unknown M5 run receipt schema")
        if set(data) != RUN_RECEIPT_ARTIFACT_KEYS:
            missing = sorted(RUN_RECEIPT_ARTIFACT_KEYS - set(data))
            extra = sorted(set(data) - RUN_RECEIPT_ARTIFACT_KEYS)
            raise ValueError(
                "M5 run receipt artifact keys do not match the schema: "
                f"missing={missing} extra={extra}"
            )
        receipt_payload = data["receipt"]
        if not isinstance(receipt_payload, Mapping):
            raise ValueError("M5 run receipt artifact must embed a receipt")
        receipt = m5_event_run_receipt_from_payload(receipt_payload)
        if data["receipt_sha256"] != _state_digest(receipt.as_policy()):
            raise ValueError(
                "M5 run receipt artifact hash does not match its receipt"
            )
        if data["audit_fingerprint"] != receipt.audit_fingerprint():
            raise ValueError(
                "M5 run receipt audit fingerprint does not match its receipt"
            )
        return receipt


def _without_mutable_status(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Drop the ledger-owned status so a later transition is not a conflict."""

    return {
        key: value for key, value in payload.items() if key != "status"
    }


def m5_event_run_receipt_from_payload(
    payload: Mapping[str, Any],
) -> M5EventRunReceipt:
    """Rebuild a receipt from its serialized payload and re-verify it."""

    if not isinstance(payload, Mapping):
        raise ValueError("M5 run receipt must be an object")
    data = dict(payload)
    state_payload = data.get("state")
    if not isinstance(state_payload, Mapping):
        raise ValueError("M5 run receipt must embed its run state")
    state = m5_event_run_state_from_payload(state_payload)
    checkpoint_payload = data.get("checkpoint")
    if not isinstance(checkpoint_payload, Mapping):
        raise ValueError("M5 run receipt must embed its committed checkpoint")
    checkpoint_id = _required_text(
        checkpoint_payload.get("checkpoint_id"),
        "checkpoint_id",
    )
    matches = tuple(
        item
        for item in state.checkpoints.checkpoints()
        if item.checkpoint_id == checkpoint_id
    )
    if len(matches) != 1:
        raise ValueError("Receipt checkpoint is missing from its run state")
    checkpoint = matches[0]
    if dict(checkpoint_payload) != checkpoint.as_policy():
        raise ValueError(
            "Receipt checkpoint payload does not match its run state"
        )
    receipt = M5EventRunReceipt(
        receipt_id=_required_text(data["receipt_id"], "receipt_id"),
        run_id=_required_text(data["run_id"], "run_id"),
        batch_id=_required_text(data["batch_id"], "batch_id"),
        stream_id=_required_text(data["stream_id"], "stream_id"),
        namespace=_required_text(data["namespace"], "namespace"),
        generated_at=_required_datetime(
            datetime.fromisoformat(str(data["generated_at"])),
            "generated_at",
        ),
        ingest_results=tuple(
            event_ingest_result_from_payload(item)
            for item in data.get("ingest_results") or ()
        ),
        invalidations=tuple(
            dependency_invalidation_from_payload(item)
            for item in data.get("invalidations") or ()
        ),
        alerts=tuple(
            event_alert_from_payload(item)
            for item in data.get("alerts") or ()
        ),
        checkpoint=checkpoint,
        health_status=_required_text(data["health_status"], "health_status"),
        silent_ok=bool(data["silent_ok"]),
        review_due=tuple(
            str(item) for item in data.get("review_due") or ()
        ),
        state=state,
        state_sha256=_required_text(data["state_sha256"], "state_sha256"),
        idempotent_noop=bool(data.get("idempotent_noop", False)),
        action=str(data.get("action", ACTION_NO_ORDER)),
    )
    expected = receipt.as_policy()
    if set(data) != set(expected):
        missing = sorted(set(expected) - set(data))
        extra = sorted(set(data) - set(expected))
        raise ValueError(
            "M5 run receipt keys do not match the schema: "
            f"missing={missing} extra={extra}"
        )
    if data != expected:
        raise ValueError("M5 run receipt does not round-trip to its canonical form")
    return receipt


def _batch_request_fingerprint(
    *,
    events: Sequence[ChangeEventInput],
    observed_times: Sequence[datetime],
    watermark: ScanWatermark,
    graph: DependencyGraph,
    direct_kinds_by_source_event_id: Mapping[str, Sequence[str]],
) -> str:
    return batch_request_fingerprint(
        events=events,
        observed_times=observed_times,
        watermark=watermark,
        graph=graph,
        direct_kinds_by_source_event_id=direct_kinds_by_source_event_id,
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
    """Return alerts whose outcome is not yet settled by a human.

    ``FAILED_TERMINAL`` means the notification never reached a human, so it
    must keep the run in ``ATTENTION`` instead of quietly returning HEALTHY.
    """

    settled = {ALERT_ACKNOWLEDGED}
    return tuple(
        item for item in state.outbox.alerts() if item.status not in settled
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
    actual_offline_authorization: M5ActualOfflineAuthorization | None = None,
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
    require_actual_offline_authorization(
        namespace=namespace,
        authorization=actual_offline_authorization,
        graph=graph,
    )
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
        else M5EventRunState.empty(
            state_key=run_id,
            namespace=namespace,
            actual_offline_authorization=actual_offline_authorization,
        )
    )
    if namespace == "ACTUAL" and (
        working.actual_offline_authorization != actual_offline_authorization
    ):
        raise ValueError("ACTUAL M5 run state authorization does not match the request")
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
            receipt_audit_fingerprint=_receipt_audit_fingerprint(
                receipt_id=receipt_id,
                run_id=run_id,
                batch_id=batch_id,
                stream_id=working.state_key,
                namespace=namespace,
                generated_at=generated_at,
                ingest_results=ingest_results,
                invalidations=invalidations,
                checkpoint=committed.checkpoint,
                action=ACTION_NO_ORDER,
            ),
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
    actual_offline_authorization: M5ActualOfflineAuthorization | None = None,
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
            else M5EventRunState.empty(
                state_key=state_key,
                namespace=namespace,
                actual_offline_authorization=actual_offline_authorization,
            )
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
        actual_offline_authorization=actual_offline_authorization,
    )
    store.commit(
        expected_revision=working.revision,
        expected_sha256=(
            None if current is None else current.state_sha256()
        ),
        state=receipt.state,
    )
    return receipt


@dataclass(frozen=True)
class M5RunApplicationResult:
    """Outcome of applying one pinned run request."""

    request_id: str
    receipt: M5EventRunReceipt
    publication: M5ReceiptPublication | None
    replayed: bool
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "request_id",
            _required_text(self.request_id, "request_id"),
        )
        if not isinstance(self.receipt, M5EventRunReceipt):
            raise ValueError("result must embed an M5EventRunReceipt")
        if self.publication is not None:
            if not isinstance(self.publication, M5ReceiptPublication):
                raise ValueError(
                    "publication must be an M5ReceiptPublication"
                )
            if self.publication.receipt_id != self.receipt.receipt_id:
                raise ValueError(
                    "Receipt publication does not match its receipt"
                )
        if self.replayed != self.receipt.idempotent_noop:
            raise ValueError("Result replay flag must match its receipt")
        if self.action != ACTION_NO_ORDER:
            raise ValueError("M5 run application must remain no_order")

    def as_policy(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "replayed": self.replayed,
            "receipt_id": self.receipt.receipt_id,
            "audit_fingerprint": self.receipt.audit_fingerprint(),
            "state_sha256": self.receipt.state_sha256,
            "state_revision": self.receipt.state.revision,
            "health_status": self.receipt.health_status,
            "silent_ok": self.receipt.silent_ok,
            "publication": (
                None
                if self.publication is None
                else {
                    "status": self.publication.status,
                    "artifact_sha256": self.publication.artifact_sha256,
                    "path": self.publication.path,
                }
            ),
            "action": self.action,
        }


def apply_run_request(
    *,
    request: M5EventRunRequest,
    store: M5EventRunStateStore,
    receipt_store: M5EventRunReceiptStore | None = None,
    lock_store: TaskLockStore | None = None,
) -> M5RunApplicationResult:
    """Apply one pinned request once, then publish its durable receipt.

    Retries are safe in both crash windows.  Before the state commit nothing is
    persisted, so the retry applies the batch exactly once.  After the commit
    the batch record makes the retry an idempotent replay that reuses the first
    verdicts, and the write-once receipt store republishes only an identical
    audit fingerprint.
    """

    if not isinstance(request, M5EventRunRequest):
        raise ValueError("request must be an M5EventRunRequest")
    request.verify()
    current = store.load(state_key=request.stream_id)
    seed = (
        M5EventRunState.empty(
            state_key=request.stream_id,
            namespace=request.namespace,
        )
        if current is None and request.stream_id != request.run_id
        else None
    )
    receipt = run_event_batch_persisted(
        events=request.events,
        observed_times=request.observed_times,
        watermark=request.watermark,
        graph=request.dependency_graph,
        run_id=request.run_id,
        generated_at=request.generated_at,
        store=store,
        namespace=request.namespace,
        direct_kinds_by_source_event_id=request.direct_kinds_by_source_event_id,
        state=seed,
        batch_id=request.batch_id,
        lock_store=lock_store,
    )
    record = next(
        (
            item
            for item in receipt.state.batch_records
            if item.batch_id == request.batch_id
        ),
        None,
    )
    if (
        record is None
        or record.request_fingerprint != request.request_fingerprint()
    ):
        raise ValueError("Applied batch does not match the pinned run request")
    publication = (
        None
        if receipt_store is None
        else receipt_store.publish(receipt=receipt, request=request)
    )
    return M5RunApplicationResult(
        request_id=request.request_id,
        receipt=receipt,
        publication=publication,
        replayed=receipt.idempotent_noop,
    )
