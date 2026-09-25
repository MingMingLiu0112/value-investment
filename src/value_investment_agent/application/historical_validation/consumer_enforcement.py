"""Fail-closed enforcement for strict historical PIT consumers.

The verifier result is never accepted as a stored capability.  A consumer must
call :func:`enforce_strict_pit_consumption` in the same process that reads the
subject.  The helper reruns verifier v2, records the exact subject/manifest
bytes it reads, and returns the parsed payload from those same bytes.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from .pit_conformance import (
    ACTION_NO_ORDER,
    PIT_CONFORMANCE_INPUT_SCHEMA,
    PIT_CONFORMANCE_SCHEMA,
    STATUS_PASS,
    verify_pit_conformance_v2,
)


CONSUMER_ENFORCEMENT_SCHEMA = "pit-conformance-consumer-enforcement-v1"


class StrictPitConsumerBlocked(RuntimeError):
    """Raised when a strict consumer lacks a fresh, byte-bound PASS."""

    def __init__(
        self,
        message: str,
        *,
        verifier_result: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.verifier_result = dict(verifier_result or {})


@dataclass(frozen=True)
class VerifiedPitSubject:
    """The exact subject bytes and parsed objects admitted to a strict consumer."""

    subject_path: Path
    manifest_path: Path
    subject_sha256: str
    manifest_sha256: str
    subject: Mapping[str, Any]
    manifest: Mapping[str, Any]
    verifier_result: Mapping[str, Any]

    def as_receipt(self) -> dict[str, Any]:
        return {
            "schema_version": CONSUMER_ENFORCEMENT_SCHEMA,
            "status": STATUS_PASS,
            "verification_mode": "IN_PROCESS_FRESH_RECHECK",
            "subject": {
                "path": str(self.subject_path),
                "sha256": self.subject_sha256,
                "schema_version": self.subject.get("schema_version"),
            },
            "manifest": {
                "path": str(self.manifest_path),
                "sha256": self.manifest_sha256,
            },
            "verifier": {
                "schema_version": self.verifier_result.get("schema_version"),
                "policy_version": self.verifier_result.get("policy_version"),
                "verified_at": self.verifier_result.get("verified_at"),
                "status": self.verifier_result.get("status"),
            },
            "strict_pit_admitted": True,
            "action": ACTION_NO_ORDER,
            "performance_claim_allowed": False,
            "valuation_approved": False,
            "trade_approved": False,
            "production_authorized": False,
        }


def _resolve_file(root: Path, path: Path, label: str) -> Path:
    resolved_root = root.resolve()
    candidate = path if path.is_absolute() else resolved_root / path
    resolved = candidate.resolve()
    if not resolved.is_relative_to(resolved_root):
        raise StrictPitConsumerBlocked(
            f"{label} resolves outside the repository root: {resolved}"
        )
    if not resolved.is_file():
        raise StrictPitConsumerBlocked(f"{label} does not exist: {resolved}")
    return resolved


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json_object(path: Path, label: str) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise StrictPitConsumerBlocked(f"{label} is not valid JSON: {path}") from error
    if not isinstance(payload, dict):
        raise StrictPitConsumerBlocked(f"{label} must be a JSON object: {path}")
    return payload, hashlib.sha256(raw).hexdigest()


def enforce_strict_pit_consumption(
    root: Path,
    *,
    subject_path: Path,
    manifest_path: Path | None,
    consumed_at: datetime | None = None,
) -> VerifiedPitSubject:
    """Require a fresh verifier v2 PASS before a strict consumer may proceed."""
    if manifest_path is None:
        raise StrictPitConsumerBlocked(
            "strict PIT consumption requires an independent v2 manifest"
        )

    resolved_root = root.resolve()
    resolved_subject = _resolve_file(resolved_root, subject_path, "PIT subject")
    resolved_manifest = _resolve_file(resolved_root, manifest_path, "PIT manifest")

    before_subject_sha256 = _digest(resolved_subject)
    before_manifest_sha256 = _digest(resolved_manifest)
    result = verify_pit_conformance_v2(
        resolved_root,
        subject_path=resolved_subject,
        manifest_path=resolved_manifest,
        verified_at=consumed_at,
    )
    if result.get("schema_version") != PIT_CONFORMANCE_SCHEMA:
        raise StrictPitConsumerBlocked(
            "PIT verifier returned an unsupported result schema",
            verifier_result=result,
        )
    if result.get("action") != ACTION_NO_ORDER:
        raise StrictPitConsumerBlocked(
            "PIT verifier result must remain action=no_order",
            verifier_result=result,
        )
    if result.get("status") != STATUS_PASS or result.get("strict_pit_admissible") is not True:
        raise StrictPitConsumerBlocked(
            "strict PIT consumption requires a fresh verifier PASS",
            verifier_result=result,
        )

    # Re-read the exact bytes after verification.  The verifier reports hashes
    # from its own read, so a change between reads fails closed instead of
    # silently binding a different subject or manifest.
    subject, subject_sha256 = _read_json_object(resolved_subject, "PIT subject")
    manifest, manifest_sha256 = _read_json_object(resolved_manifest, "PIT manifest")
    reported_subject = (result.get("subject") or {}).get("sha256")
    reported_manifest = (result.get("manifest") or {}).get("sha256")
    if (
        subject_sha256 != before_subject_sha256
        or manifest_sha256 != before_manifest_sha256
        or subject_sha256 != reported_subject
        or manifest_sha256 != reported_manifest
    ):
        raise StrictPitConsumerBlocked(
            "PIT subject or manifest bytes changed during verification",
            verifier_result=result,
        )
    if manifest.get("schema_version") != PIT_CONFORMANCE_INPUT_SCHEMA:
        raise StrictPitConsumerBlocked(
            "PIT conformance manifest schema is unsupported",
            verifier_result=result,
        )

    return VerifiedPitSubject(
        subject_path=resolved_subject,
        manifest_path=resolved_manifest,
        subject_sha256=subject_sha256,
        manifest_sha256=manifest_sha256,
        subject=MappingProxyType(subject),
        manifest=MappingProxyType(manifest),
        verifier_result=MappingProxyType(dict(result)),
    )
