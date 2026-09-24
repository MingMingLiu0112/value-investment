"""Fail-closed M5 change-event and append-only ledger contracts.

The module owns deterministic event identity, deduplication, explicit
corrections and replay ordering.  It has no scheduler, broker or notification
side effects.  Public examples must use SIMULATED namespace.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Mapping, Sequence

from .investment_decision import ACTION_NO_ORDER


M5_EVENT_SCHEMA = "m5-event-infrastructure-v1"
NAMESPACE_ACTUAL = "ACTUAL"
NAMESPACE_SIMULATED = "SIMULATED"
EVENT_NAMESPACES = frozenset({NAMESPACE_ACTUAL, NAMESPACE_SIMULATED})

EVENT_TYPE_NEW_FINANCIAL_REPORT = "NEW_FINANCIAL_REPORT"
EVENT_TYPE_MATERIAL_ANNOUNCEMENT = "MATERIAL_ANNOUNCEMENT"
EVENT_TYPE_DIVIDEND_CHANGE = "DIVIDEND_CHANGE"
EVENT_TYPE_BUYBACK = "BUYBACK"
EVENT_TYPE_CAPITAL_ALLOCATION_CHANGE = "CAPITAL_ALLOCATION_CHANGE"
EVENT_TYPE_VALUATION_ZONE_CHANGED = "VALUATION_ZONE_CHANGED"
EVENT_TYPE_PRICE_ATTRACTIVENESS_CHANGED = "PRICE_ATTRACTIVENESS_CHANGED"
EVENT_TYPE_THESIS_WEAKENED = "THESIS_WEAKENED"
EVENT_TYPE_THESIS_BREAKER_TRIGGERED = "THESIS_BREAKER_TRIGGERED"
EVENT_TYPE_MODEL_STALE = "MODEL_STALE"
EVENT_TYPE_POSITION_RISK_CHANGED = "POSITION_RISK_CHANGED"
EVENT_TYPE_SOURCE_SCAN_FAILED = "SOURCE_SCAN_FAILED"
EVENT_TYPE_SOURCE_SCAN_RECOVERED = "SOURCE_SCAN_RECOVERED"
EVENT_TYPES = frozenset(
    {
        EVENT_TYPE_NEW_FINANCIAL_REPORT,
        EVENT_TYPE_MATERIAL_ANNOUNCEMENT,
        EVENT_TYPE_DIVIDEND_CHANGE,
        EVENT_TYPE_BUYBACK,
        EVENT_TYPE_CAPITAL_ALLOCATION_CHANGE,
        EVENT_TYPE_VALUATION_ZONE_CHANGED,
        EVENT_TYPE_PRICE_ATTRACTIVENESS_CHANGED,
        EVENT_TYPE_THESIS_WEAKENED,
        EVENT_TYPE_THESIS_BREAKER_TRIGGERED,
        EVENT_TYPE_MODEL_STALE,
        EVENT_TYPE_POSITION_RISK_CHANGED,
        EVENT_TYPE_SOURCE_SCAN_FAILED,
        EVENT_TYPE_SOURCE_SCAN_RECOVERED,
    }
)
_SYSTEM_EVENT_TYPES = frozenset(
    {EVENT_TYPE_SOURCE_SCAN_FAILED, EVENT_TYPE_SOURCE_SCAN_RECOVERED}
)

SEVERITY_CRITICAL = "CRITICAL"
SEVERITY_HIGH = "HIGH"
SEVERITY_MEDIUM = "MEDIUM"
SEVERITY_LOW = "LOW"
EVENT_SEVERITIES = frozenset(
    {SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM, SEVERITY_LOW}
)

CONFIDENCE_HIGH = "HIGH"
CONFIDENCE_MEDIUM = "MEDIUM"
CONFIDENCE_LOW = "LOW"
EVENT_CONFIDENCES = frozenset(
    {CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW}
)

EVENT_STATUS_ACTIVE = "ACTIVE"
EVENT_STATUS_SUPERSEDED = "SUPERSEDED"
EVENT_STATUSES = frozenset({EVENT_STATUS_ACTIVE, EVENT_STATUS_SUPERSEDED})

EVENT_IDENTITY_CURRENT = "source-id-v3"
EVENT_IDENTITY_SOURCE_ID_V2 = "source-id-v2"
EVENT_IDENTITY_SOURCE_ID_V1 = "source-id-v1"
EVENT_IDENTITY_LEGACY = "legacy-no-source-id-v1"
EVENT_IDENTITY_VERSIONS = frozenset(
    {
        EVENT_IDENTITY_CURRENT,
        EVENT_IDENTITY_SOURCE_ID_V2,
        EVENT_IDENTITY_SOURCE_ID_V1,
        EVENT_IDENTITY_LEGACY,
    }
)
LEGACY_EVENT_SOURCE_ID = "unspecified-source"

MATERIALITY_BRIDGE_SOURCE_ID = "human-materiality-review"
HUMAN_MATERIALITY_EVIDENCE_TYPE = "human_event_materiality_review"
MATERIALITY_PENDING_STATUS = "PENDING_HUMAN_REVIEW"
ACTIONABLE_HUMAN_MATERIALITY_DECISIONS = frozenset(
    {
        "MATERIAL_REQUIRES_RECALCULATION",
        "MATERIAL_RISK_MONITOR",
        "REQUIRES_DECOMPOSITION",
    }
)

INGEST_ACCEPTED = "ACCEPTED"
INGEST_DUPLICATE = "DUPLICATE"
INGEST_CORRECTION_ACCEPTED = "CORRECTION_ACCEPTED"
INGEST_SUPERSEDES_ACCEPTED = "SUPERSEDES_ACCEPTED"
INGEST_FUTURE_REJECTED = "FUTURE_REJECTED"
INGEST_CONFLICT_REJECTED = "CONFLICT_REJECTED"
INGEST_OBSERVED_TIME_REGRESSION_REJECTED = "OBSERVED_TIME_REGRESSION_REJECTED"
INGEST_STATUSES = frozenset(
    {
        INGEST_ACCEPTED,
        INGEST_DUPLICATE,
        INGEST_CORRECTION_ACCEPTED,
        INGEST_SUPERSEDES_ACCEPTED,
        INGEST_FUTURE_REJECTED,
        INGEST_CONFLICT_REJECTED,
        INGEST_OBSERVED_TIME_REGRESSION_REJECTED,
    }
)

_SYMBOL = re.compile(r"^(?:[0-9]{6}|SYSTEM)$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _optional_text(value: object, field: str) -> str | None:
    return None if value is None else _required_text(value, field)


def _required_datetime(value: object, field: str) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"{field} must be a timezone-aware datetime")
    return value


def _optional_datetime(value: object, field: str) -> datetime | None:
    return None if value is None else _required_datetime(value, field)


def _required_bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be boolean")
    return value


def _required_int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{field} must be an integer")
    return value


def _positive_int(value: object, field: str) -> int:
    parsed = _required_int(value, field)
    if parsed <= 0:
        raise ValueError(f"{field} must be positive")
    return parsed


def _required_refs(
    value: object,
    field: str = "evidence_refs",
) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{field} must be a list")
    refs = tuple(dict(item) for item in value)
    if not refs:
        raise ValueError(f"{field} cannot be empty")
    if any(not _required_text(ref.get("id"), f"{field}.id") for ref in refs):
        raise ValueError(f"{field} entries require ids")
    return refs


def _freeze_state(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    frozen = deepcopy(dict(value))
    try:
        json.dumps(frozen, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must contain JSON-compatible values") from error
    return frozen


def _state_digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            dict(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _digest(*parts: object) -> str:
    return hashlib.sha256(
        "|".join(str(part) for part in parts).encode("utf-8")
    ).hexdigest()


def _event_fingerprint(event: "ChangeEventInput") -> str:
    """Return the UTC-normalized current event identity."""
    return hashlib.sha256(
        json.dumps(
            {
                "identity_version": EVENT_IDENTITY_CURRENT,
                "namespace": event.namespace,
                "symbol": event.symbol,
                "source_id": event.source_id,
                "source_event_id": event.source_event_id,
                "event_type": event.event_type,
                "previous_state": event.previous_state,
                "current_state": event.current_state,
                "severity": event.severity,
                "reason": event.reason,
                "evidence_refs": [dict(item) for item in event.evidence_refs],
                "confidence": event.confidence,
                "detected_at": event.detected_at.astimezone(timezone.utc).isoformat(),
                "available_at": event.available_at.astimezone(timezone.utc).isoformat(),
                "effective_at": (
                    event.effective_at.astimezone(timezone.utc).isoformat()
                    if event.effective_at
                    else None
                ),
                "requires_human_review": event.requires_human_review,
                "correction_of_event_id": event.correction_of_event_id,
                "supersedes_event_id": event.supersedes_event_id,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _source_id_v2_event_fingerprint(event: "ChangeEventInput") -> str:
    """Reproduce the pre-UTC canonical fingerprint without changing its bytes."""
    return hashlib.sha256(
        json.dumps(
            {
                "identity_version": EVENT_IDENTITY_SOURCE_ID_V2,
                "namespace": event.namespace,
                "symbol": event.symbol,
                "source_id": event.source_id,
                "source_event_id": event.source_event_id,
                "event_type": event.event_type,
                "previous_state": event.previous_state,
                "current_state": event.current_state,
                "severity": event.severity,
                "reason": event.reason,
                "evidence_refs": [dict(item) for item in event.evidence_refs],
                "confidence": event.confidence,
                "detected_at": event.detected_at.isoformat(),
                "available_at": event.available_at.isoformat(),
                "effective_at": (
                    event.effective_at.isoformat() if event.effective_at else None
                ),
                "requires_human_review": event.requires_human_review,
                "correction_of_event_id": event.correction_of_event_id,
                "supersedes_event_id": event.supersedes_event_id,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _source_id_v1_event_fingerprint(event: "ChangeEventInput") -> str:
    """Reproduce the source-id-v1 fingerprint without changing its encoding."""
    return _digest(
        "event",
        event.namespace,
        event.symbol,
        event.source_id,
        event.source_event_id,
        event.event_type,
        _state_digest(event.previous_state),
        _state_digest(event.current_state),
        event.severity,
        event.reason,
        _state_digest({"refs": tuple(dict(item) for item in event.evidence_refs)}),
        event.confidence,
        event.effective_at.isoformat() if event.effective_at else "",
        str(event.requires_human_review).lower(),
        event.correction_of_event_id or "",
        event.supersedes_event_id or "",
    )


def _legacy_event_fingerprint(event: "ChangeEventInput") -> str:
    """Reproduce pre-source_id event identity for frozen v1 payloads."""
    return _digest(
        "event",
        event.namespace,
        event.symbol,
        event.source_event_id,
        event.event_type,
        _state_digest(event.previous_state),
        _state_digest(event.current_state),
        event.severity,
        event.reason,
        _state_digest({"refs": tuple(dict(item) for item in event.evidence_refs)}),
        event.confidence,
        event.correction_of_event_id or "",
        event.supersedes_event_id or "",
    )


@dataclass(frozen=True)
class ChangeEventInput:
    """A discovered change before ledger acceptance."""

    source_event_id: str
    symbol: str
    event_type: str
    detected_at: datetime
    available_at: datetime
    effective_at: datetime | None
    previous_state: Mapping[str, Any]
    current_state: Mapping[str, Any]
    severity: str
    reason: str
    evidence_refs: tuple[dict[str, Any], ...]
    confidence: str
    requires_human_review: bool
    correction_of_event_id: str | None = None
    supersedes_event_id: str | None = None
    namespace: str = NAMESPACE_ACTUAL
    action: str = ACTION_NO_ORDER
    source_id: str = LEGACY_EVENT_SOURCE_ID
    event_identity_version: str = EVENT_IDENTITY_CURRENT

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_event_id",
            _required_text(self.source_event_id, "source_event_id"),
        )
        object.__setattr__(
            self,
            "source_id",
            _required_text(self.source_id, "source_id"),
        )
        if self.event_identity_version not in EVENT_IDENTITY_VERSIONS:
            raise ValueError("Unknown event identity version")
        if (
            self.event_identity_version == EVENT_IDENTITY_LEGACY
            and self.source_id != LEGACY_EVENT_SOURCE_ID
        ):
            raise ValueError(
                "Legacy event identity requires unspecified-source"
            )
        object.__setattr__(self, "symbol", _required_text(self.symbol, "symbol"))
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("Event symbol must be six digits or SYSTEM")
        if self.event_type not in EVENT_TYPES:
            raise ValueError("Unknown event type")
        if self.event_type in _SYSTEM_EVENT_TYPES and self.symbol != "SYSTEM":
            raise ValueError("System source events require the SYSTEM symbol")
        if self.event_type not in _SYSTEM_EVENT_TYPES and self.symbol == "SYSTEM":
            raise ValueError("Security events require a six-digit symbol")
        object.__setattr__(
            self,
            "detected_at",
            _required_datetime(self.detected_at, "detected_at"),
        )
        object.__setattr__(
            self,
            "available_at",
            _required_datetime(self.available_at, "available_at"),
        )
        object.__setattr__(
            self,
            "effective_at",
            _optional_datetime(self.effective_at, "effective_at"),
        )
        if self.available_at > self.detected_at:
            raise ValueError("available_at cannot be later than detected_at")
        object.__setattr__(
            self,
            "previous_state",
            _freeze_state(self.previous_state, "previous_state"),
        )
        object.__setattr__(
            self,
            "current_state",
            _freeze_state(self.current_state, "current_state"),
        )
        if self.severity not in EVENT_SEVERITIES:
            raise ValueError("Unknown event severity")
        object.__setattr__(self, "reason", _required_text(self.reason, "reason"))
        object.__setattr__(self, "evidence_refs", _required_refs(self.evidence_refs))
        if self.confidence not in EVENT_CONFIDENCES:
            raise ValueError("Unknown event confidence")
        object.__setattr__(
            self,
            "requires_human_review",
            _required_bool(self.requires_human_review, "requires_human_review"),
        )
        if (
            self.event_type in _SYSTEM_EVENT_TYPES
            and not self.requires_human_review
        ):
            raise ValueError("System source events must require human review")
        if (
            self.event_type == EVENT_TYPE_MATERIAL_ANNOUNCEMENT
            and not self.requires_human_review
        ):
            raise ValueError(
                "Material announcements must carry a human materiality review"
            )
        if (
            self.event_type == EVENT_TYPE_MATERIAL_ANNOUNCEMENT
            and self.event_identity_version
            in {EVENT_IDENTITY_SOURCE_ID_V2, EVENT_IDENTITY_CURRENT}
        ):
            if self.source_id != MATERIALITY_BRIDGE_SOURCE_ID:
                raise ValueError(
                    "Material announcements must originate from the human materiality bridge"
                )
            if (
                self.previous_state.get("materiality_status")
                != MATERIALITY_PENDING_STATUS
            ):
                raise ValueError(
                    "Material announcements must transition from pending human review"
                )
            if (
                self.current_state.get("materiality_status")
                not in ACTIONABLE_HUMAN_MATERIALITY_DECISIONS
            ):
                raise ValueError(
                    "Material announcements require an actionable human decision"
                )
            source_sha256 = str(
                self.current_state.get("source_sha256", "")
            ).lower()
            source_ref_id = str(self.current_state.get("source_ref_id", ""))
            source_ref_sha256 = str(
                self.current_state.get("source_ref_sha256", "")
            ).lower()
            if not _SHA256.fullmatch(source_sha256):
                raise ValueError(
                    "Material announcements require a valid source SHA-256"
                )
            if source_ref_sha256 != source_sha256:
                raise ValueError(
                    "Material announcement source hash must match source_ref_sha256"
                )
            if not source_ref_id:
                raise ValueError(
                    "Material announcements require a source_ref_id"
                )
            human_refs = tuple(
                ref
                for ref in self.evidence_refs
                if ref.get("type") == HUMAN_MATERIALITY_EVIDENCE_TYPE
            )
            if len(human_refs) != 1 or not human_refs[0].get("id"):
                raise ValueError(
                    "Material announcements require exactly one human materiality evidence reference"
                )
            if (
                str(human_refs[0].get("source_sha256", "")).lower()
                != source_sha256
            ):
                raise ValueError(
                    "Human materiality evidence hash must match source SHA-256"
                )
            source_refs = tuple(
                ref for ref in self.evidence_refs if ref.get("id") == source_ref_id
            )
            if len(source_refs) != 1:
                raise ValueError(
                    "Material announcements require one matching source reference"
                )
            if str(source_refs[0].get("sha256", "")).lower() != source_sha256:
                raise ValueError(
                    "Material announcement source reference hash must match source SHA-256"
                )
        object.__setattr__(
            self,
            "correction_of_event_id",
            _optional_text(self.correction_of_event_id, "correction_of_event_id"),
        )
        object.__setattr__(
            self,
            "supersedes_event_id",
            _optional_text(self.supersedes_event_id, "supersedes_event_id"),
        )
        if self.correction_of_event_id and self.supersedes_event_id:
            raise ValueError("An event cannot both correct and supersede another event")
        if self.namespace not in EVENT_NAMESPACES:
            raise ValueError("Unknown event namespace")
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Event infrastructure must remain no_order")

    @property
    def source_fingerprint(self) -> str:
        if self.event_identity_version == EVENT_IDENTITY_LEGACY:
            return _legacy_event_fingerprint(self)
        if self.event_identity_version == EVENT_IDENTITY_SOURCE_ID_V1:
            return _source_id_v1_event_fingerprint(self)
        if self.event_identity_version == EVENT_IDENTITY_SOURCE_ID_V2:
            return _source_id_v2_event_fingerprint(self)
        return _event_fingerprint(self)

    @property
    def dedupe_key(self) -> tuple[str, str, str]:
        return self.symbol, self.source_id, self.source_event_id

    def as_policy(self) -> dict[str, Any]:
        payload = {
            "source_event_id": self.source_event_id,
            "source_id": self.source_id,
            "symbol": self.symbol,
            "event_type": self.event_type,
            "detected_at": self.detected_at.isoformat(),
            "available_at": self.available_at.isoformat(),
            "effective_at": self.effective_at.isoformat() if self.effective_at else None,
            "previous_state": deepcopy(self.previous_state),
            "current_state": deepcopy(self.current_state),
            "severity": self.severity,
            "reason": self.reason,
            "evidence_refs": [dict(item) for item in self.evidence_refs],
            "confidence": self.confidence,
            "requires_human_review": self.requires_human_review,
            "correction_of_event_id": self.correction_of_event_id,
            "supersedes_event_id": self.supersedes_event_id,
            "namespace": self.namespace,
            "action": self.action,
        }
        if self.event_identity_version in {
            EVENT_IDENTITY_SOURCE_ID_V2,
            EVENT_IDENTITY_CURRENT,
        }:
            payload["event_identity_version"] = self.event_identity_version
        elif self.event_identity_version == EVENT_IDENTITY_LEGACY:
            payload.pop("source_id", None)
        return payload


@dataclass(frozen=True)
class ChangeEvent:
    """An accepted event with deterministic identity and ledger sequence."""

    event_id: str
    source_event_id: str
    source_id: str
    symbol: str
    event_type: str
    detected_at: datetime
    available_at: datetime
    effective_at: datetime | None
    previous_state: dict[str, Any]
    current_state: dict[str, Any]
    severity: str
    reason: str
    evidence_refs: tuple[dict[str, Any], ...]
    confidence: str
    requires_human_review: bool
    correction_of_event_id: str | None
    supersedes_event_id: str | None
    namespace: str
    action: str
    status: str
    ingested_at: datetime
    sequence: int
    event_identity_version: str = EVENT_IDENTITY_CURRENT

    @classmethod
    def from_input(
        cls,
        event: ChangeEventInput,
        *,
        event_id: str,
        sequence: int,
        ingested_at: datetime,
        status: str = EVENT_STATUS_ACTIVE,
    ) -> "ChangeEvent":
        return cls(
            event_id=event_id,
            source_event_id=event.source_event_id,
            source_id=event.source_id,
            symbol=event.symbol,
            event_type=event.event_type,
            detected_at=event.detected_at,
            available_at=event.available_at,
            effective_at=event.effective_at,
            previous_state=deepcopy(event.previous_state),
            current_state=deepcopy(event.current_state),
            severity=event.severity,
            reason=event.reason,
            evidence_refs=tuple(dict(item) for item in event.evidence_refs),
            confidence=event.confidence,
            requires_human_review=event.requires_human_review,
            correction_of_event_id=event.correction_of_event_id,
            supersedes_event_id=event.supersedes_event_id,
            namespace=event.namespace,
            action=event.action,
            event_identity_version=event.event_identity_version,
            status=status,
            ingested_at=ingested_at,
            sequence=sequence,
        )

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", _required_text(self.event_id, "event_id"))
        object.__setattr__(
            self,
            "ingested_at",
            _required_datetime(self.ingested_at, "ingested_at"),
        )
        object.__setattr__(self, "sequence", _positive_int(self.sequence, "sequence"))
        if self.status not in EVENT_STATUSES:
            raise ValueError("Unknown event status")
        if self.event_identity_version not in EVENT_IDENTITY_VERSIONS:
            raise ValueError("Unknown event identity version")
        if (
            self.event_identity_version == EVENT_IDENTITY_LEGACY
            and self.source_id != LEGACY_EVENT_SOURCE_ID
        ):
            raise ValueError(
                "Legacy event identity requires unspecified-source"
            )
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Event infrastructure must remain no_order")
        object.__setattr__(self, "previous_state", deepcopy(self.previous_state))
        object.__setattr__(self, "current_state", deepcopy(self.current_state))
        object.__setattr__(self, "evidence_refs", _required_refs(self.evidence_refs))

    @property
    def input(self) -> ChangeEventInput:
        return ChangeEventInput(
            source_event_id=self.source_event_id,
            source_id=self.source_id,
            symbol=self.symbol,
            event_type=self.event_type,
            detected_at=self.detected_at,
            available_at=self.available_at,
            effective_at=self.effective_at,
            previous_state=self.previous_state,
            current_state=self.current_state,
            severity=self.severity,
            reason=self.reason,
            evidence_refs=self.evidence_refs,
            confidence=self.confidence,
            requires_human_review=self.requires_human_review,
            correction_of_event_id=self.correction_of_event_id,
            supersedes_event_id=self.supersedes_event_id,
            namespace=self.namespace,
            action=self.action,
            event_identity_version=self.event_identity_version,
        )

    @property
    def source_fingerprint(self) -> str:
        return self.input.source_fingerprint

    @property
    def is_critical(self) -> bool:
        return self.severity == SEVERITY_CRITICAL

    def as_policy(self) -> dict[str, Any]:
        payload = self.input.as_policy()
        payload.update(
            {
                "event_id": self.event_id,
                "status": self.status,
                "ingested_at": self.ingested_at.isoformat(),
                "sequence": self.sequence,
            }
        )
        return payload


def _compute_event_id(event: ChangeEventInput) -> str:
    return "m5-" + _digest("event-id", event.source_fingerprint)[:32]


@dataclass(frozen=True)
class EventIngestResult:
    status: str
    observed_at: datetime
    event: ChangeEvent | None
    superseded_event_ids: tuple[str, ...] = ()
    duplicate_event_id: str | None = None
    is_late: bool = False
    message: str = ""

    def __post_init__(self) -> None:
        if self.status not in INGEST_STATUSES:
            raise ValueError("Unknown event ingest status")
        object.__setattr__(
            self,
            "observed_at",
            _required_datetime(self.observed_at, "observed_at"),
        )
        object.__setattr__(
            self,
            "superseded_event_ids",
            tuple(str(item) for item in self.superseded_event_ids),
        )
        object.__setattr__(
            self,
            "duplicate_event_id",
            _optional_text(self.duplicate_event_id, "duplicate_event_id"),
        )
        object.__setattr__(self, "message", str(self.message or ""))

    def as_policy(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "observed_at": self.observed_at.isoformat(),
            "event": self.event.as_policy() if self.event else None,
            "superseded_event_ids": list(self.superseded_event_ids),
            "duplicate_event_id": self.duplicate_event_id,
            "is_late": self.is_late,
            "message": self.message,
        }


class EventLedger:
    """Append-only ledger with dedupe, explicit correction and PIT replay."""

    def __init__(
        self,
        *,
        schema_version: str = M5_EVENT_SCHEMA,
        namespace: str = NAMESPACE_ACTUAL,
    ) -> None:
        self.schema_version = schema_version
        self.namespace = namespace
        self._events: dict[str, ChangeEvent] = {}
        self._order: list[str] = []
        self._latest_by_key: dict[tuple[str, str, str], str] = {}
        self._last_observed_at: datetime | None = None

    def __len__(self) -> int:
        return len(self._order)

    @property
    def last_observed_at(self) -> datetime | None:
        return self._last_observed_at

    def events(self) -> tuple[ChangeEvent, ...]:
        return tuple(self._events[event_id] for event_id in self._order)

    def active_events(self, symbol: str | None = None) -> tuple[ChangeEvent, ...]:
        events = tuple(
            event for event in self.events() if event.status == EVENT_STATUS_ACTIVE
        )
        if symbol is None:
            return events
        return tuple(event for event in events if event.symbol == symbol)

    def get(self, event_id: str) -> ChangeEvent | None:
        return self._events.get(event_id)

    def latest_for(
        self,
        *,
        symbol: str,
        source_event_id: str,
        source_id: str = LEGACY_EVENT_SOURCE_ID,
    ) -> ChangeEvent | None:
        event_id = self._latest_by_key.get(
            (symbol, _required_text(source_id, "source_id"), source_event_id)
        )
        return self._events.get(event_id) if event_id else None

    def expected_event_id(self, event: ChangeEventInput) -> str:
        """Return the immutable id that this input must have in the ledger."""
        if not isinstance(event, ChangeEventInput):
            raise ValueError("event must be a ChangeEventInput")
        if event.namespace != self.namespace:
            raise ValueError("Event namespace does not match ledger namespace")
        return _compute_event_id(event)

    def ordered_by_available_at(self) -> tuple[ChangeEvent, ...]:
        return tuple(
            sorted(
                self.events(),
                key=lambda event: (
                    event.available_at,
                    event.detected_at,
                    event.sequence,
                ),
            )
        )

    def append(
        self,
        event: ChangeEventInput,
        *,
        observed_at: datetime,
        coverage_watermark: "ScanWatermark | None" = None,
    ) -> EventIngestResult:
        observed_at = _required_datetime(observed_at, "observed_at")
        if event.namespace != self.namespace:
            raise ValueError("Event namespace does not match ledger namespace")
        if self._last_observed_at and observed_at < self._last_observed_at:
            return EventIngestResult(
                status=INGEST_OBSERVED_TIME_REGRESSION_REJECTED,
                observed_at=observed_at,
                event=None,
                message="Observed processing time cannot move backwards",
            )
        if event.available_at > observed_at or event.detected_at > observed_at:
            return EventIngestResult(
                status=INGEST_FUTURE_REJECTED,
                observed_at=observed_at,
                event=None,
                message="Event is not available or detected at the observed time",
            )

        key = event.dedupe_key
        existing_id = self._latest_by_key.get(key)
        existing = self._events.get(existing_id) if existing_id else None
        target_id = event.correction_of_event_id or event.supersedes_event_id
        superseded: tuple[str, ...] = ()

        if existing is not None:
            if existing.source_fingerprint == event.source_fingerprint:
                return EventIngestResult(
                    status=INGEST_DUPLICATE,
                    observed_at=observed_at,
                    event=existing,
                    duplicate_event_id=existing.event_id,
                    message="Exact event already exists in the ledger",
                )
            if target_id is None or target_id != existing.event_id:
                return EventIngestResult(
                    status=INGEST_CONFLICT_REJECTED,
                    observed_at=observed_at,
                    event=None,
                    message="Changed source event requires an explicit correction link",
                )

        event_id = _compute_event_id(event)
        if event_id in self._events:
            return EventIngestResult(
                status=INGEST_CONFLICT_REJECTED,
                observed_at=observed_at,
                event=None,
                message="Computed event id already exists in the ledger",
            )

        if target_id is not None:
            target = self._events.get(target_id)
            if (
                target is None
                or target.symbol != event.symbol
                or target.status != EVENT_STATUS_ACTIVE
                or (
                    event.correction_of_event_id is not None
                    and (
                        target.source_id != event.source_id
                        or target.source_event_id != event.source_event_id
                    )
                )
            ):
                return EventIngestResult(
                    status=INGEST_CONFLICT_REJECTED,
                    observed_at=observed_at,
                    event=None,
                    message="Correction or supersede target is missing, mismatched or inactive",
                )
            superseded = (target.event_id,)
            self._replace_event(target, replace(target, status=EVENT_STATUS_SUPERSEDED))

        sequence = len(self._order) + 1
        accepted = ChangeEvent.from_input(
            event,
            event_id=event_id,
            sequence=sequence,
            ingested_at=observed_at,
        )
        self._events[event_id] = accepted
        self._order.append(event_id)
        self._latest_by_key[key] = event_id
        self._last_observed_at = observed_at
        is_late = bool(
            coverage_watermark is not None
            and event.available_at <= coverage_watermark.coverage_through
        )
        if event.correction_of_event_id:
            status = INGEST_CORRECTION_ACCEPTED
        elif event.supersedes_event_id:
            status = INGEST_SUPERSEDES_ACCEPTED
        else:
            status = INGEST_ACCEPTED
        return EventIngestResult(
            status=status,
            observed_at=observed_at,
            event=accepted,
            superseded_event_ids=superseded,
            is_late=is_late,
            message="Late event accepted with historical ordering preserved"
            if is_late
            else "Event accepted",
        )

    def _replace_event(self, old: ChangeEvent, new: ChangeEvent) -> None:
        if old.event_id != new.event_id:
            raise ValueError("Event replacement must preserve event_id")
        self._events[old.event_id] = new

    def as_policy(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "namespace": self.namespace,
            "last_observed_at": (
                self._last_observed_at.isoformat() if self._last_observed_at else None
            ),
            "events": [event.as_policy() for event in self.events()],
        }

    def to_json(self) -> str:
        return json.dumps(
            self.as_policy(),
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        )


def _change_event_from_payload(payload: Mapping[str, Any]) -> ChangeEvent:
    if not isinstance(payload, Mapping):
        raise ValueError("Event must be an object")
    data = dict(payload)
    has_source_id = "source_id" in data
    has_identity_version = "event_identity_version" in data
    identity_version = (
        _required_text(
            data["event_identity_version"],
            "event_identity_version",
        )
        if has_identity_version
        else (
            EVENT_IDENTITY_SOURCE_ID_V1
            if has_source_id
            else EVENT_IDENTITY_LEGACY
        )
    )
    if identity_version not in EVENT_IDENTITY_VERSIONS:
        raise ValueError("Unknown event identity version")
    if identity_version == EVENT_IDENTITY_LEGACY:
        if has_source_id:
            raise ValueError(
                "Legacy event identity cannot include source_id"
            )
    elif not has_source_id:
        raise ValueError(
            "Versioned event identity requires source_id"
        )
    event = ChangeEvent(
        event_id=_required_text(data["event_id"], "event_id"),
        source_event_id=_required_text(data["source_event_id"], "source_event_id"),
        source_id=_required_text(
            data.get("source_id", LEGACY_EVENT_SOURCE_ID),
            "source_id",
        ),
        symbol=_required_text(data["symbol"], "symbol"),
        event_type=_required_text(data["event_type"], "event_type"),
        detected_at=_required_datetime(
            datetime.fromisoformat(str(data["detected_at"])),
            "detected_at",
        ),
        available_at=_required_datetime(
            datetime.fromisoformat(str(data["available_at"])),
            "available_at",
        ),
        effective_at=(
            _required_datetime(
                datetime.fromisoformat(str(data["effective_at"])),
                "effective_at",
            )
            if data.get("effective_at")
            else None
        ),
        previous_state=_freeze_state(data.get("previous_state", {}), "previous_state"),
        current_state=_freeze_state(data.get("current_state", {}), "current_state"),
        severity=_required_text(data["severity"], "severity"),
        reason=_required_text(data["reason"], "reason"),
        evidence_refs=_required_refs(data.get("evidence_refs")),
        confidence=_required_text(data["confidence"], "confidence"),
        requires_human_review=_required_bool(
            data["requires_human_review"],
            "requires_human_review",
        ),
        correction_of_event_id=_optional_text(
            data.get("correction_of_event_id"),
            "correction_of_event_id",
        ),
        supersedes_event_id=_optional_text(
            data.get("supersedes_event_id"),
            "supersedes_event_id",
        ),
        namespace=_required_text(data["namespace"], "namespace"),
        action=str(data.get("action", ACTION_NO_ORDER)),
        status=_required_text(data["status"], "status"),
        ingested_at=_required_datetime(
            datetime.fromisoformat(str(data["ingested_at"])),
            "ingested_at",
        ),
        sequence=_positive_int(data["sequence"], "sequence"),
        event_identity_version=identity_version,
    )
    expected_fingerprint = event.input.source_fingerprint
    if identity_version == EVENT_IDENTITY_LEGACY:
        if not event.requires_human_review:
            raise ValueError("Legacy event payload must require human review")
        if event.effective_at not in {None, event.available_at}:
            raise ValueError(
                "Legacy event effective_at must equal its available_at"
            )
    expected_id = "m5-" + _digest("event-id", expected_fingerprint)[:32]
    if event.event_id != expected_id:
        raise ValueError("Event id does not match its immutable payload")
    return event


def event_ledger_from_payload(payload: Mapping[str, Any]) -> EventLedger:
    if not isinstance(payload, Mapping):
        raise ValueError("Event ledger must be an object")
    data = dict(payload)
    if data.get("schema_version") != M5_EVENT_SCHEMA:
        raise ValueError("Unknown event ledger schema")
    ledger = EventLedger(
        schema_version=str(data["schema_version"]),
        namespace=_required_text(data.get("namespace", NAMESPACE_ACTUAL), "namespace"),
    )
    expected_sequence = 0
    for raw_event in data.get("events") or ():
        event = _change_event_from_payload(raw_event)
        if event.namespace != ledger.namespace:
            raise ValueError("Event namespace does not match ledger namespace")
        expected_sequence += 1
        if event.sequence != expected_sequence:
            raise ValueError("Event ledger sequence is not contiguous")
        if event.event_id in ledger._events:
            raise ValueError("Event ledger contains a duplicate event_id")
        ledger._events[event.event_id] = event
        ledger._order.append(event.event_id)
        ledger._latest_by_key[
            (event.symbol, event.source_id, event.source_event_id)
        ] = event.event_id
    if data.get("last_observed_at"):
        ledger._last_observed_at = _required_datetime(
            datetime.fromisoformat(str(data["last_observed_at"])),
            "last_observed_at",
        )
    _validate_serialized_event_ledger(ledger, data)
    return ledger


def _validate_serialized_event_ledger(
    ledger: EventLedger,
    payload: Mapping[str, Any],
) -> None:
    """Validate replay integrity that is implicit while appending incrementally."""

    events = ledger.events()
    successors_by_target: dict[str, list[str]] = {}
    event_ids_by_key: dict[tuple[str, str, str], list[str]] = {}
    previous_ingested_at: datetime | None = None

    for event in events:
        if previous_ingested_at is not None and event.ingested_at < previous_ingested_at:
            raise ValueError("Event ledger ingested_at cannot move backwards")
        if event.detected_at > event.ingested_at or event.available_at > event.ingested_at:
            raise ValueError("Event ledger contains an event not available at ingestion")
        event_ids_by_key.setdefault(
            (event.symbol, event.source_id, event.source_event_id),
            [],
        ).append(event.event_id)

        target_id = event.correction_of_event_id or event.supersedes_event_id
        if target_id is not None:
            target = ledger.get(target_id)
            if target is None:
                raise ValueError(
                    "Event ledger correction or supersede target is missing"
                )
            if target.sequence >= event.sequence:
                raise ValueError(
                    "Event ledger correction or supersede target must precede its successor"
                )
            if target.symbol != event.symbol:
                raise ValueError(
                    "Event ledger correction or supersede target symbol mismatch"
                )
            if (
                event.correction_of_event_id is not None
                and (
                    target.source_id != event.source_id
                    or target.source_event_id != event.source_event_id
                )
            ):
                raise ValueError(
                    "Event ledger correction target source identity mismatch"
                )
            successors_by_target.setdefault(target_id, []).append(event.event_id)
        previous_ingested_at = event.ingested_at

    for target_id, successor_ids in successors_by_target.items():
        if len(successor_ids) != 1:
            raise ValueError("Event ledger target has multiple successors")
        target = ledger.get(target_id)
        if target is None or target.status != EVENT_STATUS_SUPERSEDED:
            raise ValueError("Event ledger target status is not superseded")

    for event in events:
        is_target = event.event_id in successors_by_target
        if event.status == EVENT_STATUS_SUPERSEDED and not is_target:
            raise ValueError("Superseded event is missing a successor")
        if event.status == EVENT_STATUS_ACTIVE and is_target:
            raise ValueError("Active event cannot be a correction or supersede target")

    for event_ids in event_ids_by_key.values():
        if any(
            ledger.get(event_id).status != EVENT_STATUS_SUPERSEDED
            for event_id in event_ids[:-1]
        ):
            raise ValueError(
                "Event ledger earlier version for a source event must be superseded"
            )

    if events:
        serialized_last = payload.get("last_observed_at")
        if not serialized_last:
            raise ValueError("Event ledger must record last_observed_at")
        last_observed_at = _required_datetime(
            datetime.fromisoformat(str(serialized_last)),
            "last_observed_at",
        )
        if last_observed_at != events[-1].ingested_at:
            raise ValueError(
                "Event ledger last_observed_at does not match the final accepted event"
            )
    elif payload.get("last_observed_at") is not None:
        raise ValueError("Empty event ledger cannot record last_observed_at")
