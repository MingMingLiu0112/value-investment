"""Reuse prior Post-M1 human materiality decisions for unchanged CNINFO PDFs.

The current disclosure queue can contain announcements the user has already
reviewed. This module reconciles the two versioned receipts instead of asking
the user to judge the same source document twice. It never changes the prior
decision and never creates an event or an order.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Mapping, Sequence

from .event_materiality import (
    EVENT_MATERIALITY_SCHEMA,
    EventMaterialityDecision,
    EventMaterialityReview,
)
from .event_scan import AnnouncementReview
from .investment_decision import ACTION_NO_ORDER
from .m5_disclosure_queue import DisclosureReviewQueue
from .m5_disclosure_review import disclosure_queue_sha256


M5_RECONCILIATION_SCHEMA = "m5-human-review-reconciliation-v1"

DISPOSITION_CARRY_FORWARD = "CARRY_FORWARD_PRIOR_HUMAN_DECISION"
DISPOSITION_PENDING_HUMAN_REVIEW = "PENDING_HUMAN_REVIEW"
DISPOSITION_SUPERSEDED_PENDING = "SUPERSEDED_PENDING"
DISPOSITIONS = frozenset(
    {
        DISPOSITION_CARRY_FORWARD,
        DISPOSITION_PENDING_HUMAN_REVIEW,
        DISPOSITION_SUPERSEDED_PENDING,
    }
)

REASON_NEW_ANNOUNCEMENT = "new_announcement"
REASON_SOURCE_PDF_HASH_CHANGED = "source_pdf_hash_changed"
REASON_SOURCE_PDF_HASH_MISSING = "source_pdf_hash_missing"
REASON_PRIOR_REVIEW_INVALID = "prior_review_not_valid"
REASON_SUPERSEDED_BY_NEWER_REVIEW = "superseded_by_newer_review"
PENDING_REASONS = frozenset(
    {
        REASON_NEW_ANNOUNCEMENT,
        REASON_SOURCE_PDF_HASH_CHANGED,
        REASON_SOURCE_PDF_HASH_MISSING,
        REASON_PRIOR_REVIEW_INVALID,
        REASON_SUPERSEDED_BY_NEWER_REVIEW,
    }
)

_SYMBOL = re.compile(r"^[0-9]{6}$")
_ANNOUNCEMENT_ID = re.compile(r"^[0-9]+$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _canonical_digest(payload: Mapping[str, Any]) -> str:
    data = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _sha256(value: object, field: str) -> str:
    text = _required_text(value, field).lower()
    if not _SHA256.fullmatch(text):
        raise ValueError(f"{field} must be SHA-256 hex")
    return text


def _normalize_refs(refs: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    normalized = tuple(dict(ref) for ref in refs)
    if any(not ref.get("id") for ref in normalized):
        raise ValueError("Reconciliation evidence requires named references")
    return normalized


def _source_pdf_hash(candidate: AnnouncementReview) -> str | None:
    pdf_refs = [
        ref
        for ref in candidate.evidence_refs
        if str(ref.get("path") or "").lower().endswith(".pdf")
        or "-pdf-" in str(ref.get("id") or "")
    ]
    if not pdf_refs:
        return None
    if len(pdf_refs) != 1:
        raise ValueError(
            f"Announcement {candidate.announcement_id} has multiple PDF references"
        )
    raw_hash = pdf_refs[0].get("sha256")
    if raw_hash is None:
        return None
    return _sha256(raw_hash, "source_pdf_sha256")


def _valid_prior_decision(decision: EventMaterialityDecision) -> bool:
    return (
        decision.action == ACTION_NO_ORDER
        and decision.reviewed_at is not None
        and decision.source_sha256 == _sha256(decision.source_sha256, "source_sha256")
    )


@dataclass(frozen=True)
class M5ReviewResolution:
    symbol: str
    announcement_id: str
    disposition: str
    reason: str | None
    current_source_sha256: str | None
    prior_review_id: str | None = None
    prior_review_sha256: str | None = None
    prior_event_decision_id: str | None = None
    prior_human_decision: str | None = None
    prior_supersedes_event_id: str | None = None
    carried_forward_at: datetime | None = None
    evidence_refs: tuple[dict[str, Any], ...] = ()
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("Reconciliation symbol must contain six digits")
        if not _ANNOUNCEMENT_ID.fullmatch(self.announcement_id):
            raise ValueError("Reconciliation announcement id must contain digits only")
        if self.disposition not in DISPOSITIONS:
            raise ValueError("Unknown reconciliation disposition")
        if self.action != ACTION_NO_ORDER:
            raise ValueError("M5 reconciliation must remain no_order")
        object.__setattr__(self, "evidence_refs", _normalize_refs(self.evidence_refs))
        if self.current_source_sha256 is not None:
            object.__setattr__(
                self,
                "current_source_sha256",
                _sha256(self.current_source_sha256, "current_source_sha256"),
            )
        if self.disposition == DISPOSITION_CARRY_FORWARD:
            if self.reason is not None:
                raise ValueError("Carried-forward reviews cannot have a pending reason")
            if not all(
                (
                    self.prior_review_id,
                    self.prior_review_sha256,
                    self.prior_event_decision_id,
                    self.prior_human_decision,
                    self.current_source_sha256,
                    self.carried_forward_at,
                )
            ):
                raise ValueError("Carried-forward reviews require complete prior binding")
            if self.carried_forward_at.tzinfo is None:
                raise ValueError("carried_forward_at must include a timezone")
        else:
            if self.reason not in PENDING_REASONS:
                raise ValueError("Pending or superseded reviews require a valid reason")

    def is_pending_human_review(self) -> bool:
        return self.disposition in {
            DISPOSITION_PENDING_HUMAN_REVIEW,
            DISPOSITION_SUPERSEDED_PENDING,
        }

    def as_policy(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "announcement_id": self.announcement_id,
            "disposition": self.disposition,
            "reason": self.reason,
            "current_source_sha256": self.current_source_sha256,
            "prior_review_id": self.prior_review_id,
            "prior_review_sha256": self.prior_review_sha256,
            "prior_event_decision_id": self.prior_event_decision_id,
            "prior_human_decision": self.prior_human_decision,
            "prior_supersedes_event_id": self.prior_supersedes_event_id,
            "carried_forward_at": (
                self.carried_forward_at.isoformat()
                if self.carried_forward_at is not None
                else None
            ),
            "evidence_refs": [dict(ref) for ref in self.evidence_refs],
            "action": self.action,
        }


@dataclass(frozen=True)
class M5HumanReviewReconciliation:
    reconciliation_id: str
    schema_version: str
    current_queue_id: str
    current_queue_sha256: str
    prior_review_ids: tuple[str, ...]
    as_of: datetime
    resolutions: tuple[M5ReviewResolution, ...]
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        if self.schema_version != M5_RECONCILIATION_SCHEMA:
            raise ValueError("Unknown M5 reconciliation schema")
        if not self.reconciliation_id.strip():
            raise ValueError("M5 reconciliation requires an id")
        if self.as_of.tzinfo is None:
            raise ValueError("M5 reconciliation as_of must include a timezone")
        if self.action != ACTION_NO_ORDER:
            raise ValueError("M5 reconciliation must remain no_order")
        object.__setattr__(
            self,
            "current_queue_sha256",
            _sha256(self.current_queue_sha256, "current_queue_sha256"),
        )
        object.__setattr__(
            self,
            "prior_review_ids",
            tuple(_required_text(item, "prior review id") for item in self.prior_review_ids),
        )
        object.__setattr__(self, "resolutions", tuple(self.resolutions))
        keys = [(item.symbol, item.announcement_id) for item in self.resolutions]
        if len(keys) != len(set(keys)):
            raise ValueError("M5 reconciliation contains a duplicate announcement")

    @property
    def pending_resolutions(self) -> tuple[M5ReviewResolution, ...]:
        return tuple(item for item in self.resolutions if item.is_pending_human_review())

    @property
    def carried_forward_count(self) -> int:
        return sum(
            item.disposition == DISPOSITION_CARRY_FORWARD
            for item in self.resolutions
        )

    @property
    def pending_human_review_count(self) -> int:
        return sum(
            item.disposition == DISPOSITION_PENDING_HUMAN_REVIEW
            for item in self.resolutions
        )

    @property
    def superseded_pending_count(self) -> int:
        return sum(
            item.disposition == DISPOSITION_SUPERSEDED_PENDING
            for item in self.resolutions
        )

    @property
    def hash_conflict_count(self) -> int:
        return sum(
            item.reason == REASON_SOURCE_PDF_HASH_CHANGED
            for item in self.resolutions
        )

    def as_policy(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "reconciliation_id": self.reconciliation_id,
            "current_queue_id": self.current_queue_id,
            "current_queue_sha256": self.current_queue_sha256,
            "prior_review_ids": list(self.prior_review_ids),
            "as_of": self.as_of.isoformat(),
            "resolutions": [item.as_policy() for item in self.resolutions],
            "counts": {
                "current_candidates": len(self.resolutions),
                "carried_forward": self.carried_forward_count,
                "pending_human_review": self.pending_human_review_count,
                "superseded_pending": self.superseded_pending_count,
                "hash_conflicts": self.hash_conflict_count,
            },
            "action": self.action,
        }

    def to_json(self) -> str:
        return json.dumps(
            self.as_policy(),
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        )


def reconcile_m5_human_reviews(
    *,
    queue: DisclosureReviewQueue,
    prior_reviews: Sequence[EventMaterialityReview],
    reconciliation_id: str,
    as_of: datetime | None = None,
) -> M5HumanReviewReconciliation:
    if queue.action != ACTION_NO_ORDER:
        raise ValueError("Disclosure review queue must remain no_order")
    if any(review.action != ACTION_NO_ORDER for review in prior_reviews):
        raise ValueError("Prior materiality reviews must remain no_order")
    prior_by_key: dict[tuple[str, str], tuple[EventMaterialityReview, EventMaterialityDecision]] = {}
    prior_review_hashes: dict[str, str] = {}
    for review in prior_reviews:
        if review.schema_version != EVENT_MATERIALITY_SCHEMA:
            raise ValueError("Unsupported prior materiality review schema")
        prior_review_hashes[review.review_id] = _canonical_digest(review.as_policy())
        for decision in review.decisions:
            key = (decision.symbol, decision.announcement_id)
            if key in prior_by_key:
                raise ValueError(
                    f"Duplicate prior decision for {key[0]} / {key[1]}"
                )
            prior_by_key[key] = (review, decision)

    current = queue.pending_candidates
    current_by_key = {
        (scan.symbol, candidate.announcement_id): candidate
        for scan in queue.scans
        for candidate in scan.announcements
        if candidate.materiality_candidate
    }
    if len(current_by_key) != len(current):
        raise ValueError("Disclosure queue contains a duplicate pending candidate")

    superseding_by_old_id: dict[str, EventMaterialityDecision] = {}
    for review in prior_reviews:
        for decision in review.decisions:
            if decision.supersedes_event_id:
                superseding_by_old_id[decision.supersedes_event_id] = decision

    resolutions: list[M5ReviewResolution] = []
    carried_at = as_of or datetime.now(timezone.utc)
    for scan in queue.scans:
        for candidate in scan.announcements:
            if not candidate.materiality_candidate:
                continue
            current_hash = _source_pdf_hash(candidate)
            prior = prior_by_key.get((scan.symbol, candidate.announcement_id))
            if prior is None:
                resolutions.append(
                    M5ReviewResolution(
                        symbol=scan.symbol,
                        announcement_id=candidate.announcement_id,
                        disposition=DISPOSITION_PENDING_HUMAN_REVIEW,
                        reason=REASON_NEW_ANNOUNCEMENT,
                        current_source_sha256=current_hash,
                        evidence_refs=candidate.evidence_refs,
                    )
                )
                continue

            review, decision = prior
            if not _valid_prior_decision(decision):
                resolutions.append(
                    M5ReviewResolution(
                        symbol=scan.symbol,
                        announcement_id=candidate.announcement_id,
                        disposition=DISPOSITION_PENDING_HUMAN_REVIEW,
                        reason=REASON_PRIOR_REVIEW_INVALID,
                        current_source_sha256=current_hash,
                        prior_review_id=review.review_id,
                        prior_event_decision_id=decision.event_decision_id,
                        evidence_refs=candidate.evidence_refs,
                    )
                )
                continue
            if current_hash is None:
                resolutions.append(
                    M5ReviewResolution(
                        symbol=scan.symbol,
                        announcement_id=candidate.announcement_id,
                        disposition=DISPOSITION_PENDING_HUMAN_REVIEW,
                        reason=REASON_SOURCE_PDF_HASH_MISSING,
                        current_source_sha256=None,
                        prior_review_id=review.review_id,
                        prior_event_decision_id=decision.event_decision_id,
                        evidence_refs=candidate.evidence_refs,
                    )
                )
                continue
            if decision.source_sha256 != current_hash:
                resolutions.append(
                    M5ReviewResolution(
                        symbol=scan.symbol,
                        announcement_id=candidate.announcement_id,
                        disposition=DISPOSITION_PENDING_HUMAN_REVIEW,
                        reason=REASON_SOURCE_PDF_HASH_CHANGED,
                        current_source_sha256=current_hash,
                        prior_review_id=review.review_id,
                        prior_event_decision_id=decision.event_decision_id,
                        evidence_refs=candidate.evidence_refs,
                    )
                )
                continue
            resolutions.append(
                M5ReviewResolution(
                    symbol=scan.symbol,
                    announcement_id=candidate.announcement_id,
                    disposition=DISPOSITION_CARRY_FORWARD,
                    reason=None,
                    current_source_sha256=current_hash,
                    prior_review_id=review.review_id,
                    prior_review_sha256=prior_review_hashes[review.review_id],
                    prior_event_decision_id=decision.event_decision_id,
                    prior_human_decision=decision.human_decision,
                    prior_supersedes_event_id=decision.supersedes_event_id,
                    carried_forward_at=carried_at,
                    evidence_refs=candidate.evidence_refs,
                )
            )

    # A prior decision that itself superseded an older announcement is valid
    # for the unchanged superseding PDF. We retain the relationship in the
    # output but do not ask for a second human judgment when both receipts
    # still hash identically.
    resolutions.sort(key=lambda item: (item.symbol, item.announcement_id))
    return M5HumanReviewReconciliation(
        reconciliation_id=reconciliation_id,
        schema_version=M5_RECONCILIATION_SCHEMA,
        current_queue_id=queue.queue_id,
        current_queue_sha256=disclosure_queue_sha256(queue),
        prior_review_ids=tuple(sorted(prior_review_hashes)),
        as_of=carried_at,
        resolutions=tuple(resolutions),
        action=ACTION_NO_ORDER,
    )
