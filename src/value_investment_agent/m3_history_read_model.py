"""Public, non-personal read model for the M3 thesis-continuity chain.

This module turns immutable Entry, Journal and Consistency domain objects into
presentation rows. It contains no execution, position or order semantics.
Only simulated chains are allowed in a public workbook; actual account data
must stay in a private environment.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import json
import re
from typing import Any, Mapping, Sequence

from .investment_decision import (
    ACTION_NO_ORDER,
    COMPARISON_NEUTRAL,
    ENTRY_TYPE_RECONSTRUCTED,
    ENTRY_TYPE_SIMULATED,
    DecisionJournalEntry,
    EntryThesisSnapshot,
    InvestmentConsistencyReview,
    decision_journal_entry_from_payload,
    entry_thesis_snapshot_from_payload,
    investment_consistency_review_from_payload,
)
from .research_artifacts import canonicalize_artifact_payload, sha256_text


M3_HISTORY_SCHEMA = "m3-decision-history-read-model-v1"
M3_HISTORY_INPUT_SCHEMA = "m3-decision-history-input-v1"
PUBLIC_NAMESPACE = ENTRY_TYPE_SIMULATED

_SYMBOL = re.compile(r"^[0-9]{6}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _optional_decimal_text(value: object | None) -> str | None:
    return str(value) if value is not None else None


def _required_datetime(value: object, field: str) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"{field} must be a timezone-aware datetime")
    return value


def _required_date(value: object, field: str) -> date:
    if not isinstance(value, date) or isinstance(value, datetime):
        raise ValueError(f"{field} must be a date")
    return value


def _require_sha256(value: object, field: str) -> str:
    text = _required_text(value, field).lower()
    if not _SHA256.fullmatch(text):
        raise ValueError(f"{field} must be a SHA-256 hex digest")
    return text


def _hash_payload(payload: Mapping[str, Any]) -> str:
    return sha256_text(canonicalize_artifact_payload(dict(payload)))


@dataclass(frozen=True)
class HistoryConsistencyComparison:
    """One Original-vs-Current comparison in a public consistency card."""

    dimension: str
    original_value: str
    current_value: str
    impact: str
    change_reason: str
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field in (
            "dimension",
            "original_value",
            "current_value",
            "impact",
        ):
            object.__setattr__(
                self, field, _required_text(getattr(self, field), field)
            )
        if self.impact == COMPARISON_NEUTRAL:
            object.__setattr__(self, "change_reason", "")
        else:
            object.__setattr__(
                self,
                "change_reason",
                _required_text(self.change_reason, "change_reason"),
            )
        object.__setattr__(self, "evidence_ids", tuple(self.evidence_ids))

    def as_policy(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "original_value": self.original_value,
            "current_value": self.current_value,
            "impact": self.impact,
            "change_reason": self.change_reason,
            "evidence_ids": list(self.evidence_ids),
        }


@dataclass(frozen=True)
class EntryThesisCard:
    """Public projection of a frozen original Entry Thesis."""

    symbol: str
    entry_id: str
    entry_type: str
    entry_date: date
    confirmed_at: datetime
    entry_price: str | None
    thesis: str
    return_driver: str
    mispricing_hypothesis: str
    bear_value: str | None
    base_value: str | None
    bull_value: str | None
    confidence: str
    dividend_thesis: str
    hold_logic: str
    risks: tuple[str, ...]
    counter_evidence: tuple[str, ...]
    breakers: tuple[str, ...]
    catalysts: tuple[str, ...]
    reasons_to_add: tuple[str, ...]
    reasons_not_to_add: tuple[str, ...]
    reasons_to_reduce: tuple[str, ...]
    reasons_to_exit: tuple[str, ...]
    reconstructed_note: str
    source_sha256: str
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("History entry symbol must contain six digits")
        object.__setattr__(
            self, "source_sha256", _require_sha256(self.source_sha256, "source_sha256")
        )
        if self.action != ACTION_NO_ORDER:
            raise ValueError("History entry must remain no_order")
        object.__setattr__(
            self, "entry_date", _required_date(self.entry_date, "entry_date")
        )
        object.__setattr__(
            self, "confirmed_at", _required_datetime(self.confirmed_at, "confirmed_at")
        )
        for field in (
            "entry_id",
            "entry_type",
            "thesis",
            "return_driver",
            "mispricing_hypothesis",
            "confidence",
            "dividend_thesis",
            "hold_logic",
        ):
            object.__setattr__(
                self, field, _required_text(getattr(self, field), field)
            )
        for field in (
            "risks",
            "counter_evidence",
            "breakers",
            "catalysts",
            "reasons_to_add",
            "reasons_not_to_add",
            "reasons_to_reduce",
            "reasons_to_exit",
        ):
            object.__setattr__(self, field, tuple(getattr(self, field)))

    @property
    def is_reconstructed(self) -> bool:
        return self.entry_type == ENTRY_TYPE_RECONSTRUCTED

    def as_policy(self) -> dict[str, Any]:
        return {
            "schema_version": M3_HISTORY_SCHEMA,
            "symbol": self.symbol,
            "entry_id": self.entry_id,
            "entry_type": self.entry_type,
            "entry_date": self.entry_date.isoformat(),
            "confirmed_at": self.confirmed_at.isoformat(),
            "entry_price": self.entry_price,
            "thesis": self.thesis,
            "return_driver": self.return_driver,
            "mispricing_hypothesis": self.mispricing_hypothesis,
            "bear_value": self.bear_value,
            "base_value": self.base_value,
            "bull_value": self.bull_value,
            "confidence": self.confidence,
            "dividend_thesis": self.dividend_thesis,
            "hold_logic": self.hold_logic,
            "risks": list(self.risks),
            "counter_evidence": list(self.counter_evidence),
            "breakers": list(self.breakers),
            "catalysts": list(self.catalysts),
            "reasons_to_add": list(self.reasons_to_add),
            "reasons_not_to_add": list(self.reasons_not_to_add),
            "reasons_to_reduce": list(self.reasons_to_reduce),
            "reasons_to_exit": list(self.reasons_to_exit),
            "reconstructed_note": self.reconstructed_note,
            "source_sha256": self.source_sha256,
            "action": self.action,
        }

    @classmethod
    def from_snapshot(
        cls, snapshot: EntryThesisSnapshot, *, source_sha256: str
    ) -> EntryThesisCard:
        if not isinstance(snapshot, EntryThesisSnapshot):
            raise TypeError("History entry requires an EntryThesisSnapshot")
        return cls(
            symbol=snapshot.symbol,
            entry_id=snapshot.entry_id,
            entry_type=snapshot.entry_type,
            entry_date=snapshot.entry_date,
            confirmed_at=snapshot.confirmed_at,
            entry_price=_optional_decimal_text(snapshot.entry_price),
            thesis=snapshot.thesis,
            return_driver=snapshot.return_driver,
            mispricing_hypothesis=snapshot.mispricing_hypothesis,
            bear_value=_optional_decimal_text(snapshot.bear_value),
            base_value=_optional_decimal_text(snapshot.base_value),
            bull_value=_optional_decimal_text(snapshot.bull_value),
            confidence=snapshot.confidence,
            dividend_thesis=snapshot.dividend_thesis,
            hold_logic=snapshot.hold_logic,
            risks=snapshot.risks,
            counter_evidence=snapshot.counter_evidence,
            breakers=snapshot.breakers,
            catalysts=snapshot.catalysts,
            reasons_to_add=snapshot.reasons_to_add,
            reasons_not_to_add=snapshot.reasons_not_to_add,
            reasons_to_reduce=snapshot.reasons_to_reduce,
            reasons_to_exit=snapshot.reasons_to_exit,
            reconstructed_note=snapshot.reconstructed_note,
            source_sha256=source_sha256,
            action=snapshot.action,
        )


@dataclass(frozen=True)
class DecisionJournalLine:
    """Public projection of one immutable decision journal entry."""

    symbol: str
    journal_id: str
    decision_at: datetime
    review_id: str
    review_status: str
    system_reason: str
    human_decision: str
    human_reason: str
    entry_id: str | None
    confirmed_price: str | None
    namespace: str
    previous_journal_id: str | None
    source_sha256: str
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("Journal line symbol must contain six digits")
        object.__setattr__(
            self, "source_sha256", _require_sha256(self.source_sha256, "source_sha256")
        )
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Journal line must remain no_order")
        object.__setattr__(
            self, "decision_at", _required_datetime(self.decision_at, "decision_at")
        )
        for field in (
            "journal_id",
            "review_id",
            "review_status",
            "system_reason",
            "human_decision",
            "human_reason",
            "namespace",
        ):
            object.__setattr__(
                self, field, _required_text(getattr(self, field), field)
            )

    @property
    def is_correction(self) -> bool:
        return self.previous_journal_id is not None

    def as_policy(self) -> dict[str, Any]:
        return {
            "schema_version": M3_HISTORY_SCHEMA,
            "symbol": self.symbol,
            "journal_id": self.journal_id,
            "decision_at": self.decision_at.isoformat(),
            "review_id": self.review_id,
            "review_status": self.review_status,
            "system_reason": self.system_reason,
            "human_decision": self.human_decision,
            "human_reason": self.human_reason,
            "entry_id": self.entry_id,
            "confirmed_price": self.confirmed_price,
            "namespace": self.namespace,
            "previous_journal_id": self.previous_journal_id,
            "source_sha256": self.source_sha256,
            "action": self.action,
        }

    @classmethod
    def from_entry(
        cls, entry: DecisionJournalEntry, *, source_sha256: str
    ) -> DecisionJournalLine:
        if not isinstance(entry, DecisionJournalEntry):
            raise TypeError("Journal line requires a DecisionJournalEntry")
        return cls(
            symbol=entry.symbol,
            journal_id=entry.journal_id,
            decision_at=entry.decision_at,
            review_id=entry.review_id,
            review_status=entry.review_status,
            system_reason=entry.system_reason,
            human_decision=entry.human_decision,
            human_reason=entry.human_reason,
            entry_id=entry.entry_id,
            confirmed_price=_optional_decimal_text(entry.confirmed_price),
            namespace=entry.namespace,
            previous_journal_id=entry.previous_journal_id,
            source_sha256=source_sha256,
            action=entry.action,
        )


@dataclass(frozen=True)
class ConsistencyReviewCard:
    """Public projection of one Original-vs-Current consistency review."""

    symbol: str
    review_id: str
    entry_id: str
    as_of: date
    status: str
    comparisons: tuple[HistoryConsistencyComparison, ...]
    blockers: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    source_sha256: str
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("Consistency card symbol must contain six digits")
        object.__setattr__(
            self, "source_sha256", _require_sha256(self.source_sha256, "source_sha256")
        )
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Consistency card must remain no_order")
        object.__setattr__(self, "as_of", _required_date(self.as_of, "as_of"))
        object.__setattr__(
            self, "review_id", _required_text(self.review_id, "review_id")
        )
        object.__setattr__(self, "entry_id", _required_text(self.entry_id, "entry_id"))
        object.__setattr__(self, "status", _required_text(self.status, "status"))
        object.__setattr__(self, "comparisons", tuple(self.comparisons))
        object.__setattr__(self, "blockers", tuple(self.blockers))
        object.__setattr__(self, "evidence_ids", tuple(self.evidence_ids))

    def as_policy(self) -> dict[str, Any]:
        return {
            "schema_version": M3_HISTORY_SCHEMA,
            "symbol": self.symbol,
            "review_id": self.review_id,
            "entry_id": self.entry_id,
            "as_of": self.as_of.isoformat(),
            "status": self.status,
            "comparisons": [item.as_policy() for item in self.comparisons],
            "blockers": list(self.blockers),
            "evidence_ids": list(self.evidence_ids),
            "source_sha256": self.source_sha256,
            "action": self.action,
        }

    @classmethod
    def from_review(
        cls, review: InvestmentConsistencyReview, *, source_sha256: str
    ) -> ConsistencyReviewCard:
        if not isinstance(review, InvestmentConsistencyReview):
            raise TypeError("Consistency card requires an InvestmentConsistencyReview")
        comparisons = tuple(
            HistoryConsistencyComparison(
                dimension=item.dimension,
                original_value=item.original_value,
                current_value=item.current_value,
                impact=item.impact,
                change_reason=item.change_reason,
                evidence_ids=tuple(
                    str(ref.get("id"))
                    for ref in item.evidence_refs
                    if ref.get("id")
                ),
            )
            for item in review.comparisons
        )
        return cls(
            symbol=review.symbol,
            review_id=review.review_id,
            entry_id=review.entry_id,
            as_of=review.as_of,
            status=review.status,
            comparisons=comparisons,
            blockers=review.blockers,
            evidence_ids=tuple(
                str(ref.get("id"))
                for ref in review.evidence_refs
                if ref.get("id")
            ),
            source_sha256=source_sha256,
            action=review.action,
        )


@dataclass(frozen=True)
class DecisionHistoryChain:
    """One symbol's Entry -> Journal -> Consistency public chain."""

    symbol: str
    entry: EntryThesisCard
    journals: tuple[DecisionJournalLine, ...]
    consistency_reviews: tuple[ConsistencyReviewCard, ...]

    def __post_init__(self) -> None:
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("Decision history symbol must contain six digits")
        if self.entry.symbol != self.symbol:
            raise ValueError("Decision history entry symbol does not match")
        if self.entry.entry_type != PUBLIC_NAMESPACE:
            raise ValueError("Public decision history must be simulated")
        journal_by_id: dict[str, DecisionJournalLine] = {}
        for journal in self.journals:
            if journal.symbol != self.symbol or journal.namespace != PUBLIC_NAMESPACE:
                raise ValueError(
                    "Decision history journal must match symbol and simulation namespace"
                )
            if journal.journal_id in journal_by_id:
                raise ValueError("Decision history journal ids must be unique")
            if journal.entry_id is not None and journal.entry_id != self.entry.entry_id:
                raise ValueError(
                    "Decision history journal entry id does not match the frozen entry"
                )
            if (
                journal.previous_journal_id is not None
                and journal.previous_journal_id not in journal_by_id
            ):
                raise ValueError(
                    "Decision history journal correction has an unknown predecessor"
                )
            if journal.previous_journal_id is not None:
                predecessor = journal_by_id[journal.previous_journal_id]
                if predecessor.decision_at > journal.decision_at:
                    raise ValueError(
                        "Decision history journal correction cannot precede its predecessor"
                    )
            journal_by_id[journal.journal_id] = journal
        review_ids: set[str] = set()
        for review in self.consistency_reviews:
            if review.review_id in review_ids:
                raise ValueError("Decision history consistency review ids must be unique")
            review_ids.add(review.review_id)
        if any(
            review.symbol != self.symbol or review.entry_id != self.entry.entry_id
            for review in self.consistency_reviews
        ):
            raise ValueError(
                "Decision history consistency card must match symbol and entry"
            )
        object.__setattr__(
            self,
            "journals",
            tuple(sorted(self.journals, key=lambda item: (item.decision_at, item.journal_id))),
        )
        object.__setattr__(
            self,
            "consistency_reviews",
            tuple(sorted(self.consistency_reviews, key=lambda item: (item.as_of, item.review_id))),
        )

    @property
    def namespace(self) -> str:
        return self.entry.entry_type

    @property
    def latest_journal(self) -> DecisionJournalLine | None:
        return self.journals[-1] if self.journals else None

    @property
    def latest_consistency(self) -> ConsistencyReviewCard | None:
        return self.consistency_reviews[-1] if self.consistency_reviews else None

    def as_policy(self) -> dict[str, Any]:
        return {
            "schema_version": M3_HISTORY_SCHEMA,
            "symbol": self.symbol,
            "namespace": self.namespace,
            "entry": self.entry.as_policy(),
            "journals": [item.as_policy() for item in self.journals],
            "consistency_reviews": [
                item.as_policy() for item in self.consistency_reviews
            ],
            "action": ACTION_NO_ORDER,
        }


