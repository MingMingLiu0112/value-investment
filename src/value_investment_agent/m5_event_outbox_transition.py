"""Append-only transitions for the M5 alert outbox.

The event-batch revision records ingestion/checkpoints. Alert delivery state
changes independently, so they need their own monotonic revision and immutable
transition history. This module contains only domain records and deterministic
replay; it does not call a network or notification transport.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from .investment_decision import ACTION_NO_ORDER
from .m5_event_core import (
    _digest,
    _required_datetime,
    _required_int,
    _required_text,
    ChangeEvent,
)
from .m5_event_outbox import (
    ALERT_ACKNOWLEDGED,
    ALERT_DELIVERED,
    ALERT_FAILED_RETRYABLE,
    ALERT_FAILED_TERMINAL,
    ALERT_PENDING,
    ALERT_SENT,
    ALERT_STATUSES,
    EventAlert,
    OutboxLedger,
    alert_type_for_event_type,
)


OUTBOX_TRANSITION_SCHEMA = "m5-outbox-transition-ledger-v1"

_ALLOWED_TRANSITIONS = {
    ALERT_PENDING: frozenset(
        {ALERT_SENT, ALERT_FAILED_RETRYABLE, ALERT_FAILED_TERMINAL}
    ),
    ALERT_FAILED_RETRYABLE: frozenset(
        {ALERT_SENT, ALERT_FAILED_RETRYABLE, ALERT_FAILED_TERMINAL}
    ),
    ALERT_SENT: frozenset(
        {ALERT_DELIVERED, ALERT_FAILED_RETRYABLE, ALERT_FAILED_TERMINAL}
    ),
    ALERT_DELIVERED: frozenset({ALERT_ACKNOWLEDGED}),
    ALERT_ACKNOWLEDGED: frozenset(),
    ALERT_FAILED_TERMINAL: frozenset(),
}
_FAILURE_STATUSES = frozenset({ALERT_FAILED_RETRYABLE, ALERT_FAILED_TERMINAL})


def outbox_transition_id(
    *,
    alert_id: str,
    from_status: str,
    to_status: str,
    occurred_at: datetime,
    error: str | None,
) -> str:
    """Return the deterministic identity of one requested transition."""
    return "m5-outbox-" + _digest(
        "outbox-transition",
        alert_id,
        from_status,
        to_status,
        occurred_at.astimezone(timezone.utc).isoformat(),
        error or "",
    )[:32]


@dataclass(frozen=True)
class OutboxTransitionRecord:
    """One immutable transition applied to one alert."""

    outbox_revision: int
    alert_id: str
    from_status: str
    to_status: str
    occurred_at: datetime
    error: str | None = None
    transition_id: str = ""
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "outbox_revision",
            _required_int(self.outbox_revision, "outbox_revision"),
        )
        if self.outbox_revision < 1:
            raise ValueError("Outbox transition revision must be positive")
        object.__setattr__(
            self,
            "alert_id",
            _required_text(self.alert_id, "alert_id"),
        )
        from_status = _required_text(self.from_status, "from_status")
        to_status = _required_text(self.to_status, "to_status")
        if from_status not in ALERT_STATUSES or to_status not in ALERT_STATUSES:
            raise ValueError("Outbox transition uses an unknown alert status")
        if to_status not in _ALLOWED_TRANSITIONS[from_status]:
            raise ValueError("Outbox transition is not allowed from its current status")
        object.__setattr__(self, "from_status", from_status)
        object.__setattr__(self, "to_status", to_status)
        object.__setattr__(
            self,
            "occurred_at",
            _required_datetime(self.occurred_at, "occurred_at"),
        )
        error = (
            None
            if self.error is None
            else _required_text(self.error, "error")
        )
        if to_status in _FAILURE_STATUSES and error is None:
            raise ValueError("Failed outbox transition requires an error")
        if to_status not in _FAILURE_STATUSES and error is not None:
            raise ValueError("Successful outbox transition cannot carry an error")
        object.__setattr__(self, "error", error)
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Outbox transition must remain no_order")
        expected_id = outbox_transition_id(
            alert_id=self.alert_id,
            from_status=from_status,
            to_status=to_status,
            occurred_at=self.occurred_at,
            error=error,
        )
        transition_id = (
            expected_id
            if not self.transition_id
            else _required_text(self.transition_id, "transition_id")
        )
        if transition_id != expected_id:
            raise ValueError("Outbox transition id does not match its immutable payload")
        object.__setattr__(self, "transition_id", transition_id)

    def as_policy(self) -> dict[str, Any]:
        return {
            "outbox_revision": self.outbox_revision,
            "transition_id": self.transition_id,
            "alert_id": self.alert_id,
            "from_status": self.from_status,
            "to_status": self.to_status,
            "occurred_at": self.occurred_at.isoformat(),
            "error": self.error,
            "action": self.action,
        }


def outbox_transitions_as_policy(
    transitions: Sequence[OutboxTransitionRecord],
) -> dict[str, Any]:
    return {
        "schema_version": OUTBOX_TRANSITION_SCHEMA,
        "transitions": [item.as_policy() for item in transitions],
    }


def outbox_transitions_from_payload(
    payload: Mapping[str, Any],
) -> tuple[OutboxTransitionRecord, ...]:
    if not isinstance(payload, Mapping):
        raise ValueError("Outbox transition ledger must be an object")
    data = dict(payload)
    if data.get("schema_version") != OUTBOX_TRANSITION_SCHEMA:
        raise ValueError("Unknown outbox transition ledger schema")
    records: list[OutboxTransitionRecord] = []
    seen_ids: set[str] = set()
    for raw in data.get("transitions") or ():
        if not isinstance(raw, Mapping):
            raise ValueError("Outbox transition must be an object")
        item = dict(raw)
        record = OutboxTransitionRecord(
            outbox_revision=_required_int(
                item["outbox_revision"],
                "outbox_revision",
            ),
            alert_id=_required_text(item["alert_id"], "alert_id"),
            from_status=_required_text(item["from_status"], "from_status"),
            to_status=_required_text(item["to_status"], "to_status"),
            occurred_at=_required_datetime(
                datetime.fromisoformat(str(item["occurred_at"])),
                "occurred_at",
            ),
            error=(
                None
                if item.get("error") is None
                else _required_text(item["error"], "error")
            ),
            transition_id=_required_text(item["transition_id"], "transition_id"),
            action=str(item.get("action", ACTION_NO_ORDER)),
        )
        if record.transition_id in seen_ids:
            raise ValueError("Outbox transition ledger contains a duplicate id")
        seen_ids.add(record.transition_id)
        records.append(record)
    return tuple(records)


def replay_outbox_transitions(
    *,
    events: Sequence[ChangeEvent],
    transitions: Sequence[OutboxTransitionRecord],
) -> OutboxLedger:
    """Reconstruct the outbox from events plus its append-only transitions."""
    ledger = OutboxLedger()
    for event in events:
        enqueued = ledger.enqueue_for_event(
            event=event,
            alert_type=alert_type_for_event_type(event.event_type),
            now=event.ingested_at,
        )
        if enqueued.alert is None:
            raise ValueError("Could not reconstruct event alert during replay")

    by_id = {item.alert_id: item for item in ledger.alerts()}
    for index, record in enumerate(transitions, start=1):
        if record.outbox_revision != index:
            raise ValueError("Outbox transition revisions must be contiguous")
        current = by_id.get(record.alert_id)
        if current is None:
            raise ValueError("Outbox transition references an unknown alert")
        if current.status != record.from_status:
            raise ValueError("Outbox transition from_status does not match replay")
        if record.to_status == ALERT_SENT:
            updated = ledger.mark_sent(alert_id=record.alert_id, now=record.occurred_at)
        elif record.to_status == ALERT_DELIVERED:
            updated = ledger.mark_delivered(
                alert_id=record.alert_id,
                now=record.occurred_at,
            )
        elif record.to_status == ALERT_ACKNOWLEDGED:
            updated = ledger.mark_acknowledged(
                alert_id=record.alert_id,
                now=record.occurred_at,
            )
        elif record.to_status in _FAILURE_STATUSES:
            if record.error is None:
                raise ValueError("Outbox failure transition requires an error")
            updated = ledger.mark_failed(
                alert_id=record.alert_id,
                now=record.occurred_at,
                error=record.error,
                terminal=record.to_status == ALERT_FAILED_TERMINAL,
            )
        else:
            raise ValueError("Unsupported outbox transition during replay")
        if updated.status != record.to_status:
            raise ValueError("Outbox transition replay produced a different status")
        by_id[record.alert_id] = updated
    return ledger


def alert_by_id(ledger: OutboxLedger, alert_id: str) -> EventAlert:
    for alert in ledger.alerts():
        if alert.alert_id == alert_id:
            return alert
    raise ValueError("Alert does not exist")
