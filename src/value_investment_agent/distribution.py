"""Minimal point-in-time distribution-research domain.

This module separates historical dividend facts, distribution capacity,
sustainability assessment and market-dependent yield snapshots. It never
creates a position, order or trade signal.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, localcontext
import json
import re
from typing import Any, Iterable, Mapping, Sequence

from .quote_snapshot import QUOTE_STATUS_VERIFIED_CLOSE, QuoteSnapshot
from .research_profile import PROFILES


DIVIDEND_ORDINARY = "ordinary"
DIVIDEND_SPECIAL = "special"
DIVIDEND_TYPES = {DIVIDEND_ORDINARY, DIVIDEND_SPECIAL}

DIVIDEND_PROPOSED = "proposed"
DIVIDEND_APPROVED = "approved"
DIVIDEND_PAID = "paid"
DIVIDEND_RECORD_STATUSES = {DIVIDEND_PROPOSED, DIVIDEND_APPROVED, DIVIDEND_PAID}

HISTORY_COMPLETE = "COMPLETE"
HISTORY_PARTIAL = "PARTIAL"
HISTORY_UNKNOWN = "UNKNOWN"
HISTORY_STATUSES = {HISTORY_COMPLETE, HISTORY_PARTIAL, HISTORY_UNKNOWN}

CAPACITY_READY = "READY"
CAPACITY_PARTIAL = "PARTIAL"
CAPACITY_NOT_READY = "NOT_READY"
CAPACITY_UNKNOWN = "UNKNOWN"
CAPACITY_STATUSES = {CAPACITY_READY, CAPACITY_PARTIAL, CAPACITY_NOT_READY, CAPACITY_UNKNOWN}

SUSTAINABILITY_HIGH = "HIGH"
SUSTAINABILITY_MEDIUM = "MEDIUM"
SUSTAINABILITY_LOW = "LOW"
SUSTAINABILITY_UNKNOWN = "UNKNOWN"
SUSTAINABILITY_STATUSES = {
    SUSTAINABILITY_HIGH,
    SUSTAINABILITY_MEDIUM,
    SUSTAINABILITY_LOW,
    SUSTAINABILITY_UNKNOWN,
}

YIELD_TRAILING_PAID = "trailing_paid"
YIELD_DECLARED = "declared"
YIELD_FORWARD_ESTIMATE = "forward_estimate"
YIELD_NORMALIZED_SCENARIO = "normalized_scenario"
YIELD_BASIS_TYPES = {
    YIELD_TRAILING_PAID,
    YIELD_DECLARED,
    YIELD_FORWARD_ESTIMATE,
    YIELD_NORMALIZED_SCENARIO,
}

YIELD_CURRENT = "current"
YIELD_NORMALIZED = "normalized"
YIELD_TYPES = {YIELD_CURRENT, YIELD_NORMALIZED}

YIELD_READY = "READY"
YIELD_NOT_READY = "NOT_READY"
YIELD_UNKNOWN = "UNKNOWN"
YIELD_STATUSES = {YIELD_READY, YIELD_NOT_READY, YIELD_UNKNOWN}

CONFIDENCE_HIGH = "高"
CONFIDENCE_MEDIUM = "中"
CONFIDENCE_LOW = "低"
CONFIDENCE_UNKNOWN = "UNKNOWN"
CONFIDENCE_STATUSES = {
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_LOW,
    CONFIDENCE_UNKNOWN,
}

DIVIDEND_RESEARCH_NOT_ASSESSED = "NOT_ASSESSED"
DIVIDEND_RESEARCH_PARTIAL = "PARTIAL"
DIVIDEND_RESEARCH_AVAILABLE = "AVAILABLE"

SYMBOL_PATTERN = re.compile(r"[0-9]{6}")
CURRENCY_PATTERN = re.compile(r"[A-Z]{3}")


def _validate_refs(
    refs: Sequence[dict[str, Any]],
    *,
    allow_empty: bool = True,
) -> list[dict[str, Any]]:
    result = [dict(ref) for ref in refs]
    if not allow_empty and not result:
        raise ValueError("Evidence references are required")
    if any(not ref.get("id") for ref in result):
        raise ValueError("Evidence requires named references")
    ids = [ref["id"] for ref in result]
    if len(set(ids)) != len(ids):
        raise ValueError("Evidence reference ids must be unique")
    return result


def _merge_refs(*groups: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for group in groups:
        for ref in group:
            ref_id = ref.get("id")
            if not ref_id:
                raise ValueError("Evidence requires named references")
            if ref_id in merged and merged[ref_id] != ref:
                raise ValueError(f"Evidence references with the same id must match: {ref_id}")
            merged[ref_id] = dict(ref)
    return list(merged.values())


def _optional_date(value: object, field_name: str) -> date | None:
    if value is None:
        return None
    if not isinstance(value, date):
        raise ValueError(f"{field_name} must be a date")
    return value


def _optional_decimal(
    value: object,
    field_name: str,
    *,
    nonnegative: bool = False,
) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        number = value
    else:
        try:
            number = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as error:
            raise ValueError(f"{field_name} must be a finite decimal") from error
    if not number.is_finite():
        raise ValueError(f"{field_name} must be a finite decimal")
    if nonnegative and number < 0:
        raise ValueError(f"{field_name} must be nonnegative")
    return number


def _required_string(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required")
    return value.strip()


def _optional_string(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    return _required_string(value, field_name)


def _json_value(value: Any) -> Any:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


@dataclass(frozen=True)
class DividendRecord:
    """One proposed, approved or paid cash-distribution event.

    The three lifecycle states are deliberately different facts: a proposal is
    an intention, approval is a corporate decision, and payment is an actual
    cash event. They must not be merged into one observation.
    """

    symbol: str
    fiscal_period: str
    dividend_type: str
    status: str
    dividend_per_share: Decimal
    currency: str
    announcement_date: date | None
    approval_date: date | None
    ex_date: date | None
    payment_date: date | None
    known_at: date
    share_basis: str
    evidence_refs: list[dict[str, Any]]
    blockers: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not SYMBOL_PATTERN.fullmatch(self.symbol):
            raise ValueError("Dividend symbol must contain six digits")
        _required_string(self.fiscal_period, "fiscal_period")
        if self.dividend_type not in DIVIDEND_TYPES:
            raise ValueError("Unknown dividend type")
        if self.status not in DIVIDEND_RECORD_STATUSES:
            raise ValueError("Unknown dividend record status")
        if self.dividend_per_share < 0 or not self.dividend_per_share.is_finite():
            raise ValueError("Dividend per share must be finite and nonnegative")
        if not CURRENCY_PATTERN.fullmatch(self.currency):
            raise ValueError("Dividend currency must be a three-letter code")
        _required_string(self.share_basis, "share_basis")

        announcement_date = _optional_date(self.announcement_date, "announcement_date")
        approval_date = _optional_date(self.approval_date, "approval_date")
        ex_date = _optional_date(self.ex_date, "ex_date")
        payment_date = _optional_date(self.payment_date, "payment_date")

        if self.status == DIVIDEND_PROPOSED:
            if announcement_date is None:
                raise ValueError("A proposed dividend requires an announcement date")
            if approval_date is not None or ex_date is not None or payment_date is not None:
                raise ValueError("A proposed dividend cannot also carry approval/ex/payment dates")
        elif self.status == DIVIDEND_APPROVED:
            if approval_date is None:
                raise ValueError("An approved dividend requires an approval date")
            if ex_date is not None or payment_date is not None:
                raise ValueError("An approved dividend cannot carry ex/payment dates before payment")
        elif self.status == DIVIDEND_PAID:
            if ex_date is None or payment_date is None:
                raise ValueError("A paid dividend requires ex-date and payment date")
            if payment_date < ex_date:
                raise ValueError("Dividend payment date cannot precede ex-date")

        if announcement_date is not None and self.known_at < announcement_date:
            raise ValueError("known_at cannot precede announcement_date")
        if approval_date is not None and self.known_at < approval_date:
            raise ValueError("known_at cannot precede approval_date")
        if payment_date is not None and self.known_at < payment_date:
            raise ValueError("known_at cannot precede payment_date")
        if (
            announcement_date is not None
            and approval_date is not None
            and approval_date < announcement_date
        ):
            raise ValueError("approval_date cannot precede announcement_date")
        if (
            approval_date is not None
            and ex_date is not None
            and ex_date < approval_date
        ):
            raise ValueError("ex_date cannot precede approval_date")
        if announcement_date is not None and ex_date is not None and ex_date < announcement_date:
            raise ValueError("ex_date cannot precede announcement_date")

        object.__setattr__(
            self,
            "evidence_refs",
            _validate_refs(self.evidence_refs, allow_empty=False),
        )
        object.__setattr__(self, "blockers", list(dict.fromkeys(self.blockers)))

    def as_policy(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "fiscal_period": self.fiscal_period,
            "dividend_type": self.dividend_type,
            "status": self.status,
            "dividend_per_share": str(self.dividend_per_share),
            "currency": self.currency,
            "announcement_date": _json_value(self.announcement_date),
            "approval_date": _json_value(self.approval_date),
            "ex_date": _json_value(self.ex_date),
            "payment_date": _json_value(self.payment_date),
            "known_at": self.known_at.isoformat(),
            "share_basis": self.share_basis,
            "evidence_refs": _json_value(self.evidence_refs),
            "blockers": list(self.blockers),
        }

    def to_json(self) -> str:
        return json.dumps(self.as_policy(), ensure_ascii=False, allow_nan=False, indent=2)


@dataclass(frozen=True)
class DividendHistory:
    """Verified historical distribution facts, never a future payout prediction."""

    symbol: str
    records: tuple[DividendRecord, ...]
    as_of: date
    evidence_refs: list[dict[str, Any]]
    status: str
    blockers: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not SYMBOL_PATTERN.fullmatch(self.symbol):
            raise ValueError("Dividend-history symbol must contain six digits")
        if self.status not in HISTORY_STATUSES:
            raise ValueError("Unknown dividend-history status")
        if self.status == HISTORY_COMPLETE and self.blockers:
            raise ValueError("A COMPLETE dividend history cannot carry blockers")
        if not self.records and self.status == HISTORY_COMPLETE:
            raise ValueError("A COMPLETE dividend history requires records")

        records = tuple(self.records)
        keys: set[tuple[str, str]] = set()
        for record in records:
            if record.symbol != self.symbol:
                raise ValueError("Dividend-history records must share one security identity")
            if record.known_at > self.as_of:
                raise ValueError("Dividend-history records cannot be known after as_of")
            key = (record.fiscal_period, record.dividend_type)
            if key in keys:
                raise ValueError("Dividend-history records must have unique fiscal period/type")
            keys.add(key)
        object.__setattr__(self, "records", records)
        object.__setattr__(
            self,
            "evidence_refs",
            _validate_refs(self.evidence_refs, allow_empty=False),
        )
        object.__setattr__(self, "blockers", list(dict.fromkeys(self.blockers)))

    def as_policy(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "records": [record.as_policy() for record in self.records],
            "as_of": self.as_of.isoformat(),
            "evidence_refs": _json_value(self.evidence_refs),
            "status": self.status,
            "blockers": list(self.blockers),
        }

    def to_json(self) -> str:
        return json.dumps(self.as_policy(), ensure_ascii=False, allow_nan=False, indent=2)


@dataclass(frozen=True)
class DistributionCapacity:
    """Profile-aware cash-distribution capacity, independent of market price."""

    symbol: str
    profile_id: str
    as_of: date
    earnings_basis: dict[str, Decimal | None] = field(default_factory=dict)
    cash_flow_basis: dict[str, Decimal | None] = field(default_factory=dict)
    maintenance_reinvestment: dict[str, Decimal | None] = field(default_factory=dict)
    debt_constraints: dict[str, Decimal | None] = field(default_factory=dict)
    restricted_cash_or_upstream_constraints: dict[str, Decimal | None] = field(default_factory=dict)
    capital_allocation_context: dict[str, Any] = field(default_factory=dict)
    bear_capacity: Decimal | None = None
    base_capacity: Decimal | None = None
    bull_capacity: Decimal | None = None
    confidence: str = CONFIDENCE_UNKNOWN
    evidence_refs: list[dict[str, Any]] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    status: str = CAPACITY_UNKNOWN

    def __post_init__(self) -> None:
        if not SYMBOL_PATTERN.fullmatch(self.symbol):
            raise ValueError("Distribution-capacity symbol must contain six digits")
        if self.profile_id not in PROFILES:
            raise ValueError("Unknown research profile for distribution capacity")
        if self.status not in CAPACITY_STATUSES:
            raise ValueError("Unknown distribution-capacity status")
        if self.confidence not in CONFIDENCE_STATUSES:
            raise ValueError("Unknown distribution-capacity confidence")

        metric_groups = (
            self.earnings_basis,
            self.cash_flow_basis,
            self.maintenance_reinvestment,
            self.debt_constraints,
            self.restricted_cash_or_upstream_constraints,
        )
        normalized_groups: list[dict[str, Decimal | None]] = []
        for group in metric_groups:
            normalized: dict[str, Decimal | None] = {}
            for key, value in group.items():
                normalized[str(key).strip()] = _optional_decimal(
                    value, f"capacity metric {key}", nonnegative=True
                )
            normalized_groups.append(normalized)
        (
            earnings_basis,
            cash_flow_basis,
            maintenance_reinvestment,
            debt_constraints,
            restricted_cash_or_upstream_constraints,
        ) = normalized_groups
        object.__setattr__(self, "earnings_basis", earnings_basis)
        object.__setattr__(self, "cash_flow_basis", cash_flow_basis)
        object.__setattr__(self, "maintenance_reinvestment", maintenance_reinvestment)
        object.__setattr__(self, "debt_constraints", debt_constraints)
        object.__setattr__(
            self,
            "restricted_cash_or_upstream_constraints",
            restricted_cash_or_upstream_constraints,
        )

        bear = _optional_decimal(self.bear_capacity, "bear_capacity", nonnegative=True)
        base = _optional_decimal(self.base_capacity, "base_capacity", nonnegative=True)
        bull = _optional_decimal(self.bull_capacity, "bull_capacity", nonnegative=True)
        object.__setattr__(self, "bear_capacity", bear)
        object.__setattr__(self, "base_capacity", base)
        object.__setattr__(self, "bull_capacity", bull)
        if (
            bear is not None
            and base is not None
            and bull is not None
            and not bear <= base <= bull
        ):
            raise ValueError("Distribution capacity must satisfy bear <= base <= bull")

        blockers = list(dict.fromkeys(self.blockers))
        object.__setattr__(self, "blockers", blockers)
        evidence_refs = _validate_refs(self.evidence_refs, allow_empty=True)
        object.__setattr__(self, "evidence_refs", evidence_refs)
        if self.status == CAPACITY_READY:
            if any(value is None for value in (bear, base, bull)):
                raise ValueError("READY distribution capacity requires all three scenarios")
            if self.confidence == CONFIDENCE_UNKNOWN:
                raise ValueError("READY distribution capacity requires known confidence")
            if blockers:
                raise ValueError("READY distribution capacity cannot carry blockers")
            if not evidence_refs:
                raise ValueError("READY distribution capacity requires evidence")

    def as_policy(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "profile_id": self.profile_id,
            "as_of": self.as_of.isoformat(),
            "earnings_basis": _json_value(self.earnings_basis),
            "cash_flow_basis": _json_value(self.cash_flow_basis),
            "maintenance_reinvestment": _json_value(self.maintenance_reinvestment),
            "debt_constraints": _json_value(self.debt_constraints),
            "restricted_cash_or_upstream_constraints": _json_value(
                self.restricted_cash_or_upstream_constraints
            ),
            "capital_allocation_context": _json_value(self.capital_allocation_context),
            "bear_capacity": _json_value(self.bear_capacity),
            "base_capacity": _json_value(self.base_capacity),
            "bull_capacity": _json_value(self.bull_capacity),
            "confidence": self.confidence,
            "evidence_refs": _json_value(self.evidence_refs),
            "blockers": list(self.blockers),
            "status": self.status,
        }

    def to_json(self) -> str:
        return json.dumps(self.as_policy(), ensure_ascii=False, allow_nan=False, indent=2)


@dataclass(frozen=True)
class DividendSustainabilityAssessment:
    """Conditional, profile-aware sustainability judgement; UNKNOWN is valid."""

    symbol: str
    profile_id: str
    as_of: date
    status: str
    coverage_context: str
    capital_requirements: str
    balance_sheet_pressure: str
    cycle_risk: str
    growth_source: str
    breakers: tuple[str, ...]
    confidence: str
    reasons: tuple[str, ...]
    blockers: list[str] = field(default_factory=list)
    evidence_refs: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not SYMBOL_PATTERN.fullmatch(self.symbol):
            raise ValueError("Dividend-sustainability symbol must contain six digits")
        if self.profile_id not in PROFILES:
            raise ValueError("Unknown research profile for dividend sustainability")
        if self.status not in SUSTAINABILITY_STATUSES:
            raise ValueError("Unknown dividend-sustainability status")
        if self.confidence not in CONFIDENCE_STATUSES:
            raise ValueError("Unknown dividend-sustainability confidence")
        _required_string(self.coverage_context, "coverage_context")
        _required_string(self.capital_requirements, "capital_requirements")
        _required_string(self.balance_sheet_pressure, "balance_sheet_pressure")
        _required_string(self.cycle_risk, "cycle_risk")
        _required_string(self.growth_source, "growth_source")
        if self.status != SUSTAINABILITY_UNKNOWN:
            if not self.reasons:
                raise ValueError("A known sustainability assessment requires reasons")
            if self.confidence == CONFIDENCE_UNKNOWN:
                raise ValueError("A known sustainability assessment requires known confidence")
            if not self.evidence_refs:
                raise ValueError("A known sustainability assessment requires evidence")
        object.__setattr__(self, "breakers", tuple(dict.fromkeys(self.breakers)))
        object.__setattr__(self, "reasons", tuple(dict.fromkeys(self.reasons)))
        object.__setattr__(self, "blockers", list(dict.fromkeys(self.blockers)))
        object.__setattr__(
            self,
            "evidence_refs",
            _validate_refs(self.evidence_refs, allow_empty=True),
        )

    def as_policy(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "profile_id": self.profile_id,
            "as_of": self.as_of.isoformat(),
            "status": self.status,
            "coverage_context": self.coverage_context,
            "capital_requirements": self.capital_requirements,
            "balance_sheet_pressure": self.balance_sheet_pressure,
            "cycle_risk": self.cycle_risk,
            "growth_source": self.growth_source,
            "breakers": list(self.breakers),
            "confidence": self.confidence,
            "reasons": list(self.reasons),
            "blockers": list(self.blockers),
            "evidence_refs": _json_value(self.evidence_refs),
        }

    def to_json(self) -> str:
        return json.dumps(self.as_policy(), ensure_ascii=False, allow_nan=False, indent=2)


@dataclass(frozen=True)
class DividendYieldSnapshot:
    """A market-layer yield observation; only READY snapshots use a legal quote."""

    symbol: str
    basis_type: str
    dividend_basis_period: str
    dividend_per_share: Decimal | None
    dividend_known_at: date | None
    quote_date: date | None
    current_price: Decimal | None
    currency: str
    share_basis: str
    dividend_yield: Decimal | None
    yield_type: str
    evidence_refs: list[dict[str, Any]]
    status: str
    blockers: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not SYMBOL_PATTERN.fullmatch(self.symbol):
            raise ValueError("Dividend-yield symbol must contain six digits")
        if self.basis_type not in YIELD_BASIS_TYPES:
            raise ValueError("Unknown dividend-yield basis type")
        if self.yield_type not in YIELD_TYPES:
            raise ValueError("Unknown dividend-yield type")
        if self.status not in YIELD_STATUSES:
            raise ValueError("Unknown dividend-yield status")
        _required_string(self.dividend_basis_period, "dividend_basis_period")
        if not CURRENCY_PATTERN.fullmatch(self.currency):
            raise ValueError("Dividend-yield currency must be a three-letter code")
        _required_string(self.share_basis, "share_basis")
        if self.basis_type == YIELD_NORMALIZED_SCENARIO and self.yield_type != YIELD_NORMALIZED:
            raise ValueError("normalized_scenario must use the normalized yield type")
        if self.basis_type != YIELD_NORMALIZED_SCENARIO and self.yield_type != YIELD_CURRENT:
            raise ValueError("Non-normalized dividend basis must use the current yield type")

        dps = _optional_decimal(
            self.dividend_per_share, "dividend_per_share", nonnegative=True
        )
        price = _optional_decimal(self.current_price, "current_price", nonnegative=True)
        yield_value = _optional_decimal(self.dividend_yield, "dividend_yield", nonnegative=True)
        known_at = _optional_date(self.dividend_known_at, "dividend_known_at")
        quote_date = _optional_date(self.quote_date, "quote_date")
        object.__setattr__(self, "dividend_per_share", dps)
        object.__setattr__(self, "current_price", price)
        object.__setattr__(self, "dividend_yield", yield_value)
        object.__setattr__(self, "dividend_known_at", known_at)
        object.__setattr__(self, "quote_date", quote_date)

        if known_at is not None and quote_date is not None and quote_date < known_at:
            raise ValueError("Dividend-yield quote date cannot precede dividend known_at")
        if self.status == YIELD_READY:
            if dps is None or price is None or yield_value is None:
                raise ValueError("READY dividend yield requires DPS, price and yield")
            if known_at is None or quote_date is None or price <= 0:
                raise ValueError("READY dividend yield requires a legal quote and known-at date")
            if self.blockers:
                raise ValueError("READY dividend yield cannot carry blockers")
            with localcontext() as context:
                context.prec = 40
                calculated = dps / price
            if abs(calculated - yield_value) > Decimal("0.000000000001"):
                raise ValueError("Dividend yield does not equal DPS divided by current price")
        elif dps is not None and price is not None and price > 0 and yield_value is None:
            raise ValueError("A supplied dividend and price require an explicit yield")

        object.__setattr__(
            self,
            "evidence_refs",
            _validate_refs(self.evidence_refs, allow_empty=True),
        )
        object.__setattr__(self, "blockers", list(dict.fromkeys(self.blockers)))

    def as_policy(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "basis_type": self.basis_type,
            "dividend_basis_period": self.dividend_basis_period,
            "dividend_per_share": _json_value(self.dividend_per_share),
            "dividend_known_at": _json_value(self.dividend_known_at),
            "quote_date": _json_value(self.quote_date),
            "current_price": _json_value(self.current_price),
            "currency": self.currency,
            "share_basis": self.share_basis,
            "dividend_yield": _json_value(self.dividend_yield),
            "yield_type": self.yield_type,
            "evidence_refs": _json_value(self.evidence_refs),
            "status": self.status,
            "blockers": list(self.blockers),
        }

    def to_json(self) -> str:
        return json.dumps(self.as_policy(), ensure_ascii=False, allow_nan=False, indent=2)


def build_dividend_yield_snapshot(
    *,
    dividend: DividendRecord,
    quote: QuoteSnapshot,
    basis_type: str,
    dividend_basis_period: str,
    yield_type: str,
    currency: str | None = None,
    share_basis: str | None = None,
) -> DividendYieldSnapshot:
    """Build a yield snapshot only after identity and quote-validity checks."""
    if quote.status != QUOTE_STATUS_VERIFIED_CLOSE:
        raise ValueError("Dividend yield requires a verified close quote")
    if quote.symbol != dividend.symbol:
        raise ValueError("Dividend and quote securities differ")
    if quote.quote_date is None or quote.current_price is None:
        raise ValueError("Dividend yield requires a dated positive quote")
    selected_currency = dividend.currency if currency is None else currency.upper()
    selected_share_basis = dividend.share_basis if share_basis is None else share_basis
    if selected_currency != dividend.currency:
        raise ValueError("Dividend and requested yield currencies differ")
    if selected_share_basis != dividend.share_basis:
        raise ValueError("Dividend and requested yield share bases differ")
    if basis_type not in YIELD_BASIS_TYPES:
        raise ValueError("Unknown dividend-yield basis type")
    if yield_type not in YIELD_TYPES:
        raise ValueError("Unknown dividend-yield type")
    if (basis_type == YIELD_NORMALIZED_SCENARIO) != (yield_type == YIELD_NORMALIZED):
        raise ValueError("Dividend-yield basis and yield type are inconsistent")

    with localcontext() as context:
        context.prec = 40
        yield_value = dividend.dividend_per_share / quote.current_price
    return DividendYieldSnapshot(
        symbol=dividend.symbol,
        basis_type=basis_type,
        dividend_basis_period=dividend_basis_period,
        dividend_per_share=dividend.dividend_per_share,
        dividend_known_at=dividend.known_at,
        quote_date=quote.quote_date,
        current_price=quote.current_price,
        currency=selected_currency,
        share_basis=selected_share_basis,
        dividend_yield=yield_value,
        yield_type=yield_type,
        evidence_refs=_merge_refs(dividend.evidence_refs, quote.evidence_refs),
        status=YIELD_READY,
        blockers=[],
    )


def build_trailing_paid_yield_snapshot(
    *,
    history: DividendHistory,
    quote: QuoteSnapshot,
    as_of: date,
    currency: str = "CNY",
    share_basis: str = "ordinary shares",
) -> DividendYieldSnapshot:
    """Build a point-in-time trailing paid yield without future information."""
    if quote.status != QUOTE_STATUS_VERIFIED_CLOSE:
        raise ValueError("Trailing paid yield requires a verified close quote")
    if quote.quote_date is None or quote.current_price is None:
        raise ValueError("Trailing paid yield requires a dated positive quote")
    if quote.symbol != history.symbol:
        raise ValueError("Dividend history and quote securities differ")
    if as_of < quote.quote_date:
        raise ValueError("Yield as_of cannot precede quote_date")
    if history.records and any(
        record.currency != currency or record.share_basis != share_basis
        for record in history.records
    ):
        raise ValueError("Trailing dividend records must share the requested currency/share basis")

    window_start = quote.quote_date - timedelta(days=365)
    paid_records = [
        record
        for record in history.records
        if record.status == DIVIDEND_PAID
        and record.ex_date is not None
        and window_start <= record.ex_date <= quote.quote_date
    ]
    if not paid_records:
        return DividendYieldSnapshot(
            symbol=history.symbol,
            basis_type=YIELD_TRAILING_PAID,
            dividend_basis_period=f"{window_start.isoformat()}/{quote.quote_date.isoformat()}",
            dividend_per_share=None,
            dividend_known_at=None,
            quote_date=None,
            current_price=None,
            currency=currency,
            share_basis=share_basis,
            dividend_yield=None,
            yield_type=YIELD_CURRENT,
            evidence_refs=list(history.evidence_refs),
            status=YIELD_NOT_READY,
            blockers=["no paid dividend has an ex-date in the trailing one-year window"],
        )

    dps = sum((record.dividend_per_share for record in paid_records), Decimal("0"))
    known_at = max(
        record.payment_date for record in paid_records if record.payment_date is not None
    )
    merged = DividendRecord(
        symbol=history.symbol,
        fiscal_period=f"trailing-{window_start.isoformat()}/{quote.quote_date.isoformat()}",
        dividend_type=DIVIDEND_ORDINARY,
        status=DIVIDEND_PAID,
        dividend_per_share=dps,
        currency=paid_records[0].currency,
        announcement_date=None,
        approval_date=None,
        ex_date=known_at,
        payment_date=known_at,
        known_at=known_at,
        share_basis=paid_records[0].share_basis,
        evidence_refs=_merge_refs(
            history.evidence_refs,
            *(record.evidence_refs for record in paid_records),
        ),
        blockers=["aggregated trailing paid dividend; individual corporate-action dates remain in source records"],
    )
    return build_dividend_yield_snapshot(
        dividend=merged,
        quote=quote,
        basis_type=YIELD_TRAILING_PAID,
        dividend_basis_period=f"{window_start.isoformat()}/{quote.quote_date.isoformat()}",
        yield_type=YIELD_CURRENT,
    )


@dataclass(frozen=True)
class DividendResearchResult:
    """Typed distribution research result consumed by fixed-sample admission."""

    symbol: str
    profile_id: str
    history: DividendHistory | None
    capacity: DistributionCapacity | None
    sustainability: DividendSustainabilityAssessment | None
    yield_snapshots: tuple[DividendYieldSnapshot, ...]
    as_of: date
    blockers: list[str] = field(default_factory=list)
    evidence_refs: list[dict[str, Any]] = field(default_factory=list)
    action: str = "no_order"

    def __post_init__(self) -> None:
        if not SYMBOL_PATTERN.fullmatch(self.symbol):
            raise ValueError("Dividend-research symbol must contain six digits")
        if self.profile_id not in PROFILES:
            raise ValueError("Unknown dividend-research profile")
        if self.action != "no_order":
            raise ValueError("Dividend research can only record no_order")
        components = (self.history, self.capacity, self.sustainability)
        for component in components:
            if component is None:
                continue
            if component.symbol != self.symbol:
                raise ValueError("Dividend-research components must share one symbol")
            if getattr(component, "profile_id", None) not in (None, self.profile_id):
                raise ValueError("Dividend-research components must share one profile")
            if component.as_of > self.as_of:
                raise ValueError("Dividend-research as_of cannot precede component as_of")
        if any(snapshot.symbol != self.symbol for snapshot in self.yield_snapshots):
            raise ValueError("Dividend-research yield snapshots must share one symbol")

        object.__setattr__(self, "yield_snapshots", tuple(self.yield_snapshots))
        blockers = list(dict.fromkeys(self.blockers))
        for component in components:
            if component is not None:
                blockers.extend(component.blockers)
        for snapshot in self.yield_snapshots:
            blockers.extend(snapshot.blockers)
        object.__setattr__(self, "blockers", list(dict.fromkeys(blockers)))
        evidence_refs = _merge_refs(
            self.evidence_refs,
            *(component.evidence_refs for component in components if component is not None),
            *(snapshot.evidence_refs for snapshot in self.yield_snapshots),
        )
        object.__setattr__(self, "evidence_refs", evidence_refs)

    @property
    def cash_return_status(self) -> str:
        if self.history is None or self.capacity is None or self.sustainability is None:
            return DIVIDEND_RESEARCH_NOT_ASSESSED
        if self.blockers:
            return DIVIDEND_RESEARCH_PARTIAL
        if (
            self.history.status == HISTORY_COMPLETE
            and self.capacity.status == CAPACITY_READY
            and self.sustainability.status != SUSTAINABILITY_UNKNOWN
        ):
            return DIVIDEND_RESEARCH_AVAILABLE
        return DIVIDEND_RESEARCH_PARTIAL

    @property
    def explanation(self) -> str:
        history_status = self.history.status if self.history is not None else "MISSING"
        capacity_status = self.capacity.status if self.capacity is not None else "MISSING"
        sustainability_status = (
            self.sustainability.status if self.sustainability is not None else "MISSING"
        )
        return (
            f"类型化现金回报研究：历史={history_status}，分配能力={capacity_status}，"
            f"可持续性={sustainability_status}；不生成任何交易或仓位动作。"
        )

    def as_policy(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "profile_id": self.profile_id,
            "history": self.history.as_policy() if self.history is not None else None,
            "capacity": self.capacity.as_policy() if self.capacity is not None else None,
            "sustainability": (
                self.sustainability.as_policy() if self.sustainability is not None else None
            ),
            "yield_snapshots": [snapshot.as_policy() for snapshot in self.yield_snapshots],
            "as_of": self.as_of.isoformat(),
            "cash_return_status": self.cash_return_status,
            "blockers": list(self.blockers),
            "evidence_refs": _json_value(self.evidence_refs),
            "action": self.action,
        }

    def to_json(self) -> str:
        return json.dumps(self.as_policy(), ensure_ascii=False, allow_nan=False, indent=2)
