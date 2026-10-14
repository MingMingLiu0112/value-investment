"""Publish and load the one verified daily public snapshot (TL10-RC).

The daily entry writes a versioned packet file, records an immutable
publication receipt and atomically repoints
``config/current-daily-public-snapshot.json``. Every Web read surface loads
that pointer, re-verifies the recorded SHA-256 and serves the stored bytes; a
pointer that is missing, stale or tampered with fails closed with a named
reason instead of silently recomposing a "current" packet.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

from .common import write_new_json
from .daily_public_packet import (
    ACTION,
    ENGINE_VERSION,
    STRUCTURE_ERRORS,
    packet_content_sha256,
)


SNAPSHOT_SCHEMA_VERSION = "current-daily-public-snapshot-v1"
SNAPSHOT_POINTER_PATH = "config/current-daily-public-snapshot.json"
SNAPSHOT_RECEIPT_DIR = "runtime/daily-public-packet/receipts"
RECEIPT_SCHEMA_VERSION = "daily-public-packet-receipt-v1"
STATUS_VERIFIED = "VERIFIED"
WORKBOOK_POINTER_PATH = "config/current-trial-workbook.json"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pointer_path(root: Path) -> Path:
    return Path(root) / SNAPSHOT_POINTER_PATH


def _resolve_runtime(root: Path, name: object) -> Path | None:
    """Resolve local runtime or a retained public JSON artifact, never private paths."""
    if not isinstance(name, str) or not name:
        return None
    relative = Path(name)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        return None
    target = (Path(root) / relative).resolve()
    runtime = (Path(root) / "runtime").resolve()
    public = (Path(root) / "artifacts" / "current").resolve()
    public_json = (target.is_relative_to(public) and target.suffix == ".json"
                   and not any(term in str(relative).lower()
                               for term in ("private", "journal", "secret", "credential")))
    if not target.is_relative_to(runtime) and not public_json:
        return None
    return target


def read_pointer(root: Path) -> tuple[dict | None, str | None]:
    """Return ``(pointer, None)`` or ``(None, reason)``; never raises."""
    path = pointer_path(root)
    if not path.is_file():
        return None, "SNAPSHOT_POINTER_MISSING"
    try:
        pointer = json.loads(path.read_text(encoding="utf-8"))
    except STRUCTURE_ERRORS:
        return None, "SNAPSHOT_POINTER_UNREADABLE"
    if not isinstance(pointer, dict) or pointer.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
        return None, "SNAPSHOT_POINTER_INVALID"
    if pointer.get("action") != ACTION or pointer.get("status") != STATUS_VERIFIED:
        return None, "SNAPSHOT_POINTER_INVALID"
    return pointer, None


def load_current_packet(root: Path) -> tuple[dict | None, str | None]:
    """Load the published packet after re-verifying every recorded digest."""
    root = Path(root).resolve()
    pointer, error = read_pointer(root)
    if pointer is None:
        return None, error
    target = _resolve_runtime(root, pointer.get("packet_path"))
    if target is None or not target.is_file():
        return None, "SNAPSHOT_ARTIFACT_MISSING"
    try:
        raw = target.read_bytes()
    except OSError:
        return None, "SNAPSHOT_ARTIFACT_UNREADABLE"
    if hashlib.sha256(raw).hexdigest() != pointer.get("packet_sha256"):
        return None, "SNAPSHOT_ARTIFACT_HASH_MISMATCH"
    try:
        packet = json.loads(raw.decode("utf-8"))
    except STRUCTURE_ERRORS:
        return None, "SNAPSHOT_ARTIFACT_UNREADABLE"
    if not isinstance(packet, dict) or packet.get("action") != ACTION:
        return None, "SNAPSHOT_ARTIFACT_CONTRACT_INVALID"
    digest = packet.get("content_sha256")
    if not isinstance(digest, str) or digest != pointer.get("content_sha256"):
        return None, "SNAPSHOT_CONTENT_DIGEST_MISMATCH"
    if packet.get("publication_id") != pointer.get("publication_id"):
        return None, "SNAPSHOT_IDENTITY_MISMATCH"
    if packet_content_sha256(packet) != digest:
        return None, "SNAPSHOT_CONTENT_TAMPERED"
    return packet, None


def _receipt_path(root: Path, publication_id: str) -> Path:
    return Path(root) / SNAPSHOT_RECEIPT_DIR / f"daily-public-packet-{publication_id}.receipt.json"


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Write through a sibling temp file and replace, so readers see all or nothing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def publish_snapshot(root: Path, packet: Mapping[str, Any], packet_path: Path, *,
                     published_at: datetime | None = None) -> dict:
    """Record the receipt and atomically repoint the current snapshot."""
    root = Path(root).resolve()
    publication_id = packet.get("publication_id")
    if packet.get("packet_status") != "CURRENT" or not isinstance(publication_id, str):
        raise ValueError("only a CURRENT packet with an identity can be published")
    digest = packet.get("content_sha256")
    if not isinstance(digest, str) or digest != packet_content_sha256(packet):
        raise ValueError("packet content digest missing or inconsistent")
    artifact = Path(packet_path).resolve()
    if not artifact.is_relative_to(root) or not artifact.is_file():
        raise ValueError("packet artifact must exist under the project root")
    moment = published_at or datetime.now(timezone.utc)
    file_sha = _sha256_file(artifact)
    receipt = _receipt_path(root, publication_id)
    if not receipt.exists():
        write_new_json(receipt, {
            "schema_version": RECEIPT_SCHEMA_VERSION,
            "action": ACTION,
            "publication_id": publication_id,
            "engine_version": packet.get("engine_version") or ENGINE_VERSION,
            "research_version": packet.get("research_version"),
            "packet_path": artifact.relative_to(root).as_posix(),
            "packet_sha256": file_sha,
            "content_sha256": digest,
            "identity_inputs": packet.get("identity_inputs"),
            "generated_at": packet.get("generated_at"),
            "published_at": moment.isoformat(),
        })
    pointer = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "action": ACTION,
        "status": STATUS_VERIFIED,
        "publication_id": publication_id,
        "packet_path": artifact.relative_to(root).as_posix(),
        "packet_sha256": file_sha,
        "content_sha256": digest,
        "engine_version": packet.get("engine_version") or ENGINE_VERSION,
        "research_version": packet.get("research_version"),
        "generated_at": packet.get("generated_at"),
        "published_at": moment.isoformat(),
        "receipt_path": receipt.relative_to(root).as_posix(),
    }
    _atomic_write_json(pointer_path(root), pointer)
    return pointer


def snapshot_metadata(root: Path) -> dict:
    """Compact status for the Web: does one verified frozen version exist?"""
    root = Path(root).resolve()
    pointer, error = read_pointer(root)
    if pointer is None:
        return {"schema_version": SNAPSHOT_SCHEMA_VERSION, "action": ACTION,
                "status": "UNAVAILABLE", "reason": error, "publication_id": None,
                "packet_path": None, "packet_sha256": None, "content_sha256": None,
                "engine_version": None, "research_version": None,
                "generated_at": None, "published_at": None, "receipt_path": None,
                "dates": None, "excel_sync": None}
    packet, error = load_current_packet(root)
    verified = packet is not None
    return {"schema_version": SNAPSHOT_SCHEMA_VERSION, "action": ACTION,
            "status": "VERIFIED" if verified else "INVALID",
            "reason": error,
            "publication_id": pointer.get("publication_id"),
            "packet_path": pointer.get("packet_path"),
            "packet_sha256": pointer.get("packet_sha256"),
            "content_sha256": pointer.get("content_sha256"),
            "engine_version": pointer.get("engine_version"),
            "research_version": pointer.get("research_version"),
            "generated_at": pointer.get("generated_at"),
            "published_at": pointer.get("published_at"),
            "receipt_path": pointer.get("receipt_path"),
            "dates": (packet or {}).get("dates"),
            "excel_sync": (packet or {}).get("excel_sync")}


def _declared_workbook_path(root: Path) -> str | None:
    """Resolve the formal workbook the same way the launch scripts do."""
    value = os.environ.get("WORKBOOK_PATH")
    if not value:
        env_file = Path(root) / ".env"
        try:
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("WORKBOOK_PATH"):
                    value = line.split("=", 1)[1].strip()
                    break
        except OSError:
            value = None
    return value or None


def workbook_version_report(root: Path) -> dict:
    """Read-only comparison between the Web snapshot and the formal workbook.

    Recomputes the on-disk SHA-256 when the file is reachable and never
    claims synchronisation it cannot prove: an unresolvable path or missing
    published hash is ``NOT_VERIFIED``, a mismatch is ``DIFFERENT``.
    """
    root = Path(root).resolve()
    contract: dict | None = None
    try:
        value = json.loads((root / WORKBOOK_POINTER_PATH).read_text(encoding="utf-8"))
        contract = value if isinstance(value, dict) else None
    except STRUCTURE_ERRORS:
        contract = None
    expected = contract.get("canonical_workbook_sha256") if contract else None
    expected = expected if isinstance(expected, str) else None
    declared = _declared_workbook_path(root)
    path = Path(declared).expanduser() if declared else None
    observed = None
    if path is not None:
        try:
            observed = _sha256_file(path) if path.is_file() else None
        except OSError:
            observed = None
    if path is None:
        status = "NOT_RESOLVED"
    elif observed is None or expected is None:
        status = "NOT_VERIFIED"
    elif observed == expected:
        status = "MATCHED"
    else:
        status = "DIFFERENT"
    return {"status": status, "path": str(path) if path is not None else None,
            "expected_sha256": expected, "observed_sha256": observed,
            "pointer_published_as_of": (contract or {}).get("as_of"),
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "note": "只读校验；不覆盖、不重建正式工作簿，不同步即为不同步。"}
