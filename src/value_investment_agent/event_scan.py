"""Point-in-time event-scan evidence contract for model validity.

The contract deliberately separates two questions:

1. Does the bridge window from model_as_of through quote_date contain a
   rule-flagged material disclosure?
2. Are there earlier disclosures that should be reviewed before the model
   inputs are treated as a complete research basis?

A completed no-material-event bridge window never proves that pre-model
disclosures were incorporated into the valuation.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import re
from typing import Any, Mapping, Sequence


EVENT_SCAN_SCHEMA = "m1-event-scan-v1"

SCAN_COMPLETE_NO_MATERIAL_EVENT = (
    "COMPLETE_NO_MATERIAL_EVENT_IN_VALIDITY_WINDOW"
)
SCAN_COMPLETE_MATERIAL_EVENTS = (
    "COMPLETE_MATERIAL_EVENTS_IN_VALIDITY_WINDOW"
)
SCAN_PENDING_HUMAN_REVIEW = "PENDING_HUMAN_REVIEW"
SCAN_UNKNOWN = "UNKNOWN"
SCAN_STATUSES = {
    SCAN_COMPLETE_NO_MATERIAL_EVENT,
    SCAN_COMPLETE_MATERIAL_EVENTS,
    SCAN_PENDING_HUMAN_REVIEW,
    SCAN_UNKNOWN,
}

COVERAGE_COMPLETE = "COMPLETE"
COVERAGE_INCOMPLETE = "INCOMPLETE"
COVERAGE_STATUSES = {COVERAGE_COMPLETE, COVERAGE_INCOMPLETE}

PRE_MODEL_NONE = "NONE"
PRE_MODEL_PENDING_HUMAN_REVIEW = "PENDING_HUMAN_REVIEW"
PRE_MODEL_REVIEWED_NO_CANDIDATES = "REVIEWED_NO_CANDIDATES"
PRE_MODEL_STATUSES = {
    PRE_MODEL_NONE,
    PRE_MODEL_PENDING_HUMAN_REVIEW,
    PRE_MODEL_REVIEWED_NO_CANDIDATES,
}

REVIEW_PENDING_HUMAN_REVIEW = "PENDING_HUMAN_REVIEW"
REVIEW_REVIEWED_NO_MATERIAL_CANDIDATE = "REVIEWED_NO_MATERIAL_CANDIDATE"
REVIEW_NOT_ASSESSABLE = "NOT_ASSESSABLE"
REVIEW_STATUSES = {
    REVIEW_PENDING_HUMAN_REVIEW,
    REVIEW_REVIEWED_NO_MATERIAL_CANDIDATE,
    REVIEW_NOT_ASSESSABLE,
}


_SYMBOL = re.compile(r"^[0-9]{6}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _require_date(value: object, field: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO date string")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{field} must be an ISO date string") from error


def _require_datetime(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO timestamp string")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed


def _require_refs(value: object, field: str = "evidence_refs") -> tuple[dict[str, Any], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{field} must be a list")
    refs = tuple(dict(item) for item in value)
    if any(not _require_text(ref.get("id"), f"{field}.id") for ref in refs):
        raise ValueError(f"{field} entries require ids")
    return refs


def _iso(value: date | datetime) -> str:
    return value.isoformat()


@dataclass(frozen=True)
class AnnouncementReview:
    """One archived disclosure row plus a bounded rule review state."""

    announcement_id: str
    published_at: datetime
    title: str
    source_url: str
    rule_kind: str
    review_status: str
    materiality_candidate: bool
    pre_model: bool
    evidence_refs: tuple[dict[str, Any], ...]
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "announcement_id",
            _require_text(self.announcement_id, "announcement_id"),
        )
        if not isinstance(self.published_at, datetime):
            raise ValueError("published_at must be a timezone-aware datetime")
        if self.published_at.tzinfo is None:
            raise ValueError("published_at must include a timezone")
        object.__setattr__(self, "title", _require_text(self.title, "title"))
        object.__setattr__(self, "source_url", _require_text(self.source_url, "source_url"))
        object.__setattr__(self, "rule_kind", _require_text(self.rule_kind, "rule_kind"))
        if self.review_status not in REVIEW_STATUSES:
            raise ValueError(f"Unknown announcement review status: {self.review_status}")
        object.__setattr__(
            self,
            "evidence_refs",
            _require_refs(self.evidence_refs),
        )
        object.__setattr__(self, "notes", str(self.notes or ""))

    def as_policy(self) -> dict[str, Any]:
        return {
            "announcement_id": self.announcement_id,
            "published_at": _iso(self.published_at),
            "title": self.title,
            "source_url": self.source_url,
            "rule_kind": self.rule_kind,
            "review_status": self.review_status,
            "materiality_candidate": self.materiality_candidate,
            "pre_model": self.pre_model,
            "evidence_refs": [dict(ref) for ref in self.evidence_refs],
            "notes": self.notes,
        }


def _announcement_from_payload(value: object) -> AnnouncementReview:
    if not isinstance(value, Mapping):
        raise ValueError("event_scan announcement must be an object")
    data = dict(value)
    return AnnouncementReview(
        announcement_id=data["announcement_id"],
        published_at=_require_datetime(
            data["published_at"], "announcement.published_at"
        ),
        title=data["title"],
        source_url=data["source_url"],
        rule_kind=data["rule_kind"],
        review_status=data["review_status"],
        materiality_candidate=bool(data["materiality_candidate"]),
        pre_model=bool(data["pre_model"]),
        evidence_refs=_require_refs(
            data.get("evidence_refs"), "announcement.evidence_refs"
        ),
        notes=str(data.get("notes") or ""),
    )


@dataclass(frozen=True)
class EventScanResult:
    """Hash-pinned provider coverage for one security's disclosure window."""

    schema_version: str
    symbol: str
    provider: str
    scan_from: date
    scan_to: date
    validity_from: date
    validity_to: date
    status: str
    coverage_status: str
    pre_model_review_status: str
    announcements: tuple[AnnouncementReview, ...]
    blockers: tuple[str, ...]
    evidence_refs: tuple[dict[str, Any], ...]
    retrieved_at: datetime
    parser_version: str

    def __post_init__(self) -> None:
        if self.schema_version != EVENT_SCAN_SCHEMA:
            raise ValueError(f"Unknown event-scan schema: {self.schema_version}")
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("Event scan symbol must contain six digits")
        object.__setattr__(self, "provider", _require_text(self.provider, "provider"))
        object.__setattr__(
            self,
            "parser_version",
            _require_text(self.parser_version, "parser_version"),
        )
        if not isinstance(self.scan_from, date) or not isinstance(self.scan_to, date):
            raise ValueError("Event scan boundaries must be dates")
        if self.scan_from > self.scan_to:
            raise ValueError("Event scan cannot start after it ends")
        if not isinstance(self.validity_from, date) or not isinstance(self.validity_to, date):
            raise ValueError("Event validity boundaries must be dates")
        if self.validity_from > self.validity_to:
            raise ValueError("Event validity window cannot start after it ends")
        if self.validity_from < self.scan_from or self.validity_to > self.scan_to:
            raise ValueError("Event validity window must fit inside the scan window")
        if self.status not in SCAN_STATUSES:
            raise ValueError(f"Unknown event scan status: {self.status}")
        if self.coverage_status not in COVERAGE_STATUSES:
            raise ValueError(f"Unknown event coverage status: {self.coverage_status}")
        if self.pre_model_review_status not in PRE_MODEL_STATUSES:
            raise ValueError(
                f"Unknown pre-model review status: {self.pre_model_review_status}"
            )
        if not isinstance(self.retrieved_at, datetime) or self.retrieved_at.tzinfo is None:
            raise ValueError("Event scan retrieved_at must include a timezone")

        object.__setattr__(self, "announcements", tuple(self.announcements))
        announcement_ids = [item.announcement_id for item in self.announcements]
        if len(announcement_ids) != len(set(announcement_ids)):
            raise ValueError("Event scan announcement ids must be unique")
        if any(
            item.published_at.date() < self.scan_from
            or item.published_at.date() > self.scan_to
            for item in self.announcements
        ):
            raise ValueError("Event scan contains an announcement outside its window")
        if any(item.pre_model for item in self.announcements if item.published_at.date() >= self.validity_from):
            raise ValueError("Pre-model flag conflicts with an announcement date")

        object.__setattr__(self, "blockers", tuple(str(item) for item in self.blockers))
        object.__setattr__(self, "evidence_refs", _require_refs(self.evidence_refs))
        validity_candidates = self.validity_material_candidates
        if (
            self.status == SCAN_COMPLETE_NO_MATERIAL_EVENT
            and validity_candidates
        ):
            raise ValueError("No-material-event status cannot contain validity candidates")
        if (
            self.status == SCAN_COMPLETE_MATERIAL_EVENTS
            and not validity_candidates
        ):
            raise ValueError("Material-event status requires a validity candidate")
        if self.coverage_status == COVERAGE_COMPLETE and not self.evidence_refs:
            raise ValueError("Complete event coverage requires retained evidence")

    @property
    def validity_material_candidates(self) -> tuple[AnnouncementReview, ...]:
        return tuple(
            item
            for item in self.announcements
            if item.materiality_candidate and not item.pre_model
        )

    @property
    def pre_model_material_candidates(self) -> tuple[AnnouncementReview, ...]:
        return tuple(
            item
            for item in self.announcements
            if item.materiality_candidate and item.pre_model
        )

    def as_policy(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "symbol": self.symbol,
            "provider": self.provider,
            "scan_from": _iso(self.scan_from),
            "scan_to": _iso(self.scan_to),
            "validity_from": _iso(self.validity_from),
            "validity_to": _iso(self.validity_to),
            "status": self.status,
            "coverage_status": self.coverage_status,
            "pre_model_review_status": self.pre_model_review_status,
            "announcements": [
                item.as_policy() for item in self.announcements
            ],
            "blockers": list(self.blockers),
            "evidence_refs": [dict(ref) for ref in self.evidence_refs],
            "retrieved_at": _iso(self.retrieved_at),
            "parser_version": self.parser_version,
        }


