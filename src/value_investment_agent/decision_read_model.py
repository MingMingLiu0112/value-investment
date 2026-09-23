"""Non-personal, presentation-only read model for M3 decision reviews.

The M3 decision domain already fails closed before this module sees it.  This
read model turns an immutable ``InvestmentDecisionReview`` into a public card
that keeps review status, missing personal inputs, evidence hash bindings and
the point-in-time boundary visible.  It never creates an Entry, Journal,
Consistency result, position or order.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import json
import re
from typing import Any, Mapping, Sequence

from .investment_decision import (
    ACTION_NO_ORDER,
    DECISION_INTENTS,
    DECISION_STATUSES,
    ENTRY_REQUIRED_STATUSES,
    POSITIVE_REVIEW_STATUSES,
    STATUS_HOLD,
    STATUS_INSUFFICIENT_RESEARCH,
    STATUS_MANUAL_ADD_REVIEW,
    STATUS_MANUAL_BUY_REVIEW,
    STATUS_MANUAL_EXIT_REVIEW,
    STATUS_MANUAL_REDUCE_REVIEW,
    STATUS_RESEARCH_CANDIDATE,
    STATUS_WATCH,
    STATUS_WAIT_FOR_PRICE,
    DecisionArtifactReference,
    InvestmentDecisionReview,
)
from .research_artifacts import (
    ARTIFACT_DECISION_EVIDENCE_BUNDLE,
    ARTIFACT_INVESTMENT_DECISION_REVIEW,
    canonicalize_artifact_payload,
    sha256_text,
)


DECISION_CARD_SCHEMA = "m3-decision-card-read-model-v1"

CARD_REASON_RESEARCH_INCOMPLETE = "RESEARCH_INCOMPLETE"
CARD_REASON_PRICE_UNAVAILABLE = "PRICE_UNAVAILABLE"
CARD_REASON_PERSONAL_INPUT_MISSING = "PERSONAL_INPUT_MISSING"
CARD_REASON_ENTRY_MISSING = "ENTRY_MISSING"
CARD_REASON_HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"
CARD_REASON_OTHER = "OTHER"
CARD_REASON_KINDS = frozenset(
    {
        CARD_REASON_RESEARCH_INCOMPLETE,
        CARD_REASON_PRICE_UNAVAILABLE,
        CARD_REASON_PERSONAL_INPUT_MISSING,
        CARD_REASON_ENTRY_MISSING,
        CARD_REASON_HUMAN_REVIEW_REQUIRED,
        CARD_REASON_OTHER,
    }
)

CARD_PORTFOLIO_MISSING = "MISSING"
CARD_PORTFOLIO_PROVIDED_UNCONFIRMED = "PROVIDED_UNCONFIRMED"
CARD_PORTFOLIO_CONFIRMED = "PROVIDED_CONFIRMED"
CARD_PORTFOLIO_STATUSES = frozenset(
    {
        CARD_PORTFOLIO_MISSING,
        CARD_PORTFOLIO_PROVIDED_UNCONFIRMED,
        CARD_PORTFOLIO_CONFIRMED,
    }
)

CARD_ENTRY_NOT_REQUIRED = "NOT_REQUIRED"
CARD_ENTRY_MISSING = "MISSING"
CARD_ENTRY_AVAILABLE = "AVAILABLE"
CARD_ENTRY_RECONSTRUCTED = "RECONSTRUCTED"
CARD_ENTRY_STATUSES = frozenset(
    {
        CARD_ENTRY_NOT_REQUIRED,
        CARD_ENTRY_MISSING,
        CARD_ENTRY_AVAILABLE,
        CARD_ENTRY_RECONSTRUCTED,
    }
)

CARD_JOURNAL_ABSENT = "ABSENT"
CARD_JOURNAL_AVAILABLE = "AVAILABLE"
CARD_JOURNAL_STATUSES = frozenset({CARD_JOURNAL_ABSENT, CARD_JOURNAL_AVAILABLE})

_SYMBOL = re.compile(r"^[0-9]{6}$")
_HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PRICE_BLOCKER_PREFIXES = ("price_", "quote_")
_SYSTEM_BLOCKERS = {"decision_intent_not_provided"}
_INTENT_BY_STATUS = {
    STATUS_MANUAL_BUY_REVIEW: "buy",
    STATUS_MANUAL_ADD_REVIEW: "add",
    STATUS_HOLD: "hold",
    STATUS_MANUAL_REDUCE_REVIEW: "reduce",
    STATUS_MANUAL_EXIT_REVIEW: "exit",
}


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _optional_text(value: object, field: str) -> str | None:
    return None if value is None else _required_text(value, field)


def _required_date(value: object, field: str) -> date:
    if not isinstance(value, date) or isinstance(value, datetime):
        raise ValueError(f"{field} must be a date")
    return value


def _optional_date(value: object, field: str) -> date | None:
    if value is None:
        return None
    return _required_date(value, field)


def _required_datetime(value: object, field: str) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"{field} must be a timezone-aware datetime")
    return value


def _require_sha256(value: object, field: str) -> str:
    text = _required_text(value, field).lower()
    if not _HEX_SHA256.fullmatch(text):
        raise ValueError(f"{field} must be SHA-256 hex")
    return text


@dataclass(frozen=True)
class DecisionCardSourceHash:
    """One immutable source payload that the card can trace back to."""

    source_key: str
    artifact_type: str
    artifact_id: str | None
    sha256: str
    available_at: date | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "source_key", _required_text(self.source_key, "source_key")
        )
        object.__setattr__(
            self, "artifact_type", _required_text(self.artifact_type, "artifact_type")
        )
        object.__setattr__(
            self,
            "artifact_id",
            _optional_text(self.artifact_id, "artifact_id"),
        )
        object.__setattr__(self, "sha256", _require_sha256(self.sha256, "sha256"))
        object.__setattr__(
            self, "available_at", _optional_date(self.available_at, "available_at")
        )

    def as_policy(self) -> dict[str, Any]:
        return {
            "source_key": self.source_key,
            "artifact_type": self.artifact_type,
            "artifact_id": self.artifact_id,
            "sha256": self.sha256,
            "available_at": (
                self.available_at.isoformat() if self.available_at is not None else None
            ),
        }


def _source_hash(
    source_key: str,
    artifact_type: str,
    artifact_id: str | None,
    payload: Mapping[str, Any],
    available_at: date | None,
) -> DecisionCardSourceHash:
    return DecisionCardSourceHash(
        source_key=source_key,
        artifact_type=artifact_type,
        artifact_id=artifact_id,
        sha256=sha256_text(canonicalize_artifact_payload(payload)),
        available_at=available_at,
    )


def _reason_kind(
    review: InvestmentDecisionReview,
    decision_intent: str | None,
) -> str:
    if review.status == STATUS_INSUFFICIENT_RESEARCH:
        return CARD_REASON_RESEARCH_INCOMPLETE
    if review.status == STATUS_WAIT_FOR_PRICE:
        return CARD_REASON_PRICE_UNAVAILABLE
    if review.status == STATUS_RESEARCH_CANDIDATE:
        return CARD_REASON_RESEARCH_INCOMPLETE
    if review.status == STATUS_WATCH:
        research_blockers = [
            blocker
            for blocker in review.blockers
            if blocker not in _SYSTEM_BLOCKERS
            and not blocker.startswith(_PRICE_BLOCKER_PREFIXES)
        ]
        if decision_intent is None and not research_blockers:
            return CARD_REASON_PRICE_UNAVAILABLE
        if decision_intent in {"add", "hold", "reduce", "exit"} and review.entry_id is None:
            return CARD_REASON_ENTRY_MISSING
        if (
            decision_intent in {"buy", "add"}
            and not review.portfolio_preconditions.allows_positive_review()
        ):
            return CARD_REASON_PERSONAL_INPUT_MISSING
        return CARD_REASON_HUMAN_REVIEW_REQUIRED
    return CARD_REASON_HUMAN_REVIEW_REQUIRED


def _portfolio_status(review: InvestmentDecisionReview) -> str:
    if not review.portfolio_preconditions.provided:
        return CARD_PORTFOLIO_MISSING
    if review.portfolio_preconditions.allows_positive_review():
        return CARD_PORTFOLIO_CONFIRMED
    return CARD_PORTFOLIO_PROVIDED_UNCONFIRMED


def _entry_status(
    review: InvestmentDecisionReview,
    decision_intent: str | None,
    *,
    entry_reconstructed: bool,
) -> str:
    entry_required = review.status in ENTRY_REQUIRED_STATUSES
    if decision_intent in {"add", "hold", "reduce", "exit"}:
        entry_required = True
    if entry_required and review.entry_id is None:
        return CARD_ENTRY_MISSING
    if review.entry_id is None:
        return CARD_ENTRY_NOT_REQUIRED
    return CARD_ENTRY_RECONSTRUCTED if entry_reconstructed else CARD_ENTRY_AVAILABLE


def _missing_inputs(
    review: InvestmentDecisionReview,
    decision_intent: str | None,
    entry_status: str,
    reason_kind: str,
) -> tuple[str, ...]:
    missing: list[str] = []
    if review.status == STATUS_INSUFFICIENT_RESEARCH:
        missing.append("research_or_valuation_inputs")
    if review.status == STATUS_WAIT_FOR_PRICE or reason_kind == CARD_REASON_PRICE_UNAVAILABLE:
        missing.append("verified_price_or_quote")
    if not review.portfolio_preconditions.provided:
        missing.append("portfolio_input")
    elif not review.portfolio_preconditions.allows_positive_review():
        missing.append("portfolio_capacity_confirmation")
    if entry_status == CARD_ENTRY_MISSING:
        missing.append("original_entry")
    if decision_intent is not None and review.requires_human_review:
        missing.append("human_decision")
    return tuple(dict.fromkeys(missing))


@dataclass(frozen=True)
class DecisionCard:
    """Public non-personal view of one immutable investment decision review."""

    card_id: str
    schema_version: str
    symbol: str
    decision_as_of: date
    review_id: str
    status: str
    summary: str
    reason_kind: str
    decision_intent: str | None
    predecision_status: str
    blockers: tuple[str, ...]
    missing_inputs: tuple[str, ...]
    portfolio_status: str
    entry_status: str
    journal_status: str
    bundle_id: str
    rule_version: str
    artifact_refs: tuple[DecisionArtifactReference, ...]
    evidence_refs: tuple[dict[str, Any], ...]
    source_hashes: tuple[DecisionCardSourceHash, ...]
    created_at: datetime
    requires_human_review: bool = True
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("Decision card symbol must contain six digits")
        if self.schema_version != DECISION_CARD_SCHEMA:
            raise ValueError("Unknown decision card schema")
        for field in ("card_id", "review_id", "summary", "bundle_id", "rule_version"):
            object.__setattr__(self, field, _required_text(getattr(self, field), field))
        object.__setattr__(
            self, "decision_as_of", _required_date(self.decision_as_of, "decision_as_of")
        )
        if self.status not in DECISION_STATUSES:
            raise ValueError("Unknown decision card status")
        if self.reason_kind not in CARD_REASON_KINDS:
            raise ValueError("Unknown decision card reason kind")
        if (
            self.decision_intent is not None
            and self.decision_intent not in DECISION_INTENTS
        ):
            raise ValueError("Unknown decision card intent")
        expected_intent = _INTENT_BY_STATUS.get(self.status)
        if expected_intent is not None and self.decision_intent != expected_intent:
            raise ValueError("Decision card intent does not match its review status")
        if self.portfolio_status not in CARD_PORTFOLIO_STATUSES:
            raise ValueError("Unknown decision card portfolio status")
        if self.entry_status not in CARD_ENTRY_STATUSES:
            raise ValueError("Unknown decision card entry status")
        if self.journal_status not in CARD_JOURNAL_STATUSES:
            raise ValueError("Unknown decision card journal status")
        if self.status in POSITIVE_REVIEW_STATUSES and not self.decision_intent:
            raise ValueError("A positive review card must preserve its decision intent")
        if not self.requires_human_review:
            raise ValueError("Decision cards must remain human-review required")
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Decision card action must remain no_order")
        if self.status in POSITIVE_REVIEW_STATUSES and self.blockers:
            raise ValueError("A positive decision review cannot carry blockers")
        object.__setattr__(self, "blockers", tuple(dict.fromkeys(self.blockers)))
        object.__setattr__(self, "missing_inputs", tuple(dict.fromkeys(self.missing_inputs)))
        object.__setattr__(
            self, "artifact_refs", tuple(self.artifact_refs)
        )
        object.__setattr__(self, "source_hashes", tuple(self.source_hashes))
        object.__setattr__(
            self, "created_at", _required_datetime(self.created_at, "created_at")
        )
        normalized_refs: list[dict[str, Any]] = []
        seen_refs: set[str] = set()
        for raw in self.evidence_refs:
            ref = dict(raw)
            ref_id = ref.get("id")
            if not isinstance(ref_id, str) or not ref_id.strip():
                raise ValueError("Decision card evidence references require ids")
            if ref_id in seen_refs:
                raise ValueError("Decision card evidence reference ids must be unique")
            seen_refs.add(ref_id)
            normalized_refs.append(ref)
        object.__setattr__(self, "evidence_refs", tuple(normalized_refs))

    def is_positive_review(self) -> bool:
        return self.status in POSITIVE_REVIEW_STATUSES

    def as_policy(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "card_id": self.card_id,
            "symbol": self.symbol,
            "decision_as_of": self.decision_as_of.isoformat(),
            "review_id": self.review_id,
            "status": self.status,
            "summary": self.summary,
            "reason_kind": self.reason_kind,
            "decision_intent": self.decision_intent,
            "predecision_status": self.predecision_status,
            "blockers": list(self.blockers),
            "missing_inputs": list(self.missing_inputs),
            "portfolio_status": self.portfolio_status,
            "entry_status": self.entry_status,
            "journal_status": self.journal_status,
            "bundle_id": self.bundle_id,
            "rule_version": self.rule_version,
            "artifact_refs": [ref.as_policy() for ref in self.artifact_refs],
            "evidence_refs": [dict(ref) for ref in self.evidence_refs],
            "source_hashes": [ref.as_policy() for ref in self.source_hashes],
            "created_at": self.created_at.isoformat(),
            "requires_human_review": self.requires_human_review,
            "action": self.action,
        }

    def to_json(self) -> str:
        return json.dumps(
            self.as_policy(),
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        )


def decision_card_from_review(
    review: InvestmentDecisionReview,
    *,
    decision_intent: str | None = None,
    entry_reconstructed: bool = False,
    journal_present: bool = False,
    source_hashes: Sequence[DecisionCardSourceHash] = (),
) -> DecisionCard:
    """Build a public card without inventing a personal decision or history."""
    if not isinstance(review, InvestmentDecisionReview):
        raise TypeError("Decision cards require an InvestmentDecisionReview")
    reason_kind = _reason_kind(review, decision_intent)
    entry_status = _entry_status(
        review,
        decision_intent,
        entry_reconstructed=entry_reconstructed,
    )
    hashes = tuple(source_hashes)
    if not hashes:
        hashes = (
            _source_hash(
                "investment_decision_review",
                ARTIFACT_INVESTMENT_DECISION_REVIEW,
                review.review_id,
                review.as_policy(),
                review.decision_as_of,
            ),
            _source_hash(
                "decision_evidence_bundle",
                ARTIFACT_DECISION_EVIDENCE_BUNDLE,
                review.bundle.bundle_id,
                review.bundle.as_policy(),
                review.bundle.decision_as_of,
            ),
        )
    return DecisionCard(
        card_id=f"{review.review_id}-card",
        schema_version=DECISION_CARD_SCHEMA,
        symbol=review.symbol,
        decision_as_of=review.decision_as_of,
        review_id=review.review_id,
        status=review.status,
        summary=review.summary,
        reason_kind=reason_kind,
        decision_intent=decision_intent,
        predecision_status=review.predecision_status,
        blockers=review.blockers,
        missing_inputs=_missing_inputs(
            review,
            decision_intent,
            entry_status,
            reason_kind,
        ),
        portfolio_status=_portfolio_status(review),
        entry_status=entry_status,
        journal_status=(
            CARD_JOURNAL_AVAILABLE if journal_present else CARD_JOURNAL_ABSENT
        ),
        bundle_id=review.bundle.bundle_id,
        rule_version=review.rule_version,
        artifact_refs=review.bundle.artifact_refs,
        evidence_refs=review.bundle.evidence_refs,
        source_hashes=hashes,
        created_at=review.created_at,
        requires_human_review=review.requires_human_review,
        action=review.action,
    )


@dataclass(frozen=True)
class DecisionCardDecodeFailure:
    symbol: str | None
    error: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", _optional_text(self.symbol, "failure symbol"))
        object.__setattr__(self, "error", _required_text(self.error, "failure error"))

    def as_policy(self) -> dict[str, Any]:
        return {"symbol": self.symbol, "error": self.error}


@dataclass(frozen=True)
class DecisionCardCollection:
    """A deterministic presentation bundle; no card is an order."""

    schema_version: str
    generated_at: datetime
    source_run_id: str
    cards: tuple[DecisionCard, ...]
    input_failures: tuple[DecisionCardDecodeFailure, ...] = ()
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        if self.schema_version != DECISION_CARD_SCHEMA:
            raise ValueError("Unknown decision card collection schema")
        object.__setattr__(
            self, "generated_at", _required_datetime(self.generated_at, "generated_at")
        )
        object.__setattr__(
            self, "source_run_id", _required_text(self.source_run_id, "source_run_id")
        )
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Decision card collection must remain no_order")
        card_ids = [card.card_id for card in self.cards]
        if len(set(card_ids)) != len(card_ids):
            raise ValueError("Decision card ids must be unique")
        object.__setattr__(self, "cards", tuple(self.cards))
        object.__setattr__(self, "input_failures", tuple(self.input_failures))

    @property
    def by_symbol(self) -> dict[str, DecisionCard]:
        return {card.symbol: card for card in self.cards}

    def as_policy(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at.isoformat(),
            "source_run_id": self.source_run_id,
            "action": self.action,
            "cards": [card.as_policy() for card in self.cards],
            "input_failures": [failure.as_policy() for failure in self.input_failures],
        }

    def to_json(self) -> str:
        return json.dumps(
            self.as_policy(),
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        )
