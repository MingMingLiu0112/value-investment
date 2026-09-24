"""Read-only M6 aggregate of historical rejected ingest verdicts.

An M5 run receipt records the verdicts for one immutable batch. A later
``HEALTHY`` run must not make an earlier ``FUTURE_REJECTED``,
``CONFLICT_REJECTED`` or ``OBSERVED_TIME_REGRESSION_REJECTED`` verdict
disappear from operational review.

This module deliberately operates on durable offline artifacts only. It
re-reads every receipt from disk, verifies its immutable hashes and binds the
receipt batch/checkpoint prefix to the current run state. Missing, extra,
duplicate or tampered receipts fail closed. It does not connect to
PostgreSQL, schedule work, send a notification or create an order.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Any, Mapping

from .investment_decision import ACTION_NO_ORDER
from .m5_event_core import (
    INGEST_CONFLICT_REJECTED,
    INGEST_FUTURE_REJECTED,
    INGEST_OBSERVED_TIME_REGRESSION_REJECTED,
    NAMESPACE_SIMULATED,
)
from .m5_event_run import M5EventRunReceipt
from .m5_event_run_state import (
    M5EventRunState,
    m5_event_run_state_from_payload,
)
from .m5_event_state_store import M5EventRunStateStore


M6_HISTORICAL_INGEST_REJECTION_SCHEMA = "m6-historical-ingest-rejections-v1"
M6_HISTORICAL_INGEST_REJECTION_STATUSES = frozenset(
    {
        INGEST_FUTURE_REJECTED,
        INGEST_CONFLICT_REJECTED,
        INGEST_OBSERVED_TIME_REGRESSION_REJECTED,
    }
)

HISTORICAL_REJECTIONS_PRESENT = "ATTENTION"
HISTORICAL_REJECTIONS_CLEAR = "CLEAR"
INTEGRITY_VERIFIED = "VERIFIED"

_RECEIPT_PREFIX = "m5-receipt-"
_RECEIPT_SUFFIX = ".json"
_RECEIPT_STORE_LOCK = ".m5-event-receipt-store.lock"
_MAX_RECEIPT_BYTES = 16 * 1024 * 1024


class M6HistoricalIngestRejectionError(ValueError):
    """Base error for an invalid historical ingest aggregate."""


class M6HistoricalIngestIntegrityError(M6HistoricalIngestRejectionError):
    """Raised when durable receipt evidence fails closed integrity checks."""


@dataclass(frozen=True)
class _ReceiptArtifact:
    path: Path
    receipt: M5EventRunReceipt
    file_sha256: str
    receipt_sha256: str
    audit_fingerprint: str


def _fail(message: str) -> None:
    raise M6HistoricalIngestIntegrityError(message)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_digest(value: object) -> str:
    rendered = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return _sha256_bytes(rendered.encode("utf-8"))


def _json_constant(value: str) -> None:
    raise ValueError(f"Invalid JSON constant: {value}")


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json_bytes(raw: bytes, *, path: Path) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8")
        payload = json.loads(
            text,
            object_pairs_hook=_object_without_duplicate_keys,
            parse_constant=_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise M6HistoricalIngestIntegrityError(
            f"Receipt artifact is not valid strict JSON: {path.name}"
        ) from error
    if not isinstance(payload, dict):
        _fail(f"Receipt artifact must be a JSON object: {path.name}")
    return payload


def _is_link_or_reparse_point(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        metadata = os.stat(path, follow_symlinks=False)
    except OSError:
        return True
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(getattr(metadata, "st_file_attributes", 0) & reparse_flag)


def _require_plain_directory(path: Path) -> None:
    if not path.exists() or not path.is_dir():
        _fail(f"Receipt root is not a directory: {path}")
    if _is_link_or_reparse_point(path):
        _fail(f"Receipt root cannot be a symlink or reparse point: {path}")


def _require_plain_file(path: Path) -> None:
    if not path.is_file() or _is_link_or_reparse_point(path):
        _fail(f"Receipt artifact must be a plain file: {path.name}")


def _expected_receipt_filename(receipt_id: str) -> str:
    digest = hashlib.sha256(receipt_id.encode("utf-8")).hexdigest()
    return f"{_RECEIPT_PREFIX}{digest}{_RECEIPT_SUFFIX}"


def _read_receipt_artifact(path: Path) -> _ReceiptArtifact:
    _require_plain_file(path)
    try:
        if path.stat().st_size > _MAX_RECEIPT_BYTES:
            _fail(f"Receipt artifact exceeds the size limit: {path.name}")
    except OSError as error:
        raise M6HistoricalIngestIntegrityError(
            f"Could not stat receipt artifact: {path.name}"
        ) from error
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise M6HistoricalIngestIntegrityError(
            f"Could not read receipt artifact: {path.name}"
        ) from error
    if len(raw) > _MAX_RECEIPT_BYTES:
        _fail(f"Receipt artifact exceeds the size limit: {path.name}")
    payload = _load_json_bytes(raw, path=path)
    try:
        receipt = M5EventRunReceipt.from_payload(payload)
    except (KeyError, TypeError, ValueError) as error:
        raise M6HistoricalIngestIntegrityError(
            f"Receipt artifact failed immutable verification: {path.name}"
        ) from error
    expected_name = _expected_receipt_filename(receipt.receipt_id)
    if path.name != expected_name:
        _fail(f"Receipt filename does not match its receipt id: {path.name}")
    return _ReceiptArtifact(
        path=path,
        receipt=receipt,
        file_sha256=_sha256_bytes(raw),
        receipt_sha256=str(payload["receipt_sha256"]),
        audit_fingerprint=str(payload["audit_fingerprint"]),
    )


def _read_all_receipt_artifacts(receipt_root: Path) -> tuple[_ReceiptArtifact, ...]:
    if not receipt_root.exists():
        return ()
    _require_plain_directory(receipt_root)
    entries = sorted(receipt_root.iterdir(), key=lambda item: item.name)
    artifacts: list[_ReceiptArtifact] = []
    for entry in entries:
        if entry.name == _RECEIPT_STORE_LOCK:
            _require_plain_file(entry)
            continue
        if not (
            entry.name.startswith(_RECEIPT_PREFIX)
            and entry.name.endswith(_RECEIPT_SUFFIX)
        ):
            _fail(f"Unexpected entry in durable receipt store: {entry.name}")
        artifacts.append(_read_receipt_artifact(entry))
    return tuple(artifacts)


def _state_file_path(state_root: Path, state_key: str) -> Path:
    digest = hashlib.sha256(state_key.encode("utf-8")).hexdigest()
    return state_root / f"m5-state-{digest}.json"


def _read_state_artifact(
    *,
    state_root: Path,
    state_key: str,
) -> tuple[M5EventRunState, str]:
    if not state_root.exists():
        _fail(f"State root does not exist: {state_root}")
    _require_plain_directory(state_root)
    path = _state_file_path(state_root, state_key)
    _require_plain_file(path)
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise M6HistoricalIngestIntegrityError(
            f"Could not read current M5 state: {path.name}"
        ) from error
    payload = _load_json_bytes(raw, path=path)
    try:
        state = m5_event_run_state_from_payload(payload)
    except (KeyError, TypeError, ValueError) as error:
        raise M6HistoricalIngestIntegrityError(
            f"Current M5 state failed immutable verification: {path.name}"
        ) from error
    if state.state_key != state_key:
        _fail("Current M5 state does not match the requested state_key")
    return state, _sha256_bytes(raw)


def _checkpoint_policies(checkpoints: Any) -> tuple[Mapping[str, Any], ...]:
    return tuple(item.as_policy() for item in checkpoints)


def _bind_receipt_chain(
    *,
    state: M5EventRunState,
    artifacts: tuple[_ReceiptArtifact, ...],
) -> tuple[_ReceiptArtifact, ...]:
    if len(state.batch_records) != state.revision:
        _fail("Current state revision does not match its batch records")
    checkpoints = state.checkpoints.checkpoints()
    if len(checkpoints) != state.revision:
        _fail("Current state checkpoints do not match its batch records")

    by_revision: dict[int, _ReceiptArtifact] = {}
    seen_receipt_ids: set[str] = set()
    seen_batch_ids: set[str] = set()
    for artifact in artifacts:
        receipt = artifact.receipt
        if receipt.stream_id != state.state_key:
            _fail(
                "Receipt stream does not match the requested current state: "
                f"{receipt.receipt_id}"
            )
        matching_records = tuple(
            record
            for record in state.batch_records
            if record.receipt_id == receipt.receipt_id
        )
        if len(matching_records) != 1:
            _fail(
                "Receipt is missing its unique current-state batch record: "
                f"{receipt.receipt_id}"
            )
        record = matching_records[0]
        revision = record.state_revision
        if revision in by_revision:
            _fail(f"Duplicate receipt revision in current state: {revision}")
        if receipt.receipt_id in seen_receipt_ids:
            _fail(f"Duplicate receipt id: {receipt.receipt_id}")
        if receipt.batch_id in seen_batch_ids:
            _fail(f"Duplicate batch id: {receipt.batch_id}")

        if (
            receipt.run_id != record.run_id
            or receipt.batch_id != record.batch_id
            or receipt.namespace != record.namespace
            or receipt.generated_at != record.generated_at
            or receipt.receipt_id != record.receipt_id
            or receipt.checkpoint.checkpoint_id != record.checkpoint_id
            or record.receipt_audit_fingerprint is None
            or receipt.audit_fingerprint()
            != record.receipt_audit_fingerprint
            or receipt.state.state_key != state.state_key
            or receipt.state.namespace != state.namespace
            or receipt.state.action != state.action
        ):
            _fail(
                "Receipt batch identity does not match the current state: "
                f"{receipt.receipt_id}"
            )
        receipt_records = receipt.state.batch_records
        if (
            len(receipt_records) > len(state.batch_records)
            or state.batch_records[: len(receipt_records)] != receipt_records
        ):
            _fail(
                "Receipt batch history is not a current-state prefix: "
                f"{receipt.receipt_id}"
            )
        receipt_checkpoints = _checkpoint_policies(
            receipt.state.checkpoints.checkpoints()
        )
        current_checkpoints = _checkpoint_policies(
            checkpoints[: len(receipt_checkpoints)]
        )
        if receipt_checkpoints != current_checkpoints:
            _fail(
                "Receipt checkpoint history is not a current-state prefix: "
                f"{receipt.receipt_id}"
            )
        if receipt.checkpoint != checkpoints[revision - 1]:
            _fail(
                "Receipt checkpoint does not match the current state: "
                f"{receipt.receipt_id}"
            )
        by_revision[revision] = artifact
        seen_receipt_ids.add(receipt.receipt_id)
        seen_batch_ids.add(receipt.batch_id)

    missing = [
        revision
        for revision in range(1, state.revision + 1)
        if revision not in by_revision
    ]
    if missing:
        _fail(
            "Durable receipt store is missing current-state revisions: "
            + ", ".join(str(item) for item in missing)
        )
    if len(by_revision) != state.revision:
        _fail("Receipt count does not match the current state revision")
    return tuple(by_revision[revision] for revision in range(1, state.revision + 1))


def _rejection_payload(
    *,
    artifact: _ReceiptArtifact,
    result: Any,
    result_index: int,
) -> dict[str, Any]:
    receipt = artifact.receipt
    record = receipt.state.batch_records[receipt.state.revision - 1]
    if result.event is not None:
        _fail(
            "Rejected ingest verdict unexpectedly contains an accepted event: "
            f"{receipt.receipt_id}:{result_index}"
        )
    base = {
        "receipt_id": receipt.receipt_id,
        "receipt_file": artifact.path.name,
        "receipt_file_sha256": artifact.file_sha256,
        "receipt_artifact_sha256": artifact.receipt_sha256,
        "audit_fingerprint": artifact.audit_fingerprint,
        "state_revision": receipt.state.revision,
        "state_sha256": receipt.state_sha256,
        "run_id": receipt.run_id,
        "batch_id": receipt.batch_id,
        "stream_id": receipt.stream_id,
        "namespace": receipt.namespace,
        "generated_at": receipt.generated_at.isoformat(),
        "health_status": receipt.health_status,
        "silent_ok": receipt.silent_ok,
        "result_index": result_index,
        "status": result.status,
        "observed_at": result.observed_at.isoformat(),
        "is_late": result.is_late,
        "message": result.message,
        "superseded_event_ids": list(result.superseded_event_ids),
        "duplicate_event_id": result.duplicate_event_id,
        "checkpoint_id": record.checkpoint_id,
        "request_fingerprint": record.request_fingerprint,
        "receipt_audit_fingerprint": record.receipt_audit_fingerprint,
        "action": ACTION_NO_ORDER,
    }
    return {**base, "rejection_sha256": _canonical_digest(base)}


def _build_historical_ingest_rejection_view(
    *,
    state: M5EventRunState,
    receipt_root: Path,
    generated_at: datetime,
    state_file_sha256: str | None,
) -> dict[str, Any]:
    receipt_root = Path(receipt_root)
    if state.revision == 0 and not receipt_root.exists():
        artifacts: tuple[_ReceiptArtifact, ...] = ()
    else:
        artifacts = _read_all_receipt_artifacts(receipt_root)
    ordered = _bind_receipt_chain(state=state, artifacts=artifacts)

    rejections: list[dict[str, Any]] = []
    for artifact in ordered:
        for result_index, result in enumerate(artifact.receipt.ingest_results):
            if result.status not in M6_HISTORICAL_INGEST_REJECTION_STATUSES:
                continue
            rejections.append(
                _rejection_payload(
                    artifact=artifact,
                    result=result,
                    result_index=result_index,
                )
            )

    by_status = {
        status: sum(item["status"] == status for item in rejections)
        for status in sorted(M6_HISTORICAL_INGEST_REJECTION_STATUSES)
    }
    latest = ordered[-1].receipt if ordered else None
    namespaces = {artifact.receipt.namespace for artifact in ordered}
    evidence_class = (
        "SIMULATED_OFFLINE_ONLY"
        if not namespaces or namespaces <= {NAMESPACE_SIMULATED}
        else "MIXED_OR_UNEXPECTED_NAMESPACE"
    )
    status = (
        HISTORICAL_REJECTIONS_PRESENT
        if rejections
        else HISTORICAL_REJECTIONS_CLEAR
    )
    return {
        "schema_version": M6_HISTORICAL_INGEST_REJECTION_SCHEMA,
        "generated_at": generated_at.isoformat(),
        "action": ACTION_NO_ORDER,
        "status": status,
        "state_key": state.state_key,
        "historical_rejection_count": len(rejections),
        "historical_rejections_by_status": by_status,
        "historical_rejections": rejections,
        "current_state": {
            "revision": state.revision,
            "sha256": state.state_sha256(),
            "file_sha256": state_file_sha256,
            "latest_receipt_id": latest.receipt_id if latest else None,
            "latest_receipt_health_status": (
                latest.health_status if latest else None
            ),
            "latest_receipt_silent_ok": latest.silent_ok if latest else None,
        },
        "integrity": {
            "status": INTEGRITY_VERIFIED,
            "authenticity_status": "LOCAL_CONSISTENCY_ONLY",
            "receipt_chain_verified": True,
            "state_binding_verified": True,
            "receipt_count": len(ordered),
            "expected_receipt_count": state.revision,
            "raw_receipt_hashes_recomputed": True,
            "raw_receipt_bytes_external_anchor_status": "NOT_AVAILABLE_OFFLINE",
        },
        "boundary": {
            "read_only": True,
            "evidence_class": evidence_class,
            "counts_toward_real_operational_sessions": False,
            "counts_toward_real_operational_events": False,
            "production_database_connected": False,
            "scheduler_created": False,
            "notification_sent": False,
            "production_action_performed": False,
            "operational_acceptance_status": "NOT_STARTED",
            "action": ACTION_NO_ORDER,
        },
    }


def build_historical_ingest_rejection_view(
    *,
    state_key: str,
    state_store: M5EventRunStateStore,
    receipt_root: Path,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Build a fail-closed view using a caller-supplied state-store contract.

    The current state is authoritative for the batch/checkpoint chain. Every
    revision in that chain must have one durable receipt and no receipt may be
    missing, duplicated or unbound. Rejected verdicts are then aggregated from
    the immutable receipt payloads, not from the current mutable run health.
    """

    if not isinstance(state_key, str) or not state_key.strip():
        raise M6HistoricalIngestRejectionError("state_key is required")
    if generated_at is None:
        generated_at = datetime.now(timezone.utc)
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise M6HistoricalIngestRejectionError("generated_at must be timezone-aware")
    state = state_store.load(state_key=state_key)
    if state is None:
        _fail(f"Current M5 state does not exist: {state_key}")
    if not isinstance(state, M5EventRunState):
        _fail("State store returned an invalid M5 run state")
    if state.state_key != state_key:
        _fail("State store returned a different state_key")
    return _build_historical_ingest_rejection_view(
        state=state,
        receipt_root=Path(receipt_root),
        generated_at=generated_at,
        state_file_sha256=None,
    )


