"""Explainable M3 decision, entry, journal and consistency contracts.

This module contains no execution semantics. Reviews always require human
confirmation, never generate a position or order, and fail closed when
research, price, capacity or original-thesis evidence is incomplete.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from typing import Any, Iterable, Mapping, Sequence

from .pre_decision_eligibility import (
    PreDecisionEligibility,
    STATUS_ELIGIBLE,
    STATUS_NOT_ELIGIBLE,
)
from .price_attractiveness import (
    PRICE_ATTRACTIVENESS_STATUSES,
    STATUS_KEY_OBSERVATION,
    STATUS_NOT_ASSESSABLE,
    STATUS_RESEARCH_ATTRACTIVE,
    STATUS_WAITING_FOR_BETTER_PRICE,
)


DECISION_SCHEMA = "m3-investment-decision-v2"
LEGACY_DECISION_SCHEMA = "m3-investment-decision-v1"
ACTION_NO_ORDER = "no_order"

STATUS_INSUFFICIENT_RESEARCH = "INSUFFICIENT_RESEARCH"
STATUS_RESEARCH_CANDIDATE = "RESEARCH_CANDIDATE"
STATUS_WATCH = "WATCH"
STATUS_WAIT_FOR_PRICE = "WAIT_FOR_PRICE"
STATUS_MANUAL_BUY_REVIEW = "MANUAL_BUY_REVIEW"
STATUS_MANUAL_ADD_REVIEW = "MANUAL_ADD_REVIEW"
STATUS_HOLD = "HOLD"
STATUS_MANUAL_REDUCE_REVIEW = "MANUAL_REDUCE_REVIEW"
STATUS_MANUAL_EXIT_REVIEW = "MANUAL_EXIT_REVIEW"

DECISION_STATUSES = frozenset(
    {
        STATUS_INSUFFICIENT_RESEARCH,
        STATUS_RESEARCH_CANDIDATE,
        STATUS_WATCH,
        STATUS_WAIT_FOR_PRICE,
        STATUS_MANUAL_BUY_REVIEW,
        STATUS_MANUAL_ADD_REVIEW,
        STATUS_HOLD,
        STATUS_MANUAL_REDUCE_REVIEW,
        STATUS_MANUAL_EXIT_REVIEW,
    }
)

POSITIVE_REVIEW_STATUSES = frozenset(
    {STATUS_MANUAL_BUY_REVIEW, STATUS_MANUAL_ADD_REVIEW}
)
ENTRY_REQUIRED_STATUSES = frozenset(
    {
        STATUS_MANUAL_ADD_REVIEW,
        STATUS_HOLD,
        STATUS_MANUAL_REDUCE_REVIEW,
        STATUS_MANUAL_EXIT_REVIEW,
    }
)

CONFIDENCE_HIGH = "高"
CONFIDENCE_MEDIUM = "中"
CONFIDENCE_LOW = "低"
CONFIDENCE_VALUES = frozenset(
    {CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW}
)
POSITIVE_MINIMUM_CONFIDENCE = frozenset(
    {CONFIDENCE_HIGH, CONFIDENCE_MEDIUM}
)

ENTRY_TYPE_ACTUAL = "actual"
ENTRY_TYPE_SIMULATED = "simulated"
ENTRY_TYPE_RECONSTRUCTED = "reconstructed"
ENTRY_TYPES = frozenset(
    {ENTRY_TYPE_ACTUAL, ENTRY_TYPE_SIMULATED, ENTRY_TYPE_RECONSTRUCTED}
)

HUMAN_CONFIRM_BUY = "CONFIRM_BUY"
HUMAN_CONFIRM_ADD = "CONFIRM_ADD"
HUMAN_CONFIRM_HOLD = "CONFIRM_HOLD"
HUMAN_CONFIRM_REDUCE = "CONFIRM_REDUCE"
HUMAN_CONFIRM_EXIT = "CONFIRM_EXIT"
HUMAN_REJECT = "REJECT"
HUMAN_DEFER = "DEFER"
HUMAN_CANCEL = "CANCEL"
HUMAN_DECISIONS = frozenset(
    {
        HUMAN_CONFIRM_BUY,
        HUMAN_CONFIRM_ADD,
        HUMAN_CONFIRM_HOLD,
        HUMAN_CONFIRM_REDUCE,
        HUMAN_CONFIRM_EXIT,
        HUMAN_REJECT,
        HUMAN_DEFER,
        HUMAN_CANCEL,
    }
)

CONSISTENCY_CONSISTENT = "CONSISTENT"
CONSISTENCY_WEAKENED = "WEAKENED"
CONSISTENCY_BROKEN = "BROKEN"
CONSISTENCY_FULFILLED = "FULFILLED"
CONSISTENCY_STATUSES = frozenset(
    {
        CONSISTENCY_CONSISTENT,
        CONSISTENCY_WEAKENED,
        CONSISTENCY_BROKEN,
        CONSISTENCY_FULFILLED,
    }
)

COMPARISON_NEUTRAL = "NEUTRAL"
COMPARISON_POSITIVE = "POSITIVE"
COMPARISON_NEGATIVE = "NEGATIVE"
COMPARISON_FULFILLED = "FULFILLED"
COMPARISON_BROKEN = "BROKEN"
COMPARISON_IMPACTS = frozenset(
    {
        COMPARISON_NEUTRAL,
        COMPARISON_POSITIVE,
        COMPARISON_NEGATIVE,
        COMPARISON_FULFILLED,
        COMPARISON_BROKEN,
    }
)

DIMENSION_THESIS = "thesis"
DIMENSION_RETURN_DRIVER = "return_driver"
DIMENSION_VALUATION = "valuation"
DIMENSION_RISK = "risk"
DIMENSION_DIVIDEND = "dividend"
DIMENSION_BREAKERS = "breakers"
CONSISTENCY_DIMENSIONS = frozenset(
    {
        DIMENSION_THESIS,
        DIMENSION_RETURN_DRIVER,
        DIMENSION_VALUATION,
        DIMENSION_RISK,
        DIMENSION_DIVIDEND,
        DIMENSION_BREAKERS,
    }
)

POSITIVE_ARTIFACT_TYPES = frozenset(
    {
        "research_case",
        "valuation_assumptions",
        "valuation_result",
        "model_validity",
        "quote_snapshot",
        "price_bridge",
        "price_attractiveness",
        "human_research_approval",
        "event_materiality_review",
        "portfolio_preconditions",
    }
)

_SYMBOL = re.compile(r"^[0-9]{6}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


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


def _optional_datetime(value: object, field: str) -> datetime | None:
    if value is None:
        return None
    return _required_datetime(value, field)


def _optional_decimal(value: object, field: str) -> Decimal | None:
    if value is None:
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError(f"{field} must be a finite decimal") from error
    if not number.is_finite():
        raise ValueError(f"{field} must be a finite decimal")
    return number


def _require_sha256(value: object, field: str) -> str:
    text = _required_text(value, field).lower()
    if not _SHA256.fullmatch(text):
        raise ValueError(f"{field} must be SHA-256 hex")
    return text


def _normalize_refs(refs: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    normalized = tuple(dict(ref) for ref in refs)
    if any(not ref.get("id") for ref in normalized):
        raise ValueError("Evidence references require ids")
    return normalized


def _merge_refs(*groups: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    merged: dict[str, dict[str, Any]] = {}
    for group in groups:
        for raw in group:
            ref = dict(raw)
            ref_id = ref.get("id")
            if not ref_id:
                raise ValueError("Evidence references require ids")
            current = merged.get(ref_id)
            if current is None:
                merged[ref_id] = ref
                continue
            for key, value in ref.items():
                if key in current and current[key] != value:
                    raise ValueError(f"Evidence id conflict: {ref_id}")
                current[key] = value
    return tuple(merged.values())


@dataclass(frozen=True)
class DecisionArtifactReference:
    artifact_type: str
    artifact_id: str
    sha256: str
    schema_version: str
    available_at: date | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "artifact_type", _required_text(self.artifact_type, "artifact_type")
        )
        object.__setattr__(
            self, "artifact_id", _required_text(self.artifact_id, "artifact_id")
        )
        object.__setattr__(
            self, "sha256", _require_sha256(self.sha256, "artifact sha256")
        )
        object.__setattr__(
            self,
            "schema_version",
            _required_text(self.schema_version, "schema_version"),
        )
        object.__setattr__(self, "available_at", _optional_date(self.available_at, "available_at"))

    def as_policy(self) -> dict[str, Any]:
        return {
            "artifact_type": self.artifact_type,
            "artifact_id": self.artifact_id,
            "sha256": self.sha256,
            "schema_version": self.schema_version,
            "available_at": (
                self.available_at.isoformat() if self.available_at is not None else None
            ),
        }


@dataclass(frozen=True)
class DecisionEvidenceBundle:
    bundle_id: str
    symbol: str
    decision_as_of: date
    rule_version: str
    artifact_refs: tuple[DecisionArtifactReference, ...]
    evidence_refs: tuple[dict[str, Any], ...] = ()
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("Decision bundle symbol must contain six digits")
        object.__setattr__(self, "bundle_id", _required_text(self.bundle_id, "bundle_id"))
        object.__setattr__(
            self, "decision_as_of", _required_date(self.decision_as_of, "decision_as_of")
        )
        object.__setattr__(
            self, "rule_version", _required_text(self.rule_version, "rule_version")
        )
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Decision bundle must remain no_order")
        types = [ref.artifact_type for ref in self.artifact_refs]
        if len(types) != len(set(types)):
            raise ValueError("Decision bundle artifact types must be unique")
        object.__setattr__(self, "evidence_refs", _normalize_refs(self.evidence_refs))

    def artifact_types(self) -> set[str]:
        return {ref.artifact_type for ref in self.artifact_refs}

    def has_artifact_types(self, required: Iterable[str]) -> bool:
        return set(required).issubset(self.artifact_types())

    def as_policy(self) -> dict[str, Any]:
        return {
            "schema_version": DECISION_SCHEMA,
            "bundle_id": self.bundle_id,
            "symbol": self.symbol,
            "decision_as_of": self.decision_as_of.isoformat(),
            "rule_version": self.rule_version,
            "artifact_refs": [ref.as_policy() for ref in self.artifact_refs],
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


@dataclass(frozen=True)
class DecisionJournalEntry:
    journal_id: str
    symbol: str
    decision_at: datetime
    review_id: str
    review_status: str
    system_reason: str
    human_decision: str
    human_reason: str
    entry_id: str | None
    confirmed_price: Decimal | None
    namespace: str
    previous_journal_id: str | None = None
    created_at: datetime | None = None
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("Journal symbol must contain six digits")
        for field in (
            "journal_id",
            "review_id",
            "system_reason",
            "human_reason",
        ):
            object.__setattr__(self, field, _required_text(getattr(self, field), field))
        object.__setattr__(
            self, "decision_at", _required_datetime(self.decision_at, "decision_at")
        )
        if self.review_status not in DECISION_STATUSES:
            raise ValueError("Journal review status is unknown")
        if self.human_decision not in HUMAN_DECISIONS:
            raise ValueError("Journal human decision is unknown")
        if self.namespace not in {ENTRY_TYPE_ACTUAL, ENTRY_TYPE_SIMULATED}:
            raise ValueError("Journal namespace must be actual or simulated")
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Journal entry must remain no_order")
        if self.previous_journal_id == self.journal_id:
            raise ValueError("Journal correction cannot link to itself")
        if self.human_decision in {
            HUMAN_CONFIRM_BUY,
            HUMAN_CONFIRM_ADD,
            HUMAN_CONFIRM_HOLD,
            HUMAN_CONFIRM_REDUCE,
            HUMAN_CONFIRM_EXIT,
        } and not self.entry_id:
            raise ValueError("Confirmed decisions require an entry id")
        if (
            self.human_decision
            in {
                HUMAN_CONFIRM_BUY,
                HUMAN_CONFIRM_ADD,
                HUMAN_CONFIRM_REDUCE,
                HUMAN_CONFIRM_EXIT,
            }
            and self.confirmed_price is None
        ):
            raise ValueError("Transaction confirmations require a confirmed price")
        if self.confirmed_price is not None and (
            not self.confirmed_price.is_finite() or self.confirmed_price <= 0
        ):
            raise ValueError("Confirmed price must be a positive finite decimal")
        if self.created_at is not None:
            object.__setattr__(
                self, "created_at", _required_datetime(self.created_at, "created_at")
            )

    def is_correction(self) -> bool:
        return self.previous_journal_id is not None

    def as_policy(self) -> dict[str, Any]:
        return {
            "schema_version": DECISION_SCHEMA,
            "journal_id": self.journal_id,
            "symbol": self.symbol,
            "decision_at": self.decision_at.isoformat(),
            "review_id": self.review_id,
            "review_status": self.review_status,
            "system_reason": self.system_reason,
            "human_decision": self.human_decision,
            "human_reason": self.human_reason,
            "entry_id": self.entry_id,
            "confirmed_price": (
                str(self.confirmed_price) if self.confirmed_price is not None else None
            ),
            "namespace": self.namespace,
            "previous_journal_id": self.previous_journal_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "action": self.action,
        }

    def to_json(self) -> str:
        return json.dumps(
            self.as_policy(),
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        )


@dataclass(frozen=True)
class ConsistencyComparison:
    dimension: str
    original_value: str
    current_value: str
    impact: str
    change_reason: str
    evidence_refs: tuple[dict[str, Any], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "dimension", _required_text(self.dimension, "dimension")
        )
        if self.dimension not in CONSISTENCY_DIMENSIONS:
            raise ValueError("Unknown consistency comparison dimension")
        object.__setattr__(
            self, "original_value", _required_text(self.original_value, "original_value")
        )
        object.__setattr__(
            self, "current_value", _required_text(self.current_value, "current_value")
        )
        if self.impact not in COMPARISON_IMPACTS:
            raise ValueError("Unknown consistency comparison impact")
        if self.impact != COMPARISON_NEUTRAL:
            object.__setattr__(
                self,
                "change_reason",
                _required_text(self.change_reason, "change_reason"),
            )
        else:
            object.__setattr__(self, "change_reason", "")
        object.__setattr__(self, "evidence_refs", _normalize_refs(self.evidence_refs))

    def as_policy(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "original_value": self.original_value,
            "current_value": self.current_value,
            "impact": self.impact,
            "change_reason": self.change_reason,
            "evidence_refs": [dict(ref) for ref in self.evidence_refs],
        }


@dataclass(frozen=True)
class InvestmentConsistencyReview:
    review_id: str
    symbol: str
    entry_id: str
    as_of: date
    status: str
    comparisons: tuple[ConsistencyComparison, ...]
    blockers: tuple[str, ...] = ()
    evidence_refs: tuple[dict[str, Any], ...] = ()
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("Consistency review symbol must contain six digits")
        for field in ("review_id", "entry_id"):
            object.__setattr__(self, field, _required_text(getattr(self, field), field))
        object.__setattr__(self, "as_of", _required_date(self.as_of, "as_of"))
        if self.status not in CONSISTENCY_STATUSES:
            raise ValueError("Unknown consistency status")
        if not self.comparisons:
            raise ValueError("Consistency review requires comparisons")
        if self.status != aggregate_consistency_status(self.comparisons):
            raise ValueError("Consistency status does not match its comparisons")
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Consistency review must remain no_order")
        object.__setattr__(self, "blockers", tuple(self.blockers))
        object.__setattr__(self, "evidence_refs", _normalize_refs(self.evidence_refs))

    def as_policy(self) -> dict[str, Any]:
        return {
            "schema_version": DECISION_SCHEMA,
            "review_id": self.review_id,
            "symbol": self.symbol,
            "entry_id": self.entry_id,
            "as_of": self.as_of.isoformat(),
            "status": self.status,
            "comparisons": [item.as_policy() for item in self.comparisons],
            "blockers": list(self.blockers),
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


def aggregate_consistency_status(
    comparisons: Sequence[ConsistencyComparison],
) -> str:
    if not comparisons:
        raise ValueError("Consistency aggregation requires comparisons")
    impacts = {item.impact for item in comparisons}
    if COMPARISON_BROKEN in impacts:
        return CONSISTENCY_BROKEN
    if COMPARISON_NEGATIVE in impacts:
        return CONSISTENCY_WEAKENED
    if impacts == {COMPARISON_FULFILLED}:
        return CONSISTENCY_FULFILLED
    return CONSISTENCY_CONSISTENT


DECISION_INTENTS = frozenset({"buy", "add", "hold", "reduce", "exit"})
_PRICE_BLOCKER_PREFIXES = ("price_", "quote_")


def _predecision_reason(
    predecision: PreDecisionEligibility,
) -> str | None:
    if predecision.status == STATUS_ELIGIBLE:
        return None
    research_blockers = [
        blocker
        for blocker in predecision.blockers
        if not blocker.startswith(_PRICE_BLOCKER_PREFIXES)
    ]
    if research_blockers:
        return STATUS_INSUFFICIENT_RESEARCH
    return STATUS_WAIT_FOR_PRICE


def evaluate_investment_decision(
    *,
    predecision: PreDecisionEligibility,
    bundle: DecisionEvidenceBundle,
    decision_as_of: date,
    decision_intent: str | None,
    confidence: str | None = None,
    portfolio_preconditions: MinimalPortfolioPreconditions | None = None,
    entry: EntryThesisSnapshot | None = None,
    reason: str | None = None,
    rule_version: str = "m3-decision-v1",
    created_at: datetime | None = None,
) -> InvestmentDecisionReview:
    if predecision.decision_as_of != decision_as_of:
        raise ValueError("Predecision date must match decision review date")
    if bundle.symbol != predecision.symbol or bundle.decision_as_of != decision_as_of:
        raise ValueError("Decision bundle identity must match predecision")
    if entry is not None and entry.symbol != predecision.symbol:
        raise ValueError("Entry snapshot must match decision symbol")
    if decision_intent is not None and decision_intent not in DECISION_INTENTS:
        raise ValueError("Unknown decision intent")
    if confidence is not None and confidence not in CONFIDENCE_VALUES:
        raise ValueError("Unknown decision confidence")

    portfolio = portfolio_preconditions or MinimalPortfolioPreconditions.missing()
    blockers = list(predecision.blockers)
    reasons: list[str] = []
    entry_id = entry.entry_id if entry is not None else None
    status = STATUS_WATCH
    summary = "研究已形成，等待明确的人工决策意图或前置条件。"

    if predecision.status == STATUS_NOT_ELIGIBLE:
        reason_status = _predecision_reason(predecision)
        if reason_status == STATUS_INSUFFICIENT_RESEARCH:
            status = STATUS_INSUFFICIENT_RESEARCH
            summary = "研究或估值前置条件不完整，不能进入正向决策复核。"
        else:
            status = STATUS_WAIT_FOR_PRICE
            summary = "研究前置已满足，但当前价格/报价链尚未合法形成。"

    if decision_intent is None:
        blockers.append("decision_intent_not_provided")
        return InvestmentDecisionReview(
            review_id=f"{predecision.symbol}-{decision_as_of.isoformat()}-watch-{rule_version}",
            symbol=predecision.symbol,
            decision_as_of=decision_as_of,
            status=STATUS_WATCH if status != STATUS_INSUFFICIENT_RESEARCH else status,
            summary=summary,
            reasons=tuple(reasons),
            blockers=tuple(dict.fromkeys(blockers)),
            confidence=confidence,
            bundle=bundle,
            predecision_status=predecision.status,
            portfolio_preconditions=portfolio,
            entry_id=entry_id,
            created_at=created_at or datetime.now(timezone.utc),
            rule_version=rule_version,
            price_attractiveness_status=predecision.price_attractiveness_status,
        )

    if decision_intent in {"reduce", "exit"}:
        if entry is None:
            blockers.append("original_entry_missing")
            status = STATUS_WATCH
            summary = "减仓或退出复核必须引用原始 Entry Thesis。"
        elif not reason:
            blockers.append("decision_reason_missing")
            status = STATUS_WATCH
            summary = "减仓或退出需要明确 fundamental、valuation 或机会成本理由。"
        else:
            status = (
                STATUS_MANUAL_EXIT_REVIEW
                if decision_intent == "exit"
                else STATUS_MANUAL_REDUCE_REVIEW
            )
            summary = reason
            reasons.append(reason)
        return InvestmentDecisionReview(
            review_id=(
                f"{predecision.symbol}-{decision_as_of.isoformat()}-"
                f"{decision_intent}-{rule_version}"
            ),
            symbol=predecision.symbol,
            decision_as_of=decision_as_of,
            status=status,
            summary=summary,
            reasons=tuple(reasons),
            blockers=tuple(dict.fromkeys(blockers)),
            confidence=confidence,
            bundle=bundle,
            predecision_status=predecision.status,
            portfolio_preconditions=portfolio,
            entry_id=entry_id,
            created_at=created_at or datetime.now(timezone.utc),
            rule_version=rule_version,
            price_attractiveness_status=predecision.price_attractiveness_status,
        )

    if predecision.status != STATUS_ELIGIBLE:
        return InvestmentDecisionReview(
            review_id=(
                f"{predecision.symbol}-{decision_as_of.isoformat()}-"
                f"{decision_intent}-{rule_version}"
            ),
            symbol=predecision.symbol,
            decision_as_of=decision_as_of,
            status=status,
            summary=summary,
            reasons=tuple(reasons),
            blockers=tuple(dict.fromkeys(blockers)),
            confidence=confidence,
            bundle=bundle,
            predecision_status=predecision.status,
            portfolio_preconditions=portfolio,
            entry_id=entry_id,
            created_at=created_at or datetime.now(timezone.utc),
            rule_version=rule_version,
            price_attractiveness_status=predecision.price_attractiveness_status,
        )

    if decision_intent in {"buy", "add"} and not predecision.positive_price_review_eligible:
        blockers.append("positive_price_review_not_eligible")
        if predecision.price_attractiveness_status == STATUS_NOT_ASSESSABLE:
            status = STATUS_INSUFFICIENT_RESEARCH
            summary = "当前价格吸引力不可评估，不能进入 BUY / ADD 人工复核。"
        elif predecision.price_attractiveness_status == STATUS_WAITING_FOR_BETTER_PRICE:
            status = STATUS_WAIT_FOR_PRICE
            summary = "研究可评估但当前价格仍等待更有吸引力的条件，不能进入 BUY / ADD 人工复核。"
        else:
            status = STATUS_WATCH
            summary = "当前价格状态仅为观察或缺乏吸引力，不能进入 BUY / ADD 人工复核。"
        return InvestmentDecisionReview(
            review_id=(
                f"{predecision.symbol}-{decision_as_of.isoformat()}-"
                f"{decision_intent}-{rule_version}"
            ),
            symbol=predecision.symbol,
            decision_as_of=decision_as_of,
            status=status,
            summary=summary,
            reasons=tuple(reasons),
            blockers=tuple(dict.fromkeys(blockers)),
            confidence=confidence,
            bundle=bundle,
            predecision_status=predecision.status,
            portfolio_preconditions=portfolio,
            entry_id=entry_id,
            created_at=created_at or datetime.now(timezone.utc),
            rule_version=rule_version,
            price_attractiveness_status=predecision.price_attractiveness_status,
        )

    if not portfolio.allows_positive_review():
        blockers.extend(portfolio.blockers)
        status = STATUS_WATCH
        summary = "缺少人工确认的组合容量前置，不能形成个人化正向复核。"
        return InvestmentDecisionReview(
            review_id=(
                f"{predecision.symbol}-{decision_as_of.isoformat()}-"
                f"{decision_intent}-{rule_version}"
            ),
            symbol=predecision.symbol,
            decision_as_of=decision_as_of,
            status=status,
            summary=summary,
            reasons=tuple(reasons),
            blockers=tuple(dict.fromkeys(blockers)),
            confidence=confidence,
            bundle=bundle,
            predecision_status=predecision.status,
            portfolio_preconditions=portfolio,
            entry_id=entry_id,
            created_at=created_at or datetime.now(timezone.utc),
            rule_version=rule_version,
            price_attractiveness_status=predecision.price_attractiveness_status,
        )

    if decision_intent == "buy":
        if entry is not None:
            blockers.append("existing_entry_conflicts_with_new_buy_review")
            status = STATUS_WATCH
        else:
            status = STATUS_MANUAL_BUY_REVIEW
            summary = "研究、价格与容量前置均满足，进入人工买入理由复核。"
    elif decision_intent == "add":
        if entry is None:
            blockers.append("original_entry_missing")
            status = STATUS_WATCH
        elif not reason:
            blockers.append("add_reason_missing")
            status = STATUS_WATCH
        else:
            status = STATUS_MANUAL_ADD_REVIEW
            summary = reason
            reasons.append(reason)
    elif decision_intent == "hold":
        if entry is None:
            blockers.append("original_entry_missing")
            status = STATUS_WATCH
        elif not reason:
            blockers.append("hold_reason_missing")
            status = STATUS_WATCH
        else:
            status = STATUS_HOLD
            summary = reason
            reasons.append(reason)
    else:
        blockers.append("unsupported_decision_intent")

    if status in POSITIVE_REVIEW_STATUSES:
        if confidence not in POSITIVE_MINIMUM_CONFIDENCE:
            blockers.append("positive_review_confidence_below_policy")
            status = STATUS_WATCH
        if not bundle.has_artifact_types(POSITIVE_ARTIFACT_TYPES):
            blockers.append("positive_review_evidence_bundle_incomplete")
            status = STATUS_WATCH

    return InvestmentDecisionReview(
        review_id=(
            f"{predecision.symbol}-{decision_as_of.isoformat()}-"
            f"{decision_intent}-{rule_version}"
        ),
        symbol=predecision.symbol,
        decision_as_of=decision_as_of,
        status=status,
        summary=summary,
        reasons=tuple(reasons),
        blockers=tuple(dict.fromkeys(blockers)),
        confidence=confidence,
        bundle=bundle,
        predecision_status=predecision.status,
        portfolio_preconditions=portfolio,
        entry_id=entry_id,
            created_at=created_at or datetime.now(timezone.utc),
            rule_version=rule_version,
            price_attractiveness_status=predecision.price_attractiveness_status,
        )


def decision_artifact_reference_from_payload(
    payload: Mapping[str, Any],
) -> DecisionArtifactReference:
    data = dict(payload)
    raw_date = data.get("available_at")
    return DecisionArtifactReference(
        artifact_type=str(data["artifact_type"]),
        artifact_id=str(data["artifact_id"]),
        sha256=str(data["sha256"]),
        schema_version=str(data["schema_version"]),
        available_at=(
            date.fromisoformat(str(raw_date)) if raw_date is not None else None
        ),
    )


def decision_evidence_bundle_from_payload(
    payload: Mapping[str, Any],
) -> DecisionEvidenceBundle:
    data = dict(payload)
    if data.get("schema_version") not in {DECISION_SCHEMA, LEGACY_DECISION_SCHEMA}:
        raise ValueError("Unknown decision evidence bundle schema")
    return DecisionEvidenceBundle(
        bundle_id=str(data["bundle_id"]),
        symbol=str(data["symbol"]),
        decision_as_of=date.fromisoformat(str(data["decision_as_of"])),
        rule_version=str(data["rule_version"]),
        artifact_refs=tuple(
            decision_artifact_reference_from_payload(item)
            for item in data.get("artifact_refs") or ()
        ),
        evidence_refs=tuple(dict(item) for item in data.get("evidence_refs") or ()),
        action=str(data.get("action", ACTION_NO_ORDER)),
    )


def minimal_portfolio_preconditions_from_payload(
    payload: Mapping[str, Any],
) -> MinimalPortfolioPreconditions:
    data = dict(payload)
    if data.get("schema_version") not in {DECISION_SCHEMA, LEGACY_DECISION_SCHEMA}:
        raise ValueError("Unknown portfolio preconditions schema")
    confirmed_at = data.get("confirmed_at")
    return MinimalPortfolioPreconditions(
        provided=bool(data["provided"]),
        context_scope=str(data.get("context_scope") or ""),
        capacity_confirmed=bool(data.get("capacity_confirmed")),
        confirmed_at=(
            datetime.fromisoformat(str(confirmed_at))
            if confirmed_at is not None
            else None
        ),
        blockers=tuple(str(item) for item in data.get("blockers") or ()),
        evidence_refs=tuple(dict(item) for item in data.get("evidence_refs") or ()),
        action=str(data.get("action", ACTION_NO_ORDER)),
    )


def investment_decision_review_from_payload(
    payload: Mapping[str, Any],
) -> InvestmentDecisionReview:
    data = dict(payload)
    if data.get("schema_version") not in {DECISION_SCHEMA, LEGACY_DECISION_SCHEMA}:
        raise ValueError("Unknown investment decision review schema")
    return InvestmentDecisionReview(
        review_id=str(data["review_id"]),
        symbol=str(data["symbol"]),
        decision_as_of=date.fromisoformat(str(data["decision_as_of"])),
        status=str(data["status"]),
        summary=str(data["summary"]),
        reasons=tuple(str(item) for item in data.get("reasons") or ()),
        blockers=tuple(str(item) for item in data.get("blockers") or ()),
        confidence=(
            str(data["confidence"]) if data.get("confidence") is not None else None
        ),
        bundle=decision_evidence_bundle_from_payload(data["bundle"]),
        predecision_status=str(data["predecision_status"]),
        portfolio_preconditions=minimal_portfolio_preconditions_from_payload(
            data["portfolio_preconditions"]
        ),
        entry_id=(
            str(data["entry_id"]) if data.get("entry_id") is not None else None
        ),
        created_at=datetime.fromisoformat(str(data["created_at"])),
        rule_version=str(data["rule_version"]),
        price_attractiveness_status=str(
            data.get("price_attractiveness_status", STATUS_NOT_ASSESSABLE)
        ),
        requires_human_review=bool(data.get("requires_human_review", True)),
        action=str(data.get("action", ACTION_NO_ORDER)),
    )


def entry_thesis_snapshot_from_payload(
    payload: Mapping[str, Any],
) -> EntryThesisSnapshot:
    data = dict(payload)
    if data.get("schema_version") not in {DECISION_SCHEMA, LEGACY_DECISION_SCHEMA}:
        raise ValueError("Unknown entry thesis snapshot schema")

    def decimal_value(field: str) -> Decimal | None:
        raw = data.get(field)
        return _optional_decimal(raw, field)

    created_at = data.get("created_at")
    return EntryThesisSnapshot(
        entry_id=str(data["entry_id"]),
        symbol=str(data["symbol"]),
        confirmed_at=datetime.fromisoformat(str(data["confirmed_at"])),
        entry_type=str(data["entry_type"]),
        entry_date=date.fromisoformat(str(data["entry_date"])),
        entry_price=decimal_value("entry_price"),
        review_id=str(data["review_id"]),
        bundle_id=str(data["bundle_id"]),
        thesis=str(data["thesis"]),
        return_driver=str(data["return_driver"]),
        mispricing_hypothesis=str(data["mispricing_hypothesis"]),
        bear_value=decimal_value("bear_value"),
        base_value=decimal_value("base_value"),
        bull_value=decimal_value("bull_value"),
        confidence=str(data["confidence"]),
        dividend_thesis=str(data["dividend_thesis"]),
        hold_logic=str(data["hold_logic"]),
        risks=tuple(str(item) for item in data.get("risks") or ()),
        counter_evidence=tuple(
            str(item) for item in data.get("counter_evidence") or ()
        ),
        breakers=tuple(str(item) for item in data.get("breakers") or ()),
        catalysts=tuple(str(item) for item in data.get("catalysts") or ()),
        reasons_to_add=tuple(
            str(item) for item in data.get("reasons_to_add") or ()
        ),
        reasons_not_to_add=tuple(
            str(item) for item in data.get("reasons_not_to_add") or ()
        ),
        reasons_to_reduce=tuple(
            str(item) for item in data.get("reasons_to_reduce") or ()
        ),
        reasons_to_exit=tuple(
            str(item) for item in data.get("reasons_to_exit") or ()
        ),
        reconstructed_note=str(data.get("reconstructed_note") or ""),
        created_at=(
            datetime.fromisoformat(str(created_at))
            if created_at is not None
            else None
        ),
        action=str(data.get("action", ACTION_NO_ORDER)),
    )


def decision_journal_entry_from_payload(
    payload: Mapping[str, Any],
) -> DecisionJournalEntry:
    data = dict(payload)
    if data.get("schema_version") not in {DECISION_SCHEMA, LEGACY_DECISION_SCHEMA}:
        raise ValueError("Unknown decision journal schema")
    created_at = data.get("created_at")
    return DecisionJournalEntry(
        journal_id=str(data["journal_id"]),
        symbol=str(data["symbol"]),
        decision_at=datetime.fromisoformat(str(data["decision_at"])),
        review_id=str(data["review_id"]),
        review_status=str(data["review_status"]),
        system_reason=str(data["system_reason"]),
        human_decision=str(data["human_decision"]),
        human_reason=str(data["human_reason"]),
        entry_id=(
            str(data["entry_id"]) if data.get("entry_id") is not None else None
        ),
        confirmed_price=_optional_decimal(data.get("confirmed_price"), "confirmed_price"),
        namespace=str(data["namespace"]),
        previous_journal_id=(
            str(data["previous_journal_id"])
            if data.get("previous_journal_id") is not None
            else None
        ),
        created_at=(
            datetime.fromisoformat(str(created_at))
            if created_at is not None
            else None
        ),
        action=str(data.get("action", ACTION_NO_ORDER)),
    )


def consistency_comparison_from_payload(
    payload: Mapping[str, Any],
) -> ConsistencyComparison:
    data = dict(payload)
    return ConsistencyComparison(
        dimension=str(data["dimension"]),
        original_value=str(data["original_value"]),
        current_value=str(data["current_value"]),
        impact=str(data["impact"]),
        change_reason=str(data.get("change_reason") or ""),
        evidence_refs=tuple(dict(item) for item in data.get("evidence_refs") or ()),
    )


def investment_consistency_review_from_payload(
    payload: Mapping[str, Any],
) -> InvestmentConsistencyReview:
    data = dict(payload)
    if data.get("schema_version") not in {DECISION_SCHEMA, LEGACY_DECISION_SCHEMA}:
        raise ValueError("Unknown investment consistency review schema")
    return InvestmentConsistencyReview(
        review_id=str(data["review_id"]),
        symbol=str(data["symbol"]),
        entry_id=str(data["entry_id"]),
        as_of=date.fromisoformat(str(data["as_of"])),
        status=str(data["status"]),
        comparisons=tuple(
            consistency_comparison_from_payload(item)
            for item in data.get("comparisons") or ()
        ),
        blockers=tuple(str(item) for item in data.get("blockers") or ()),
        evidence_refs=tuple(dict(item) for item in data.get("evidence_refs") or ()),
        action=str(data.get("action", ACTION_NO_ORDER)),
    )


@dataclass(frozen=True)
class MinimalPortfolioPreconditions:
    provided: bool
    context_scope: str
    capacity_confirmed: bool
    confirmed_at: datetime | None
    blockers: tuple[str, ...] = ()
    evidence_refs: tuple[dict[str, Any], ...] = ()
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Portfolio preconditions must remain no_order")
        if not isinstance(self.provided, bool):
            raise ValueError("portfolio provided must be boolean")
        blockers = list(self.blockers)
        if self.provided:
            object.__setattr__(
                self, "context_scope", _required_text(self.context_scope, "context_scope")
            )
            object.__setattr__(
                self, "confirmed_at", _required_datetime(self.confirmed_at, "confirmed_at")
            )
            if not isinstance(self.capacity_confirmed, bool):
                raise ValueError("capacity_confirmed must be boolean")
            if not self.capacity_confirmed:
                blockers.append("portfolio_capacity_not_confirmed")
        else:
            object.__setattr__(self, "context_scope", "missing")
            object.__setattr__(self, "capacity_confirmed", False)
            object.__setattr__(self, "confirmed_at", None)
            blockers.append("portfolio_input_missing")
        object.__setattr__(self, "blockers", tuple(dict.fromkeys(blockers)))
        object.__setattr__(self, "evidence_refs", _normalize_refs(self.evidence_refs))

    @classmethod
    def missing(cls) -> MinimalPortfolioPreconditions:
        return cls(
            provided=False,
            context_scope="",
            capacity_confirmed=False,
            confirmed_at=None,
        )

    def allows_positive_review(self) -> bool:
        return (
            self.provided
            and self.capacity_confirmed
            and self.confirmed_at is not None
            and not self.blockers
        )

    def to_json(self) -> str:
        return json.dumps(
            self.as_policy(),
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        )

    def as_policy(self) -> dict[str, Any]:
        return {
            "schema_version": DECISION_SCHEMA,
            "provided": self.provided,
            "context_scope": self.context_scope,
            "capacity_confirmed": self.capacity_confirmed,
            "confirmed_at": (
                self.confirmed_at.isoformat() if self.confirmed_at is not None else None
            ),
            "blockers": list(self.blockers),
            "evidence_refs": [dict(ref) for ref in self.evidence_refs],
            "action": self.action,
        }


@dataclass(frozen=True)
class InvestmentDecisionReview:
    review_id: str
    symbol: str
    decision_as_of: date
    status: str
    summary: str
    reasons: tuple[str, ...]
    blockers: tuple[str, ...]
    confidence: str | None
    bundle: DecisionEvidenceBundle
    predecision_status: str
    portfolio_preconditions: MinimalPortfolioPreconditions
    entry_id: str | None
    created_at: datetime
    rule_version: str
    price_attractiveness_status: str
    requires_human_review: bool = True
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("Decision review symbol must contain six digits")
        object.__setattr__(self, "review_id", _required_text(self.review_id, "review_id"))
        object.__setattr__(
            self, "decision_as_of", _required_date(self.decision_as_of, "decision_as_of")
        )
        if self.status not in DECISION_STATUSES:
            raise ValueError("Unknown investment decision status")
        object.__setattr__(self, "summary", _required_text(self.summary, "summary"))
        object.__setattr__(
            self, "rule_version", _required_text(self.rule_version, "rule_version")
        )
        object.__setattr__(
            self, "created_at", _required_datetime(self.created_at, "created_at")
        )
        if self.bundle.symbol != self.symbol or self.bundle.decision_as_of != self.decision_as_of:
            raise ValueError("Decision bundle identity must match the review")
        if self.predecision_status not in {STATUS_ELIGIBLE, STATUS_NOT_ELIGIBLE}:
            raise ValueError("Unknown predecision status in decision review")
        if self.price_attractiveness_status not in PRICE_ATTRACTIVENESS_STATUSES:
            raise ValueError("Unknown price attractiveness status in decision review")
        if not self.requires_human_review:
            raise ValueError("M3 reviews always require human confirmation")
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Decision review must remain no_order")
        object.__setattr__(self, "blockers", tuple(self.blockers))
        object.__setattr__(self, "reasons", tuple(self.reasons))
        if self.confidence is not None and self.confidence not in CONFIDENCE_VALUES:
            raise ValueError("Unknown decision confidence")
        if self.status in ENTRY_REQUIRED_STATUSES and not self.entry_id:
            raise ValueError(f"{self.status} requires the original entry id")
        if self.status in POSITIVE_REVIEW_STATUSES:
            if self.predecision_status != STATUS_ELIGIBLE:
                raise ValueError("Positive review requires predecision eligibility")
            if self.price_attractiveness_status != STATUS_RESEARCH_ATTRACTIVE:
                raise ValueError("Positive review requires RESEARCH_ATTRACTIVE price status")
            if not self.portfolio_preconditions.allows_positive_review():
                raise ValueError("Positive review requires confirmed portfolio capacity")
            if self.confidence not in POSITIVE_MINIMUM_CONFIDENCE:
                raise ValueError("Positive review requires medium or high confidence")
            if self.blockers:
                raise ValueError("Positive review cannot carry blockers")
            if not self.bundle.has_artifact_types(POSITIVE_ARTIFACT_TYPES):
                raise ValueError("Positive review evidence bundle is incomplete")

    def is_positive_review(self) -> bool:
        return self.status in POSITIVE_REVIEW_STATUSES

    def as_policy(self) -> dict[str, Any]:
        return {
            "schema_version": DECISION_SCHEMA,
            "review_id": self.review_id,
            "symbol": self.symbol,
            "decision_as_of": self.decision_as_of.isoformat(),
            "status": self.status,
            "summary": self.summary,
            "reasons": list(self.reasons),
            "blockers": list(self.blockers),
            "confidence": self.confidence,
            "bundle": self.bundle.as_policy(),
            "predecision_status": self.predecision_status,
            "portfolio_preconditions": self.portfolio_preconditions.as_policy(),
            "entry_id": self.entry_id,
            "created_at": self.created_at.isoformat(),
            "rule_version": self.rule_version,
            "price_attractiveness_status": self.price_attractiveness_status,
            "requires_human_review": self.requires_human_review,
            "action": self.action,
        }

    @property
    def decision_review_sha256(self) -> str:
        payload = json.dumps(
            self.as_policy(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_json(self) -> str:
        return json.dumps(
            self.as_policy(),
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        )


@dataclass(frozen=True)
class EntryThesisSnapshot:
    entry_id: str
    symbol: str
    confirmed_at: datetime
    entry_type: str
    entry_date: date
    entry_price: Decimal | None
    review_id: str
    bundle_id: str
    thesis: str
    return_driver: str
    mispricing_hypothesis: str
    bear_value: Decimal | None
    base_value: Decimal | None
    bull_value: Decimal | None
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
    reconstructed_note: str = ""
    created_at: datetime | None = None
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("Entry snapshot symbol must contain six digits")
        for field in (
            "entry_id",
            "review_id",
            "bundle_id",
            "thesis",
            "return_driver",
            "mispricing_hypothesis",
            "dividend_thesis",
            "hold_logic",
        ):
            object.__setattr__(self, field, _required_text(getattr(self, field), field))
        object.__setattr__(self, "confirmed_at", _required_datetime(self.confirmed_at, "confirmed_at"))
        object.__setattr__(self, "entry_date", _required_date(self.entry_date, "entry_date"))
        if self.entry_type not in ENTRY_TYPES:
            raise ValueError("Unknown entry type")
        if self.entry_date > self.confirmed_at.date():
            raise ValueError("Entry date cannot be after human confirmation")
        if self.confidence not in CONFIDENCE_VALUES:
            raise ValueError("Entry confidence must be 高, 中 or 低")
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Entry snapshot must remain no_order")
        values = (self.bear_value, self.base_value, self.bull_value)
        if any(value is not None and (not value.is_finite() or value <= 0) for value in values):
            raise ValueError("Entry scenario values must be positive finite decimals")
        if all(value is not None for value in values) and not (
            self.bear_value <= self.base_value <= self.bull_value
        ):
            raise ValueError("Entry scenarios must be bear <= base <= bull")
        if self.entry_type == ENTRY_TYPE_RECONSTRUCTED:
            object.__setattr__(
                self,
                "reconstructed_note",
                _required_text(self.reconstructed_note, "reconstructed_note"),
            )
        else:
            if self.entry_price is None:
                raise ValueError("Confirmed actual or simulated entries require a price")
            object.__setattr__(self, "reconstructed_note", "")
        if self.created_at is not None:
            object.__setattr__(
                self, "created_at", _required_datetime(self.created_at, "created_at")
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

    def as_policy(self) -> dict[str, Any]:
        def scenario(value: Decimal | None) -> str | None:
            return str(value) if value is not None else None

        return {
            "schema_version": DECISION_SCHEMA,
            "entry_id": self.entry_id,
            "symbol": self.symbol,
            "confirmed_at": self.confirmed_at.isoformat(),
            "entry_type": self.entry_type,
            "entry_date": self.entry_date.isoformat(),
            "entry_price": scenario(self.entry_price),
            "review_id": self.review_id,
            "bundle_id": self.bundle_id,
            "thesis": self.thesis,
            "return_driver": self.return_driver,
            "mispricing_hypothesis": self.mispricing_hypothesis,
            "bear_value": scenario(self.bear_value),
            "base_value": scenario(self.base_value),
            "bull_value": scenario(self.bull_value),
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
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "action": self.action,
        }

    def to_json(self) -> str:
        return json.dumps(
            self.as_policy(),
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        )
