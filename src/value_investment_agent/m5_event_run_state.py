"""Versioned aggregate state for offline M5 event runs.

The state is deliberately storage-neutral: callers may persist ``to_json()``
atomically and restore it with ``m5_event_run_state_from_payload()``. Import
validation is fail-closed and checks references across all child ledgers.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import re
from typing import Any, Mapping

from .investment_decision import ACTION_NO_ORDER
from .m5_event_checkpoint import (
    CHECKPOINT_COMMITTED,
    CheckpointLedger,
    checkpoint_ledger_from_payload,
)
from .m5_event_core import (
    M5_EVENT_SCHEMA,
    NAMESPACE_SIMULATED,
    EventLedger,
    _digest,
    _required_datetime,
    _required_int,
    _required_text,
    _state_digest,
    event_ledger_from_payload,
)
from .m5_event_outbox import (
    EventAlert,
    OutboxLedger,
    alert_type_for_event_type,
    outbox_ledger_from_payload,
)
from .m5_event_watermark import WatermarkLedger, watermark_ledger_from_payload


M5_RUN_STATE_SCHEMA = "m5-event-run-state-v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class M5EventBatchRecord:
    """Idempotency metadata for one logical batch applied to a state."""

    batch_id: str
    run_id: str
    namespace: str
    generated_at: datetime
    request_fingerprint: str
    receipt_id: str
    checkpoint_id: str
    state_revision: int
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "batch_id",
            _required_text(self.batch_id, "batch_id"),
        )
        object.__setattr__(
            self,
            "run_id",
            _required_text(self.run_id, "run_id"),
        )
        object.__setattr__(
            self,
            "namespace",
            _required_text(self.namespace, "namespace"),
        )
        object.__setattr__(
            self,
            "generated_at",
            _required_datetime(self.generated_at, "generated_at"),
        )
        object.__setattr__(
            self,
            "request_fingerprint",
            _required_text(self.request_fingerprint, "request_fingerprint").lower(),
        )
        if not _SHA256.fullmatch(self.request_fingerprint):
            raise ValueError("Batch request fingerprint must be SHA-256 hex")
        object.__setattr__(
            self,
            "receipt_id",
            _required_text(self.receipt_id, "receipt_id"),
        )
        object.__setattr__(
            self,
            "checkpoint_id",
            _required_text(self.checkpoint_id, "checkpoint_id"),
        )
        object.__setattr__(
            self,
            "state_revision",
            _required_int(self.state_revision, "state_revision"),
        )
        if self.state_revision < 1:
            raise ValueError("Batch state revision must be positive")
        expected_receipt_id = "m5-run-" + _digest(
            "run-receipt",
            self.run_id,
            self.batch_id,
            self.generated_at.isoformat(),
        )[:32]
        if self.receipt_id != expected_receipt_id:
            raise ValueError("Batch receipt id does not match its immutable payload")
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Batch record must remain no_order")

    def as_policy(self) -> dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "run_id": self.run_id,
            "namespace": self.namespace,
            "generated_at": self.generated_at.isoformat(),
            "request_fingerprint": self.request_fingerprint,
            "receipt_id": self.receipt_id,
            "checkpoint_id": self.checkpoint_id,
            "state_revision": self.state_revision,
            "action": self.action,
        }


@dataclass(frozen=True)
class M5EventRunState:
    """Serializable aggregate used by the offline M5 run coordinator."""

    state_key: str
    namespace: str
    revision: int
    event_ledger: EventLedger
    watermarks: WatermarkLedger
    checkpoints: CheckpointLedger
    outbox: OutboxLedger
    batch_records: tuple[M5EventBatchRecord, ...] = ()
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "state_key",
            _required_text(self.state_key, "state_key"),
        )
        object.__setattr__(
            self,
            "namespace",
            _required_text(self.namespace, "namespace"),
        )
        if self.namespace != NAMESPACE_SIMULATED:
            raise ValueError("Public M5 run state must remain SIMULATED")
        object.__setattr__(
            self,
            "revision",
            _required_int(self.revision, "revision"),
        )
        if self.revision < 0:
            raise ValueError("M5 run state revision cannot be negative")
        if not isinstance(self.event_ledger, EventLedger):
            raise ValueError("event_ledger must be an EventLedger")
        if self.event_ledger.namespace != self.namespace:
            raise ValueError("Event ledger namespace must match run state")
        if not isinstance(self.watermarks, WatermarkLedger):
            raise ValueError("watermarks must be a WatermarkLedger")
        if not isinstance(self.checkpoints, CheckpointLedger):
            raise ValueError("checkpoints must be a CheckpointLedger")
        if not isinstance(self.outbox, OutboxLedger):
            raise ValueError("outbox must be an OutboxLedger")
        records = tuple(self.batch_records)
        if any(not isinstance(item, M5EventBatchRecord) for item in records):
            raise ValueError("batch_records must contain M5EventBatchRecord")
        object.__setattr__(self, "batch_records", records)
        if self.action != ACTION_NO_ORDER:
            raise ValueError("M5 run state must remain no_order")
        self._validate_cross_ledger_integrity()

    def _validate_cross_ledger_integrity(self) -> None:
        events = self.event_ledger.events()
        event_ids = {event.event_id for event in events}
        checkpoints = self.checkpoints.checkpoints()
        if any(item.run_id != self.state_key for item in checkpoints):
            raise ValueError("Checkpoint run identity does not match state_key")
        if any(item.status == "RUNNING" for item in checkpoints):
            raise ValueError("Exportable M5 run state cannot contain an open checkpoint")

        committed = [
            item for item in checkpoints if item.status == CHECKPOINT_COMMITTED
        ]
        previous_sequence = 0
        for checkpoint in committed:
            if checkpoint.last_sequence > len(events):
                raise ValueError(
                    "Checkpoint sequence exceeds the event ledger length"
                )
            if checkpoint.last_sequence < previous_sequence:
                raise ValueError("Committed checkpoint sequence cannot regress")
            expected_ids = tuple(
                event.event_id
                for event in events[previous_sequence : checkpoint.last_sequence]
            )
            if checkpoint.ingested_event_ids != expected_ids:
                raise ValueError(
                    "Checkpoint ingested event ids do not match its sequence window"
                )
            previous_sequence = checkpoint.last_sequence

        latest_committed = committed[-1] if committed else None
        if events and latest_committed is None:
            raise ValueError("Non-empty event ledger requires a committed checkpoint")
        if events and latest_committed.last_sequence != len(events):
            raise ValueError("Latest committed checkpoint does not cover all events")
        current_watermark_ids = {
            item.watermark_id for item in self.watermarks.watermarks()
        }
        if committed:
            if not latest_committed.watermark_ids:
                raise ValueError("Latest committed checkpoint requires watermarks")
            if set(latest_committed.watermark_ids) != current_watermark_ids:
                raise ValueError(
                    "Latest checkpoint watermarks do not match current watermarks"
                )
        elif current_watermark_ids:
            raise ValueError("Watermarks require a committed checkpoint")

        events_by_id = {event.event_id: event for event in events}
        alerts_by_event_id: dict[str, list[EventAlert]] = {}
        for alert in self.outbox.alerts():
            if alert.event_id is None:
                continue
            if alert.event_id not in events_by_id:
                raise ValueError("Outbox alert references an unknown event")
            alerts_by_event_id.setdefault(alert.event_id, []).append(alert)

        for event in events:
            linked_alerts = alerts_by_event_id.get(event.event_id, [])
            expected_alert_type = alert_type_for_event_type(event.event_type)
            expected_dedupe_key = f"event:{event.event_id}:{expected_alert_type}"
            if not any(
                alert.alert_type == expected_alert_type
                and alert.dedupe_key == expected_dedupe_key
                for alert in linked_alerts
            ):
                raise ValueError("Event is missing its expected outbox alert")
            source_event = events_by_id[event.event_id]
            for alert in linked_alerts:
                if alert.severity != source_event.severity:
                    raise ValueError(
                        "Outbox alert severity does not match its event"
                    )
                if alert.requires_human_review != source_event.requires_human_review:
                    raise ValueError(
                        "Outbox alert review requirement does not match its event"
                    )

        if not self.batch_records:
            if self.revision != 0:
                raise ValueError("State revision without batch records is invalid")
            if committed:
                raise ValueError("Committed checkpoints require batch records")
            return
        if len(self.batch_records) != len(committed):
            raise ValueError("Batch records must match committed checkpoints")
        seen_batches: set[str] = set()
        seen_receipts: set[str] = set()
        for index, record in enumerate(self.batch_records, start=1):
            if record.batch_id in seen_batches:
                raise ValueError("State contains a duplicate batch id")
            if record.receipt_id in seen_receipts:
                raise ValueError("State contains a duplicate batch receipt id")
            if record.namespace != self.namespace:
                raise ValueError("Batch record namespace must match run state")
            if record.state_revision != index:
                raise ValueError("Batch state revision must be contiguous")
            if record.checkpoint_id != committed[index - 1].checkpoint_id:
                raise ValueError(
                    "Batch records and committed checkpoints are out of order"
                )
            seen_batches.add(record.batch_id)
            seen_receipts.add(record.receipt_id)
        if self.revision != len(self.batch_records):
            raise ValueError("State revision does not match its latest batch record")

    def as_policy(self) -> dict[str, Any]:
        return {
            "schema_version": M5_RUN_STATE_SCHEMA,
            "state_key": self.state_key,
            "namespace": self.namespace,
            "revision": self.revision,
            "event_ledger": self.event_ledger.as_policy(),
            "watermarks": self.watermarks.as_policy(),
            "checkpoints": self.checkpoints.as_policy(),
            "outbox": self.outbox.as_policy(),
            "batch_records": [item.as_policy() for item in self.batch_records],
            "action": self.action,
        }

    def state_sha256(self) -> str:
        return _state_digest(self.as_policy())

    def to_json(self) -> str:
        return json.dumps(
            self.as_policy(),
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        )

    def clone(self) -> "M5EventRunState":
        return m5_event_run_state_from_payload(json.loads(self.to_json()))

    @classmethod
    def empty(
        cls,
        *,
        state_key: str,
        namespace: str = NAMESPACE_SIMULATED,
    ) -> "M5EventRunState":
        return cls(
            state_key=state_key,
            namespace=namespace,
            revision=0,
            event_ledger=EventLedger(namespace=namespace),
            watermarks=WatermarkLedger(),
            checkpoints=CheckpointLedger(),
            outbox=OutboxLedger(),
            batch_records=(),
        )


def m5_event_run_state_from_payload(payload: Mapping[str, Any]) -> M5EventRunState:
    if not isinstance(payload, Mapping):
        raise ValueError("M5 run state must be an object")
    data = dict(payload)
    if data.get("schema_version") != M5_RUN_STATE_SCHEMA:
        raise ValueError("Unknown M5 run state schema")
    batch_records: list[M5EventBatchRecord] = []
    for raw in data.get("batch_records") or ():
        if not isinstance(raw, Mapping):
            raise ValueError("Batch record must be an object")
        item = dict(raw)
        batch_records.append(
            M5EventBatchRecord(
                batch_id=_required_text(item["batch_id"], "batch_id"),
                run_id=_required_text(item["run_id"], "run_id"),
                namespace=_required_text(item["namespace"], "namespace"),
                generated_at=_required_datetime(
                    datetime.fromisoformat(str(item["generated_at"])),
                    "generated_at",
                ),
                request_fingerprint=_required_text(
                    item["request_fingerprint"],
                    "request_fingerprint",
                ),
                receipt_id=_required_text(item["receipt_id"], "receipt_id"),
                checkpoint_id=_required_text(
                    item["checkpoint_id"],
                    "checkpoint_id",
                ),
                state_revision=_required_int(
                    item["state_revision"],
                    "state_revision",
                ),
                action=str(item.get("action", ACTION_NO_ORDER)),
            )
        )
    return M5EventRunState(
        state_key=_required_text(data["state_key"], "state_key"),
        namespace=_required_text(data["namespace"], "namespace"),
        revision=_required_int(data["revision"], "revision"),
        event_ledger=event_ledger_from_payload(data.get("event_ledger") or {}),
        watermarks=watermark_ledger_from_payload(data.get("watermarks") or {}),
        checkpoints=checkpoint_ledger_from_payload(data.get("checkpoints") or {}),
        outbox=outbox_ledger_from_payload(data.get("outbox") or {}),
        batch_records=tuple(batch_records),
        action=str(data.get("action", ACTION_NO_ORDER)),
    )
