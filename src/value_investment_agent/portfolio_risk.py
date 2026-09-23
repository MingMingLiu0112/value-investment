"""Non-personal portfolio risk and concentration assessment for M4.

The assessment consumes an explicitly human-confirmed IPS and reconciled
portfolio snapshot. It reports concentration, cash-reserve and liquidity risk;
it never emits a position size, target weight or order. Missing private inputs
remain visible and the result stays incomplete.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import json
import re
from typing import Any, Mapping, Sequence

from .investment_decision import ACTION_NO_ORDER
from .portfolio_contracts import (
    NAMESPACE_ACTUAL,
    NAMESPACE_SIMULATED,
    QUANTITY_HUMAN_CONFIRMED,
    PortfolioInputBundle,
)


SCHEMA_VERSION = "m4-portfolio-risk-assessment-v1"

STATUS_PASS = "PASS"
STATUS_VIOLATION = "VIOLATION"
STATUS_REVIEW_REQUIRED = "REVIEW_REQUIRED"
STATUS_INCOMPLETE = "INCOMPLETE"
STATUSES = frozenset(
    {STATUS_PASS, STATUS_VIOLATION, STATUS_REVIEW_REQUIRED, STATUS_INCOMPLETE}
)

ASSESSMENT_NAMESPACE_ACTUAL = NAMESPACE_ACTUAL
ASSESSMENT_NAMESPACE_SIMULATED = NAMESPACE_SIMULATED
ASSESSMENT_NAMESPACES = frozenset(
    {ASSESSMENT_NAMESPACE_ACTUAL, ASSESSMENT_NAMESPACE_SIMULATED}
)

LIQUIDITY_LIQUID = "LIQUID"
LIQUIDITY_RESTRICTED = "RESTRICTED"
LIQUIDITY_UNKNOWN = "UNKNOWN"
LIQUIDITY_PROFILES = frozenset(
    {LIQUIDITY_LIQUID, LIQUIDITY_RESTRICTED, LIQUIDITY_UNKNOWN}
)

FINDING_SINGLE_SECURITY = "single_security_concentration"
FINDING_INDUSTRY = "industry_concentration"
FINDING_CYCLICAL = "cyclical_exposure"
FINDING_MINIMUM_CASH = "minimum_cash"
FINDING_RESERVED_CASH = "reserved_cash"
FINDING_LIQUIDITY = "liquidity_profile"


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
        raise ValueError(f"Risk payload contains execution keys: {', '.join(forbidden)}")


def _weight(part: Decimal, total: Decimal) -> Decimal:
    if total <= 0:
        return Decimal("0")
    return part / total


@dataclass(frozen=True)
class SecurityRiskAttributes:
    """Non-price risk identity for one portfolio security."""

    symbol: str
    industry: str
    cyclical: bool
    liquidity_profile: str
    common_factors: tuple[str, ...] = ()
    evidence_refs: tuple[dict[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("Risk symbol must contain six digits")
        object.__setattr__(self, "industry", _required_text(self.industry, "industry"))
        if self.liquidity_profile not in LIQUIDITY_PROFILES:
            raise ValueError("Unknown security liquidity profile")
        object.__setattr__(
            self,
            "common_factors",
            tuple(
                _required_text(item, "common factor")
                for item in self.common_factors
            ),
        )
        if len(self.common_factors) != len(set(self.common_factors)):
            raise ValueError("Common factors must be unique")
        object.__setattr__(self, "evidence_refs", _normalize_refs(self.evidence_refs))

    def as_policy(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "industry": self.industry,
            "cyclical": self.cyclical,
            "liquidity_profile": self.liquidity_profile,
            "common_factors": list(self.common_factors),
            "evidence_refs": [dict(ref) for ref in self.evidence_refs],
        }


def security_risk_attributes_from_payload(
    payload: Mapping[str, Any],
) -> SecurityRiskAttributes:
    if not isinstance(payload, Mapping):
        raise ValueError("Security risk attributes must be an object")
    data = dict(payload)
    return SecurityRiskAttributes(
        symbol=str(data["symbol"]),
        industry=str(data["industry"]),
        cyclical=bool(data["cyclical"]),
        liquidity_profile=str(data["liquidity_profile"]),
        common_factors=tuple(str(item) for item in data.get("common_factors") or ()),
        evidence_refs=tuple(dict(item) for item in data.get("evidence_refs") or ()),
    )


@dataclass(frozen=True)
class RiskFinding:
    """One machine-identifiable portfolio risk or human-review item."""

    kind: str
    subject: str
    measured: Decimal | None
    limit: Decimal | None
    message: str
    evidence_refs: tuple[dict[str, Any], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", _required_text(self.kind, "finding kind"))
        object.__setattr__(self, "subject", _required_text(self.subject, "subject"))
        object.__setattr__(
            self,
            "measured",
            _optional_decimal(self.measured, "finding measured"),
        )
        object.__setattr__(
            self,
            "limit",
            _optional_decimal(self.limit, "finding limit"),
        )
        object.__setattr__(self, "message", _required_text(self.message, "finding message"))
        object.__setattr__(self, "evidence_refs", _normalize_refs(self.evidence_refs))

    def as_policy(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "subject": self.subject,
            "measured": _decimal_text(self.measured),
            "limit": _decimal_text(self.limit),
            "message": self.message,
            "evidence_refs": [dict(ref) for ref in self.evidence_refs],
        }


@dataclass(frozen=True)
class PortfolioRiskAssessment:
    """Conservative point-in-time portfolio risk assessment."""

    assessment_id: str
    as_of: date
    generated_at: datetime
    bundle: PortfolioInputBundle
    security_attributes: Mapping[str, SecurityRiskAttributes]
    assessment_namespace: str = ASSESSMENT_NAMESPACE_ACTUAL
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        object.__setattr__(self, "assessment_id", _required_text(self.assessment_id, "assessment_id"))
        if not isinstance(self.as_of, date) or isinstance(self.as_of, datetime):
            raise ValueError("assessment as_of must be a date")
        if not isinstance(self.generated_at, datetime) or self.generated_at.tzinfo is None:
            raise ValueError("generated_at must be a timezone-aware datetime")
        if self.assessment_namespace not in ASSESSMENT_NAMESPACES:
            raise ValueError("Unknown risk assessment namespace")
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Risk assessment must remain no_order")
        object.__setattr__(
            self,
            "security_attributes",
            dict(self.security_attributes),
        )
        if self._structural_inputs_complete():
            if self.bundle.snapshot.namespace != self.assessment_namespace:
                raise ValueError("Risk assessment namespace must match the snapshot")
            if self.bundle.snapshot.as_of != self.as_of:
                raise ValueError("Risk as_of must match the portfolio snapshot")
            if self.generated_at < self.bundle.snapshot.available_at:
                raise ValueError("Risk cannot be generated before snapshot availability")
            missing = [
                holding.symbol
                for holding in self.bundle.snapshot.holdings
                if holding.symbol not in self.security_attributes
            ]
            if missing:
                raise ValueError(f"Missing security risk attributes: {', '.join(missing)}")
            if not self.security_attributes:
                raise ValueError("Risk assessment requires security attributes")

    def _structural_inputs_complete(self) -> bool:
        if not self.policy.can_support_guidance():
            return False
        if not self.snapshot.is_reconciled:
            return False
        if self.snapshot.namespace not in ASSESSMENT_NAMESPACES:
            return False
        if self.snapshot.cash_cny is None:
            return False
        return all(
            holding.quantity_source == QUANTITY_HUMAN_CONFIRMED
            and holding.market_value_cny is not None
            for holding in self.snapshot.holdings
        )

    @property
    def policy(self):
        return self.bundle.policy

    @property
    def snapshot(self):
        return self.bundle.snapshot

    def missing_inputs(self) -> tuple[str, ...]:
        missing = [
            f"policy.{item}"
            for item in self.policy.missing_guidance_inputs()
        ]
        if not self.snapshot.is_reconciled:
            missing.append("snapshot.reconciliation")
        if self.snapshot.account_scope == "missing":
            missing.append("snapshot.account_scope")
        if self.snapshot.cash_cny is None:
            missing.append("snapshot.cash_cny")
        if any(
            holding.quantity_source != QUANTITY_HUMAN_CONFIRMED
            for holding in self.snapshot.holdings
        ):
            missing.append("snapshot.holding_quantity_confirmation")
        if any(
            holding.market_value_cny is None
            for holding in self.snapshot.holdings
        ):
            missing.append("snapshot.holding_market_value")
        if self._structural_inputs_complete():
            missing.extend(
                f"security_attributes.{holding.symbol}"
                for holding in self.snapshot.holdings
                if holding.symbol not in self.security_attributes
            )
        return tuple(dict.fromkeys(missing))

    def can_assess(self) -> bool:
        return not self.missing_inputs()

    def total_assets_cny(self) -> Decimal | None:
        if not self.can_assess():
            return None
        cash = self.snapshot.cash_cny
        if cash is None:
            return None
        return cash + sum(
            (holding.market_value_cny or Decimal("0"))
            for holding in self.snapshot.holdings
        )

    def cash_cny(self) -> Decimal | None:
        return self.snapshot.cash_cny if self.can_assess() else None

    def reserved_cash_cny(self) -> Decimal | None:
        if not self.can_assess():
            return None
        minimum = self.policy.minimum_cash_cny or Decimal("0")
        emergency = self.policy.emergency_cash_cny or Decimal("0")
        liquidity = self.policy.liquidity_needs_cny or Decimal("0")
        return max(minimum, emergency + liquidity)

    def security_weights(self) -> dict[str, Decimal]:
        total = self.total_assets_cny()
        if total is None or total <= 0:
            return {}
        return {
            holding.symbol: _weight(holding.market_value_cny or Decimal("0"), total)
            for holding in self.snapshot.holdings
        }

    def industry_exposures(self) -> dict[str, Decimal]:
        total = self.total_assets_cny()
        if total is None or total <= 0:
            return {}
        result: dict[str, Decimal] = {}
        for holding in self.snapshot.holdings:
            attributes = self.security_attributes[holding.symbol]
            result[attributes.industry] = result.get(
                attributes.industry, Decimal("0")
            ) + _weight(holding.market_value_cny or Decimal("0"), total)
        return result

    def cyclical_exposure(self) -> Decimal:
        total = self.total_assets_cny()
        if total is None or total <= 0:
            return Decimal("0")
        part = sum(
            (holding.market_value_cny or Decimal("0"))
            for holding in self.snapshot.holdings
            if self.security_attributes[holding.symbol].cyclical
        )
        return _weight(part, total)

    def common_factor_exposures(self) -> dict[str, Decimal]:
        total = self.total_assets_cny()
        if total is None or total <= 0:
            return {}
        result: dict[str, Decimal] = {}
        for holding in self.snapshot.holdings:
            attributes = self.security_attributes[holding.symbol]
            weight = _weight(holding.market_value_cny or Decimal("0"), total)
            for factor in attributes.common_factors:
                result[factor] = result.get(factor, Decimal("0")) + weight
        return result

    def liquidity_profile_exposures(self) -> dict[str, Decimal]:
        total = self.total_assets_cny()
        if total is None or total <= 0:
            return {}
        result: dict[str, Decimal] = {}
        for holding in self.snapshot.holdings:
            profile = self.security_attributes[holding.symbol].liquidity_profile
            weight = _weight(holding.market_value_cny or Decimal("0"), total)
            result[profile] = result.get(profile, Decimal("0")) + weight
        return result

    def _finding_refs(self, symbol: str) -> tuple[dict[str, Any], ...]:
        holding = next(item for item in self.snapshot.holdings if item.symbol == symbol)
        return (*self.security_attributes[symbol].evidence_refs, *holding.evidence_refs)

    def findings(self) -> tuple[RiskFinding, ...]:
        if not self.can_assess():
            return ()

        result: list[RiskFinding] = []
        weights = self.security_weights()
        max_security = self.policy.max_single_security_pct
        max_industry = self.policy.max_single_industry_pct
        max_cyclical = self.policy.max_cyclical_exposure_pct

        for holding in self.snapshot.holdings:
            weight = weights[holding.symbol]
            if max_security is not None and weight > max_security / Decimal("100"):
                result.append(
                    RiskFinding(
                        kind=FINDING_SINGLE_SECURITY,
                        subject=holding.symbol,
                        measured=weight,
                        limit=max_security / Decimal("100"),
                        message=f"Security exposure exceeds the single-security cap",
                        evidence_refs=self._finding_refs(holding.symbol),
                    )
                )

        for industry, weight in self.industry_exposures().items():
            if max_industry is not None and weight > max_industry / Decimal("100"):
                subject = next(
                    self.security_attributes[h.symbol].industry
                    for h in self.snapshot.holdings
                    if self.security_attributes[h.symbol].industry == industry
                )
                result.append(
                    RiskFinding(
                        kind=FINDING_INDUSTRY,
                        subject=subject,
                        measured=weight,
                        limit=max_industry / Decimal("100"),
                        message="Industry exposure exceeds the policy cap",
                        evidence_refs=_normalize_refs(
                            ref
                            for h in self.snapshot.holdings
                            if self.security_attributes[h.symbol].industry == industry
                            for ref in self._finding_refs(h.symbol)
                        ),
                    )
                )

        cyclical = self.cyclical_exposure()
        if max_cyclical is not None and cyclical > max_cyclical / Decimal("100"):
            result.append(
                RiskFinding(
                    kind=FINDING_CYCLICAL,
                    subject="portfolio",
                    measured=cyclical,
                    limit=max_cyclical / Decimal("100"),
                    message="Cyclical exposure exceeds the policy cap",
                    evidence_refs=_normalize_refs(
                        ref
                        for h in self.snapshot.holdings
                        if self.security_attributes[h.symbol].cyclical
                        for ref in self._finding_refs(h.symbol)
                    ),
                )
            )

        cash = self.cash_cny()
        reserved = self.reserved_cash_cny()
        minimum = self.policy.minimum_cash_cny
        if cash is not None and reserved is not None:
            if minimum is not None and cash < minimum:
                result.append(
                    RiskFinding(
                        kind=FINDING_MINIMUM_CASH,
                        subject="cash",
                        measured=cash,
                        limit=minimum,
                        message="Cash is below the policy minimum",
                        evidence_refs=self.policy.evidence_refs,
                    )
                )
            if cash < reserved:
                result.append(
                    RiskFinding(
                        kind=FINDING_RESERVED_CASH,
                        subject="cash",
                        measured=cash,
                        limit=reserved,
                        message="Cash is below the combined emergency/liquidity reserve",
                        evidence_refs=self.policy.evidence_refs,
                    )
                )

        for profile, weight in self.liquidity_profile_exposures().items():
            if profile == LIQUIDITY_LIQUID:
                continue
            result.append(
                RiskFinding(
                    kind=FINDING_LIQUIDITY,
                    subject=profile,
                    measured=weight,
                    limit=None,
                    message="Non-liquid exposure requires explicit human review",
                    evidence_refs=_normalize_refs(
                        ref
                        for h in self.snapshot.holdings
                        if self.security_attributes[h.symbol].liquidity_profile == profile
                        for ref in self._finding_refs(h.symbol)
                    ),
                )
            )
        return tuple(result)

    @property
    def status(self) -> str:
        if not self.can_assess():
            return STATUS_INCOMPLETE
        findings = self.findings()
        if any(item.kind in {
            FINDING_SINGLE_SECURITY,
            FINDING_INDUSTRY,
            FINDING_CYCLICAL,
            FINDING_MINIMUM_CASH,
            FINDING_RESERVED_CASH,
        } for item in findings):
            return STATUS_VIOLATION
        if any(item.kind == FINDING_LIQUIDITY for item in findings):
            return STATUS_REVIEW_REQUIRED
        return STATUS_PASS

    def blockers(self) -> tuple[str, ...]:
        if not self.can_assess():
            return self.missing_inputs()
        if self.status == STATUS_PASS:
            return ()
        return tuple(item.kind for item in self.findings())

    def evidence_refs(self) -> tuple[dict[str, Any], ...]:
        merged: dict[str, dict[str, Any]] = {}
        groups = (
            self.policy.evidence_refs,
            self.snapshot.evidence_refs,
            *(
                self.security_attributes[h.symbol].evidence_refs
                for h in self.snapshot.holdings
                if h.symbol in self.security_attributes
            ),
        )
        for ref in (item for group in groups for item in group):
            ref_id = ref.get("id")
            if ref_id and ref_id not in merged:
                merged[ref_id] = dict(ref)
        return tuple(merged.values())

    @property
    def sensitivity(self) -> str:
        if self.assessment_namespace == ASSESSMENT_NAMESPACE_SIMULATED:
            return "SIMULATED_PUBLIC_DEMONSTRATION"
        return "PRIVATE_USER_CONFIRMED"

    def as_policy(self) -> dict[str, Any]:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "assessment_namespace": self.assessment_namespace,
            "assessment_id": self.assessment_id,
            "as_of": self.as_of.isoformat(),
            "generated_at": self.generated_at.isoformat(),
            "policy_id": self.policy.policy_id,
            "snapshot_id": self.snapshot.snapshot_id,
            "status": self.status,
            "missing_inputs": list(self.missing_inputs()),
            "total_assets_cny": _decimal_text(self.total_assets_cny()),
            "cash_cny": _decimal_text(self.cash_cny()),
            "reserved_cash_cny": _decimal_text(self.reserved_cash_cny()),
            "security_weights": {
                symbol: _decimal_text(weight)
                for symbol, weight in self.security_weights().items()
            },
            "industry_exposures": {
                industry: _decimal_text(weight)
                for industry, weight in self.industry_exposures().items()
            },
            "cyclical_exposure": _decimal_text(self.cyclical_exposure()),
            "common_factor_exposures": {
                factor: _decimal_text(weight)
                for factor, weight in self.common_factor_exposures().items()
            },
            "liquidity_profile_exposures": {
                profile: _decimal_text(weight)
                for profile, weight in self.liquidity_profile_exposures().items()
            },
            "security_attributes": {
                symbol: attributes.as_policy()
                for symbol, attributes in sorted(self.security_attributes.items())
            },
            "findings": [item.as_policy() for item in self.findings()],
            "blockers": list(self.blockers()),
            "evidence_refs": [dict(ref) for ref in self.evidence_refs()],
            "sensitivity": self.sensitivity,
            "action": self.action,
        }
        _reject_public_execution_keys(payload)
        return payload

    def to_json(self) -> str:
        return json.dumps(self.as_policy(), ensure_ascii=False, allow_nan=False, indent=2)


def build_portfolio_risk_assessment(
    *,
    bundle: PortfolioInputBundle,
    security_attributes: Mapping[str, SecurityRiskAttributes],
    as_of: date,
    generated_at: datetime,
    assessment_id: str,
    assessment_namespace: str = ASSESSMENT_NAMESPACE_ACTUAL,
) -> PortfolioRiskAssessment:
    return PortfolioRiskAssessment(
        assessment_id=assessment_id,
        as_of=as_of,
        generated_at=generated_at,
        bundle=bundle,
        security_attributes=security_attributes,
        assessment_namespace=assessment_namespace,
    )
