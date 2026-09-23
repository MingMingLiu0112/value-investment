"""Fail-closed M4 position ceilings and portfolio budget constraints.

This domain consumes a human-confirmed IPS, a reconciled snapshot and explicit
pre-registered tier caps. It reports whether a security has research, price,
event and approval preconditions, then derives only a ceiling and budget
status. It never emits a target weight, position size, order or allocation
decision; humans remain the only source of executable choices.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import json
import re
from typing import Any, Mapping, Sequence

from .investment_decision import (
    ACTION_NO_ORDER,
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_VALUES,
)
from .portfolio_contracts import (
    CONFIRMATION_DRAFT,
    CONFIRMATION_HUMAN,
    NAMESPACE_ACTUAL,
    NAMESPACE_SIMULATED,
    QUANTITY_HUMAN_CONFIRMED,
    PortfolioInputBundle,
)
from .portfolio_risk import (
    LIQUIDITY_LIQUID,
    LIQUIDITY_RESTRICTED,
    LIQUIDITY_UNKNOWN,
    LIQUIDITY_PROFILES,
)


SCHEMA_VERSION = "m4-position-guidance-v1"

STATUS_INCOMPLETE = "INCOMPLETE"
STATUS_READY = "READY"
STATUS_PARTIAL = "PARTIAL"
STATUS_BUDGET_CONFLICT = "BUDGET_CONFLICT"
STATUS_REVIEW_REQUIRED = "REVIEW_REQUIRED"
STATUS_NO_ACTIONABLE_CAPACITY = "NO_ACTIONABLE_CAPACITY"
STATUSES = frozenset(
    {
        STATUS_INCOMPLETE,
        STATUS_READY,
        STATUS_PARTIAL,
        STATUS_BUDGET_CONFLICT,
        STATUS_REVIEW_REQUIRED,
        STATUS_NO_ACTIONABLE_CAPACITY,
    }
)

TIER_NONE = "NONE"
TIER_STARTER = "STARTER"
TIER_NORMAL = "NORMAL"
TIER_MAX = "MAX"
TIERS = frozenset({TIER_NONE, TIER_STARTER, TIER_NORMAL, TIER_MAX})

LINE_WAIT = "WAIT"
LINE_ELIGIBLE = "ELIGIBLE"
LINE_REVIEW_REQUIRED = "REVIEW_REQUIRED"
LINE_STATUSES = frozenset({LINE_WAIT, LINE_ELIGIBLE, LINE_REVIEW_REQUIRED})

INTENT_BUY = "BUY_REVIEW"
INTENT_ADD = "ADD_REVIEW"
INTENT_HOLD = "HOLD_REVIEW"
INTENTS = frozenset({INTENT_BUY, INTENT_ADD, INTENT_HOLD})

BUDGET_AVAILABLE = "AVAILABLE"
BUDGET_CONSTRAINED = "CONSTRAINED"
BUDGET_EXHAUSTED = "EXHAUSTED"
BUDGET_NOT_APPLICABLE = "NOT_APPLICABLE"
BUDGET_STATUSES = frozenset(
    {
        BUDGET_AVAILABLE,
        BUDGET_CONSTRAINED,
        BUDGET_EXHAUSTED,
        BUDGET_NOT_APPLICABLE,
    }
)

_SYMBOL = re.compile(r"^[0-9]{6}$")
_FORBIDDEN_PUBLIC_KEYS = {
    "buy",
    "sell",
    "target_weight",
    "position_size",
    "order_quantity",
    "proposed_entry",
    "live_eligible",
}


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _optional_text(value: object, field: str) -> str | None:
    return None if value is None else _required_text(value, field)


def _decimal(value: object, field: str) -> Decimal:
    if isinstance(value, Decimal):
        parsed = value
    elif isinstance(value, (int, str)):
        try:
            parsed = Decimal(str(value))
        except (InvalidOperation, ValueError) as error:
            raise ValueError(f"{field} must be a finite decimal") from error
    else:
        raise ValueError(f"{field} must be a finite decimal")
    if not parsed.is_finite():
        raise ValueError(f"{field} must be a finite decimal")
    return parsed


def _optional_decimal(value: object, field: str) -> Decimal | None:
    return None if value is None else _decimal(value, field)


def _decimal_text(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _percentage(value: object, field: str) -> Decimal:
    parsed = _decimal(value, field)
    if not Decimal("0") < parsed <= Decimal("100"):
        raise ValueError(f"{field} must be in (0, 100]")
    return parsed


def _percentage_or_zero(value: object, field: str) -> Decimal:
    parsed = _decimal(value, field)
    if not Decimal("0") <= parsed <= Decimal("100"):
        raise ValueError(f"{field} must be in [0, 100]")
    return parsed


def _date(value: object, field: str) -> date:
    if not isinstance(value, date) or isinstance(value, datetime):
        raise ValueError(f"{field} must be a date")
    return value


def _datetime(value: object, field: str) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"{field} must be a timezone-aware datetime")
    return value


def _normalize_refs(refs: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    normalized = []
    for index, ref in enumerate(refs):
        if not isinstance(ref, Mapping):
            raise ValueError(f"Evidence ref {index} must be an object")
        payload = dict(ref)
        if not isinstance(payload.get("id"), str) or not payload["id"].strip():
            raise ValueError(f"Evidence ref {index} requires an id")
        payload["id"] = payload["id"].strip()
        normalized.append(payload)
    return tuple(normalized)


def _reject_public_execution_keys(value: Mapping[str, Any]) -> None:
    forbidden = sorted(_FORBIDDEN_PUBLIC_KEYS & set(value))
    if forbidden:
        raise ValueError(f"Guidance payload contains execution keys: {', '.join(forbidden)}")


@dataclass(frozen=True)
class PositionTierPolicy:
    """Explicitly confirmed cap schedule; no default tier fractions are used."""

    policy_id: str
    policy_version: str
    as_of: date
    confirmation_status: str
    confirmed_at: datetime | None
    starter_cap_pct: Decimal
    normal_cap_pct: Decimal
    max_cap_pct: Decimal
    evidence_refs: tuple[dict[str, Any], ...] = ()
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", _required_text(self.policy_id, "policy_id"))
        object.__setattr__(
            self,
            "policy_version",
            _required_text(self.policy_version, "policy_version"),
        )
        object.__setattr__(self, "as_of", _date(self.as_of, "as_of"))
        if self.confirmation_status not in {CONFIRMATION_DRAFT, CONFIRMATION_HUMAN}:
            raise ValueError("Unknown position tier confirmation status")
        if self.confirmation_status == CONFIRMATION_HUMAN:
            object.__setattr__(
                self,
                "confirmed_at",
                _datetime(self.confirmed_at, "confirmed_at"),
            )
            if not self.evidence_refs:
                raise ValueError("Confirmed tier policy requires evidence")
        elif self.confirmed_at is not None:
            raise ValueError("Draft tier policy cannot carry confirmed_at")
        if self.confirmation_status == CONFIRMATION_DRAFT:
            starter = _percentage_or_zero(self.starter_cap_pct, "starter_cap_pct")
            normal = _percentage_or_zero(self.normal_cap_pct, "normal_cap_pct")
            maximum = _percentage_or_zero(self.max_cap_pct, "max_cap_pct")
        else:
            starter = _percentage(self.starter_cap_pct, "starter_cap_pct")
            normal = _percentage(self.normal_cap_pct, "normal_cap_pct")
            maximum = _percentage(self.max_cap_pct, "max_cap_pct")
        object.__setattr__(self, "starter_cap_pct", starter)
        object.__setattr__(self, "normal_cap_pct", normal)
        object.__setattr__(self, "max_cap_pct", maximum)
        if not self.starter_cap_pct <= self.normal_cap_pct <= self.max_cap_pct:
            raise ValueError("Tier caps must be starter <= normal <= max")
        object.__setattr__(self, "evidence_refs", _normalize_refs(self.evidence_refs))
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Position tier policy must remain no_order")

    @classmethod
    def missing(cls, *, as_of: date | None = None) -> PositionTierPolicy:
        return cls(
            policy_id="tier-policy-missing",
            policy_version="v0-missing",
            as_of=as_of or date.min,
            confirmation_status=CONFIRMATION_DRAFT,
            confirmed_at=None,
            starter_cap_pct=Decimal("0"),
            normal_cap_pct=Decimal("0"),
            max_cap_pct=Decimal("0"),
        )

    def missing_inputs(self) -> tuple[str, ...]:
        result = []
        if self.confirmation_status != CONFIRMATION_HUMAN:
            result.append("human_confirmation")
        if self.confirmed_at is None:
            result.append("confirmed_at")
        if self.starter_cap_pct <= 0:
            result.append("starter_cap_pct")
        if self.normal_cap_pct <= 0:
            result.append("normal_cap_pct")
        if self.max_cap_pct <= 0:
            result.append("max_cap_pct")
        return tuple(result)

    def can_support_guidance(self) -> bool:
        return not self.missing_inputs()

    def as_policy(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "as_of": self.as_of.isoformat(),
            "confirmation_status": self.confirmation_status,
            "confirmed_at": self.confirmed_at.isoformat() if self.confirmed_at else None,
            "starter_cap_pct": str(self.starter_cap_pct),
            "normal_cap_pct": str(self.normal_cap_pct),
            "max_cap_pct": str(self.max_cap_pct),
            "evidence_refs": [dict(ref) for ref in self.evidence_refs],
            "action": self.action,
        }


@dataclass(frozen=True)
class PositionCandidateInput:
    """Verified research/price/event/approval state for one security."""

    symbol: str
    review_intent: str
    confidence: str
    research_gate_passed: bool
    human_approval_valid: bool
    event_review_clean: bool
    model_valid: bool
    price_assessable: bool
    thesis_breakers: tuple[str, ...] = ()
    liquidity_profile: str = LIQUIDITY_LIQUID
    industry: str = ""
    cyclical: bool = False
    evidence_refs: tuple[dict[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("Position candidate symbol must contain six digits")
        if self.review_intent not in INTENTS:
            raise ValueError("Unknown position review intent")
        if self.confidence not in CONFIDENCE_VALUES:
            raise ValueError("Unknown position candidate confidence")
        if self.liquidity_profile not in LIQUIDITY_PROFILES:
            raise ValueError("Unknown candidate liquidity profile")
        object.__setattr__(
            self,
            "thesis_breakers",
            tuple(
                _required_text(item, "thesis breaker")
                for item in self.thesis_breakers
            ),
        )
        object.__setattr__(
            self,
            "industry",
            _required_text(self.industry, "industry"),
        )
        object.__setattr__(self, "evidence_refs", _normalize_refs(self.evidence_refs))
        if not self.evidence_refs:
            raise ValueError("Position candidate evidence is required")

    def preconditions_passed(self) -> bool:
        return all(
            (
                self.research_gate_passed,
                self.human_approval_valid,
                self.event_review_clean,
                self.model_valid,
                self.price_assessable,
                not self.thesis_breakers,
            )
        )

    def as_policy(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "review_intent": self.review_intent,
            "confidence": self.confidence,
            "research_gate_passed": self.research_gate_passed,
            "human_approval_valid": self.human_approval_valid,
            "event_review_clean": self.event_review_clean,
            "model_valid": self.model_valid,
            "price_assessable": self.price_assessable,
            "thesis_breakers": list(self.thesis_breakers),
            "liquidity_profile": self.liquidity_profile,
            "industry": self.industry,
            "cyclical": self.cyclical,
            "evidence_refs": [dict(ref) for ref in self.evidence_refs],
        }


@dataclass(frozen=True)
class PositionGuidanceLine:
    """A ceiling and guardrail, not a target weight or order."""

    symbol: str
    review_intent: str
    status: str
    tier: str
    ceiling_pct: Decimal | None
    current_weight_pct: Decimal
    remaining_ceiling_pct: Decimal | None
    budget_status: str
    stop_add_conditions: tuple[str, ...] = ()
    reduce_review_triggers: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    evidence_refs: tuple[dict[str, Any], ...] = ()
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("Guidance line symbol must contain six digits")
        if self.review_intent not in INTENTS:
            raise ValueError("Unknown guidance line review intent")
        if self.status not in LINE_STATUSES:
            raise ValueError("Unknown guidance line status")
        if self.tier not in TIERS:
            raise ValueError("Unknown guidance tier")
        if self.budget_status not in BUDGET_STATUSES:
            raise ValueError("Unknown guidance budget status")
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Position guidance line must remain no_order")
        object.__setattr__(
            self,
            "ceiling_pct",
            _optional_decimal(self.ceiling_pct, "ceiling_pct"),
        )
        if self.ceiling_pct is not None and not Decimal("0") < self.ceiling_pct <= Decimal("1"):
            raise ValueError("Guidance ceiling must be in (0, 1]")
        if self.status == LINE_ELIGIBLE and self.ceiling_pct is None:
            raise ValueError("Eligible guidance line requires a ceiling")
        if self.status not in {LINE_ELIGIBLE, LINE_REVIEW_REQUIRED} and self.ceiling_pct is not None:
            raise ValueError("Wait guidance line cannot carry a ceiling")
        object.__setattr__(
            self,
            "remaining_ceiling_pct",
            _optional_decimal(
                self.remaining_ceiling_pct,
                "remaining_ceiling_pct",
            ),
        )
        object.__setattr__(
            self,
            "stop_add_conditions",
            tuple(
                _required_text(item, "stop-add condition")
                for item in self.stop_add_conditions
            ),
        )
        object.__setattr__(
            self,
            "reduce_review_triggers",
            tuple(
                _required_text(item, "reduce-review trigger")
                for item in self.reduce_review_triggers
            ),
        )
        object.__setattr__(
            self,
            "blockers",
            tuple(_required_text(item, "blocker") for item in self.blockers),
        )
        object.__setattr__(self, "evidence_refs", _normalize_refs(self.evidence_refs))

    def as_policy(self) -> dict[str, Any]:
        payload = {
            "symbol": self.symbol,
            "review_intent": self.review_intent,
            "status": self.status,
            "tier": self.tier,
            "ceiling_pct": _decimal_text(self.ceiling_pct),
            "current_weight_pct": _decimal_text(self.current_weight_pct),
            "remaining_ceiling_pct": _decimal_text(self.remaining_ceiling_pct),
            "budget_status": self.budget_status,
            "stop_add_conditions": list(self.stop_add_conditions),
            "reduce_review_triggers": list(self.reduce_review_triggers),
            "blockers": list(self.blockers),
            "evidence_refs": [dict(ref) for ref in self.evidence_refs],
            "action": self.action,
        }
        _reject_public_execution_keys(payload)
        return payload


@dataclass(frozen=True)
class PositionGuidanceResult:
    """Portfolio-wide guidance summary with shared budget bookkeeping."""

    assessment_id: str
    as_of: date
    generated_at: datetime
    bundle: PortfolioInputBundle
    tier_policy: PositionTierPolicy
    candidates: Mapping[str, PositionCandidateInput]
    assessment_namespace: str = NAMESPACE_ACTUAL
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "assessment_id",
            _required_text(self.assessment_id, "assessment_id"),
        )
        object.__setattr__(self, "as_of", _date(self.as_of, "as_of"))
        object.__setattr__(
            self,
            "generated_at",
            _datetime(self.generated_at, "generated_at"),
        )
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Position guidance result must remain no_order")
        if self.assessment_namespace not in {NAMESPACE_ACTUAL, NAMESPACE_SIMULATED}:
            raise ValueError("Unknown position guidance namespace")
        if self.assessment_namespace != self.bundle.snapshot.namespace:
            raise ValueError("Position guidance namespace must match its snapshot")
        if self.tier_policy.can_support_guidance():
            policy = self.bundle.policy
            if policy.max_single_security_pct is None:
                raise ValueError("Confirmed IPS requires a single-security cap")
            if self.tier_policy.max_cap_pct > policy.max_single_security_pct:
                raise ValueError("Max tier cap cannot exceed the IPS single-security cap")

    def missing_inputs(self) -> tuple[str, ...]:
        missing = [
            f"policy.{item}"
            for item in self.bundle.policy.missing_guidance_inputs()
        ]
        snapshot = self.bundle.snapshot
        if not snapshot.is_reconciled:
            missing.append("snapshot.reconciliation")
        if snapshot.account_scope == "missing":
            missing.append("snapshot.account_scope")
        if snapshot.cash_cny is None:
            missing.append("snapshot.cash_cny")
        if any(
            holding.quantity_source != QUANTITY_HUMAN_CONFIRMED
            for holding in snapshot.holdings
        ):
            missing.append("snapshot.holding_quantity_confirmation")
        if any(holding.market_value_cny is None for holding in snapshot.holdings):
            missing.append("snapshot.holding_market_value")
        if self.assessment_namespace == NAMESPACE_ACTUAL and snapshot.namespace != NAMESPACE_ACTUAL:
            missing.append("snapshot.actual_namespace")
        missing.extend(
            f"tier_policy.{item}"
            for item in self.tier_policy.missing_inputs()
        )
        for symbol in sorted(self.candidates):
            candidate = self.candidates[symbol]
            if candidate.symbol != symbol:
                missing.append(f"candidate.{symbol}.symbol_mismatch")
            if not candidate.evidence_refs and candidate.preconditions_passed():
                missing.append(f"candidate.{symbol}.evidence_refs")
            if candidate.review_intent not in {INTENT_BUY, INTENT_ADD, INTENT_HOLD}:
                missing.append(f"candidate.{symbol}.review_intent")
        return tuple(dict.fromkeys(missing))

    def can_guide(self) -> bool:
        return not self.missing_inputs()

    def total_assets_cny(self) -> Decimal | None:
        if not self.bundle.can_support_guidance():
            return None
        cash = self.bundle.snapshot.cash_cny
        if cash is None:
            return None
        return cash + sum(
            holding.market_value_cny or Decimal("0")
            for holding in self.bundle.snapshot.holdings
        )

    def reserved_cash_cny(self) -> Decimal | None:
        if not self.bundle.can_support_guidance():
            return None
        policy = self.bundle.policy
        minimum = policy.minimum_cash_cny or Decimal("0")
        emergency = policy.emergency_cash_cny or Decimal("0")
        liquidity = policy.liquidity_needs_cny or Decimal("0")
        return max(minimum, emergency + liquidity)

    def free_budget_cny(self) -> Decimal | None:
        total = self.total_assets_cny()
        reserved = self.reserved_cash_cny()
        if total is None or reserved is None:
            return None
        current_exposure = total - (self.bundle.snapshot.cash_cny or Decimal("0"))
        return max(total - reserved - current_exposure, Decimal("0"))

    def current_weight(self, symbol: str) -> Decimal:
        total = self.total_assets_cny()
        if total is None or total <= 0:
            return Decimal("0")
        for holding in self.bundle.snapshot.holdings:
            if holding.symbol == symbol:
                return (holding.market_value_cny or Decimal("0")) / total
        return Decimal("0")

    def industry_exposure(self, industry: str) -> Decimal:
        total = self.total_assets_cny()
        if total is None or total <= 0:
            return Decimal("0")
        part = Decimal("0")
        for holding in self.bundle.snapshot.holdings:
            candidate = self.candidates.get(holding.symbol)
            if candidate is not None and candidate.industry == industry:
                part += holding.market_value_cny or Decimal("0")
        return part / total

    def cyclical_exposure(self) -> Decimal:
        total = self.total_assets_cny()
        if total is None or total <= 0:
            return Decimal("0")
        part = Decimal("0")
        for holding in self.bundle.snapshot.holdings:
            candidate = self.candidates.get(holding.symbol)
            if candidate is not None and candidate.cyclical:
                part += holding.market_value_cny or Decimal("0")
        return part / total

    def lines(self) -> tuple[PositionGuidanceLine, ...]:
        if not self.can_guide():
            return ()

        policy = self.bundle.policy
        tier_caps = {
            CONFIDENCE_LOW: self.tier_policy.starter_cap_pct,
            CONFIDENCE_MEDIUM: self.tier_policy.normal_cap_pct,
            CONFIDENCE_HIGH: self.tier_policy.max_cap_pct,
        }
        free_budget_pct = (
            self.free_budget_cny() / self.total_assets_cny()
            if self.free_budget_cny() is not None and self.total_assets_cny()
            else Decimal("0")
        )
        tentative_remaining: list[Decimal] = []
        for candidate in self.candidates.values():
            if not candidate.preconditions_passed():
                continue
            cap = tier_caps[candidate.confidence] / Decimal("100")
            current = self.current_weight(candidate.symbol)
            if candidate.liquidity_profile == LIQUIDITY_LIQUID:
                tentative_remaining.append(max(cap - current, Decimal("0")))
        aggregate_budget_constrained = (
            sum(tentative_remaining, Decimal("0")) > free_budget_pct
            and sum(tentative_remaining, Decimal("0")) > Decimal("0")
        )
        result = []
        for symbol, candidate in sorted(self.candidates.items()):
            current = self.current_weight(symbol)
            stop_add = []
            triggers = []
            blockers = list(candidate.thesis_breakers)

            if not candidate.preconditions_passed():
                result.append(
                    PositionGuidanceLine(
                        symbol=symbol,
                        review_intent=candidate.review_intent,
                        status=LINE_WAIT,
                        tier=TIER_NONE,
                        ceiling_pct=None,
                        current_weight_pct=current,
                        remaining_ceiling_pct=None,
                        budget_status=BUDGET_NOT_APPLICABLE,
                        stop_add_conditions=tuple(stop_add),
                        reduce_review_triggers=tuple(triggers),
                        blockers=tuple(blockers),
                        evidence_refs=candidate.evidence_refs,
                    )
                )
                continue

            ceiling_pct = tier_caps[candidate.confidence] / Decimal("100")
            remaining = max(ceiling_pct - current, Decimal("0"))
            status = LINE_ELIGIBLE
            budget_status = BUDGET_AVAILABLE
            liquidity_restricted = candidate.liquidity_profile != LIQUIDITY_LIQUID

            if liquidity_restricted:
                status = LINE_REVIEW_REQUIRED
                stop_add.append("liquidity_profile_requires_review")
                triggers.append("liquidity_profile_requires_review")
                remaining = None

            if current >= ceiling_pct:
                stop_add.append("current_exposure_at_ceiling")
            if current > ceiling_pct:
                triggers.append("current_exposure_exceeds_ceiling")

            max_industry = policy.max_single_industry_pct
            industry_now = self.industry_exposure(candidate.industry)
            if max_industry is not None and industry_now >= max_industry / Decimal("100"):
                stop_add.append("industry_budget_at_limit")
            if max_industry is not None and industry_now > max_industry / Decimal("100"):
                triggers.append("industry_exposure_exceeds_cap")

            max_cyclical = policy.max_cyclical_exposure_pct
            cyclical_now = self.cyclical_exposure()
            if candidate.cyclical and max_cyclical is not None:
                if cyclical_now >= max_cyclical / Decimal("100"):
                    stop_add.append("cyclical_budget_at_limit")
                if cyclical_now > max_cyclical / Decimal("100"):
                    triggers.append("cyclical_exposure_exceeds_cap")

            if free_budget_pct <= 0:
                budget_status = BUDGET_EXHAUSTED
                stop_add.append("shared_budget_exhausted")
                remaining = Decimal("0")
            elif remaining is not None and remaining > free_budget_pct:
                budget_status = BUDGET_CONSTRAINED
                stop_add.append("shared_budget_constrains_ceiling")

            if (
                remaining is not None
                and remaining > Decimal("0")
                and aggregate_budget_constrained
                and budget_status == BUDGET_AVAILABLE
            ):
                budget_status = BUDGET_CONSTRAINED
                stop_add.append("shared_budget_constrains_ceiling")

            if liquidity_restricted:
                remaining = None

            result.append(
                PositionGuidanceLine(
                    symbol=symbol,
                    review_intent=candidate.review_intent,
                    status=status,
                    tier=self._tier_for(candidate.confidence),
                    ceiling_pct=ceiling_pct,
                    current_weight_pct=current,
                    remaining_ceiling_pct=remaining,
                    budget_status=budget_status,
                    stop_add_conditions=tuple(dict.fromkeys(stop_add)),
                    reduce_review_triggers=tuple(dict.fromkeys(triggers)),
                    blockers=tuple(dict.fromkeys(blockers)),
                    evidence_refs=candidate.evidence_refs,
                )
            )
        return tuple(result)

    @staticmethod
    def _tier_for(confidence: str) -> str:
        return {
            CONFIDENCE_LOW: TIER_STARTER,
            CONFIDENCE_MEDIUM: TIER_NORMAL,
            CONFIDENCE_HIGH: TIER_MAX,
        }[confidence]

    @property
    def status(self) -> str:
        if not self.can_guide():
            return STATUS_INCOMPLETE
        lines = self.lines()
        if not lines:
            return STATUS_READY
        if any(line.status == LINE_REVIEW_REQUIRED for line in lines):
            return STATUS_REVIEW_REQUIRED
        eligible = [line for line in lines if line.status == LINE_ELIGIBLE]
        if not eligible:
            return STATUS_NO_ACTIONABLE_CAPACITY
        if any(line.budget_status in {BUDGET_CONSTRAINED, BUDGET_EXHAUSTED} for line in lines):
            return STATUS_BUDGET_CONFLICT
        if any(line.status == LINE_WAIT for line in lines):
            return STATUS_PARTIAL
        return STATUS_READY

    @property
    def sensitivity(self) -> str:
        if self.assessment_namespace == NAMESPACE_SIMULATED:
            return "SIMULATED_PUBLIC_DEMONSTRATION"
        return "PRIVATE_USER_CONFIRMED"

    def as_policy(self) -> dict[str, Any]:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "assessment_namespace": self.assessment_namespace,
            "assessment_id": self.assessment_id,
            "as_of": self.as_of.isoformat(),
            "generated_at": self.generated_at.isoformat(),
            "status": self.status,
            "missing_inputs": list(self.missing_inputs()),
            "total_assets_cny": _decimal_text(self.total_assets_cny()),
            "reserved_cash_cny": _decimal_text(self.reserved_cash_cny()),
            "free_budget_cny": _decimal_text(self.free_budget_cny()),
            "tier_policy": self.tier_policy.as_policy(),
            "candidates": {
                symbol: candidate.as_policy()
                for symbol, candidate in sorted(self.candidates.items())
            },
            "lines": [line.as_policy() for line in self.lines()],
            "sensitivity": self.sensitivity,
            "action": self.action,
        }
        _reject_public_execution_keys(payload)
        return payload

    def to_json(self) -> str:
        return json.dumps(self.as_policy(), ensure_ascii=False, allow_nan=False, indent=2)


def build_position_guidance(
    *,
    bundle: PortfolioInputBundle,
    tier_policy: PositionTierPolicy,
    candidates: Mapping[str, PositionCandidateInput],
    as_of: date,
    generated_at: datetime,
    assessment_id: str,
    assessment_namespace: str = NAMESPACE_ACTUAL,
) -> PositionGuidanceResult:
    return PositionGuidanceResult(
        assessment_id=assessment_id,
        as_of=as_of,
        generated_at=generated_at,
        bundle=bundle,
        tier_policy=tier_policy,
        candidates=candidates,
        assessment_namespace=assessment_namespace,
    )


def position_candidate_from_payload(payload: Mapping[str, Any]) -> PositionCandidateInput:
    data = dict(payload)
    return PositionCandidateInput(
        symbol=str(data["symbol"]),
        review_intent=str(data["review_intent"]),
        confidence=str(data["confidence"]),
        research_gate_passed=bool(data["research_gate_passed"]),
        human_approval_valid=bool(data["human_approval_valid"]),
        event_review_clean=bool(data["event_review_clean"]),
        model_valid=bool(data["model_valid"]),
        price_assessable=bool(data["price_assessable"]),
        thesis_breakers=tuple(str(item) for item in data.get("thesis_breakers") or ()),
        liquidity_profile=str(data.get("liquidity_profile", LIQUIDITY_LIQUID)),
        industry=str(data.get("industry", "")),
        cyclical=bool(data.get("cyclical", False)),
        evidence_refs=tuple(dict(item) for item in data.get("evidence_refs") or ()),
    )


def position_tier_policy_from_payload(payload: Mapping[str, Any]) -> PositionTierPolicy:
    data = dict(payload)
    return PositionTierPolicy(
        policy_id=str(data["policy_id"]),
        policy_version=str(data["policy_version"]),
        as_of=date.fromisoformat(str(data["as_of"])),
        confirmation_status=str(data["confirmation_status"]),
        confirmed_at=datetime.fromisoformat(str(data["confirmed_at"]))
        if data.get("confirmed_at")
        else None,
        starter_cap_pct=_decimal(data["starter_cap_pct"], "starter_cap_pct"),
        normal_cap_pct=_decimal(data["normal_cap_pct"], "normal_cap_pct"),
        max_cap_pct=_decimal(data["max_cap_pct"], "max_cap_pct"),
        evidence_refs=tuple(dict(item) for item in data.get("evidence_refs") or ()),
        action=str(data.get("action", ACTION_NO_ORDER)),
    )