def event_scan_from_payload(value: object) -> EventScanResult:
    if not isinstance(value, Mapping):
        raise ValueError("event_scan must be an object")
    data = dict(value)
    return EventScanResult(
        schema_version=_require_text(data["schema_version"], "schema_version"),
        symbol=_require_text(data["symbol"], "symbol"),
        provider=_require_text(data["provider"], "provider"),
        scan_from=_require_date(data["scan_from"], "scan_from"),
        scan_to=_require_date(data["scan_to"], "scan_to"),
        validity_from=_require_date(data["validity_from"], "validity_from"),
        validity_to=_require_date(data["validity_to"], "validity_to"),
        status=_require_text(data["status"], "status"),
        coverage_status=_require_text(data["coverage_status"], "coverage_status"),
        pre_model_review_status=_require_text(
            data["pre_model_review_status"], "pre_model_review_status"
        ),
        announcements=tuple(
            _announcement_from_payload(item)
            for item in data.get("announcements") or []
        ),
        blockers=tuple(str(item) for item in data.get("blockers") or []),
        evidence_refs=_require_refs(data.get("evidence_refs")),
        retrieved_at=_require_datetime(data["retrieved_at"], "retrieved_at"),
        parser_version=_require_text(data["parser_version"], "parser_version"),
    )


def load_event_scan_payload(
    payload: Mapping[str, Any],
    *,
    root: Any = None,
) -> EventScanResult:
    """Load a hash-pinned event-scan evidence file referenced by a package."""

    if root is None:
        return event_scan_from_payload(payload)
    path = _require_text(payload.get("path"), "event_scan.path")
    expected_sha256 = _require_text(payload.get("sha256"), "event_scan.sha256").lower()
    if not _SHA256.fullmatch(expected_sha256):
        raise ValueError("event_scan.sha256 must be a SHA-256 digest")
    target = (root / path).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError("event_scan path escapes the project root")
    if not target.is_file():
        raise FileNotFoundError(f"event_scan evidence missing: {path}")
    import hashlib

    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    if digest != expected_sha256:
        raise ValueError(f"event_scan evidence hash changed: {path}")
    import json

    result = event_scan_from_payload(json.loads(target.read_text(encoding="utf-8")))
    if result.symbol != payload.get("symbol"):
        raise ValueError("event_scan evidence symbol does not match its reference")
    return result
