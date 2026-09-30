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
from ...domain.research.evidence_stop import ResearchScheduleRequest


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
    """Atomically persist one admission per scoped request and evidence IDs."""

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
