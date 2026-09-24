"""Deduplicated M5 alert outbox without network delivery."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any, Mapping

from .investment_decision import ACTION_NO_ORDER
from .m5_event_core import (
    M5_EVENT_SCHEMA,
    _digest,
    _required_bool,
    _required_datetime,
    _required_int,
    _required_text,
    _SYSTEM_EVENT_TYPES,
    ChangeEvent,
    EVENT_TYPE_DIVIDEND_CHANGE,
    EVENT_TYPE_MODEL_STALE,
    EVENT_TYPE_POSITION_RISK_CHANGED,
    EVENT_TYPE_SOURCE_SCAN_FAILED,
    EVENT_TYPE_SOURCE_SCAN_RECOVERED,
    EVENT_TYPE_THESIS_BREAKER_TRIGGERED,
    EVENT_TYPE_THESIS_WEAKENED,
    EVENT_SEVERITIES,
)


ALERT_PENDING = "PENDING"
ALERT_SENT = "SENT"
ALERT_DELIVERED = "DELIVERED"
ALERT_ACKNOWLEDGED = "ACKNOWLEDGED"
ALERT_FAILED_RETRYABLE = "FAILED_RETRYABLE"
ALERT_FAILED_TERMINAL = "FAILED_TERMINAL"
ALERT_STATUSES = frozenset(
    {
        ALERT_PENDING,
        ALERT_SENT,
        ALERT_DELIVERED,
        ALERT_ACKNOWLEDGED,
        ALERT_FAILED_RETRYABLE,
        ALERT_FAILED_TERMINAL,
    }
)

ALERT_TYPE_REVIEW_DUE = "REVIEW_DUE"
ALERT_TYPE_CRITICAL_BREAKER = "CRITICAL_BREAKER"
ALERT_TYPE_MODEL_STALE = "MODEL_STALE"
ALERT_TYPE_THESIS_ALERT = "THESIS_ALERT"
ALERT_TYPE_DIVIDEND_ALERT = "DIVIDEND_ALERT"
ALERT_TYPE_POSITION_RISK = "POSITION_RISK"
ALERT_TYPE_SYSTEM_HEALTH = "SYSTEM_HEALTH"
ALERT_TYPES = frozenset(
    {
        ALERT_TYPE_REVIEW_DUE,
        ALERT_TYPE_CRITICAL_BREAKER,
        ALERT_TYPE_MODEL_STALE,
        ALERT_TYPE_THESIS_ALERT,
        ALERT_TYPE_DIVIDEND_ALERT,
        ALERT_TYPE_POSITION_RISK,
        ALERT_TYPE_SYSTEM_HEALTH,
    }
)

_ALERT_TYPE_BY_EVENT_TYPE = {
    EVENT_TYPE_THESIS_BREAKER_TRIGGERED: ALERT_TYPE_CRITICAL_BREAKER,
    EVENT_TYPE_THESIS_WEAKENED: ALERT_TYPE_THESIS_ALERT,
    EVENT_TYPE_MODEL_STALE: ALERT_TYPE_MODEL_STALE,
    EVENT_TYPE_DIVIDEND_CHANGE: ALERT_TYPE_DIVIDEND_ALERT,
    EVENT_TYPE_POSITION_RISK_CHANGED: ALERT_TYPE_POSITION_RISK,
    EVENT_TYPE_SOURCE_SCAN_FAILED: ALERT_TYPE_SYSTEM_HEALTH,
    EVENT_TYPE_SOURCE_SCAN_RECOVERED: ALERT_TYPE_SYSTEM_HEALTH,
}


def alert_type_for_event_type(event_type: str) -> str:
    """Return the canonical alert type for one accepted event type."""
    return _ALERT_TYPE_BY_EVENT_TYPE.get(event_type, ALERT_TYPE_REVIEW_DUE)


ALERT_ENQUEUED = "ENQUEUED"
ALERT_DUPLICATE = "DUPLICATE"
ALERT_TERMINAL_DUPLICATE = "TERMINAL_DUPLICATE"
ALERT_ENQUEUE_STATUSES = frozenset(
    {ALERT_ENQUEUED, ALERT_DUPLICATE, ALERT_TERMINAL_DUPLICATE}
)


@dataclass(frozen=True)
class EventAlert:
    alert_id: str
    alert_type: str
    severity: str
    event_id: str | None
    dedupe_key: str
    requires_human_review: bool
    created_at: datetime
    status: str
    attempts: int
    next_attempt_at: datetime | None
    last_error: str | None
    delivered_at: datetime | None
    sent_at: datetime | None = None
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        object.__setattr__(self, "alert_id", _required_text(self.alert_id, "alert_id"))
        if self.alert_type not in ALERT_TYPES:
            raise ValueError("Unknown alert type")
        if self.severity not in EVENT_SEVERITIES:
            raise ValueError("Unknown alert severity")
        object.__setattr__(
            self,
            "event_id",
            None if self.event_id is None else _required_text(self.event_id, "event_id"),
        )
        object.__setattr__(
            self,
            "dedupe_key",
            _required_text(self.dedupe_key, "dedupe_key"),
        )
        object.__setattr__(
            self,
            "requires_human_review",
            _required_bool(self.requires_human_review, "requires_human_review"),
        )
        object.__setattr__(
            self,
            "created_at",
            _required_datetime(self.created_at, "created_at"),
        )
        if self.status not in ALERT_STATUSES:
            raise ValueError("Unknown alert status")
        object.__setattr__(
            self,
            "attempts",
            _required_int(self.attempts, "attempts"),
        )
        if self.attempts < 0:
            raise ValueError("Alert attempts cannot be negative")
        object.__setattr__(
            self,
            "next_attempt_at",
            None
            if self.next_attempt_at is None
            else _required_datetime(self.next_attempt_at, "next_attempt_at"),
        )
        object.__setattr__(
            self,
            "last_error",
            None if self.last_error is None else _required_text(self.last_error, "last_error"),
        )
        object.__setattr__(
            self,
            "delivered_at",
            None
            if self.delivered_at is None
            else _required_datetime(self.delivered_at, "delivered_at"),
        )
        object.__setattr__(
            self,
            "sent_at",
            None
            if self.sent_at is None
            else _required_datetime(self.sent_at, "sent_at"),
        )
        if self.next_attempt_at is not None and self.next_attempt_at < self.created_at:
            raise ValueError("Alert next attempt cannot precede creation")
        if self.sent_at is not None and self.sent_at < self.created_at:
            raise ValueError("Alert sent time cannot precede creation")
        if self.delivered_at is not None and self.delivered_at < self.created_at:
            raise ValueError("Alert delivery cannot precede creation")
        if (
            self.delivered_at is not None
            and self.sent_at is not None
            and self.delivered_at < self.sent_at
        ):
            raise ValueError("Alert delivery cannot precede its send attempt")
        if self.status == ALERT_PENDING:
            if self.attempts != 0 or self.next_attempt_at is None:
                raise ValueError("Pending alert requires zero attempts and next_attempt_at")
            if self.sent_at is not None or self.delivered_at is not None:
                raise ValueError("Pending alert cannot have send or delivery times")
        elif self.status == ALERT_SENT:
            if self.attempts < 1 or self.next_attempt_at is not None:
                raise ValueError("Sent alert requires attempts and no retry time")
            if self.sent_at is None or self.delivered_at is not None:
                raise ValueError("Sent alert requires sent_at and no delivered_at")
        elif self.status in {ALERT_DELIVERED, ALERT_ACKNOWLEDGED}:
            if self.attempts < 1 or self.next_attempt_at is not None:
                raise ValueError("Delivered alert requires attempts and no retry time")
            if self.delivered_at is None:
                raise ValueError("Delivered alert requires delivered_at")
            if self.sent_at is None:
                raise ValueError("Delivered alert requires sent_at")
        elif self.status == ALERT_FAILED_RETRYABLE:
            if self.attempts < 1 or self.next_attempt_at is None:
                raise ValueError("Retryable failure requires attempts and next_attempt_at")
            if self.delivered_at is not None:
                raise ValueError("Retryable failure cannot have delivered_at")
        elif self.status == ALERT_FAILED_TERMINAL:
            if self.attempts < 1 or self.next_attempt_at is not None:
                raise ValueError("Terminal failure requires attempts and no retry time")
            if self.delivered_at is not None:
                raise ValueError("Terminal failure cannot have delivered_at")
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Event alert must remain no_order")

    def as_policy(self) -> dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "alert_type": self.alert_type,
            "severity": self.severity,
            "event_id": self.event_id,
            "dedupe_key": self.dedupe_key,
            "requires_human_review": self.requires_human_review,
            "created_at": self.created_at.isoformat(),
            "status": self.status,
            "attempts": self.attempts,
            "next_attempt_at": self.next_attempt_at.isoformat()
            if self.next_attempt_at
            else None,
            "last_error": self.last_error,
            "delivered_at": self.delivered_at.isoformat() if self.delivered_at else None,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "action": self.action,
        }


@dataclass(frozen=True)
class AlertEnqueueResult:
    status: str
    alert: EventAlert | None
    duplicate_alert: EventAlert | None = None
    message: str = ""

    def __post_init__(self) -> None:
        if self.status not in ALERT_ENQUEUE_STATUSES:
            raise ValueError("Unknown alert enqueue status")
        if self.alert is not None and not isinstance(self.alert, EventAlert):
            raise ValueError("alert must be an EventAlert")
        if self.duplicate_alert is not None and not isinstance(
            self.duplicate_alert,
            EventAlert,
        ):
            raise ValueError("duplicate_alert must be an EventAlert")
        object.__setattr__(self, "message", str(self.message or ""))

    def as_policy(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "alert": self.alert.as_policy() if self.alert else None,
            "duplicate_alert": self.duplicate_alert.as_policy()
            if self.duplicate_alert
            else None,
            "message": self.message,
        }


class OutboxLedger:
    """Deduplicated, retryable alert bookkeeping without network delivery."""

    def __init__(self, *, schema_version: str = M5_EVENT_SCHEMA) -> None:
        self.schema_version = schema_version
        self._alerts: list[EventAlert] = []
        self._by_dedupe: dict[str, EventAlert] = {}

    def alerts(self) -> tuple[EventAlert, ...]:
        return tuple(self._alerts)

    def enqueue_for_event(
        self,
        *,
        event: ChangeEvent,
        alert_type: str,
        now: datetime,
    ) -> AlertEnqueueResult:
        return self._enqueue(
            alert_type=alert_type,
            severity=event.severity,
            event_id=event.event_id,
            dedupe_key=f"event:{event.event_id}:{alert_type}",
            requires_human_review=event.requires_human_review,
            now=now,
            critical=event.is_critical,
        )

    def enqueue_system_health(
        self,
        *,
        event: ChangeEvent,
        now: datetime,
    ) -> AlertEnqueueResult:
        if event.event_type not in _SYSTEM_EVENT_TYPES:
            raise ValueError("System health alert requires a source health event")
        return self._enqueue(
            alert_type=ALERT_TYPE_SYSTEM_HEALTH,
            severity=event.severity,
            event_id=event.event_id,
            dedupe_key=f"health:{event.event_id}",
            requires_human_review=True,
            now=now,
            critical=False,
        )

    def _enqueue(
        self,
        *,
        alert_type: str,
        severity: str,
        event_id: str | None,
        dedupe_key: str,
        requires_human_review: bool,
        now: datetime,
        critical: bool,
    ) -> AlertEnqueueResult:
        now = _required_datetime(now, "now")
        existing = self._by_dedupe.get(dedupe_key)
        if existing is not None:
            return AlertEnqueueResult(
                status=(
                    ALERT_TERMINAL_DUPLICATE
                    if existing.status in {ALERT_ACKNOWLEDGED, ALERT_FAILED_TERMINAL}
                    else ALERT_DUPLICATE
                ),
                alert=None,
                duplicate_alert=existing,
                message="Alert already tracked for this event",
            )
        alert = EventAlert(
            alert_id="m5-alert-"
            + _digest("alert", alert_type, event_id or "", dedupe_key, now.isoformat())[
                :32
            ],
            alert_type=alert_type,
            severity=severity,
            event_id=event_id,
            dedupe_key=dedupe_key,
            requires_human_review=requires_human_review,
            created_at=now,
            status=ALERT_PENDING,
            attempts=0,
            next_attempt_at=now,
            last_error=None,
            delivered_at=None,
        )
        self._alerts.append(alert)
        self._by_dedupe[dedupe_key] = alert
        return AlertEnqueueResult(status=ALERT_ENQUEUED, alert=alert, message="Alert enqueued")

    def mark_sent(self, *, alert_id: str, now: datetime) -> EventAlert:
        alert = self._require(alert_id)
        if alert.status not in {ALERT_PENDING, ALERT_FAILED_RETRYABLE}:
            raise ValueError("Only pending or retryable alerts can be sent")
        now = _required_datetime(now, "now")
        if alert.next_attempt_at is not None and now < alert.next_attempt_at:
            raise ValueError("Alert cannot be sent before its next attempt time")
        updated = self._copy_with(
            alert,
            status=ALERT_SENT,
            attempts=alert.attempts + 1,
            next_attempt_at=None,
            last_error=None,
            sent_at=now,
        )
        self._replace(alert, updated)
        return updated

    def mark_delivered(self, *, alert_id: str, now: datetime) -> EventAlert:
        alert = self._require(alert_id)
        if alert.status != ALERT_SENT:
            raise ValueError("Only sent alerts can be delivered")
        now = _required_datetime(now, "now")
        if alert.sent_at is not None and now < alert.sent_at:
            raise ValueError("Alert delivery cannot precede its send attempt")
        updated = self._copy_with(
            alert,
            status=ALERT_DELIVERED,
            delivered_at=now,
        )
        self._replace(alert, updated)
        return updated

    def mark_acknowledged(self, *, alert_id: str, now: datetime) -> EventAlert:
        alert = self._require(alert_id)
        if alert.status != ALERT_DELIVERED:
            raise ValueError("Only delivered alerts can be acknowledged")
        now = _required_datetime(now, "now")
        if alert.delivered_at is not None and now < alert.delivered_at:
            raise ValueError("Alert acknowledgement cannot precede delivery")
        updated = self._copy_with(alert, status=ALERT_ACKNOWLEDGED)
        self._replace(alert, updated)
        return updated

    def mark_failed(
        self,
        *,
        alert_id: str,
        now: datetime,
        error: str,
        terminal: bool = False,
    ) -> EventAlert:
        alert = self._require(alert_id)
        if alert.status not in {ALERT_PENDING, ALERT_SENT, ALERT_FAILED_RETRYABLE}:
            raise ValueError("Alert cannot be retried from its current status")
        now = _required_datetime(now, "now")
        for label, timestamp in (
            ("creation", alert.created_at),
            ("next attempt", alert.next_attempt_at),
            ("send attempt", alert.sent_at),
        ):
            if timestamp is not None and now < timestamp:
                raise ValueError(f"Alert failure cannot precede its {label} time")
        backoff_seconds = min(300, 30 * (2 ** max(alert.attempts, 1)))
        updated = self._copy_with(
            alert,
            status=ALERT_FAILED_TERMINAL if terminal else ALERT_FAILED_RETRYABLE,
            attempts=alert.attempts + 1,
            next_attempt_at=(
                None if terminal else now + timedelta(seconds=backoff_seconds)
            ),
            last_error=error,
        )
        self._replace(alert, updated)
        return updated

    def pending(self, now: datetime) -> tuple[EventAlert, ...]:
        now = _required_datetime(now, "now")
        return tuple(
            sorted(
                (
                    item
                    for item in self._alerts
                    if (
                        item.status == ALERT_PENDING
                        and item.next_attempt_at is not None
                        and item.next_attempt_at <= now
                    )
                    or (
                        item.status == ALERT_FAILED_RETRYABLE
                        and item.next_attempt_at is not None
                        and item.next_attempt_at <= now
                    )
                ),
                key=lambda item: (item.created_at, item.alert_id),
            )
        )

    def _copy_with(self, alert: EventAlert, **changes: Any) -> EventAlert:
        return replace(alert, **changes)

    def _require(self, alert_id: str) -> EventAlert:
        alert_id = _required_text(alert_id, "alert_id")
        for item in self._alerts:
            if item.alert_id == alert_id:
                return item
        raise ValueError("Alert does not exist")

    def _replace(self, old: EventAlert, new: EventAlert) -> None:
        for index, item in enumerate(self._alerts):
            if item.alert_id == old.alert_id:
                self._alerts[index] = new
                self._by_dedupe[old.dedupe_key] = new
                return
        raise ValueError("Alert does not exist")

    def as_policy(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "alerts": [item.as_policy() for item in self._alerts],
        }


def event_alert_from_payload(payload: Mapping[str, Any]) -> EventAlert:
    """Parse a serialized outbox alert fail-closed."""

    if not isinstance(payload, Mapping):
        raise ValueError("Outbox alert must be an object")
    data = dict(payload)
    alert = EventAlert(
        alert_id=_required_text(data["alert_id"], "alert_id"),
        alert_type=_required_text(data["alert_type"], "alert_type"),
        severity=_required_text(data["severity"], "severity"),
        event_id=(
            None
            if data.get("event_id") is None
            else _required_text(data["event_id"], "event_id")
        ),
        dedupe_key=_required_text(data["dedupe_key"], "dedupe_key"),
        requires_human_review=_required_bool(
            data["requires_human_review"],
            "requires_human_review",
        ),
        created_at=_required_datetime(
            datetime.fromisoformat(str(data["created_at"])),
            "created_at",
        ),
        status=_required_text(data["status"], "status"),
        attempts=_required_int(data["attempts"], "attempts"),
        next_attempt_at=(
            _required_datetime(
                datetime.fromisoformat(str(data["next_attempt_at"])),
                "next_attempt_at",
            )
            if data.get("next_attempt_at")
            else None
        ),
        last_error=(
            None
            if data.get("last_error") is None
            else _required_text(data["last_error"], "last_error")
        ),
        delivered_at=(
            _required_datetime(
                datetime.fromisoformat(str(data["delivered_at"])),
                "delivered_at",
            )
            if data.get("delivered_at")
            else None
        ),
        sent_at=(
            _required_datetime(
                datetime.fromisoformat(str(data["sent_at"])),
                "sent_at",
            )
            if data.get("sent_at")
            else None
        ),
        action=str(data.get("action", ACTION_NO_ORDER)),
    )
    expected = set(alert.as_policy())
    if set(data) != expected:
        missing = sorted(expected - set(data))
        extra = sorted(set(data) - expected)
        raise ValueError(
            "Outbox alert payload keys do not match the schema: "
            f"missing={missing} extra={extra}"
        )
    return alert


def outbox_ledger_from_payload(payload: Mapping[str, Any]) -> OutboxLedger:
    if not isinstance(payload, Mapping):
        raise ValueError("Outbox ledger must be an object")
    data = dict(payload)
    if data.get("schema_version") != M5_EVENT_SCHEMA:
        raise ValueError("Unknown outbox ledger schema")
    ledger = OutboxLedger(schema_version=str(data["schema_version"]))
    seen_alert_ids: set[str] = set()
    for raw in data.get("alerts") or ():
        alert = event_alert_from_payload(raw)
        if alert.alert_id in seen_alert_ids:
            raise ValueError("Outbox ledger contains a duplicate alert id")
        if alert.dedupe_key in ledger._by_dedupe:
            raise ValueError("Outbox ledger contains a duplicate dedupe key")
        seen_alert_ids.add(alert.alert_id)
        ledger._alerts.append(alert)
        ledger._by_dedupe[alert.dedupe_key] = alert
    return ledger
