"""Append-only research artifact persistence contract.

This module defines the canonical identity and hash rules shared by the domain
and repository layers. It intentionally imports no database, HTTP or Excel
code. A repository turns these objects into rows; presentation never consumes
the database directly.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
import re
from typing import Any, Mapping, Sequence


SCOPE_SECURITY = "security"
SCOPE_BATCH = "batch"
SCOPE_REVIEW = "review"
SCOPE_TYPES = frozenset({SCOPE_SECURITY, SCOPE_BATCH, SCOPE_REVIEW})

ARTIFACT_RESEARCH_CASE = "research_case"
ARTIFACT_VALUATION_ASSUMPTIONS = "valuation_assumptions"
ARTIFACT_VALUATION_RESULT = "valuation_result"
ARTIFACT_MODEL_VALIDITY = "model_validity"
ARTIFACT_QUOTE_SNAPSHOT = "quote_snapshot"
ARTIFACT_PRICE_BRIDGE = "price_bridge"
ARTIFACT_PRICE_ATTRACTIVENESS = "price_attractiveness"
ARTIFACT_DIVIDEND_RESEARCH = "dividend_research"
ARTIFACT_CURRENT_RESEARCH_STATUS = "current_research_status"
ARTIFACT_FIXED_SAMPLE_ADMISSION = "fixed_sample_admission"
ARTIFACT_RESEARCH_GATE = "research_gate"
ARTIFACT_BATCH_RUN_RESULT = "batch_run_result"
ARTIFACT_RAW_DOCUMENT = "raw_document"

ARTIFACT_TYPES = frozenset(
    {
        ARTIFACT_RESEARCH_CASE,
        ARTIFACT_VALUATION_ASSUMPTIONS,
        ARTIFACT_VALUATION_RESULT,
        ARTIFACT_MODEL_VALIDITY,
        ARTIFACT_QUOTE_SNAPSHOT,
        ARTIFACT_PRICE_BRIDGE,
        ARTIFACT_PRICE_ATTRACTIVENESS,
        ARTIFACT_DIVIDEND_RESEARCH,
        ARTIFACT_CURRENT_RESEARCH_STATUS,
        ARTIFACT_FIXED_SAMPLE_ADMISSION,
        ARTIFACT_RESEARCH_GATE,
        ARTIFACT_BATCH_RUN_RESULT,
        ARTIFACT_RAW_DOCUMENT,
    }
)

_SCOPE_ALLOWLIST: dict[str, frozenset[str]] = {
    ARTIFACT_RESEARCH_CASE: frozenset({SCOPE_SECURITY}),
    ARTIFACT_RESEARCH_GATE: frozenset({SCOPE_SECURITY}),
    ARTIFACT_VALUATION_ASSUMPTIONS: frozenset({SCOPE_SECURITY}),
    ARTIFACT_VALUATION_RESULT: frozenset({SCOPE_SECURITY}),
    ARTIFACT_MODEL_VALIDITY: frozenset({SCOPE_SECURITY}),
    ARTIFACT_QUOTE_SNAPSHOT: frozenset({SCOPE_SECURITY}),
    ARTIFACT_PRICE_BRIDGE: frozenset({SCOPE_SECURITY}),
    ARTIFACT_PRICE_ATTRACTIVENESS: frozenset({SCOPE_SECURITY}),
    ARTIFACT_DIVIDEND_RESEARCH: frozenset({SCOPE_SECURITY}),
    ARTIFACT_CURRENT_RESEARCH_STATUS: frozenset({SCOPE_SECURITY}),
    ARTIFACT_FIXED_SAMPLE_ADMISSION: frozenset({SCOPE_REVIEW}),
    ARTIFACT_BATCH_RUN_RESULT: frozenset({SCOPE_BATCH}),
    ARTIFACT_RAW_DOCUMENT: frozenset({SCOPE_SECURITY, SCOPE_REVIEW}),
}

_HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SYMBOL = re.compile(r"^[0-9]{6}$")


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        if value.utcoffset() is None:
            raise ValueError("Canonical artifact datetime must include timezone")
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("Canonical artifact decimals must be finite")
        return str(value)
    raise TypeError(f"Unsupported canonical artifact value: {type(value).__name__}")


def _validate_json_shape(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str) or not key:
                raise ValueError(f"Canonical artifact key is invalid at {path}")
            _validate_json_shape(child, f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _validate_json_shape(child, f"{path}[{index}]")
        return
    if value is None or isinstance(value, (str, bool, int, float)):
        if isinstance(value, float) and (
            value != value or value in (float("inf"), float("-inf"))
        ):
            raise ValueError(f"Canonical artifact number is not finite at {path}")
        return
    if isinstance(value, (Decimal, date, datetime)):
        _json_default(value)
        return
    raise ValueError(f"Unsupported canonical artifact value at {path}")


def canonicalize_artifact_payload(payload: Mapping[str, Any]) -> str:
    """Return deterministic UTF-8 canonical JSON or fail closed."""
    if not isinstance(payload, dict) or not payload:
        raise ValueError("Research artifact payload must be a nonempty object")
    _validate_json_shape(dict(payload))
    try:
        return json.dumps(
            dict(payload),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
            default=_json_default,
        )
    except (TypeError, ValueError) as error:
        raise ValueError("Research artifact payload cannot be canonicalized") from error


def sha256_text(value: str | bytes) -> str:
    data = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(data).hexdigest()


def _normalize_evidence_refs(refs: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    if not isinstance(refs, Sequence) or isinstance(refs, (str, bytes)):
        raise ValueError("Evidence references must be a sequence")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in refs:
        if not isinstance(raw, Mapping):
            raise ValueError("Evidence references must be objects")
        ref = dict(raw)
        ref_id = ref.get("id")
        if not isinstance(ref_id, str) or not ref_id.strip():
            raise ValueError("Evidence references require named ids")
        if ref_id in seen:
            raise ValueError("Evidence reference ids must be unique")
        seen.add(ref_id)
        result.append(ref)
    return tuple(result)


@dataclass(frozen=True)
class ResearchArtifactIdentity:
    """Stable identity used to address one immutable artifact version."""

    scope_type: str
    scope_key: str
    artifact_type: str
    schema_version: str
    as_of: date | None
    available_at: datetime

    def __post_init__(self) -> None:
        if self.scope_type not in SCOPE_TYPES:
            raise ValueError(f"Unknown research artifact scope: {self.scope_type}")
        if not isinstance(self.scope_key, str) or not self.scope_key.strip():
            raise ValueError("Research artifact scope key is required")
        if self.artifact_type not in ARTIFACT_TYPES:
            raise ValueError(f"Unknown research artifact type: {self.artifact_type}")
        allowed_scopes = _SCOPE_ALLOWLIST[self.artifact_type]
        if self.scope_type not in allowed_scopes:
            raise ValueError(
                f"{self.artifact_type} does not allow scope {self.scope_type}"
            )
        if not isinstance(self.schema_version, str) or not self.schema_version.strip():
            raise ValueError("Research artifact schema version is required")
        if self.as_of is not None and not isinstance(self.as_of, date):
            raise ValueError("Research artifact as_of must be a date or null")
        if not isinstance(self.available_at, datetime):
            raise ValueError("Research artifact available_at must be a datetime")
        if self.available_at.tzinfo is None:
            raise ValueError("Research artifact available_at must include timezone")
        if self.scope_type == SCOPE_SECURITY and not _SYMBOL.fullmatch(self.scope_key):
            raise ValueError("Security-scope artifacts require a six-digit symbol key")

    def as_dict(self) -> dict[str, Any]:
        return {
            "scope_type": self.scope_type,
            "scope_key": self.scope_key,
            "artifact_type": self.artifact_type,
            "schema_version": self.schema_version,
            "as_of": self.as_of.isoformat() if self.as_of else None,
            "available_at": self.available_at.isoformat(),
        }

    def identity_key(self) -> str:
        fields = (
            self.scope_type,
            self.scope_key,
            self.artifact_type,
            self.schema_version,
            self.as_of.isoformat() if self.as_of is not None else "",
            self.available_at.isoformat(),
        )
        return "\x1f".join(fields)


@dataclass(frozen=True)
class ResearchArtifactEnvelope:
    """A validated immutable artifact before it receives a repository row id."""

    identity: ResearchArtifactIdentity
    canonical_payload: str
    payload_sha256: str
    evidence_refs: tuple[dict[str, Any], ...]
    run_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.canonical_payload, str) or not self.canonical_payload:
            raise ValueError("Research artifact canonical payload is required")
        if not _HEX_SHA256.fullmatch(self.payload_sha256):
            raise ValueError("Research artifact payload hash must be SHA-256 hex")
        expected = sha256_text(self.canonical_payload)
        if expected != self.payload_sha256:
            raise ValueError("Research artifact payload hash does not match")
        if not isinstance(self.run_id, str) or not self.run_id.strip():
            raise ValueError("Research artifact run identity is required")
        object.__setattr__(self, "evidence_refs", _normalize_evidence_refs(self.evidence_refs))

    @classmethod
    def build(
        cls,
        *,
        identity: ResearchArtifactIdentity,
        payload: Mapping[str, Any],
        evidence_refs: Sequence[Mapping[str, Any]] = (),
        run_id: str,
    ) -> ResearchArtifactEnvelope:
        canonical = canonicalize_artifact_payload(payload)
        return cls(
            identity=identity,
            canonical_payload=canonical,
            payload_sha256=sha256_text(canonical),
            evidence_refs=_normalize_evidence_refs(evidence_refs),
            run_id=run_id,
        )

    def natural_key(self) -> str:
        return sha256_text(
            self.identity.identity_key() + "\x1e" + self.payload_sha256
        )

    def payload_object(self) -> dict[str, Any]:
        return json.loads(self.canonical_payload)

    def verify_payload(self) -> str:
        """Return the expected hash after recomputing it from exact bytes."""
        return sha256_text(self.canonical_payload)


@dataclass(frozen=True)
class StoredResearchArtifact:
    """An artifact returned by a repository after exact hash verification."""

    artifact_id: str
    envelope: ResearchArtifactEnvelope
    created_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.artifact_id, str) or not self.artifact_id.strip():
            raise ValueError("Stored artifact id is required")
        if not isinstance(self.created_at, datetime) or self.created_at.tzinfo is None:
            raise ValueError("Stored artifact created_at must be timezone-aware")


@dataclass(frozen=True)
class ResearchArtifactHead:
    """Mutable latest pointer, kept separate from the immutable version rows."""

    scope_type: str
    scope_key: str
    artifact_type: str
    artifact_id: str
    schema_version: str
    as_of: date | None
    available_at: datetime
    payload_sha256: str
    updated_at: datetime

    def __post_init__(self) -> None:
        if self.scope_type not in SCOPE_TYPES:
            raise ValueError("Unknown research artifact head scope")
        if self.artifact_type not in ARTIFACT_TYPES:
            raise ValueError("Unknown research artifact head type")
        if not _HEX_SHA256.fullmatch(self.payload_sha256):
            raise ValueError("Research artifact head hash must be SHA-256 hex")
        if self.available_at.tzinfo is None or self.updated_at.tzinfo is None:
            raise ValueError("Research artifact head timestamps must include timezone")


def parse_stored_artifact_payload(
    artifact: StoredResearchArtifact,
) -> dict[str, Any]:
    """Recompute the hash, then restore the canonical object."""
    if artifact.envelope.verify_payload() != artifact.envelope.payload_sha256:
        raise ValueError("Stored research artifact failed hash verification")
    return artifact.envelope.payload_object()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