def build_historical_ingest_rejection_view_from_paths(
    *,
    state_key: str,
    state_root: Path,
    receipt_root: Path,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Build the aggregate without instantiating a writable JSON store."""

    if not isinstance(state_key, str) or not state_key.strip():
        raise M6HistoricalIngestRejectionError("state_key is required")
    if generated_at is None:
        generated_at = datetime.now(timezone.utc)
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise M6HistoricalIngestRejectionError("generated_at must be timezone-aware")
    state, state_file_sha256 = _read_state_artifact(
        state_root=Path(state_root),
        state_key=state_key,
    )
    return _build_historical_ingest_rejection_view(
        state=state,
        receipt_root=Path(receipt_root),
        generated_at=generated_at,
        state_file_sha256=state_file_sha256,
    )


__all__ = [
    "HISTORICAL_REJECTIONS_CLEAR",
    "HISTORICAL_REJECTIONS_PRESENT",
    "INTEGRITY_VERIFIED",
    "M6_HISTORICAL_INGEST_REJECTION_SCHEMA",
    "M6_HISTORICAL_INGEST_REJECTION_STATUSES",
    "M6HistoricalIngestIntegrityError",
    "M6HistoricalIngestRejectionError",
    "build_historical_ingest_rejection_view",
    "build_historical_ingest_rejection_view_from_paths",
]
