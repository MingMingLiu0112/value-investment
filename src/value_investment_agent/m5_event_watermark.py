"""Monotonic M5 scan watermarks and single-scope task leases."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import json
from typing import Any, Mapping, Sequence

from .investment_decision import ACTION_NO_ORDER
from .m5_event_core import (
    M5_EVENT_SCHEMA,
    _digest,
    _positive_int,
    _required_datetime,
    _required_refs,
    _required_text,
)


WATERMARK_COVERAGE_COMPLETE = "COMPLETE"
WATERMARK_COVERAGE_INCOMPLETE = "INCOMPLETE"
WATERMARK_COVERAGE_STATUSES = frozenset(
    {WATERMARK_COVERAGE_COMPLETE, WATERMARK_COVERAGE_INCOMPLETE}
)

SOURCE_HEALTHY = "HEALTHY"
SOURCE_DEGRADED = "DEGRADED"
SOURCE_OUTAGE = "OUTAGE"
SOURCE_RECOVERED = "RECOVERED"
SOURCE_HEALTH_STATUSES = frozenset(
    {SOURCE_HEALTHY, SOURCE_DEGRADED, SOURCE_OUTAGE, SOURCE_RECOVERED}
)

WATERMARK_ACCEPTED = "ACCEPTED"
WATERMARK_DUPLICATE = "DUPLICATE"
WATERMARK_REGRESSION_REJECTED = "REGRESSION_REJECTED"
WATERMARK_RESULT_STATUSES = frozenset(
    {WATERMARK_ACCEPTED, WATERMARK_DUPLICATE, WATERMARK_REGRESSION_REJECTED}
)

LOCK_ACQUIRED = "ACQUIRED"
LOCK_REPLACED_EXPIRED = "REPLACED_EXPIRED"
LOCK_ALREADY_HELD = "ALREADY_HELD"
LOCK_CONFLICT = "CONFLICT"
LOCK_RELEASED = "RELEASED"
LOCK_ALREADY_RELEASED = "ALREADY_RELEASED"
LOCK_OWNER_MISMATCH = "OWNER_MISMATCH"
LOCK_TOKEN_MISMATCH = "TOKEN_MISMATCH"
LOCK_RENEWED = "RENEWED"
LOCK_EXPIRED = "EXPIRED"
LOCK_NOT_FOUND = "NOT_FOUND"
LOCK_RESULT_STATUSES = frozenset(
    {
        LOCK_ACQUIRED,
        LOCK_REPLACED_EXPIRED,
        LOCK_ALREADY_HELD,
        LOCK_CONFLICT,
        LOCK_RELEASED,
        LOCK_ALREADY_RELEASED,
        LOCK_OWNER_MISMATCH,
        LOCK_TOKEN_MISMATCH,
        LOCK_RENEWED,
        LOCK_EXPIRED,
        LOCK_NOT_FOUND,
    }
)


@dataclass(frozen=True)
class ScanWatermark:
    """Provider coverage boundary for point-in-time event scanning."""

    watermark_id: str
    scope: str
    source: str
    coverage_through: datetime
    retrieved_at: datetime
    parser_version: str
    coverage_status: str
    source_health: str
    evidence_refs: tuple[dict[str, Any], ...]
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "watermark_id",
            _required_text(self.watermark_id, "watermark_id"),
        )
        object.__setattr__(self, "scope", _required_text(self.scope, "scope"))
        object.__setattr__(self, "source", _required_text(self.source, "source"))
        object.__setattr__(
            self,
            "coverage_through",
            _required_datetime(self.coverage_through, "coverage_through"),
        )
        object.__setattr__(
            self,
            "retrieved_at",
            _required_datetime(self.retrieved_at, "retrieved_at"),
        )
        if self.coverage_through > self.retrieved_at:
            raise ValueError("Coverage boundary cannot be later than retrieval time")
        object.__setattr__(
            self,
            "parser_version",
            _required_text(self.parser_version, "parser_version"),
        )
        if self.coverage_status not in WATERMARK_COVERAGE_STATUSES:
            raise ValueError("Unknown watermark coverage status")
        if self.source_health not in SOURCE_HEALTH_STATUSES:
            raise ValueError("Unknown source health status")
        object.__setattr__(self, "evidence_refs", _required_refs(self.evidence_refs))
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Watermark must remain no_order")

    def covers(self, value: datetime) -> bool:
        return value <= self.coverage_through

    def as_policy(self) -> dict[str, Any]:
        return {
            "watermark_id": self.watermark_id,
            "scope": self.scope,
            "source": self.source,
            "coverage_through": self.coverage_through.isoformat(),
            "retrieved_at": self.retrieved_at.isoformat(),
            "parser_version": self.parser_version,
            "coverage_status": self.coverage_status,
            "source_health": self.source_health,
            "evidence_refs": [dict(item) for item in self.evidence_refs],
            "action": self.action,
        }


@dataclass(frozen=True)
class WatermarkResult:
    status: str
    watermark: ScanWatermark | None
    previous: ScanWatermark | None = None
    message: str = ""

    def __post_init__(self) -> None:
        if self.status not in WATERMARK_RESULT_STATUSES:
            raise ValueError("Unknown watermark result status")
        if self.watermark is not None and not isinstance(self.watermark, ScanWatermark):
            raise ValueError("watermark must be a ScanWatermark")
        if self.previous is not None and not isinstance(self.previous, ScanWatermark):
            raise ValueError("previous must be a ScanWatermark")
        object.__setattr__(self, "message", str(self.message or ""))

    def as_policy(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "watermark": self.watermark.as_policy() if self.watermark else None,
            "previous": self.previous.as_policy() if self.previous else None,
            "message": self.message,
        }


class WatermarkLedger:
    """Monotonic per-scope/per-source scan watermarks."""

    def __init__(self, *, schema_version: str = M5_EVENT_SCHEMA) -> None:
        self.schema_version = schema_version
        self._latest: dict[tuple[str, str], ScanWatermark] = {}

    def __len__(self) -> int:
        return len(self._latest)

    def watermarks(self) -> tuple[ScanWatermark, ...]:
        return tuple(
            sorted(
                self._latest.values(),
                key=lambda item: (item.scope, item.source, item.coverage_through),
            )
        )

    def current(self, *, scope: str, source: str | None = None) -> ScanWatermark | None:
        if source is not None:
            return self._latest.get((scope, source))
        matches = [item for key, item in self._latest.items() if key[0] == scope]
        return max(matches, key=lambda item: item.coverage_through) if matches else None

    def advance(self, watermark: ScanWatermark) -> WatermarkResult:
        key = (watermark.scope, watermark.source)
        existing = self._latest.get(key)
        if existing is not None:
            if watermark.coverage_through < existing.coverage_through:
                return WatermarkResult(
                    status=WATERMARK_REGRESSION_REJECTED,
                    watermark=None,
                    previous=existing,
                    message="Scan coverage cannot move backwards",
                )
            if (
                watermark.coverage_through == existing.coverage_through
                and watermark.watermark_id != existing.watermark_id
                and watermark.retrieved_at <= existing.retrieved_at
            ):
                return WatermarkResult(
                    status=WATERMARK_DUPLICATE,
                    watermark=existing,
                    previous=existing,
                    message="Equivalent coverage is already recorded",
                )
        self._latest[key] = watermark
        return WatermarkResult(
            status=WATERMARK_ACCEPTED,
            watermark=watermark,
            previous=existing,
            message="Scan watermark advanced",
        )

    def as_policy(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "watermarks": [item.as_policy() for item in self.watermarks()],
        }


def watermark_ledger_from_payload(payload: Mapping[str, Any]) -> WatermarkLedger:
    if not isinstance(payload, Mapping):
        raise ValueError("Watermark ledger must be an object")
    data = dict(payload)
    if data.get("schema_version") != M5_EVENT_SCHEMA:
        raise ValueError("Unknown watermark ledger schema")
    ledger = WatermarkLedger(schema_version=str(data["schema_version"]))
    for raw in data.get("watermarks") or ():
        item = dict(raw)
        watermark = ScanWatermark(
            watermark_id=_required_text(item["watermark_id"], "watermark_id"),
            scope=_required_text(item["scope"], "scope"),
            source=_required_text(item["source"], "source"),
            coverage_through=_required_datetime(
                datetime.fromisoformat(str(item["coverage_through"])),
                "coverage_through",
            ),
            retrieved_at=_required_datetime(
                datetime.fromisoformat(str(item["retrieved_at"])),
                "retrieved_at",
            ),
            parser_version=_required_text(item["parser_version"], "parser_version"),
            coverage_status=_required_text(item["coverage_status"], "coverage_status"),
            source_health=_required_text(item["source_health"], "source_health"),
            evidence_refs=_required_refs(item.get("evidence_refs")),
            action=str(item.get("action", ACTION_NO_ORDER)),
        )
        result = ledger.advance(watermark)
        if result.status == WATERMARK_REGRESSION_REJECTED:
            raise ValueError("Serialized watermarks contain a regression")
    return ledger


@dataclass(frozen=True)
class TaskLock:
    lock_id: str
    scope: str
    owner: str
    token: str
    acquired_at: datetime
    expires_at: datetime
    released_at: datetime | None = None
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        object.__setattr__(self, "lock_id", _required_text(self.lock_id, "lock_id"))
        object.__setattr__(self, "scope", _required_text(self.scope, "scope"))
        object.__setattr__(self, "owner", _required_text(self.owner, "owner"))
        object.__setattr__(self, "token", _required_text(self.token, "token"))
        object.__setattr__(
            self,
            "acquired_at",
            _required_datetime(self.acquired_at, "acquired_at"),
        )
        object.__setattr__(
            self,
            "expires_at",
            _required_datetime(self.expires_at, "expires_at"),
        )
        if self.expires_at <= self.acquired_at:
            raise ValueError("Lock expiry must be after acquisition")
        object.__setattr__(
            self,
            "released_at",
            None
            if self.released_at is None
            else _required_datetime(self.released_at, "released_at"),
        )
        if self.released_at is not None and self.released_at < self.acquired_at:
            raise ValueError("Lock release cannot precede acquisition")
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Task lock must remain no_order")

    def is_active(self, now: datetime) -> bool:
        now = _required_datetime(now, "now")
        return self.released_at is None and now < self.expires_at

    def as_policy(self) -> dict[str, Any]:
        return {
            "lock_id": self.lock_id,
            "scope": self.scope,
            "owner": self.owner,
            "token": self.token,
            "acquired_at": self.acquired_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "released_at": self.released_at.isoformat() if self.released_at else None,
            "action": self.action,
        }


@dataclass(frozen=True)
class TaskLockResult:
    status: str
    lock: TaskLock | None
    conflicting_lock: TaskLock | None = None
    message: str = ""

    def __post_init__(self) -> None:
        if self.status not in LOCK_RESULT_STATUSES:
            raise ValueError("Unknown task lock result status")
        if self.lock is not None and not isinstance(self.lock, TaskLock):
            raise ValueError("lock must be a TaskLock")
        if self.conflicting_lock is not None and not isinstance(
            self.conflicting_lock,
            TaskLock,
        ):
            raise ValueError("conflicting_lock must be a TaskLock")
        object.__setattr__(self, "message", str(self.message or ""))

    def as_policy(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "lock": self.lock.as_policy() if self.lock else None,
            "conflicting_lock": (
                self.conflicting_lock.as_policy() if self.conflicting_lock else None
            ),
            "message": self.message,
        }


class TaskLockStore:
    """Single-lock-per-scope coordination without filesystem side effects."""

    def __init__(self, *, schema_version: str = M5_EVENT_SCHEMA) -> None:
        self.schema_version = schema_version
        self._locks: dict[str, TaskLock] = {}

    def locks(self) -> tuple[TaskLock, ...]:
        return tuple(sorted(self._locks.values(), key=lambda item: item.scope))

    def acquire(
        self,
        *,
        scope: str,
        owner: str,
        token: str,
        now: datetime,
        lease_seconds: int,
    ) -> TaskLockResult:
        scope = _required_text(scope, "scope")
        owner = _required_text(owner, "owner")
        token = _required_text(token, "token")
        now = _required_datetime(now, "now")
        lease_seconds = _positive_int(lease_seconds, "lease_seconds")
        existing = self._locks.get(scope)
        if existing is not None and existing.is_active(now):
            if existing.owner == owner and existing.token == token:
                return TaskLockResult(
                    status=LOCK_ALREADY_HELD,
                    lock=existing,
                    message="This owner already holds the lock",
                )
            return TaskLockResult(
                status=LOCK_CONFLICT,
                lock=None,
                conflicting_lock=existing,
                message="Another owner holds an unexpired lock",
            )
        if existing is not None and now < existing.acquired_at:
            raise ValueError("Lock acquisition time cannot precede the prior lock")
        if (
            existing is not None
            and existing.released_at is not None
            and now < existing.released_at
        ):
            raise ValueError("Lock acquisition cannot precede the prior release")
        lock = TaskLock(
            lock_id="m5-lock-" + _digest(scope, owner, token, now.isoformat())[:32],
            scope=scope,
            owner=owner,
            token=token,
            acquired_at=now,
            expires_at=now + timedelta(seconds=lease_seconds),
        )
        self._locks[scope] = lock
        return TaskLockResult(
            status=LOCK_REPLACED_EXPIRED if existing is not None else LOCK_ACQUIRED,
            lock=lock,
            conflicting_lock=existing,
            message="Lock acquired after expiry" if existing else "Lock acquired",
        )

    def release(
        self,
        *,
        scope: str,
        owner: str,
        token: str,
        now: datetime,
    ) -> TaskLockResult:
        scope = _required_text(scope, "scope")
        owner = _required_text(owner, "owner")
        token = _required_text(token, "token")
        now = _required_datetime(now, "now")
        existing = self._locks.get(scope)
        if existing is None:
            return TaskLockResult(
                status=LOCK_NOT_FOUND,
                lock=None,
                message="No lock exists for this scope",
            )
        if existing.owner != owner:
            return TaskLockResult(
                status=LOCK_OWNER_MISMATCH,
                lock=None,
                conflicting_lock=existing,
                message="Release owner does not match the held lock",
            )
        if existing.token != token:
            return TaskLockResult(
                status=LOCK_TOKEN_MISMATCH,
                lock=None,
                conflicting_lock=existing,
                message="Release token does not match the held lock",
            )
        if now < existing.acquired_at:
            raise ValueError("Lock release time cannot precede acquisition")
        if existing.released_at is not None:
            return TaskLockResult(
                status=LOCK_ALREADY_RELEASED,
                lock=existing,
                message="Lock was already released",
            )
        released = TaskLock(
            lock_id=existing.lock_id,
            scope=existing.scope,
            owner=existing.owner,
            token=existing.token,
            acquired_at=existing.acquired_at,
            expires_at=existing.expires_at,
            released_at=now,
        )
        self._locks[scope] = released
        return TaskLockResult(
            status=LOCK_RELEASED,
            lock=released,
            message="Lock released",
        )

    def renew(
        self,
        *,
        scope: str,
        owner: str,
        token: str,
        now: datetime,
        lease_seconds: int,
    ) -> TaskLockResult:
        scope = _required_text(scope, "scope")
        owner = _required_text(owner, "owner")
        token = _required_text(token, "token")
        now = _required_datetime(now, "now")
        lease_seconds = _positive_int(lease_seconds, "lease_seconds")
        existing = self._locks.get(scope)
        if existing is None:
            return TaskLockResult(
                status=LOCK_NOT_FOUND,
                lock=None,
                message="No lock exists for this scope",
            )
        if existing.owner != owner:
            return TaskLockResult(
                status=LOCK_OWNER_MISMATCH,
                lock=None,
                conflicting_lock=existing,
                message="Renew owner does not match the held lock",
            )
        if existing.token != token:
            return TaskLockResult(
                status=LOCK_TOKEN_MISMATCH,
                lock=None,
                conflicting_lock=existing,
                message="Renew token does not match the held lock",
            )
        if existing.released_at is not None or now >= existing.expires_at:
            return TaskLockResult(
                status=LOCK_EXPIRED,
                lock=existing,
                message="Lock is released or expired",
            )
        if now < existing.acquired_at:
            raise ValueError("Lock renewal time cannot precede acquisition")
        renewed = TaskLock(
            lock_id=existing.lock_id,
            scope=existing.scope,
            owner=existing.owner,
            token=existing.token,
            acquired_at=existing.acquired_at,
            expires_at=now + timedelta(seconds=lease_seconds),
        )
        self._locks[scope] = renewed
        return TaskLockResult(
            status=LOCK_RENEWED,
            lock=renewed,
            message="Lock lease renewed",
        )

    def as_policy(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "locks": [item.as_policy() for item in self.locks()],
        }
