"""Crash-safe M5 run checkpoints for bounded event ingestion."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Sequence

from .investment_decision import ACTION_NO_ORDER
from .m5_event_core import (
    M5_EVENT_SCHEMA,
    _digest,
    _required_datetime,
    _required_int,
    _required_refs,
    _required_text,
)
from .m5_event_watermark import LOCK_CONFLICT, LOCK_NOT_FOUND


CHECKPOINT_RUNNING = "RUNNING"
CHECKPOINT_COMMITTED = "COMMITTED"
CHECKPOINT_FAILED = "FAILED"
CHECKPOINT_STATUSES = frozenset(
    {CHECKPOINT_RUNNING, CHECKPOINT_COMMITTED, CHECKPOINT_FAILED}
)


@dataclass(frozen=True)
class TaskCheckpoint:
    checkpoint_id: str
    run_id: str
    scope: str
    status: str
    started_at: datetime
    completed_at: datetime | None
    last_sequence: int
    watermark_ids: tuple[str, ...]
    ingested_event_ids: tuple[str, ...]
    error: str | None
    evidence_refs: tuple[dict[str, Any], ...]
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "checkpoint_id",
            _required_text(self.checkpoint_id, "checkpoint_id"),
        )
        object.__setattr__(self, "run_id", _required_text(self.run_id, "run_id"))
        object.__setattr__(self, "scope", _required_text(self.scope, "scope"))
        if self.status not in CHECKPOINT_STATUSES:
            raise ValueError("Unknown checkpoint status")
        object.__setattr__(
            self,
            "started_at",
            _required_datetime(self.started_at, "started_at"),
        )
        object.__setattr__(
            self,
            "completed_at",
            None
            if self.completed_at is None
            else _required_datetime(self.completed_at, "completed_at"),
        )
        if self.status == CHECKPOINT_RUNNING and self.completed_at is not None:
            raise ValueError("Running checkpoint cannot have completed_at")
        if self.status != CHECKPOINT_RUNNING and self.completed_at is None:
            raise ValueError("Terminal checkpoint requires completed_at")
        if self.completed_at is not None and self.completed_at < self.started_at:
            raise ValueError("Checkpoint completion cannot precede its start")
        object.__setattr__(
            self,
            "last_sequence",
            _required_int(self.last_sequence, "last_sequence"),
        )
        if self.last_sequence < 0:
            raise ValueError("last_sequence cannot be negative")
        watermark_ids = tuple(
            _required_text(item, "watermark_id") for item in self.watermark_ids
        )
        ingested_event_ids = tuple(
            _required_text(item, "ingested_event_id")
            for item in self.ingested_event_ids
        )
        if len(set(watermark_ids)) != len(watermark_ids):
            raise ValueError("Checkpoint watermark ids must be unique")
        if len(set(ingested_event_ids)) != len(ingested_event_ids):
            raise ValueError("Checkpoint ingested event ids must be unique")
        object.__setattr__(self, "watermark_ids", watermark_ids)
        object.__setattr__(self, "ingested_event_ids", ingested_event_ids)
        if self.status == CHECKPOINT_RUNNING and (
            self.last_sequence != 0 or watermark_ids or ingested_event_ids
        ):
            raise ValueError("Running checkpoint cannot claim committed progress")
        object.__setattr__(
            self,
            "error",
            None if self.error is None else _required_text(self.error, "error"),
        )
        if self.status == CHECKPOINT_FAILED and not self.error:
            raise ValueError("Failed checkpoint requires an error")
        if self.status != CHECKPOINT_FAILED and self.error:
            raise ValueError("Only failed checkpoints can carry an error")
        object.__setattr__(self, "evidence_refs", _required_refs(self.evidence_refs))
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Task checkpoint must remain no_order")

    def as_policy(self) -> dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "run_id": self.run_id,
            "scope": self.scope,
            "status": self.status,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "last_sequence": self.last_sequence,
            "watermark_ids": list(self.watermark_ids),
            "ingested_event_ids": list(self.ingested_event_ids),
            "error": self.error,
            "evidence_refs": [dict(item) for item in self.evidence_refs],
            "action": self.action,
        }


@dataclass(frozen=True)
class CheckpointResult:
    status: str
    checkpoint: TaskCheckpoint | None
    message: str = ""

    def __post_init__(self) -> None:
        if self.status not in {
            CHECKPOINT_RUNNING,
            CHECKPOINT_COMMITTED,
            CHECKPOINT_FAILED,
            LOCK_CONFLICT,
            LOCK_NOT_FOUND,
        }:
            raise ValueError("Unknown checkpoint result status")
        if self.checkpoint is not None and not isinstance(
            self.checkpoint,
            TaskCheckpoint,
        ):
            raise ValueError("checkpoint must be a TaskCheckpoint")
        object.__setattr__(self, "message", str(self.message or ""))

    def as_policy(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "checkpoint": self.checkpoint.as_policy() if self.checkpoint else None,
            "message": self.message,
        }


class CheckpointLedger:
    """Versioned run checkpoints for crash-safe, idempotent recovery."""

    def __init__(self, *, schema_version: str = M5_EVENT_SCHEMA) -> None:
        self.schema_version = schema_version
        self._checkpoints: list[TaskCheckpoint] = []

    def checkpoints(self) -> tuple[TaskCheckpoint, ...]:
        return tuple(self._checkpoints)

    def latest(self, run_id: str) -> TaskCheckpoint | None:
        matches = [item for item in self._checkpoints if item.run_id == run_id]
        return matches[-1] if matches else None

    def start(
        self,
        *,
        run_id: str,
        scope: str,
        started_at: datetime,
        evidence_refs: Sequence[Mapping[str, Any]] = (),
    ) -> CheckpointResult:
        run_id = _required_text(run_id, "run_id")
        scope = _required_text(scope, "scope")
        started_at = _required_datetime(started_at, "started_at")
        refs = _required_refs(evidence_refs)
        existing = self.latest(run_id)
        if existing is not None:
            if existing.status == CHECKPOINT_RUNNING:
                return CheckpointResult(
                    status=LOCK_CONFLICT,
                    checkpoint=None,
                    message="Run already has an open checkpoint",
                )
            if started_at < existing.completed_at:
                raise ValueError(
                    "Checkpoint start cannot precede the prior terminal checkpoint"
                )
        checkpoint_id = "m5-checkpoint-" + _digest(
            run_id,
            scope,
            started_at.isoformat(),
            len(self._checkpoints),
        )[:32]
        if any(item.checkpoint_id == checkpoint_id for item in self._checkpoints):
            return CheckpointResult(
                status=LOCK_CONFLICT,
                checkpoint=None,
                message="Checkpoint id already exists",
            )
        checkpoint = TaskCheckpoint(
            checkpoint_id=checkpoint_id,
            run_id=run_id,
            scope=scope,
            status=CHECKPOINT_RUNNING,
            started_at=started_at,
            completed_at=None,
            last_sequence=0,
            watermark_ids=(),
            ingested_event_ids=(),
            error=None,
            evidence_refs=refs,
        )
        self._checkpoints.append(checkpoint)
        return CheckpointResult(
            status=CHECKPOINT_RUNNING,
            checkpoint=checkpoint,
            message="Checkpoint started",
        )

    def commit(
        self,
        *,
        checkpoint_id: str,
        completed_at: datetime,
        last_sequence: int,
        watermark_ids: Sequence[str] = (),
        ingested_event_ids: Sequence[str] = (),
    ) -> CheckpointResult:
        checkpoint = self._require_open_checkpoint(checkpoint_id)
        prior = [
            item
            for item in self._checkpoints
            if item.run_id == checkpoint.run_id
            and item.status == CHECKPOINT_COMMITTED
        ]
        if prior and last_sequence < prior[-1].last_sequence:
            raise ValueError("Committed checkpoint sequence cannot regress")
        committed = TaskCheckpoint(
            checkpoint_id=checkpoint.checkpoint_id,
            run_id=checkpoint.run_id,
            scope=checkpoint.scope,
            status=CHECKPOINT_COMMITTED,
            started_at=checkpoint.started_at,
            completed_at=_required_datetime(completed_at, "completed_at"),
            last_sequence=_required_int(last_sequence, "last_sequence"),
            watermark_ids=tuple(str(item) for item in watermark_ids),
            ingested_event_ids=tuple(str(item) for item in ingested_event_ids),
            error=None,
            evidence_refs=checkpoint.evidence_refs,
        )
        self._replace(checkpoint, committed)
        return CheckpointResult(
            status=CHECKPOINT_COMMITTED,
            checkpoint=committed,
            message="Checkpoint committed",
        )

    def fail(
        self,
        *,
        checkpoint_id: str,
        completed_at: datetime,
        error: str,
    ) -> CheckpointResult:
        checkpoint = self._require_open_checkpoint(checkpoint_id)
        failed = TaskCheckpoint(
            checkpoint_id=checkpoint.checkpoint_id,
            run_id=checkpoint.run_id,
            scope=checkpoint.scope,
            status=CHECKPOINT_FAILED,
            started_at=checkpoint.started_at,
            completed_at=_required_datetime(completed_at, "completed_at"),
            last_sequence=checkpoint.last_sequence,
            watermark_ids=checkpoint.watermark_ids,
            ingested_event_ids=checkpoint.ingested_event_ids,
            error=_required_text(error, "error"),
            evidence_refs=checkpoint.evidence_refs,
        )
        self._replace(checkpoint, failed)
        return CheckpointResult(
            status=CHECKPOINT_FAILED,
            checkpoint=failed,
            message="Checkpoint failed",
        )

    def _require_open_checkpoint(self, checkpoint_id: str) -> TaskCheckpoint:
        checkpoint_id = _required_text(checkpoint_id, "checkpoint_id")
        for item in reversed(self._checkpoints):
            if item.checkpoint_id == checkpoint_id:
                if item.status != CHECKPOINT_RUNNING:
                    raise ValueError("Checkpoint is already terminal")
                return item
        raise ValueError("Checkpoint does not exist")

    def _replace(self, old: TaskCheckpoint, new: TaskCheckpoint) -> None:
        for index, item in enumerate(self._checkpoints):
            if item.checkpoint_id == old.checkpoint_id:
                self._checkpoints[index] = new
                return
        raise ValueError("Checkpoint does not exist")

    def as_policy(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "checkpoints": [item.as_policy() for item in self._checkpoints],
        }


def checkpoint_ledger_from_payload(payload: Mapping[str, Any]) -> CheckpointLedger:
    if not isinstance(payload, Mapping):
        raise ValueError("Checkpoint ledger must be an object")
    data = dict(payload)
    if data.get("schema_version") != M5_EVENT_SCHEMA:
        raise ValueError("Unknown checkpoint ledger schema")
    ledger = CheckpointLedger(schema_version=str(data["schema_version"]))
    seen_ids: set[str] = set()
    prior_by_run: dict[str, TaskCheckpoint] = {}
    for raw in data.get("checkpoints") or ():
        item = dict(raw)
        checkpoint = TaskCheckpoint(
            checkpoint_id=_required_text(item["checkpoint_id"], "checkpoint_id"),
            run_id=_required_text(item["run_id"], "run_id"),
            scope=_required_text(item["scope"], "scope"),
            status=_required_text(item["status"], "status"),
            started_at=_required_datetime(
                datetime.fromisoformat(str(item["started_at"])),
                "started_at",
            ),
            completed_at=(
                _required_datetime(
                    datetime.fromisoformat(str(item["completed_at"])),
                    "completed_at",
                )
                if item.get("completed_at")
                else None
            ),
            last_sequence=_required_int(item["last_sequence"], "last_sequence"),
            watermark_ids=tuple(str(value) for value in item.get("watermark_ids") or ()),
            ingested_event_ids=tuple(
                str(value) for value in item.get("ingested_event_ids") or ()
            ),
            error=None if item.get("error") is None else str(item["error"]),
            evidence_refs=_required_refs(item.get("evidence_refs")),
            action=str(item.get("action", ACTION_NO_ORDER)),
        )
        expected_id = "m5-checkpoint-" + _digest(
            checkpoint.run_id,
            checkpoint.scope,
            checkpoint.started_at.isoformat(),
            len(ledger._checkpoints),
        )[:32]
        legacy_id = "m5-checkpoint-" + _digest(
            checkpoint.run_id,
            checkpoint.scope,
            checkpoint.started_at.isoformat(),
        )[:32]
        if checkpoint.checkpoint_id not in {expected_id, legacy_id}:
            raise ValueError("Checkpoint id does not match its immutable payload")
        if checkpoint.checkpoint_id in seen_ids:
            raise ValueError("Checkpoint ledger contains a duplicate checkpoint id")
        prior = prior_by_run.get(checkpoint.run_id)
        if prior is not None:
            if prior.status == CHECKPOINT_RUNNING:
                raise ValueError("Checkpoint ledger contains an open prior attempt")
            if checkpoint.started_at < prior.completed_at:
                raise ValueError("Checkpoint attempts overlap in time")
            if (
                checkpoint.status == CHECKPOINT_COMMITTED
                and prior.status == CHECKPOINT_COMMITTED
                and checkpoint.last_sequence < prior.last_sequence
            ):
                raise ValueError("Checkpoint sequence cannot regress")
        seen_ids.add(checkpoint.checkpoint_id)
        prior_by_run[checkpoint.run_id] = checkpoint
        ledger._checkpoints.append(checkpoint)
    return ledger
