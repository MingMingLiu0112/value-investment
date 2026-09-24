"""Human materiality decisions for discovered disclosures.

The event scanner discovers and deduplicates announcements. This contract keeps
the final materiality verdict separate so a title-based rule can never silently
become a valuation fact. It deliberately has no trade semantics.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
import json
import re
from typing import Any, Mapping


EVENT_MATERIALITY_SCHEMA = "post-m1-event-materiality-v1"
ACTION_NO_ORDER = "no_order"
REVIEWER_HUMAN_RESEARCH_LEAD = "human_research_lead"

DECISION_NOT_MATERIAL = "NOT_MATERIAL"
DECISION_SUPPORTING = "MATERIAL_SUPPORTING_EVIDENCE"
DECISION_ALREADY_INCORPORATED = "MATERIAL_ALREADY_INCORPORATED"
DECISION_REQUIRES_RECALCULATION = "MATERIAL_REQUIRES_RECALCULATION"
DECISION_RISK_MONITOR = "MATERIAL_RISK_MONITOR"
DECISION_DUPLICATE = "DUPLICATE_OR_DERIVED"
DECISION_REQUIRES_DECOMPOSITION = "REQUIRES_DECOMPOSITION"

MATERIALITY_DECISIONS = {
    DECISION_NOT_MATERIAL,
    DECISION_SUPPORTING,
    DECISION_ALREADY_INCORPORATED,
    DECISION_REQUIRES_RECALCULATION,
    DECISION_RISK_MONITOR,
    DECISION_DUPLICATE,
    DECISION_REQUIRES_DECOMPOSITION,
}

_SYMBOL = re.compile(r"^[0-9]{6}$")
_ANNOUNCEMENT_ID = re.compile(r"^[0-9]+$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _require_refs(
    refs: tuple[dict[str, Any], ...],
) -> tuple[dict[str, Any], ...]:
    normalized = tuple(dict(ref) for ref in refs)
    if any(not ref.get("id") for ref in normalized):
        raise ValueError("Materiality evidence references require ids")
    return normalized


@dataclass(frozen=True)
class EventMaterialityDecision:
    """One human classification bound to one source PDF and announcement id."""

    event_decision_id: str
    symbol: str
    announcement_id: str
    title: str
    published_at: datetime

    source_ref: dict[str, Any]
    source_sha256: str

    machine_candidate_reason: str
    human_decision: str

    affected_domains: tuple[str, ...]
    affected_fact_fields: tuple[str, ...]
    affected_assumptions: tuple[str, ...]
    affected_artifacts: tuple[str, ...]

    requires_recalculation: bool
    requires_model_stale: bool
    requires_followup: bool

    supersedes_event_id: str | None = None
    event_cluster_id: str | None = None

    reviewed_at: datetime | None = None
    reviewer_type: str = REVIEWER_HUMAN_RESEARCH_LEAD
    review_notes: tuple[str, ...] = ()
    decision_version: str = "20260923.1"
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        for field in (
            "event_decision_id",
            "symbol",
            "announcement_id",
            "title",
            "machine_candidate_reason",
            "decision_version",
        ):
            if not getattr(self, field).strip():
                raise ValueError(f"Event materiality {field} is required")
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("Event materiality symbol must contain six digits")
        if not _ANNOUNCEMENT_ID.fullmatch(self.announcement_id):
            raise ValueError("Announcement id must contain digits only")
        if not isinstance(self.published_at, datetime) or self.published_at.tzinfo is None:
            raise ValueError("Event published_at must include timezone")
        if self.reviewed_at is not None and (
            not isinstance(self.reviewed_at, datetime)
            or self.reviewed_at.tzinfo is None
        ):
            raise ValueError("Event reviewed_at must include timezone")
        if self.human_decision not in MATERIALITY_DECISIONS:
            raise ValueError("Unknown event materiality decision")
        if self.reviewer_type != REVIEWER_HUMAN_RESEARCH_LEAD:
            raise ValueError("Only a human research lead can classify an event")
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Event materiality decision must remain no_order")
        if not _SHA256.fullmatch(self.source_sha256):
            raise ValueError("Event source hash must be SHA-256 hex")
        object.__setattr__(self, "source_sha256", self.source_sha256.lower())
        source_sha256 = self.source_ref.get("sha256")
        if source_sha256 is not None and str(source_sha256).lower() != self.source_sha256:
            raise ValueError("Event source hash must match source_ref.sha256")
        if not self.source_ref.get("id"):
            raise ValueError("Event source reference requires an id")
        object.__setattr__(self, "source_ref", dict(self.source_ref))
        object.__setattr__(
            self,
            "affected_domains",
            tuple(str(item) for item in self.affected_domains),
        )
        object.__setattr__(
            self,
            "affected_fact_fields",
            tuple(str(item) for item in self.affected_fact_fields),
        )
        object.__setattr__(
            self,
            "affected_assumptions",
            tuple(str(item) for item in self.affected_assumptions),
        )
        object.__setattr__(
            self,
            "affected_artifacts",
            tuple(str(item) for item in self.affected_artifacts),
        )
        object.__setattr__(
            self,
            "review_notes",
            tuple(str(item) for item in self.review_notes),
        )

        expected_stale = self.human_decision == DECISION_REQUIRES_RECALCULATION
        expected_recalc = expected_stale
        expected_followup = self.human_decision in {
            DECISION_RISK_MONITOR,
            DECISION_REQUIRES_DECOMPOSITION,
        }
        if self.requires_recalculation != expected_recalc:
            raise ValueError("requires_recalculation conflicts with the decision")
        if self.requires_model_stale != expected_stale:
            raise ValueError("requires_model_stale conflicts with the decision")
        if self.requires_followup != expected_followup:
            raise ValueError("requires_followup conflicts with the decision")
        if (
            self.human_decision == DECISION_DUPLICATE
            and not self.event_cluster_id
            and not self.supersedes_event_id
        ):
            raise ValueError("Duplicate events require a primary cluster or source id")
        if self.supersedes_event_id is not None and not _ANNOUNCEMENT_ID.fullmatch(
            self.supersedes_event_id
        ):
            raise ValueError("Superseded event id must contain digits only")

    def as_policy(self) -> dict[str, Any]:
        return {
            "schema_version": EVENT_MATERIALITY_SCHEMA,
            "event_decision_id": self.event_decision_id,
            "symbol": self.symbol,
            "announcement_id": self.announcement_id,
            "title": self.title,
            "published_at": self.published_at.isoformat(),
            "source_ref": dict(self.source_ref),
            "source_sha256": self.source_sha256,
            "machine_candidate_reason": self.machine_candidate_reason,
            "human_decision": self.human_decision,
            "affected_domains": list(self.affected_domains),
            "affected_fact_fields": list(self.affected_fact_fields),
            "affected_assumptions": list(self.affected_assumptions),
            "affected_artifacts": list(self.affected_artifacts),
            "requires_recalculation": self.requires_recalculation,
            "requires_model_stale": self.requires_model_stale,
            "requires_followup": self.requires_followup,
            "supersedes_event_id": self.supersedes_event_id,
            "event_cluster_id": self.event_cluster_id,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "reviewer_type": self.reviewer_type,
            "review_notes": list(self.review_notes),
            "decision_version": self.decision_version,
            "action": self.action,
        }


@dataclass(frozen=True)
class EventMaterialityReview:
    """Coverage-watermarked review of one company event-scan batch."""

    review_id: str
    schema_version: str
    symbol: str
    scan_id: str
    scan_sha256: str
    scan_from: date
    scan_to: date
    reviewed_at: datetime
    review_as_of: date
    reviewer_type: str
    decisions: tuple[EventMaterialityDecision, ...]
    evidence_refs: tuple[dict[str, Any], ...]
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        if self.schema_version != EVENT_MATERIALITY_SCHEMA:
            raise ValueError("Unknown event materiality review schema")
        if not self.review_id.strip() or not self.symbol.strip():
            raise ValueError("Event materiality review id and symbol are required")
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("Event materiality review symbol must contain six digits")
        if not self.scan_id.strip():
            raise ValueError("Event materiality review requires a scan id")
        if not _SHA256.fullmatch(self.scan_sha256):
            raise ValueError("Event scan hash must be SHA-256 hex")
        object.__setattr__(self, "scan_sha256", self.scan_sha256.lower())
        if self.scan_to < self.scan_from:
            raise ValueError("Event scan window cannot end before it starts")
        if self.scan_to > self.review_as_of:
            raise ValueError("Event scan window cannot extend beyond the review date")
        if self.review_as_of < self.scan_from:
            raise ValueError("Event review date cannot precede the scan window")
        if self.reviewed_at.tzinfo is None:
            raise ValueError("Event review timestamp must include timezone")
        if self.review_as_of != self.reviewed_at.date():
            raise ValueError("Event review timestamp must match review_as_of")
        if self.reviewer_type != REVIEWER_HUMAN_RESEARCH_LEAD:
            raise ValueError("Only a human research lead can review events")
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Event materiality review must remain no_order")
        if not self.decisions:
            raise ValueError("Event materiality review requires decisions")
        if any(item.symbol != self.symbol for item in self.decisions):
            raise ValueError("Every event decision must match the review symbol")
        if any(
            item.reviewed_at is not None and item.reviewed_at > self.reviewed_at
            for item in self.decisions
        ):
            raise ValueError("Event decision time cannot follow the review time")
        ids = [item.announcement_id for item in self.decisions]
        if len(ids) != len(set(ids)):
            raise ValueError("Event review contains a duplicate announcement id")
        object.__setattr__(
            self,
            "evidence_refs",
            _require_refs(tuple(self.evidence_refs)),
        )

    @property
    def coverage_watermark(self) -> date:
        return self.scan_to

    @property
    def recalculation_decisions(self) -> tuple[EventMaterialityDecision, ...]:
        return tuple(
            item
            for item in self.decisions
            if item.human_decision == DECISION_REQUIRES_RECALCULATION
        )

    @property
    def decomposition_decisions(self) -> tuple[EventMaterialityDecision, ...]:
        return tuple(
            item
            for item in self.decisions
            if item.human_decision == DECISION_REQUIRES_DECOMPOSITION
        )

    @property
    def monitored_risk_decisions(self) -> tuple[EventMaterialityDecision, ...]:
        return tuple(
            item
            for item in self.decisions
            if item.human_decision == DECISION_RISK_MONITOR
        )

    @property
    def has_unresolved_recalculation(self) -> bool:
        return bool(self.recalculation_decisions)

    @property
    def has_unresolved_decomposition(self) -> bool:
        return bool(self.decomposition_decisions)

    @property
    def review_blockers(self) -> tuple[str, ...]:
        blockers: list[str] = []
        if self.has_unresolved_recalculation:
            blockers.extend(
                f"event_requires_recalculation:{item.announcement_id}"
                for item in self.recalculation_decisions
            )
        if self.has_unresolved_decomposition:
            blockers.extend(
                f"event_requires_decomposition:{item.announcement_id}"
                for item in self.decomposition_decisions
            )
        if self.monitored_risk_decisions:
            blockers.extend(
                f"event_risk_monitor:{item.announcement_id}"
                for item in self.monitored_risk_decisions
            )
        return tuple(blockers)

    def covers(self, decision_as_of: date) -> bool:
        return self.coverage_watermark >= decision_as_of

    def as_policy(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "review_id": self.review_id,
            "symbol": self.symbol,
            "scan_id": self.scan_id,
            "scan_sha256": self.scan_sha256,
            "scan_from": self.scan_from.isoformat(),
            "scan_to": self.scan_to.isoformat(),
            "reviewed_at": self.reviewed_at.isoformat(),
            "review_as_of": self.review_as_of.isoformat(),
            "reviewer_type": self.reviewer_type,
            "coverage_watermark": self.coverage_watermark.isoformat(),
            "decisions": [item.as_policy() for item in self.decisions],
            "evidence_refs": [dict(ref) for ref in self.evidence_refs],
            "action": self.action,
        }

    def to_json(self) -> str:
        return json.dumps(
            self.as_policy(),
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        )


def _date(value: object, field: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{field} must be an ISO date") from error


def _datetime(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO timestamp")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed


def event_materiality_decision_from_payload(
    payload: Mapping[str, Any],
) -> EventMaterialityDecision:
    if not isinstance(payload, Mapping):
        raise ValueError("Event materiality decision must be an object")
    data = dict(payload)
    if data.get("schema_version") != EVENT_MATERIALITY_SCHEMA:
        raise ValueError("Unknown event materiality decision schema")
    return EventMaterialityDecision(
        event_decision_id=str(data["event_decision_id"]),
        symbol=str(data["symbol"]),
        announcement_id=str(data["announcement_id"]),
        title=str(data["title"]),
        published_at=_datetime(data["published_at"], "published_at"),
        source_ref=dict(data["source_ref"]),
        source_sha256=str(data["source_sha256"]),
        machine_candidate_reason=str(data["machine_candidate_reason"]),
        human_decision=str(data["human_decision"]),
        affected_domains=tuple(str(item) for item in data.get("affected_domains") or ()),
        affected_fact_fields=tuple(
            str(item) for item in data.get("affected_fact_fields") or ()
        ),
        affected_assumptions=tuple(
            str(item) for item in data.get("affected_assumptions") or ()
        ),
        affected_artifacts=tuple(
            str(item) for item in data.get("affected_artifacts") or ()
        ),
        requires_recalculation=bool(data["requires_recalculation"]),
        requires_model_stale=bool(data["requires_model_stale"]),
        requires_followup=bool(data["requires_followup"]),
        supersedes_event_id=(
            str(data["supersedes_event_id"])
            if data.get("supersedes_event_id") is not None
            else None
        ),
        event_cluster_id=(
            str(data["event_cluster_id"])
            if data.get("event_cluster_id") is not None
            else None
        ),
        reviewed_at=(
            _datetime(data["reviewed_at"], "reviewed_at")
            if data.get("reviewed_at") is not None
            else None
        ),
        reviewer_type=str(data.get("reviewer_type", REVIEWER_HUMAN_RESEARCH_LEAD)),
        review_notes=tuple(str(item) for item in data.get("review_notes") or ()),
        decision_version=str(data.get("decision_version", "20260923.1")),
        action=str(data.get("action", ACTION_NO_ORDER)),
    )


def event_materiality_review_from_payload(
    payload: Mapping[str, Any],
) -> EventMaterialityReview:
    if not isinstance(payload, Mapping):
        raise ValueError("Event materiality review must be an object")
    data = dict(payload)
    if data.get("schema_version") != EVENT_MATERIALITY_SCHEMA:
        raise ValueError("Unknown event materiality review schema")
    return EventMaterialityReview(
        review_id=str(data["review_id"]),
        schema_version=str(data["schema_version"]),
        symbol=str(data["symbol"]),
        scan_id=str(data["scan_id"]),
        scan_sha256=str(data["scan_sha256"]),
        scan_from=_date(data["scan_from"], "scan_from"),
        scan_to=_date(data["scan_to"], "scan_to"),
        reviewed_at=_datetime(data["reviewed_at"], "reviewed_at"),
        review_as_of=_date(data["review_as_of"], "review_as_of"),
        reviewer_type=str(data["reviewer_type"]),
        decisions=tuple(
            event_materiality_decision_from_payload(item)
            for item in data.get("decisions") or ()
        ),
        evidence_refs=tuple(dict(item) for item in data.get("evidence_refs") or ()),
        action=str(data.get("action", ACTION_NO_ORDER)),
    )
