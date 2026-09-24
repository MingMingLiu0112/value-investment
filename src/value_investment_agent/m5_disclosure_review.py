"""Fail-closed human-review intake for the real CNINFO M5 disclosure queue.

The queue deliberately stops before materiality. This module converts only
explicit human decisions into the existing EventMaterialityReview contract,
after re-binding the queue fingerprint, archived PDF hash and review clock.
It never supplies a verdict and never creates a change event by itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping

from .event_materiality import (
    ACTION_NO_ORDER,
    DECISION_REQUIRES_DECOMPOSITION,
    DECISION_REQUIRES_RECALCULATION,
    DECISION_RISK_MONITOR,
    MATERIALITY_DECISIONS,
    REVIEWER_HUMAN_RESEARCH_LEAD,
    EventMaterialityDecision,
    EventMaterialityReview,
)
from .event_scan import COVERAGE_COMPLETE
from .m5_disclosure_queue import (
    SOURCE_ARCHIVED,
    DisclosureReviewQueue,
)


DISCLOSURE_REVIEW_INTAKE_SCHEMA = "m5-disclosure-review-intake-v1"
DECISION_VERSION = "20260924.1"
CN_TZ = timezone(timedelta(hours=8))

_SYMBOL = re.compile(r"^[0-9]{6}$")
_ANNOUNCEMENT_ID = re.compile(r"^[0-9]+$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TAG_SPLIT = re.compile(r"[,，;；\n]+")

RECOMMENDED_DOMAIN_TAGS = (
    "balance_sheet_risk",
    "income_statement_risk",
    "cash_flow_risk",
    "lease",
    "minority_interest",
    "investment",
    "goodwill",
    "debt",
    "tax",
    "dividend",
    "distribution",
    "buyback",
    "business_model",
    "competitive_position",
    "portfolio_risk",
    "concentration",
    "position",
    "model",
    "entry",
)
RECOMMENDED_ARTIFACT_TAGS = (
    "valuation_result",
    "model_validity",
    "research_thesis",
    "entry",
    "decision_review",
)


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _optional_text(value: object, field: str) -> str | None:
    if value is None or value == "":
        return None
    return _text(value, field)


def _tags(value: object, field: str) -> tuple[str, ...]:
    if value is None or value == "":
        return ()
    if not isinstance(value, str):
        raise ValueError(f"{field} must be text")
    values = tuple(item.strip() for item in _TAG_SPLIT.split(value) if item.strip())
    if len(values) != len(set(values)):
        raise ValueError(f"{field} contains duplicate tags")
    return values


def _notes(value: object, field: str) -> tuple[str, ...]:
    if isinstance(value, str):
        values = tuple(line.strip() for line in value.splitlines() if line.strip())
    else:
        values = tuple(str(item).strip() for item in value if str(item).strip())
    if not values:
        raise ValueError(f"{field} is required")
    return values


def disclosure_queue_sha256(queue: DisclosureReviewQueue) -> str:
    payload = json.dumps(
        queue.as_policy(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DisclosureReviewDecisionInput:
    """One explicit human decision keyed to one pending queue candidate."""

    announcement_id: str
    symbol: str
    human_decision: str
    affected_domains: tuple[str, ...] = ()
    affected_fact_fields: tuple[str, ...] = ()
    affected_assumptions: tuple[str, ...] = ()
    affected_artifacts: tuple[str, ...] = ()
    review_notes: tuple[str, ...] = ()
    supersedes_event_id: str | None = None
    event_cluster_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "announcement_id", _text(self.announcement_id, "announcement id"))
        if not _ANNOUNCEMENT_ID.fullmatch(self.announcement_id):
            raise ValueError("Announcement id must contain digits only")
        object.__setattr__(self, "symbol", _text(self.symbol, "symbol"))
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("Symbol must contain six digits")
        if self.human_decision not in MATERIALITY_DECISIONS:
            raise ValueError("Unknown materiality decision")
        object.__setattr__(self, "human_decision", self.human_decision)
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
        object.__setattr__(self, "review_notes", _notes(self.review_notes, "review notes"))
        object.__setattr__(
            self,
            "supersedes_event_id",
            _optional_text(self.supersedes_event_id, "supersedes event id"),
        )
        object.__setattr__(
            self,
            "event_cluster_id",
            _optional_text(self.event_cluster_id, "event cluster id"),
        )

    @property
    def key(self) -> tuple[str, str]:
        return self.symbol, self.announcement_id

    def as_policy(self) -> dict[str, Any]:
        return {
            "announcement_id": self.announcement_id,
            "symbol": self.symbol,
            "human_decision": self.human_decision,
            "affected_domains": list(self.affected_domains),
            "affected_fact_fields": list(self.affected_fact_fields),
            "affected_assumptions": list(self.affected_assumptions),
            "affected_artifacts": list(self.affected_artifacts),
            "review_notes": list(self.review_notes),
            "supersedes_event_id": self.supersedes_event_id,
            "event_cluster_id": self.event_cluster_id,
        }


def disclosure_review_decision_input_from_payload(
    value: Mapping[str, Any],
) -> DisclosureReviewDecisionInput:
    if not isinstance(value, Mapping):
        raise ValueError("Disclosure review decision must be an object")
    data = dict(value)
    return DisclosureReviewDecisionInput(
        announcement_id=str(data["announcement_id"]),
        symbol=str(data["symbol"]),
        human_decision=str(data["human_decision"]),
        affected_domains=tuple(str(item) for item in data.get("affected_domains") or ()),
        affected_fact_fields=tuple(str(item) for item in data.get("affected_fact_fields") or ()),
        affected_assumptions=tuple(str(item) for item in data.get("affected_assumptions") or ()),
        affected_artifacts=tuple(str(item) for item in data.get("affected_artifacts") or ()),
        review_notes=tuple(str(item) for item in data.get("review_notes") or ()),
        supersedes_event_id=data.get("supersedes_event_id"),
        event_cluster_id=data.get("event_cluster_id"),
    )


@dataclass(frozen=True)
class DisclosureReviewIntake:
    """Queue-bound human review input set. It contains no materiality verdict."""

    schema_version: str
    queue_id: str
    queue_sha256: str
    reviewed_at: datetime
    decisions: tuple[DisclosureReviewDecisionInput, ...]
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        if self.schema_version != DISCLOSURE_REVIEW_INTAKE_SCHEMA:
            raise ValueError("Unknown disclosure review intake schema")
        if not self.queue_id.strip():
            raise ValueError("Disclosure review intake requires a queue id")
        if not _SHA256.fullmatch(self.queue_sha256):
            raise ValueError("Disclosure review intake queue hash must be SHA-256")
        object.__setattr__(self, "queue_sha256", self.queue_sha256.lower())
        if not isinstance(self.reviewed_at, datetime) or self.reviewed_at.tzinfo is None:
            raise ValueError("Disclosure review reviewed_at must include timezone")
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Disclosure review intake must remain no_order")
        if not self.decisions:
            raise ValueError("Disclosure review intake requires decisions")
        keys = [item.key for item in self.decisions]
        if len(keys) != len(set(keys)):
            raise ValueError("Disclosure review intake contains duplicate decisions")
        object.__setattr__(self, "decisions", tuple(self.decisions))

    def by_key(self) -> dict[tuple[str, str], DisclosureReviewDecisionInput]:
        return {item.key: item for item in self.decisions}

    def as_policy(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "queue_id": self.queue_id,
            "queue_sha256": self.queue_sha256,
            "reviewed_at": self.reviewed_at.isoformat(),
            "decisions": [item.as_policy() for item in self.decisions],
            "action": self.action,
        }

    def to_json(self) -> str:
        return json.dumps(
            self.as_policy(),
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        )


def disclosure_review_intake_from_payload(
    value: Mapping[str, Any],
) -> DisclosureReviewIntake:
    if not isinstance(value, Mapping):
        raise ValueError("Disclosure review intake must be an object")
    data = dict(value)
    return DisclosureReviewIntake(
        schema_version=str(data["schema_version"]),
        queue_id=str(data["queue_id"]),
        queue_sha256=str(data["queue_sha256"]),
        reviewed_at=datetime.fromisoformat(str(data["reviewed_at"])),
        decisions=tuple(
            disclosure_review_decision_input_from_payload(item)
            for item in data.get("decisions") or ()
        ),
        action=str(data.get("action", ACTION_NO_ORDER)),
    )


def _archived_pdf_ref(candidate: Any) -> dict[str, Any]:
    refs = [
        dict(ref)
        for ref in candidate.evidence_refs
        if ref.get("source_status") == SOURCE_ARCHIVED
        or str(ref.get("path") or "").lower().endswith(".pdf")
        or "-pdf-" in str(ref.get("id") or "")
    ]
    if len(refs) != 1:
        raise ArchivedPdfVerificationError(
            "Candidate must have exactly one PDF reference: "
            f"{candidate.announcement_id}; found={len(refs)}",
            reason="archive_reference_ambiguous",
        )
    ref = refs[0]
    if ref.get("source_status") != SOURCE_ARCHIVED:
        raise ArchivedPdfVerificationError(
            f"Candidate PDF is not archived: {candidate.announcement_id}",
            reason="archive_not_archived",
        )
    return ref


class ArchivedPdfVerificationError(ValueError):
    """A fail-closed source-archive verification failure."""

    def __init__(
        self,
        message: str,
        *,
        reason: str,
        actual_sha256: str | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.actual_sha256 = actual_sha256


def _assert_no_link_components(root: Path, relative_path: Path) -> None:
    current = root
    for part in relative_path.parts:
        current = current / part
        if current.is_symlink() or (
            hasattr(os.path, "isjunction") and os.path.isjunction(current)
        ):
            raise ArchivedPdfVerificationError(
                f"Candidate PDF path contains a link: {relative_path}",
                reason="archive_path_link",
            )


def verify_archived_pdf(
    candidate: Any,
    *,
    archive_root: Path,
    symbol: str,
) -> tuple[dict[str, Any], str]:
    """Recompute the archived PDF digest before a human decision is converted.

    The queue is an input, not a trust root. A recorded digest is accepted only
    when the referenced regular PDF is still inside the supplied archive root
    and its current bytes reproduce that digest.
    """

    ref = _archived_pdf_ref(candidate)
    if not _SYMBOL.fullmatch(symbol):
        raise ValueError("Archive verification symbol must contain six digits")
    expected_id = f"{symbol}-pdf-{candidate.announcement_id}"
    if ref.get("id") != expected_id:
        raise ArchivedPdfVerificationError(
            f"Candidate PDF reference id does not match: {candidate.announcement_id}",
            reason="archive_identity_mismatch",
        )
    if ref.get("source_url") != candidate.source_url:
        raise ArchivedPdfVerificationError(
            f"Candidate PDF source URL does not match: {candidate.announcement_id}",
            reason="archive_identity_mismatch",
        )
    recorded = ref.get("sha256")
    if not isinstance(recorded, str) or not _SHA256.fullmatch(recorded):
        raise ArchivedPdfVerificationError(
            f"Candidate PDF hash is invalid: {candidate.announcement_id}",
            reason="archive_hash_invalid",
        )
    raw_path = ref.get("path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ArchivedPdfVerificationError(
            f"Candidate PDF path is missing: {candidate.announcement_id}",
            reason="archive_path_missing",
        )

    root = archive_root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError(f"Archive root is not a directory: {root}")
    relative_path = Path(raw_path)
    expected_suffix = (
        symbol,
        "announcements",
        candidate.published_at.astimezone(CN_TZ).date().isoformat(),
        f"{candidate.announcement_id}.pdf",
    )
    if (
        relative_path.is_absolute()
        or relative_path.drive
        or ".." in relative_path.parts
        or tuple(relative_path.parts[-4:]) != expected_suffix
    ):
        raise ArchivedPdfVerificationError(
            f"Candidate PDF path is not canonical: {candidate.announcement_id}",
            reason="archive_path_invalid",
        )
    _assert_no_link_components(root, relative_path)
    lexical_path = root / relative_path
    try:
        path = lexical_path.resolve(strict=True)
    except FileNotFoundError as error:
        raise ArchivedPdfVerificationError(
            f"Candidate PDF is missing: {candidate.announcement_id}",
            reason="archive_missing",
        ) from error
    if path != lexical_path or not path.is_relative_to(root):
        raise ArchivedPdfVerificationError(
            f"Candidate PDF escapes archive root: {candidate.announcement_id}",
            reason="archive_path_escape",
        )
    if not path.is_file() or path.suffix.lower() != ".pdf":
        raise ArchivedPdfVerificationError(
            f"Candidate archive is not a regular PDF: {candidate.announcement_id}",
            reason="archive_not_regular_pdf",
        )

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        first_block = handle.read(1024 * 1024)
        if not first_block.startswith(b"%PDF-"):
            raise ArchivedPdfVerificationError(
                f"Candidate archive is not a PDF: {candidate.announcement_id}",
                reason="archive_magic_invalid",
            )
        digest.update(first_block)
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    actual = digest.hexdigest()
    if actual != recorded.lower():
        raise ArchivedPdfVerificationError(
            "Candidate PDF hash mismatch: "
            f"{candidate.announcement_id}; expected={recorded.lower()}, actual={actual}",
            reason="archive_hash_mismatch",
            actual_sha256=actual,
        )
    return ref, actual


def _flags(human_decision: str) -> tuple[bool, bool, bool]:
    if human_decision == DECISION_REQUIRES_RECALCULATION:
        return True, True, False
    if human_decision in {DECISION_REQUIRES_DECOMPOSITION, DECISION_RISK_MONITOR}:
        return False, False, True
    return False, False, False


def _build_decision(
    candidate: Any,
    input_row: DisclosureReviewDecisionInput,
    *,
    archive_root: Path,
    symbol: str,
    reviewed_at: datetime,
    decision_version: str,
) -> EventMaterialityDecision:
    if reviewed_at < candidate.published_at:
        raise ValueError(
            f"Review cannot precede publication: {candidate.announcement_id}"
        )
    pdf_ref, source_sha256 = verify_archived_pdf(
        candidate,
        archive_root=archive_root,
        symbol=symbol,
    )
    recalc, stale, followup = _flags(input_row.human_decision)
    decision = EventMaterialityDecision(
        event_decision_id=(
            f"cninfo-{input_row.symbol}-{input_row.announcement_id}-{decision_version}"
        ),
        symbol=input_row.symbol,
        announcement_id=input_row.announcement_id,
        title=candidate.title,
        published_at=candidate.published_at,
        source_ref=pdf_ref,
        source_sha256=source_sha256,
        machine_candidate_reason=(
            f"title-based machine candidate; rule_kind={candidate.rule_kind}"
        ),
        human_decision=input_row.human_decision,
        affected_domains=input_row.affected_domains,
        affected_fact_fields=input_row.affected_fact_fields,
        affected_assumptions=input_row.affected_assumptions,
        affected_artifacts=input_row.affected_artifacts,
        requires_recalculation=recalc,
        requires_model_stale=stale,
        requires_followup=followup,
        supersedes_event_id=input_row.supersedes_event_id,
        event_cluster_id=input_row.event_cluster_id,
        reviewed_at=reviewed_at,
        reviewer_type=REVIEWER_HUMAN_RESEARCH_LEAD,
        review_notes=input_row.review_notes,
        decision_version=decision_version,
        action=ACTION_NO_ORDER,
    )
    if input_row.human_decision == DECISION_REQUIRES_RECALCULATION and not any(
        (
            input_row.affected_domains,
            input_row.affected_fact_fields,
            input_row.affected_assumptions,
            input_row.affected_artifacts,
        )
    ):
        raise ValueError(
            "A recalculation decision requires at least one affected domain, field, assumption or artifact"
        )
    return decision


def build_disclosure_materiality_reviews(
    queue: DisclosureReviewQueue,
    intake: DisclosureReviewIntake,
    *,
    archive_root: Path,
    decision_version: str = DECISION_VERSION,
) -> tuple[EventMaterialityReview, ...]:
    """Bind every pending queue candidate to exactly one human decision."""

    if queue.queue_id != intake.queue_id:
        raise ValueError("Disclosure review intake queue id does not match")
    actual_queue_sha256 = disclosure_queue_sha256(queue)
    if actual_queue_sha256 != intake.queue_sha256:
        raise ValueError(
            "Disclosure review intake queue hash does not match: "
            f"expected={actual_queue_sha256}, supplied={intake.queue_sha256}"
        )
    reviewed_at = intake.reviewed_at.astimezone(CN_TZ)
    inputs = intake.by_key()
    reviews: list[EventMaterialityReview] = []
    for scan in queue.scans:
        if scan.coverage_status != COVERAGE_COMPLETE or scan.blockers:
            raise ValueError(f"Disclosure scan is incomplete: {scan.symbol}")
        candidates = scan.validity_material_candidates
        expected = {candidate.announcement_id for candidate in candidates}
        supplied = {
            announcement_id
            for symbol, announcement_id in inputs
            if symbol == scan.symbol
        }
        if supplied != expected:
            missing = sorted(expected - supplied)
            extra = sorted(supplied - expected)
            raise ValueError(
                f"Review coverage mismatch for {scan.symbol}; "
                f"missing={missing}, extra={extra}"
            )
        index_refs = [dict(ref) for ref in scan.evidence_refs if ref.get("sha256")]
        if not index_refs:
            raise ValueError(f"Disclosure scan has no hashed index: {scan.symbol}")
        ordered = sorted(
            candidates,
            key=lambda item: (item.published_at, item.announcement_id),
        )
        decisions = tuple(
            _build_decision(
                candidate,
                inputs[(scan.symbol, candidate.announcement_id)],
                archive_root=archive_root,
                symbol=scan.symbol,
                reviewed_at=reviewed_at,
                decision_version=decision_version,
            )
            for candidate in ordered
        )
        reviews.append(
            EventMaterialityReview(
                review_id=f"{queue.queue_id}-{scan.symbol}-materiality-review-{decision_version}",
                schema_version="post-m1-event-materiality-v1",
                symbol=scan.symbol,
                scan_id=f"{queue.queue_id}-{scan.symbol}",
                scan_sha256=str(index_refs[0]["sha256"]),
                scan_from=scan.scan_from,
                scan_to=scan.scan_to,
                reviewed_at=reviewed_at,
                review_as_of=reviewed_at.date(),
                reviewer_type=REVIEWER_HUMAN_RESEARCH_LEAD,
                decisions=decisions,
                evidence_refs=tuple(dict(ref) for ref in scan.evidence_refs),
                action=ACTION_NO_ORDER,
            )
        )
    return tuple(reviews)
