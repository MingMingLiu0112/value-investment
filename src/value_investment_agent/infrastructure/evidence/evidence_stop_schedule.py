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
    schedule_request_from_payload,
)
from ...domain.research.issuer_identity import (
    source_identity_matches_registered_issuer,
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
        if not isinstance(identity, Mapping) or not source_identity_matches_registered_issuer(
            symbol=symbol,
            location=location,
            issuer_identity=identity,
        ):
            continue
        local_path = source.get("local_path")
        path = Path(local_path) if isinstance(local_path, str) and local_path else Path(location)
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


def record_admitted_schedule_resume(
    *,
    root: Path,
    schedule_id: str,
    recovery_receipt_sha256: str,
    interrupted_run_id: str,
    research_run_id: str,
    output_sha256: str,
) -> dict[str, Any]:
    """Append the completion of one explicitly resumed admitted schedule."""

    project_root = root.resolve()
    schedule_id = _validated_sha256(schedule_id, "schedule_id")
    recovery_sha = _validated_sha256(
        recovery_receipt_sha256, "recovery_receipt_sha256"
    )
    output_sha = _validated_sha256(output_sha256, "output_sha256")
    if not interrupted_run_id.strip() or not research_run_id.strip():
        raise ValueError("resume completion requires both run identifiers")

    recovery_path = (
        project_root
        / "runtime"
        / "research-evidence-stop-recoveries"
        / f"{schedule_id}.json"
    )
    _require_project_file(project_root, recovery_path, "recovery receipt")
    recovery_bytes = recovery_path.read_bytes()
    if hashlib.sha256(recovery_bytes).hexdigest() != recovery_sha:
        raise ValueError("recovery receipt hash does not match")
    try:
        recovery = json.loads(recovery_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("recovery receipt is not valid UTF-8 JSON") from error
    if not isinstance(recovery, Mapping) or any((
        recovery.get("schema_version") != "research-evidence-stop-recovery-v1",
        recovery.get("schedule_id") != schedule_id,
        recovery.get("interrupted_run_id") != interrupted_run_id.strip(),
        recovery.get("status") != "RECOVERY_RECORDED_AWAITING_EXPLICIT_RESUME",
        recovery.get("automatic_retry") is not False,
        recovery.get("resume_performed") is not False,
        recovery.get("action") != "no_order",
    )):
        raise ValueError("recovery receipt does not match the explicit resume")

    resume_dir = _ensure_runtime_subdirectory(
        project_root, "research-evidence-stop-resumes"
    )
    resume_path = resume_dir / f"{schedule_id}.json"
    payload = {
        "schema_version": "research-evidence-stop-resume-v1",
        "schedule_id": schedule_id,
        "interrupted_run_id": interrupted_run_id.strip(),
        "research_run_id": research_run_id.strip(),
        "recovery_receipt_sha256": recovery_sha,
        "output_sha256": output_sha,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "status": "EXPLICIT_RESUME_COMPLETED",
        "automatic_retry": False,
        "resume_performed": True,
        "action": "no_order",
    }
    encoded = (
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    ).encode("utf-8")
    if resume_path.is_symlink():
        raise ValueError("resume completion receipt cannot be a symlink")
    try:
        descriptor = os.open(
            resume_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError as error:
        raise ValueError("explicit resume was already completed") from error
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    return {
        "status": payload["status"],
        "automatic_retry": False,
        "resume_performed": True,
        "schedule_id": schedule_id,
        "receipt_path": str(resume_path),
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


def load_evidence_stop_resolutions(root: Path) -> dict[str, Mapping[str, Any]]:
    """Load append-only stop resolutions and fail closed on conflicting claims."""

    project_root = root.resolve()
    directory = project_root / "runtime" / "research-evidence-stop-resolutions"
    if not directory.exists():
        return {}
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("Evidence Stop resolution directory must be a real directory")
    by_stop: dict[str, Mapping[str, Any]] = {}
    for path in sorted(directory.glob("*.json")):
        _require_project_file(project_root, path, "Evidence Stop resolution")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("Evidence Stop resolution is not valid UTF-8 JSON") from error
        schedule_id = payload.get("schedule_id") if isinstance(payload, Mapping) else None
        stop_ids = payload.get("stop_ids") if isinstance(payload, Mapping) else None
        evidence_ids = payload.get("resolved_evidence_ids") if isinstance(payload, Mapping) else None
        if not isinstance(payload, Mapping) or any((
            payload.get("schema_version") != "research-evidence-stop-resolution-v1",
            payload.get("status") != "EVIDENCE_RESOLVED",
            payload.get("action") != "no_order",
            not isinstance(schedule_id, str) or schedule_id != path.stem,
            not isinstance(payload.get("symbol"), str)
            or re.fullmatch(r"[0-9]{6}", payload["symbol"]) is None,
            not isinstance(stop_ids, list) or not stop_ids
            or any(not isinstance(item, str) or not item.strip() for item in stop_ids)
            or len(set(stop_ids)) != len(stop_ids),
            not isinstance(evidence_ids, list) or not evidence_ids
            or any(not isinstance(item, str) or not item.strip() for item in evidence_ids)
            or len(set(evidence_ids)) != len(evidence_ids),
        )):
            raise ValueError("Evidence Stop resolution contract is invalid")
        for stop_id in stop_ids:
            existing = by_stop.get(stop_id)
            if existing is not None and existing.get("schedule_id") != schedule_id:
                raise ValueError("Evidence Stop has conflicting resolution receipts")
            by_stop[stop_id] = payload
    return by_stop


def resolved_evidence_stop_ids(root: Path) -> frozenset[str]:
    """Return stop ids with one valid append-only resolution receipt."""

    return frozenset(load_evidence_stop_resolutions(root))


def record_evidence_stop_resolution(
    *,
    root: Path,
    schedule_id: str,
    request_path: Path,
    package_path: Path,
    research_result_path: Path,
    research_result_sha256: str,
) -> dict[str, Any]:
    """Close a missing-evidence scope after its admitted run completed.

    This records evidence resolution only. It cannot approve assumptions,
    valuation, price admission, a recommendation or an order.
    """

    project_root = root.resolve()
    schedule_id = _validated_sha256(schedule_id, "schedule_id")
    result_sha = _validated_sha256(research_result_sha256, "research_result_sha256")
    _require_project_file(project_root, request_path, "schedule request")
    _require_project_file(project_root, package_path, "research package")
    _require_project_file(project_root, research_result_path, "research result")

    ledger_path = project_root / "config" / "research-evidence-stop-ledger-v1.json"
    _require_project_file(project_root, ledger_path, "evidence-stop ledger")
    ledger_bytes = ledger_path.read_bytes()
    ledger_sha = hashlib.sha256(ledger_bytes).hexdigest()
    try:
        ledger = json.loads(ledger_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Evidence Stop ledger is not valid UTF-8 JSON") from error
    stops = evidence_stops_from_payload(ledger)

    consumption_path = (
        project_root / "runtime" / "research-evidence-stop-consumptions"
        / f"{schedule_id}.json"
    )
    recovery_path = (
        project_root / "runtime" / "research-evidence-stop-recoveries"
        / f"{schedule_id}.json"
    )
    resume_path = (
        project_root / "runtime" / "research-evidence-stop-resumes"
        / f"{schedule_id}.json"
    )
    for path, label in (
        (consumption_path, "admission receipt"),
        (recovery_path, "recovery receipt"),
        (resume_path, "resume receipt"),
    ):
        _require_project_file(project_root, path, label)

    def load_receipt(path: Path, label: str) -> tuple[Mapping[str, Any], str]:
        raw = path.read_bytes()
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(f"{label} is not valid UTF-8 JSON") from error
        if not isinstance(payload, Mapping):
            raise ValueError(f"{label} must be an object")
        return payload, hashlib.sha256(raw).hexdigest()

    consumption, consumption_sha = load_receipt(consumption_path, "admission receipt")
    recovery, recovery_sha = load_receipt(recovery_path, "recovery receipt")
    resume, resume_sha = load_receipt(resume_path, "resume receipt")
    request_bytes = request_path.read_bytes()
    request_sha = hashlib.sha256(request_bytes).hexdigest()
    try:
        request_payload = json.loads(request_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("schedule request is not valid UTF-8 JSON") from error
    request = schedule_request_from_payload(request_payload)
    scope_key = list(request.key)
    evidence_ids = sorted(request.new_evidence_ids)

    if not isinstance(consumption, Mapping) or any((
        consumption.get("schema_version") != "research-evidence-stop-consumption-v1",
        consumption.get("schedule_id") != schedule_id,
        consumption.get("symbol") != request.symbol,
        consumption.get("scope_key") != scope_key,
        consumption.get("new_evidence_ids") != evidence_ids,
        consumption.get("ledger_sha256") != ledger_sha,
        consumption.get("request_sha256") != request_sha,
        consumption.get("status") != "ADMITTED_ONCE",
        consumption.get("action") != "no_order",
    )):
        raise ValueError("admission receipt does not match the resolution request")

    matching_stops = tuple(stop for stop in stops if stop.key == request.key)
    if not matching_stops:
        raise ValueError("no Evidence Stop matches the resolution request")
    stop_ids = sorted(stop.stop_id for stop in matching_stops)

    package_bytes = package_path.read_bytes()
    package_sha = hashlib.sha256(package_bytes).hexdigest()
    try:
        package = json.loads(package_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("research package is not valid UTF-8 JSON") from error
    if not isinstance(package, Mapping):
        raise ValueError("research package must be an object")
    verified_ids = verified_official_package_source_ids(
        project_root,
        package.get("sources") or (),
        request.new_evidence_ids,
        symbol=request.symbol,
    )
    decision = evaluate_research_schedule(
        symbol=request.symbol,
        stops=stops,
        request=request,
        verified_evidence_ids=verified_ids,
    )
    if decision.get("status") != "REOPENED_WITH_NEW_EVIDENCE" or not decision.get("allowed"):
        raise ValueError("resolved evidence no longer satisfies the registered reopen scope")

    if not isinstance(recovery, Mapping) or any((
        recovery.get("schema_version") != "research-evidence-stop-recovery-v1",
        recovery.get("schedule_id") != schedule_id,
        recovery.get("symbol") != request.symbol,
        recovery.get("scope_key") != scope_key,
        recovery.get("new_evidence_ids") != evidence_ids,
        recovery.get("ledger_sha256") != ledger_sha,
        recovery.get("request_sha256") != request_sha,
        recovery.get("admission_receipt_sha256") != consumption_sha,
        recovery.get("status") != "RECOVERY_RECORDED_AWAITING_EXPLICIT_RESUME",
        recovery.get("automatic_retry") is not False,
        recovery.get("resume_performed") is not False,
        recovery.get("action") != "no_order",
    )):
        raise ValueError("recovery receipt does not match the resolution request")
    if not isinstance(resume, Mapping) or any((
        resume.get("schema_version") != "research-evidence-stop-resume-v1",
        resume.get("schedule_id") != schedule_id,
        resume.get("recovery_receipt_sha256") != recovery_sha,
        resume.get("output_sha256") != result_sha,
        resume.get("status") != "EXPLICIT_RESUME_COMPLETED",
        resume.get("automatic_retry") is not False,
        resume.get("resume_performed") is not True,
        resume.get("action") != "no_order",
    )):
        raise ValueError("resume receipt does not match the completed research result")

    result_bytes = research_result_path.read_bytes()
    if hashlib.sha256(result_bytes).hexdigest() != result_sha:
        raise ValueError("research result hash does not match")
    try:
        result = json.loads(result_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("research result is not valid UTF-8 JSON") from error
    schedule_gate = result.get("schedule_gate") if isinstance(result, Mapping) else None
    schedule_consumption = result.get("schedule_consumption") if isinstance(result, Mapping) else None
    if not isinstance(result, Mapping) or any((
        result.get("symbol") != request.symbol,
        result.get("run_id") != resume.get("research_run_id"),
        result.get("action") != "no_order",
        not isinstance(schedule_gate, Mapping),
        schedule_gate.get("status") != "REOPENED_WITH_NEW_EVIDENCE",
        schedule_gate.get("matched_stop_ids") != stop_ids,
        schedule_gate.get("new_evidence_ids") != evidence_ids,
        not isinstance(schedule_consumption, Mapping),
        schedule_consumption.get("schedule_id") != schedule_id,
    )):
        raise ValueError("research result does not bind the completed Evidence Stop scope")

    verified_sources = {
        (str(row.get("path", "")).replace("\\", "/"), row.get("sha256"))
        for row in (result.get("source_verification") or {}).get("sources", ())
        if isinstance(row, Mapping)
    }
    for source in package.get("sources") or ():
        if isinstance(source, Mapping) and source.get("id") in request.new_evidence_ids:
            pair = (
                str(source.get("local_path", "")).replace("\\", "/"),
                source.get("sha256"),
            )
            if pair not in verified_sources:
                raise ValueError("resolved evidence is absent from the completed run binding")

    payload = {
        "schema_version": "research-evidence-stop-resolution-v1",
        "schedule_id": schedule_id,
        "symbol": request.symbol,
        "scope_key": scope_key,
        "stop_ids": stop_ids,
        "resolved_evidence_ids": evidence_ids,
        "ledger_sha256": ledger_sha,
        "request_sha256": request_sha,
        "admission_receipt_sha256": consumption_sha,
        "recovery_receipt_sha256": recovery_sha,
        "resume_receipt_sha256": resume_sha,
        "research_run_id": result.get("run_id"),
        "research_package": {
            "path": package_path.relative_to(project_root).as_posix(),
            "sha256": package_sha,
        },
        "research_result": {
            "path": research_result_path.relative_to(project_root).as_posix(),
            "sha256": result_sha,
        },
        "resolved_at": datetime.now(timezone.utc).isoformat(),
        "status": "EVIDENCE_RESOLVED",
        "scope": "missing_evidence_scope_only; no assumption, valuation, price, recommendation or order approval",
        "action": "no_order",
    }
    encoded = (
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    ).encode("utf-8")
    directory = _ensure_runtime_subdirectory(
        project_root, "research-evidence-stop-resolutions"
    )
    target = directory / f"{schedule_id}.json"
    if target.is_symlink():
        raise ValueError("Evidence Stop resolution cannot be a symlink")
    try:
        descriptor_file = os.open(
            target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
        )
    except FileExistsError:
        existing = json.loads(target.read_text(encoding="utf-8"))
        comparable = (
            "schema_version", "schedule_id", "symbol", "scope_key", "stop_ids",
            "resolved_evidence_ids", "ledger_sha256", "request_sha256",
            "admission_receipt_sha256", "recovery_receipt_sha256",
            "resume_receipt_sha256", "research_run_id", "research_package",
            "research_result",
            "status", "scope", "action",
        )
        if any(existing.get(key) != payload.get(key) for key in comparable):
            raise ValueError("Evidence Stop resolution conflicts with the existing receipt")
        return {
            "created": False,
            "status": "EVIDENCE_RESOLUTION_ALREADY_RECORDED",
            "schedule_id": schedule_id,
            "stop_ids": stop_ids,
            "receipt_path": str(target),
            "receipt_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        }
    with os.fdopen(descriptor_file, "wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    return {
        "created": True,
        "status": payload["status"],
        "schedule_id": schedule_id,
        "stop_ids": stop_ids,
        "receipt_path": str(target),
        "receipt_sha256": hashlib.sha256(encoded).hexdigest(),
    }
