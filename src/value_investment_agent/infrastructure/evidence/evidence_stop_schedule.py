"""Filesystem adapters for verified, one-time Evidence Stop reopen requests."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from ...domain.research.research_run_contract import canonical_contract_payload
from ...domain.research.evidence_stop import (
    ResearchScheduleRequest,
    evaluate_research_schedule,
    evidence_stops_from_payload,
)


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_OFFICIAL_SOURCE_KINDS = {"official_issuer_filing", "official_exchange_filing"}


def verified_official_package_source_ids(
    root: Path,
    sources: Sequence[Mapping[str, Any]],
    requested_ids: Sequence[str],
    *,
    symbol: str,
) -> frozenset[str]:
    """Return requested IDs whose unique official source bytes match SHA-256."""

    project_root = root.resolve()
    requested = set(requested_ids)
    candidates: dict[str, list[Mapping[str, Any]]] = {}
    for source in sources:
        if isinstance(source, Mapping) and source.get("id") in requested:
            candidates.setdefault(str(source["id"]), []).append(source)

    verified: set[str] = set()
    for evidence_id, matches in candidates.items():
        if len(matches) != 1:
            continue
        source = matches[0]
        location = source.get("location")
        expected = source.get("sha256")
        if (
            source.get("kind") not in _OFFICIAL_SOURCE_KINDS
            or not isinstance(location, str)
            or not isinstance(expected, str)
            or not _SHA256.fullmatch(expected.lower())
        ):
            continue
        identity = source.get("issuer_identity")
        if (
            not isinstance(identity, Mapping)
            or identity.get("security_code") != symbol
        ):
            continue
        path = Path(location)
        if not path.is_absolute():
            path = project_root / path
        try:
            path = path.resolve()
            if not path.is_relative_to(project_root) or not path.is_file():
                continue
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            continue
        if actual == expected.lower():
            verified.add(evidence_id)
    return frozenset(verified)


def claim_research_schedule_once(
    *,
    root: Path,
    request: ResearchScheduleRequest,
    decision: Mapping[str, Any],
    ledger_sha256: str,
    request_sha256: str | None,
) -> dict[str, Any]:
    """Atomically persist stop reopens; normal research does not consume a stop."""

    if decision.get("allowed") and decision.get("status") == "ALLOW_NORMAL_RESEARCH":
        return {
            "created": True,
            "consumed": False,
            "status": "NORMAL_RESEARCH_NOT_CONSUMED",
            "schedule_id": None,
            "receipt_path": None,
        }
    if not decision.get("allowed") or not decision.get("new_evidence_ids"):
        raise ValueError("only an admitted request with new evidence can be consumed")
    schedule_identity = {
        "symbol": request.symbol,
        "scope_key": list(request.key),
        "new_evidence_ids": sorted(decision["new_evidence_ids"]),
    }
    schedule_id = hashlib.sha256(
        canonical_contract_payload(schedule_identity).encode("utf-8")
    ).hexdigest()
    project_root = root.resolve()
    receipt_path = (
        project_root
        / "runtime"
        / "research-evidence-stop-consumptions"
        / f"{schedule_id}.json"
    )
    runtime_dir = project_root / "runtime"
    receipt_dir = receipt_path.parent
    for directory in (runtime_dir, receipt_dir):
        if directory.is_symlink():
            raise ValueError("Evidence Stop receipts cannot use symlink directories")
        if directory.exists() and not directory.is_dir():
            raise ValueError("Evidence Stop receipt path must be a directory")
        directory.mkdir(exist_ok=True)
        if not directory.resolve().is_relative_to(project_root):
            raise ValueError("Evidence Stop receipt path must remain under the project root")
    payload = {
        "schema_version": "research-evidence-stop-consumption-v1",
        "schedule_id": schedule_id,
        "symbol": request.symbol,
        "scope_key": schedule_identity["scope_key"],
        "new_evidence_ids": schedule_identity["new_evidence_ids"],
        "ledger_sha256": ledger_sha256,
        "request_sha256": request_sha256,
        "admitted_at": datetime.now(timezone.utc).isoformat(),
        "status": "ADMITTED_ONCE",
        "action": "no_order",
    }
    encoded = (
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    ).encode("utf-8")
    try:
        descriptor = os.open(
            receipt_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError:
        return {
            "created": False,
            "schedule_id": schedule_id,
            "receipt_path": str(receipt_path),
        }
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    return {
        "created": True,
        "schedule_id": schedule_id,
        "receipt_path": str(receipt_path),
        "receipt_sha256": hashlib.sha256(encoded).hexdigest(),
    }


def recover_admitted_schedule(
    *,
    root: Path,
    request: ResearchScheduleRequest,
    evidence_sources: Sequence[Mapping[str, Any]],
    ledger_sha256: str,
    request_sha256: str | None,
    interrupted_run_id: str,
) -> dict[str, Any]:
    """Record one explicit recovery for an already admitted, interrupted schedule.

    This validates the original admission and its current official evidence again,
    but deliberately does not execute or retry the research work.
    """

    project_root = root.resolve()
    if not isinstance(interrupted_run_id, str) or not interrupted_run_id.strip():
        raise ValueError("interrupted_run_id is required for explicit recovery")
    expected_ledger_hash = _validated_sha256(ledger_sha256, "ledger_sha256")
    expected_request_hash = (
        None if request_sha256 is None
        else _validated_sha256(request_sha256, "request_sha256")
    )
    ledger_path = project_root / "config" / "research-evidence-stop-ledger-v1.json"
    _require_project_file(project_root, ledger_path, "evidence-stop ledger")
    ledger_bytes = ledger_path.read_bytes()
    if hashlib.sha256(ledger_bytes).hexdigest() != expected_ledger_hash:
        raise ValueError("Evidence Stop ledger hash no longer matches the admission")
    try:
        ledger_payload = json.loads(ledger_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Evidence Stop ledger is not valid UTF-8 JSON") from error
    if not isinstance(ledger_payload, Mapping):
        raise ValueError("Evidence Stop ledger must be an object")
    stops = evidence_stops_from_payload(ledger_payload)
    verified_ids = verified_official_package_source_ids(
        project_root,
        evidence_sources,
        request.new_evidence_ids,
        symbol=request.symbol,
    )
    decision = evaluate_research_schedule(
        symbol=request.symbol,
        stops=stops,
        request=request,
        verified_evidence_ids=verified_ids,
    )
    if not decision.get("allowed") or decision.get("status") != "REOPENED_WITH_NEW_EVIDENCE":
        raise ValueError(
            "admitted schedule no longer passes issuer, hash and reopen validation"
        )

    schedule_identity = {
        "symbol": request.symbol,
        "scope_key": list(request.key),
        "new_evidence_ids": sorted(decision["new_evidence_ids"]),
    }
    schedule_id = hashlib.sha256(
        canonical_contract_payload(schedule_identity).encode("utf-8")
    ).hexdigest()
    consumption_path = (
        project_root
        / "runtime"
        / "research-evidence-stop-consumptions"
        / f"{schedule_id}.json"
    )
    _require_project_file(project_root, consumption_path, "admission receipt")
    admission_bytes = consumption_path.read_bytes()
    try:
        admission = json.loads(admission_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("admission receipt is not valid UTF-8 JSON") from error
    expected_evidence_ids = schedule_identity["new_evidence_ids"]
    if not isinstance(admission, Mapping) or any((
        admission.get("schema_version") != "research-evidence-stop-consumption-v1",
        admission.get("schedule_id") != schedule_id,
        admission.get("symbol") != request.symbol,
        admission.get("scope_key") != schedule_identity["scope_key"],
        admission.get("new_evidence_ids") != expected_evidence_ids,
        admission.get("ledger_sha256") != expected_ledger_hash,
        admission.get("request_sha256") != expected_request_hash,
        admission.get("status") != "ADMITTED_ONCE",
        admission.get("action") != "no_order",
    )):
        raise ValueError("admission receipt does not match the requested recovery")
    admitted_at = admission.get("admitted_at")
    if not isinstance(admitted_at, str):
        raise ValueError("admission receipt is missing its admission timestamp")
    try:
        admitted_timestamp = datetime.fromisoformat(admitted_at)
    except ValueError as error:
        raise ValueError("admission receipt timestamp is invalid") from error
    if admitted_timestamp.tzinfo is None:
        raise ValueError("admission receipt timestamp must include a timezone")

    admission_receipt_sha256 = hashlib.sha256(admission_bytes).hexdigest()
    recovery_dir = _ensure_runtime_subdirectory(
        project_root, "research-evidence-stop-recoveries"
    )
    recovery_path = recovery_dir / f"{schedule_id}.json"
    recovery_payload = {
        "schema_version": "research-evidence-stop-recovery-v1",
        "schedule_id": schedule_id,
        "symbol": request.symbol,
        "scope_key": schedule_identity["scope_key"],
        "new_evidence_ids": expected_evidence_ids,
        "ledger_sha256": expected_ledger_hash,
        "request_sha256": expected_request_hash,
        "admission_receipt_sha256": admission_receipt_sha256,
        "interrupted_run_id": interrupted_run_id.strip(),
        "recovered_at": datetime.now(timezone.utc).isoformat(),
        "status": "RECOVERY_RECORDED_AWAITING_EXPLICIT_RESUME",
        "automatic_retry": False,
        "resume_performed": False,
        "action": "no_order",
    }
    encoded = (
        json.dumps(recovery_payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    ).encode("utf-8")
    if recovery_path.is_symlink():
        raise ValueError("recovery receipt cannot be a symlink")
    try:
        descriptor = os.open(
            recovery_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError:
        if recovery_path.is_symlink():
            raise ValueError("recovery receipt cannot be a symlink")
        existing_bytes = recovery_path.read_bytes()
        try:
            existing = json.loads(existing_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("existing recovery receipt is invalid; manual review required") from error
        if (
            not isinstance(existing, Mapping)
            or any(existing.get(key) != recovery_payload[key] for key in (
                "schema_version", "schedule_id", "symbol", "scope_key",
                "new_evidence_ids", "ledger_sha256", "request_sha256",
                "admission_receipt_sha256", "interrupted_run_id",
                "status", "automatic_retry", "resume_performed", "action",
            ))
        ):
            raise ValueError("existing recovery receipt conflicts; manual review required")
        return {
            "created": False,
            "status": "RECOVERY_ALREADY_RECORDED",
            "automatic_retry": False,
            "resume_performed": False,
            "schedule_id": schedule_id,
            "receipt_path": str(recovery_path),
        }
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    return {
        "created": True,
        "status": recovery_payload["status"],
        "automatic_retry": False,
        "resume_performed": False,
        "schedule_id": schedule_id,
        "receipt_path": str(recovery_path),
        "receipt_sha256": hashlib.sha256(encoded).hexdigest(),
    }


def _validated_sha256(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value.lower()):
        raise ValueError(f"{field_name} must be a SHA-256 hex digest")
    return value.lower()


def _require_project_file(project_root: Path, path: Path, label: str) -> None:
    try:
        relative = path.relative_to(project_root)
    except ValueError as error:
        raise ValueError(f"{label} must be under the project root") from error
    current = project_root
    for part in relative.parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"{label} cannot use symlink directories")
    if path.is_symlink():
        raise ValueError(f"{label} cannot be a symlink")
    try:
        resolved = path.resolve()
    except OSError as error:
        raise ValueError(f"{label} path cannot be resolved") from error
    if not resolved.is_relative_to(project_root) or not resolved.is_file():
        raise ValueError(f"{label} must be a file under the project root")


def _ensure_runtime_subdirectory(project_root: Path, name: str) -> Path:
    runtime_dir = project_root / "runtime"
    if runtime_dir.is_symlink():
        raise ValueError("Evidence Stop receipts cannot use symlink directories")
    if runtime_dir.exists() and not runtime_dir.is_dir():
        raise ValueError("Evidence Stop receipt path must be a directory")
    runtime_dir.mkdir(exist_ok=True)
    target = runtime_dir / name
    if target.is_symlink():
        raise ValueError("Evidence Stop receipts cannot use symlink directories")
    if target.exists() and not target.is_dir():
        raise ValueError("Evidence Stop receipt path must be a directory")
    target.mkdir(exist_ok=True)
    if not target.resolve().is_relative_to(project_root):
        raise ValueError("Evidence Stop receipt path must remain under the project root")
    return target
