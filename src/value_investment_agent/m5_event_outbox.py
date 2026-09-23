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
        if self.status == ALERT_FAILED_RETRYABLE and self.next_attempt_at is None:
            raise ValueError("Retryable failure requires next_attempt_at")
        if self.status == ALERT_DELIVERED and self.delivered_at is None:
            raise ValueError("Delivered alert requires delivered_at")
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
            dedupe_key=f"health:{event.source_event_id}",
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
        updated = self._copy_with(
            alert,
            status=ALERT_SENT,
            attempts=alert.attempts + 1,
            next_attempt_at=None,
            last_error=None,
        )
        self._replace(alert, updated)
        return updated

    def mark_delivered(self, *, alert_id: str, now: datetime) -> EventAlert:
        alert = self._require(alert_id)
        if alert.status != ALERT_SENT:
            raise ValueError("Only sent alerts can be delivered")
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
        backoff_seconds = min(300, 30 * (2 ** (alert.attempts - 1)))
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
                    if item.status == ALERT_PENDING
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
