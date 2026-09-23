"""Transparent enterprise-to-equity bridge review with scenario haircuts.

The domain is deliberately generic: it exposes how much of an equity valuation
comes from operating value versus financial/legal-entity bridge items. Unknown
recoverability is retained as unknown and never silently converted to 100%.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import json
import re
from typing import Any, Mapping, Sequence


BRIDGE_REVIEW_SCHEMA = "post-m1-bridge-contribution-review-v1"
ACTION_NO_ORDER = "no_order"

KIND_NON_OPERATING_ASSET = "non_operating_asset"
KIND_DEBT = "debt"
KIND_MINORITY_INTEREST = "minority_interest"
KIND_OTHER_CLAIM = "other_claim"
KINDS = {
    KIND_NON_OPERATING_ASSET,
    KIND_DEBT,
    KIND_MINORITY_INTEREST,
    KIND_OTHER_CLAIM,
}

RECOVERABILITY_VERIFIED = "VERIFIED"
RECOVERABILITY_PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
RECOVERABILITY_CONSERVATIVE_ASSUMPTION = "CONSERVATIVE_ASSUMPTION"
RECOVERABILITY_UNKNOWN = "UNKNOWN"
RECOVERABILITY_CONTRACTUAL = "CONTRACTUAL"
RECOVERABILITY_VALUES = {
    RECOVERABILITY_VERIFIED,
    RECOVERABILITY_PARTIALLY_SUPPORTED,
    RECOVERABILITY_CONSERVATIVE_ASSUMPTION,
    RECOVERABILITY_UNKNOWN,
    RECOVERABILITY_CONTRACTUAL,
}

LEGAL_AVAILABILITY_VERIFIED = "VERIFIED"
LEGAL_AVAILABILITY_PARTIAL = "PARTIAL"
LEGAL_AVAILABILITY_RESTRICTED = "RESTRICTED"
LEGAL_AVAILABILITY_UNKNOWN = "UNKNOWN"
LEGAL_AVAILABILITY_VALUES = {
    LEGAL_AVAILABILITY_VERIFIED,
    LEGAL_AVAILABILITY_PARTIAL,
    LEGAL_AVAILABILITY_RESTRICTED,
    LEGAL_AVAILABILITY_UNKNOWN,
}

LIQUIDITY_HIGH = "HIGH"
LIQUIDITY_MEDIUM = "MEDIUM"
LIQUIDITY_LOW = "LOW"
LIQUIDITY_UNKNOWN = "UNKNOWN"
LIQUIDITY_VALUES = {
    LIQUIDITY_HIGH,
    LIQUIDITY_MEDIUM,
    LIQUIDITY_LOW,
    LIQUIDITY_UNKNOWN,
}

CONFIDENCE_HIGH = "高"
CONFIDENCE_MEDIUM = "中"
CONFIDENCE_LOW = "低"
CONFIDENCE_VALUES = {CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW}

SCENARIOS = {"bear", "base", "bull"}

_SYMBOL = re.compile(r"^[0-9]{6}$")


def _finite_decimal(value: Decimal | None, field: str) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{field} must be a finite Decimal")
    return value


def _positive_decimal(value: Decimal, field: str) -> Decimal:
    checked = _finite_decimal(value, field)
    if checked is None or checked <= 0:
        raise ValueError(f"{field} must be positive")
    return checked


def _refs(refs: tuple[dict[str, Any], ...]) -> tuple[dict[str, Any], ...]:
    normalized = tuple(dict(ref) for ref in refs)
    if any(not ref.get("id") for ref in normalized):
        raise ValueError("Bridge review evidence references require ids")
    return normalized


@dataclass(frozen=True)
class BridgeComponentAssessment:
    """One bridge line, including bear/base/bull legal and recovery judgment."""

    symbol: str
    name: str
    kind: str
    book_value: Decimal
    legal_availability: str
    liquidity: str
    recoverability: str
    bear_haircut: Decimal | None
    base_haircut: Decimal | None
    bull_haircut: Decimal | None
    bear_recoverable_value: Decimal | None
    base_recoverable_value: Decimal | None
    bull_recoverable_value: Decimal | None
    basis: str
    confidence: str
    evidence_refs: tuple[dict[str, Any], ...]
    blockers: tuple[str, ...] = ()
    stress_test_only: bool = False
    not_valuation_input: bool = False
    not_price_assessment_input: bool = False

    def __post_init__(self) -> None:
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("Bridge component symbol must contain six digits")
        if not self.name.strip() or not self.basis.strip():
            raise ValueError("Bridge component name and basis are required")
        if self.kind not in KINDS:
            raise ValueError("Unknown bridge component kind")
        if self.legal_availability not in LEGAL_AVAILABILITY_VALUES:
            raise ValueError("Unknown bridge legal availability")
        if self.liquidity not in LIQUIDITY_VALUES:
            raise ValueError("Unknown bridge liquidity")
        if self.recoverability not in RECOVERABILITY_VALUES:
            raise ValueError("Unknown bridge recoverability")
        if self.confidence not in CONFIDENCE_VALUES:
            raise ValueError("Bridge confidence must be 高, 中 or 低")
        object.__setattr__(self, "book_value", _positive_decimal(self.book_value, "book_value"))

        haircuts = (self.bear_haircut, self.base_haircut, self.bull_haircut)
        recoverable = (
            self.bear_recoverable_value,
            self.base_recoverable_value,
            self.bull_recoverable_value,
        )
        unknown = self.recoverability == RECOVERABILITY_UNKNOWN
        if unknown:
            if any(value is not None for value in haircuts) or any(
                value is not None for value in recoverable
            ):
                raise ValueError("UNKNOWN recoverability cannot carry a haircut or value")
            if not self.blockers:
                raise ValueError("UNKNOWN recoverability requires a blocker")
        elif any(value is None for value in haircuts):
            raise ValueError("Known recoverability requires bear/base/bull haircuts")
        else:
            for value in haircuts:
                if value < 0 or value > 1:
                    raise ValueError("Bridge haircuts must be within 0 and 1")
            if not (self.bear_haircut >= self.base_haircut >= self.bull_haircut):
                raise ValueError("Bridge haircuts must be bear >= base >= bull")
            expected = tuple(
                self.book_value * (Decimal("1") - value) for value in haircuts
            )
            for supplied, wanted in zip(recoverable, expected):
                if supplied is None or supplied != wanted:
                    raise ValueError(
                        "Bridge recoverable values must equal book_value * (1 - haircut)"
                    )
        if self.kind in {KIND_DEBT, KIND_MINORITY_INTEREST, KIND_OTHER_CLAIM}:
            if self.recoverability != RECOVERABILITY_CONTRACTUAL:
                raise ValueError("Claims must use CONTRACTUAL recoverability")
            if any(value != 0 for value in haircuts if value is not None):
                raise ValueError("Claims must use a zero haircut")
        object.__setattr__(
            self,
            "evidence_refs",
            _refs(tuple(self.evidence_refs)),
        )
        object.__setattr__(
            self,
            "blockers",
            tuple(str(item) for item in self.blockers),
        )

    def as_policy(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "kind": self.kind,
            "book_value": str(self.book_value),
            "legal_availability": self.legal_availability,
            "liquidity": self.liquidity,
            "recoverability": self.recoverability,
            "bear_haircut": _decimal(self.bear_haircut),
            "base_haircut": _decimal(self.base_haircut),
            "bull_haircut": _decimal(self.bull_haircut),
            "bear_recoverable_value": _decimal(self.bear_recoverable_value),
            "base_recoverable_value": _decimal(self.base_recoverable_value),
            "bull_recoverable_value": _decimal(self.bull_recoverable_value),
            "basis": self.basis,
            "confidence": self.confidence,
            "evidence_refs": [dict(ref) for ref in self.evidence_refs],
            "blockers": list(self.blockers),
            "stress_test_only": self.stress_test_only,
            "not_valuation_input": self.not_valuation_input,
            "not_price_assessment_input": self.not_price_assessment_input,
        }


def _decimal(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _sum_component_values(
    components: Sequence[BridgeComponentAssessment],
    kind: str,
    scenario: str,
) -> tuple[Decimal, list[str]]:
    total = Decimal("0")
    blockers: list[str] = []
    for component in components:
        if component.kind != kind:
            continue
        value = getattr(component, f"{scenario}_recoverable_value")
        if value is None:
            blockers.append(f"unrecognized_{kind}:{component.name}")
            continue
        total += value
    return total, blockers


@dataclass(frozen=True)
class BridgeContributionAssessment:
    """One scenario arithmetic decomposition, independent of ValuationResult."""

    symbol: str
    valuation_scenario: str
    currency: str
    ordinary_shares: Decimal
    operating_enterprise_value: Decimal
    gross_non_operating_assets: Decimal
    debt: Decimal
    minority_interest: Decimal
    other_claims: Decimal
    net_equity_bridge: Decimal
    net_bridge_per_share: Decimal
    total_equity_value: Decimal
    total_value_per_share: Decimal
    bridge_share_of_equity_value: Decimal
    bridge_components: tuple[BridgeComponentAssessment, ...]
    confidence: str
    blockers: tuple[str, ...]
    evidence_refs: tuple[dict[str, Any], ...]
    action: str = ACTION_NO_ORDER
    stress_test_only: bool = False
    not_valuation_input: bool = False
    not_price_assessment_input: bool = False

    def __post_init__(self) -> None:
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("Bridge contribution symbol must contain six digits")
        if self.valuation_scenario not in SCENARIOS:
            raise ValueError("Unknown bridge valuation scenario")
        if self.currency not in {"CNY", "USD", "HKD"}:
            raise ValueError("Unsupported bridge currency")
        _positive_decimal(self.ordinary_shares, "ordinary_shares")
        if self.ordinary_shares != self.ordinary_shares.to_integral_value():
            raise ValueError("Ordinary shares must be a positive integer")
        _positive_decimal(self.operating_enterprise_value, "operating_enterprise_value")
        for field in (
            "gross_non_operating_assets",
            "debt",
            "minority_interest",
            "other_claims",
            "total_equity_value",
        ):
            value = _finite_decimal(getattr(self, field), field)
            if value is not None and value < 0:
                raise ValueError(f"{field} cannot be negative")
        _positive_decimal(self.total_equity_value, "total_equity_value")
        expected_bridge = (
            self.gross_non_operating_assets
            - self.debt
            - self.minority_interest
            - self.other_claims
        )
        if self.net_equity_bridge != expected_bridge:
            raise ValueError("Bridge arithmetic does not reconcile")
        expected_total = self.operating_enterprise_value + self.net_equity_bridge
        if self.total_equity_value != expected_total:
            raise ValueError("Total equity value does not reconcile")
        expected_per_share = self.total_equity_value / self.ordinary_shares
        if self.total_value_per_share != expected_per_share:
            raise ValueError("Per-share value does not reconcile")
        expected_net_per_share = self.net_equity_bridge / self.ordinary_shares
        if self.net_bridge_per_share != expected_net_per_share:
            raise ValueError("Net bridge per share does not reconcile")
        expected_share = self.net_equity_bridge / self.total_equity_value
        if self.bridge_share_of_equity_value != expected_share:
            raise ValueError("Bridge share of equity value does not reconcile")
        if self.confidence not in CONFIDENCE_VALUES:
            raise ValueError("Bridge confidence must be 高, 中 or 低")
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Bridge review must remain no_order")
        if any(component.symbol != self.symbol for component in self.bridge_components):
            raise ValueError("Bridge components must share the review symbol")
        object.__setattr__(
            self,
            "bridge_components",
            tuple(self.bridge_components),
        )
        object.__setattr__(
            self,
            "blockers",
            tuple(dict.fromkeys(str(item) for item in self.blockers)),
        )
        object.__setattr__(
            self,
            "evidence_refs",
            _refs(tuple(self.evidence_refs)),
        )

    def as_policy(self) -> dict[str, Any]:
        return {
            "schema_version": BRIDGE_REVIEW_SCHEMA,
            "symbol": self.symbol,
            "valuation_scenario": self.valuation_scenario,
            "currency": self.currency,
            "ordinary_shares": str(self.ordinary_shares),
            "operating_enterprise_value": str(self.operating_enterprise_value),
            "gross_non_operating_assets": str(self.gross_non_operating_assets),
            "debt": str(self.debt),
            "minority_interest": str(self.minority_interest),
            "other_claims": str(self.other_claims),
            "net_equity_bridge": str(self.net_equity_bridge),
            "net_bridge_per_share": str(self.net_bridge_per_share),
            "total_equity_value": str(self.total_equity_value),
            "total_value_per_share": str(self.total_value_per_share),
            "bridge_share_of_equity_value": str(
                self.bridge_share_of_equity_value
            ),
            "bridge_components": [item.as_policy() for item in self.bridge_components],
            "confidence": self.confidence,
            "blockers": list(self.blockers),
            "evidence_refs": [dict(ref) for ref in self.evidence_refs],
            "action": self.action,
            "stress_test_only": self.stress_test_only,
            "not_valuation_input": self.not_valuation_input,
            "not_price_assessment_input": self.not_price_assessment_input,
        }

    def to_json(self) -> str:
        return json.dumps(
            self.as_policy(),
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        )


def build_bridge_contribution(
    *,
    symbol: str,
    valuation_scenario: str,
    currency: str,
    ordinary_shares: Decimal,
    operating_enterprise_value: Decimal,
    components: Sequence[BridgeComponentAssessment],
    confidence: str,
    evidence_refs: Sequence[dict[str, Any]] = (),
    blockers: Sequence[str] = (),
) -> BridgeContributionAssessment:
    """Recalculate every arithmetic field from the reviewed components."""
    gross, asset_blockers = _sum_component_values(
        components,
        KIND_NON_OPERATING_ASSET,
        valuation_scenario,
    )
    debt, debt_blockers = _sum_component_values(
        components,
        KIND_DEBT,
        valuation_scenario,
    )
    minority, minority_blockers = _sum_component_values(
        components,
        KIND_MINORITY_INTEREST,
        valuation_scenario,
    )
    other, other_blockers = _sum_component_values(
        components,
        KIND_OTHER_CLAIM,
        valuation_scenario,
    )
    net_bridge = gross - debt - minority - other
    total_equity = operating_enterprise_value + net_bridge
    net_per_share = net_bridge / ordinary_shares
    total_per_share = total_equity / ordinary_shares
    share_of_equity = net_bridge / total_equity
    merged_blockers = [
        *asset_blockers,
        *debt_blockers,
        *minority_blockers,
        *other_blockers,
        *blockers,
    ]
    for component in components:
        merged_blockers.extend(component.blockers)
    stress_test_only = any(component.stress_test_only for component in components)
    not_valuation_input = any(component.not_valuation_input for component in components)
    not_price_assessment_input = any(
        component.not_price_assessment_input for component in components
    )
    return BridgeContributionAssessment(
        symbol=symbol,
        valuation_scenario=valuation_scenario,
        currency=currency,
        ordinary_shares=ordinary_shares,
        operating_enterprise_value=operating_enterprise_value,
        gross_non_operating_assets=gross,
        debt=debt,
        minority_interest=minority,
        other_claims=other,
        net_equity_bridge=net_bridge,
        net_bridge_per_share=net_per_share,
        total_equity_value=total_equity,
        total_value_per_share=total_per_share,
        bridge_share_of_equity_value=share_of_equity,
        bridge_components=tuple(components),
        confidence=confidence,
        blockers=tuple(dict.fromkeys(merged_blockers)),
        evidence_refs=tuple(dict(ref) for ref in evidence_refs),
        stress_test_only=stress_test_only,
        not_valuation_input=not_valuation_input,
        not_price_assessment_input=not_price_assessment_input,
    )


def bridge_component_from_payload(
    payload: Mapping[str, Any],
) -> BridgeComponentAssessment:
    data = dict(payload)
    return BridgeComponentAssessment(
        symbol=str(data["symbol"]),
        name=str(data["name"]),
        kind=str(data["kind"]),
        book_value=Decimal(data["book_value"]),
        legal_availability=str(data["legal_availability"]),
        liquidity=str(data["liquidity"]),
        recoverability=str(data["recoverability"]),
        bear_haircut=_optional_decimal(data.get("bear_haircut"), "bear_haircut"),
        base_haircut=_optional_decimal(data.get("base_haircut"), "base_haircut"),
        bull_haircut=_optional_decimal(data.get("bull_haircut"), "bull_haircut"),
        bear_recoverable_value=_optional_decimal(
            data.get("bear_recoverable_value"), "bear_recoverable_value"
        ),
        base_recoverable_value=_optional_decimal(
            data.get("base_recoverable_value"), "base_recoverable_value"
        ),
        bull_recoverable_value=_optional_decimal(
            data.get("bull_recoverable_value"), "bull_recoverable_value"
        ),
        basis=str(data["basis"]),
        confidence=str(data["confidence"]),
        evidence_refs=tuple(dict(item) for item in data.get("evidence_refs") or ()),
        blockers=tuple(str(item) for item in data.get("blockers") or ()),
        stress_test_only=bool(data.get("stress_test_only", False)),
        not_valuation_input=bool(data.get("not_valuation_input", False)),
        not_price_assessment_input=bool(data.get("not_price_assessment_input", False)),
    )


def _optional_decimal(value: object, field: str) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"{field} must be a decimal") from error


def bridge_contribution_from_payload(
    payload: Mapping[str, Any],
) -> BridgeContributionAssessment:
    data = dict(payload)
    if data.get("schema_version") != BRIDGE_REVIEW_SCHEMA:
        raise ValueError("Unknown bridge contribution schema")
    return BridgeContributionAssessment(
        symbol=str(data["symbol"]),
        valuation_scenario=str(data["valuation_scenario"]),
        currency=str(data["currency"]),
        ordinary_shares=Decimal(data["ordinary_shares"]),
        operating_enterprise_value=Decimal(data["operating_enterprise_value"]),
        gross_non_operating_assets=Decimal(data["gross_non_operating_assets"]),
        debt=Decimal(data["debt"]),
        minority_interest=Decimal(data["minority_interest"]),
        other_claims=Decimal(data["other_claims"]),
        net_equity_bridge=Decimal(data["net_equity_bridge"]),
        net_bridge_per_share=Decimal(data["net_bridge_per_share"]),
        total_equity_value=Decimal(data["total_equity_value"]),
        total_value_per_share=Decimal(data["total_value_per_share"]),
        bridge_share_of_equity_value=Decimal(data["bridge_share_of_equity_value"]),
        bridge_components=tuple(
            bridge_component_from_payload(item)
            for item in data.get("bridge_components") or ()
        ),
        confidence=str(data["confidence"]),
        blockers=tuple(str(item) for item in data.get("blockers") or ()),
        evidence_refs=tuple(dict(item) for item in data.get("evidence_refs") or ()),
        action=str(data.get("action", ACTION_NO_ORDER)),
        stress_test_only=bool(data.get("stress_test_only", False)),
        not_valuation_input=bool(data.get("not_valuation_input", False)),
        not_price_assessment_input=bool(data.get("not_price_assessment_input", False)),
    )