@dataclass(frozen=True)
class DecisionHistoryCollection:
    """Deterministic public collection of simulated decision-history chains."""

    schema_version: str
    generated_at: datetime
    source_id: str
    chains: tuple[DecisionHistoryChain, ...]
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        if self.schema_version != M3_HISTORY_SCHEMA:
            raise ValueError("Unknown decision history collection schema")
        object.__setattr__(
            self, "generated_at", _required_datetime(self.generated_at, "generated_at")
        )
        object.__setattr__(
            self, "source_id", _required_text(self.source_id, "source_id")
        )
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Decision history collection must remain no_order")
        symbols = [chain.symbol for chain in self.chains]
        if len(symbols) != len(set(symbols)):
            raise ValueError("Decision history symbols must be unique")
        object.__setattr__(self, "chains", tuple(self.chains))

    @property
    def by_symbol(self) -> dict[str, DecisionHistoryChain]:
        return {chain.symbol: chain for chain in self.chains}

    def as_policy(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at.isoformat(),
            "source_id": self.source_id,
            "action": self.action,
            "chains": [chain.as_policy() for chain in self.chains],
        }

    def to_json(self) -> str:
        return json.dumps(
            self.as_policy(),
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        )


def build_history_chain_from_payloads(
    *,
    entry_payload: Mapping[str, Any],
    journal_payloads: Sequence[Mapping[str, Any]],
    consistency_payloads: Sequence[Mapping[str, Any]] = (),
) -> DecisionHistoryChain:
    """Decode one public simulated chain and bind each input to its source hash."""
    entry = entry_thesis_snapshot_from_payload(dict(entry_payload))
    journals = [
        decision_journal_entry_from_payload(dict(item))
        for item in journal_payloads
    ]
    consistency = [
        investment_consistency_review_from_payload(dict(item))
        for item in consistency_payloads
    ]
    return DecisionHistoryChain(
        symbol=entry.symbol,
        entry=EntryThesisCard.from_snapshot(
            entry,
            source_sha256=_hash_payload(entry_payload),
        ),
        journals=tuple(
            DecisionJournalLine.from_entry(
                item,
                source_sha256=_hash_payload(raw),
            )
            for item, raw in zip(journals, journal_payloads, strict=True)
        ),
        consistency_reviews=tuple(
            ConsistencyReviewCard.from_review(
                item,
                source_sha256=_hash_payload(raw),
            )
            for item, raw in zip(
                consistency, consistency_payloads, strict=True
            )
        ),
    )


def build_decision_history_collection(
    *,
    generated_at: datetime,
    source_id: str,
    chains: Sequence[DecisionHistoryChain],
) -> DecisionHistoryCollection:
    return DecisionHistoryCollection(
        schema_version=M3_HISTORY_SCHEMA,
        generated_at=generated_at,
        source_id=source_id,
        chains=tuple(chains),
        action=ACTION_NO_ORDER,
    )
