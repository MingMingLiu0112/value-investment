"""Private, fail-closed input contracts for M4 portfolio guidance.

These objects describe a human-confirmed investment policy and portfolio
snapshot.  They do not calculate a position, invent a risk preference, read a
broker account or create an order.  Missing fields remain visible and prevent
personalized guidance instead of being replaced with universal percentages.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import json
import re
from typing import Any, Mapping, Sequence

from .investment_decision import ACTION_NO_ORDER


SCHEMA_VERSION = "m4-portfolio-contracts-v1"
NAMESPACE_ACTUAL = "ACTUAL"
NAMESPACE_SIMULATED = "SIMULATED"
PORTFOLIO_NAMESPACES = frozenset({NAMESPACE_ACTUAL, NAMESPACE_SIMULATED})

CONFIRMATION_DRAFT = "DRAFT"
CONFIRMATION_HUMAN = "HUMAN_CONFIRMED"
CONFIRMATION_STATUSES = frozenset({CONFIRMATION_DRAFT, CONFIRMATION_HUMAN})

RECONCILIATION_UNCONFIRMED = "UNCONFIRMED"
RECONCILIATION_PENDING = "PENDING_RECONCILIATION"
RECONCILIATION_RECONCILED = "RECONCILED"
RECONCILIATION_STATUSES = frozenset(
    {
        RECONCILIATION_UNCONFIRMED,
        RECONCILIATION_PENDING,
        RECONCILIATION_RECONCILED,
    }
)

QUANTITY_HUMAN_CONFIRMED = "HUMAN_CONFIRMED"
QUANTITY_PENDING_RECONCILIATION = "PENDING_RECONCILIATION"
QUANTITY_SOURCES = frozenset(
    {QUANTITY_HUMAN_CONFIRMED, QUANTITY_PENDING_RECONCILIATION}
)

RISK_UNKNOWN = "UNKNOWN"
RISK_CONSERVATIVE = "CONSERVATIVE"
RISK_BALANCED = "BALANCED"
RISK_GROWTH = "GROWTH"
RISK_TOLERANCES = frozenset(
    {RISK_UNKNOWN, RISK_CONSERVATIVE, RISK_BALANCED, RISK_GROWTH}
)

_SYMBOL = re.compile(r"^[0-9]{6}$")
_EXCHANGES = frozenset({"SSE", "SZSE", "BSE"})
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
    if value is None:
        return None
    return _required_text(value, field)


def _required_date(value: object, field: str) -> date:
    if not isinstance(value, date) or isinstance(value, datetime):
        raise ValueError(f"{field} must be a date")
    return value


def _required_datetime(value: object, field: str) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"{field} must be a timezone-aware datetime")
    return value


def _optional_datetime(value: object, field: str) -> datetime | None:
    if value is None:
        return None
    return _required_datetime(value, field)


def _decimal(value: object, field: str) -> Decimal | None:
    if value is None:
        return None
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


def _nonnegative_decimal(value: object, field: str) -> Decimal | None:
    parsed = _decimal(value, field)
    if parsed is not None and parsed < 0:
        raise ValueError(f"{field} cannot be negative")
    return parsed


def _positive_decimal(value: object, field: str) -> Decimal | None:
    parsed = _decimal(value, field)
    if parsed is not None and parsed <= 0:
        raise ValueError(f"{field} must be positive")
    return parsed


def _percentage(value: object, field: str) -> Decimal | None:
    parsed = _decimal(value, field)
    if parsed is not None and not (0 < parsed <= 100):
        raise ValueError(f"{field} must be in (0, 100]")
    return parsed


def _optional_bool(value: object, field: str) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be boolean or null")
    return value


def _required_bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be boolean")
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


def _reject_public_execution_keys(value: object) -> None:
    if isinstance(value, Mapping):
        forbidden = sorted(_FORBIDDEN_PUBLIC_KEYS & set(value))
        if forbidden:
            raise ValueError(
                f"Portfolio contracts contain execution keys: {forbidden}"
            )
        for nested in value.values():
            _reject_public_execution_keys(nested)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for item in value:
            _reject_public_execution_keys(item)


@dataclass(frozen=True)
class InvestorPolicyStatement:
    policy_id: str
    policy_version: str
    as_of: date
    confirmation_status: str
    confirmed_at: datetime | None
    account_scope: str
    investable_assets_cny: Decimal | None
    minimum_cash_cny: Decimal | None
    emergency_cash_cny: Decimal | None
    liquidity_needs_cny: Decimal | None
    time_horizon_years: Decimal | None
    max_single_security_pct: Decimal | None
    max_single_industry_pct: Decimal | None
    max_cyclical_exposure_pct: Decimal | None
    dividend_income_goal_cny: Decimal | None
    risk_tolerance: str
    concentration_allowed: bool | None
    tax_regime: str | None
    restrictions: tuple[str, ...]
    evidence_refs: tuple[dict[str, Any], ...]
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_id", _required_text(self.policy_id, "policy_id"))
        object.__setattr__(
            self,
            "policy_version",
            _required_text(self.policy_version, "policy_version"),
        )
        object.__setattr__(self, "as_of", _required_date(self.as_of, "as_of"))
        if self.confirmation_status not in CONFIRMATION_STATUSES:
            raise ValueError("Unknown investor policy confirmation status")
        if self.confirmation_status == CONFIRMATION_HUMAN:
            object.__setattr__(
                self,
                "confirmed_at",
                _required_datetime(self.confirmed_at, "confirmed_at"),
            )
            object.__setattr__(
                self,
                "account_scope",
                _required_text(self.account_scope, "account_scope"),
            )
            if self.account_scope == "missing":
                raise ValueError("Confirmed policy requires a real account scope")
            if not self.evidence_refs:
                raise ValueError("Confirmed policy requires confirmation evidence")
        else:
            if self.confirmed_at is not None:
                raise ValueError("Draft policy cannot carry confirmed_at")
            object.__setattr__(self, "account_scope", _required_text(self.account_scope, "account_scope"))
        if self.risk_tolerance not in RISK_TOLERANCES:
            raise ValueError("Unknown investor risk tolerance")
        object.__setattr__(
            self,
            "investable_assets_cny",
            _nonnegative_decimal(self.investable_assets_cny, "investable_assets_cny"),
        )
        object.__setattr__(
            self,
            "minimum_cash_cny",
            _nonnegative_decimal(self.minimum_cash_cny, "minimum_cash_cny"),
        )
        object.__setattr__(
            self,
            "emergency_cash_cny",
            _nonnegative_decimal(self.emergency_cash_cny, "emergency_cash_cny"),
        )
        object.__setattr__(
            self,
            "liquidity_needs_cny",
            _nonnegative_decimal(self.liquidity_needs_cny, "liquidity_needs_cny"),
        )
        object.__setattr__(
            self,
            "time_horizon_years",
            _positive_decimal(self.time_horizon_years, "time_horizon_years"),
        )
        object.__setattr__(
            self,
            "max_single_security_pct",
            _percentage(self.max_single_security_pct, "max_single_security_pct"),
        )
        object.__setattr__(
            self,
            "max_single_industry_pct",
            _percentage(self.max_single_industry_pct, "max_single_industry_pct"),
        )
        object.__setattr__(
            self,
            "max_cyclical_exposure_pct",
            _percentage(
                self.max_cyclical_exposure_pct,
                "max_cyclical_exposure_pct",
            ),
        )
        object.__setattr__(
            self,
            "dividend_income_goal_cny",
            _nonnegative_decimal(
                self.dividend_income_goal_cny,
                "dividend_income_goal_cny",
            ),
        )
        object.__setattr__(
            self,
            "concentration_allowed",
            _optional_bool(self.concentration_allowed, "concentration_allowed"),
        )
        object.__setattr__(
            self, "tax_regime", _optional_text(self.tax_regime, "tax_regime")
        )
        object.__setattr__(self, "restrictions", tuple(_required_text(item, "restriction") for item in self.restrictions))
        object.__setattr__(self, "evidence_refs", _normalize_refs(self.evidence_refs))
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Investor policy must remain no_order")

    @classmethod
    def missing(cls, *, policy_id: str = "policy-missing", as_of: date | None = None) -> InvestorPolicyStatement:
        return cls(
            policy_id=policy_id,
            policy_version="v0-missing",
            as_of=as_of or date.min,
            confirmation_status=CONFIRMATION_DRAFT,
            confirmed_at=None,
            account_scope="missing",
            investable_assets_cny=None,
            minimum_cash_cny=None,
            emergency_cash_cny=None,
            liquidity_needs_cny=None,
            time_horizon_years=None,
            max_single_security_pct=None,
            max_single_industry_pct=None,
            max_cyclical_exposure_pct=None,
            dividend_income_goal_cny=None,
            risk_tolerance=RISK_UNKNOWN,
            concentration_allowed=None,
            tax_regime=None,
            restrictions=("no_order",),
            evidence_refs=(),
        )

    @property
    def is_human_confirmed(self) -> bool:
        return self.confirmation_status == CONFIRMATION_HUMAN

    @property
    def sensitivity(self) -> str:
        return "PRIVATE_USER_CONFIRMED"

    def missing_guidance_inputs(self) -> tuple[str, ...]:
        missing = []
        if not self.is_human_confirmed:
            missing.append("human_confirmation")
        if self.investable_assets_cny is None or self.investable_assets_cny == 0:
            missing.append("investable_assets_cny")
        if self.minimum_cash_cny is None:
            missing.append("minimum_cash_cny")
        if self.time_horizon_years is None:
            missing.append("time_horizon_years")
        if self.max_single_security_pct is None:
            missing.append("max_single_security_pct")
        if self.max_single_industry_pct is None:
            missing.append("max_single_industry_pct")
        if self.concentration_allowed is None:
            missing.append("concentration_allowed")
        if self.risk_tolerance == RISK_UNKNOWN:
            missing.append("risk_tolerance")
        return tuple(missing)

    def can_support_guidance(self) -> bool:
        return not self.missing_guidance_inputs()

    def as_policy(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "as_of": self.as_of.isoformat(),
            "confirmation_status": self.confirmation_status,
            "confirmed_at": self.confirmed_at.isoformat() if self.confirmed_at else None,
            "account_scope": self.account_scope,
            "investable_assets_cny": str(self.investable_assets_cny) if self.investable_assets_cny is not None else None,
            "minimum_cash_cny": str(self.minimum_cash_cny) if self.minimum_cash_cny is not None else None,
            "emergency_cash_cny": str(self.emergency_cash_cny) if self.emergency_cash_cny is not None else None,
            "liquidity_needs_cny": str(self.liquidity_needs_cny) if self.liquidity_needs_cny is not None else None,
            "time_horizon_years": str(self.time_horizon_years) if self.time_horizon_years is not None else None,
            "max_single_security_pct": str(self.max_single_security_pct) if self.max_single_security_pct is not None else None,
            "max_single_industry_pct": str(self.max_single_industry_pct) if self.max_single_industry_pct is not None else None,
            "max_cyclical_exposure_pct": str(self.max_cyclical_exposure_pct) if self.max_cyclical_exposure_pct is not None else None,
            "dividend_income_goal_cny": str(self.dividend_income_goal_cny) if self.dividend_income_goal_cny is not None else None,
            "risk_tolerance": self.risk_tolerance,
            "concentration_allowed": self.concentration_allowed,
            "tax_regime": self.tax_regime,
            "restrictions": list(self.restrictions),
            "evidence_refs": [dict(ref) for ref in self.evidence_refs],
            "sensitivity": self.sensitivity,
            "action": self.action,
        }

    def to_json(self) -> str:
        return json.dumps(self.as_policy(), ensure_ascii=False, allow_nan=False, indent=2)


@dataclass(frozen=True)
class PortfolioHolding:
    symbol: str
    exchange: str
    quantity: Decimal
    cost_basis_cny: Decimal | None
    market_value_cny: Decimal | None
    quantity_source: str
    corporate_action_adjusted: bool
    evidence_refs: tuple[dict[str, Any], ...]

    def __post_init__(self) -> None:
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("Portfolio holding symbol must contain six digits")
        if self.exchange not in _EXCHANGES:
            raise ValueError("Unknown portfolio holding exchange")
        if self.quantity_source not in QUANTITY_SOURCES:
            raise ValueError("Unknown holding quantity source")
        object.__setattr__(
            self,
            "corporate_action_adjusted",
            _required_bool(
                self.corporate_action_adjusted,
                "corporate_action_adjusted",
            ),
        )
        object.__setattr__(
            self,
            "quantity",
            _positive_decimal(self.quantity, "quantity"),
        )
        if self.quantity is None:
            raise ValueError("quantity is required")
        object.__setattr__(
            self,
            "cost_basis_cny",
            _nonnegative_decimal(self.cost_basis_cny, "cost_basis_cny"),
        )
        object.__setattr__(
            self,
            "market_value_cny",
            _nonnegative_decimal(self.market_value_cny, "market_value_cny"),
        )
        object.__setattr__(self, "evidence_refs", _normalize_refs(self.evidence_refs))
        if self.quantity_source == QUANTITY_HUMAN_CONFIRMED and not self.evidence_refs:
            raise ValueError("Human-confirmed holding requires reconciliation evidence")

    def as_policy(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "exchange": self.exchange,
            "quantity": str(self.quantity),
            "cost_basis_cny": str(self.cost_basis_cny) if self.cost_basis_cny is not None else None,
            "market_value_cny": str(self.market_value_cny) if self.market_value_cny is not None else None,
            "quantity_source": self.quantity_source,
            "corporate_action_adjusted": self.corporate_action_adjusted,
            "evidence_refs": [dict(ref) for ref in self.evidence_refs],
        }


@dataclass(frozen=True)
class PortfolioSnapshot:
    snapshot_id: str
    snapshot_version: str
    as_of: date
    available_at: datetime
    account_scope: str
    namespace: str
    cash_cny: Decimal | None
    holdings: tuple[PortfolioHolding, ...]
    reconciliation_status: str
    reconciled_at: datetime | None
    evidence_refs: tuple[dict[str, Any], ...]
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        object.__setattr__(self, "snapshot_id", _required_text(self.snapshot_id, "snapshot_id"))
        object.__setattr__(
            self,
            "snapshot_version",
            _required_text(self.snapshot_version, "snapshot_version"),
        )
        object.__setattr__(self, "as_of", _required_date(self.as_of, "as_of"))
        object.__setattr__(
            self,
            "available_at",
            _required_datetime(self.available_at, "available_at"),
        )
        object.__setattr__(
            self,
            "account_scope",
            _required_text(self.account_scope, "account_scope"),
        )
        if self.namespace not in PORTFOLIO_NAMESPACES:
            raise ValueError("Unknown portfolio namespace")
        if self.reconciliation_status not in RECONCILIATION_STATUSES:
            raise ValueError("Unknown portfolio reconciliation status")
        object.__setattr__(
            self,
            "cash_cny",
            _nonnegative_decimal(self.cash_cny, "cash_cny"),
        )
        symbols = [holding.symbol for holding in self.holdings]
        if len(set(symbols)) != len(symbols):
            raise ValueError("Portfolio snapshot holdings must be unique by symbol")
        object.__setattr__(self, "holdings", tuple(self.holdings))
        object.__setattr__(self, "evidence_refs", _normalize_refs(self.evidence_refs))
        if self.reconciliation_status == RECONCILIATION_RECONCILED:
            object.__setattr__(
                self,
                "reconciled_at",
                _required_datetime(self.reconciled_at, "reconciled_at"),
            )
            if self.cash_cny is None:
                raise ValueError("Reconciled snapshot requires cash")
            if not self.evidence_refs:
                raise ValueError("Reconciled snapshot requires reconciliation evidence")
            if any(
                holding.quantity_source != QUANTITY_HUMAN_CONFIRMED
                for holding in self.holdings
            ):
                raise ValueError("Reconciled snapshot requires confirmed holdings")
        else:
            if self.reconciled_at is not None:
                raise ValueError("Unreconciled snapshot cannot carry reconciled_at")
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Portfolio snapshot must remain no_order")

    @classmethod
    def missing(cls, *, snapshot_id: str = "snapshot-missing", as_of: date | None = None) -> PortfolioSnapshot:
        now = datetime.now().astimezone()
        return cls(
            snapshot_id=snapshot_id,
            snapshot_version="v0-missing",
            as_of=as_of or date.min,
            available_at=now,
            account_scope="missing",
            namespace=NAMESPACE_ACTUAL,
            cash_cny=None,
            holdings=(),
            reconciliation_status=RECONCILIATION_UNCONFIRMED,
            reconciled_at=None,
            evidence_refs=(),
        )

    @property
    def is_reconciled(self) -> bool:
        return self.reconciliation_status == RECONCILIATION_RECONCILED

    @property
    def sensitivity(self) -> str:
        return "PRIVATE_USER_CONFIRMED"

    def missing_guidance_inputs(self) -> tuple[str, ...]:
        missing = []
        if self.account_scope == "missing":
            missing.append("account_scope")
        if not self.is_reconciled:
            missing.append("reconciliation")
        if self.namespace != NAMESPACE_ACTUAL:
            missing.append("actual_namespace")
        if self.cash_cny is None:
            missing.append("cash_cny")
        if any(
            holding.quantity_source != QUANTITY_HUMAN_CONFIRMED
            for holding in self.holdings
        ):
            missing.append("holding_quantity_confirmation")
        if any(
            holding.market_value_cny is None
            for holding in self.holdings
        ):
            missing.append("holding_market_value")
        return tuple(missing)

    def can_support_real_guidance(self) -> bool:
        return not self.missing_guidance_inputs()

    def as_policy(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "snapshot_id": self.snapshot_id,
            "snapshot_version": self.snapshot_version,
            "as_of": self.as_of.isoformat(),
            "available_at": self.available_at.isoformat(),
            "account_scope": self.account_scope,
            "namespace": self.namespace,
            "cash_cny": str(self.cash_cny) if self.cash_cny is not None else None,
            "holdings": [holding.as_policy() for holding in self.holdings],
            "reconciliation_status": self.reconciliation_status,
            "reconciled_at": self.reconciled_at.isoformat() if self.reconciled_at else None,
            "evidence_refs": [dict(ref) for ref in self.evidence_refs],
            "sensitivity": self.sensitivity,
            "action": self.action,
        }

    def to_json(self) -> str:
        return json.dumps(self.as_policy(), ensure_ascii=False, allow_nan=False, indent=2)


@dataclass(frozen=True)
class PortfolioInputBundle:
    policy: InvestorPolicyStatement
    snapshot: PortfolioSnapshot
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        if self.policy.account_scope != self.snapshot.account_scope:
            raise ValueError("Portfolio policy and snapshot account scopes must match")
        if self.policy.as_of > self.snapshot.as_of:
            raise ValueError("Portfolio policy cannot be dated after the holdings snapshot")
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Portfolio input bundle must remain no_order")

    @classmethod
    def missing(
        cls,
        *,
        as_of: date | None = None,
    ) -> PortfolioInputBundle:
        return cls(
            policy=InvestorPolicyStatement.missing(as_of=as_of),
            snapshot=PortfolioSnapshot.missing(as_of=as_of),
        )

    @property
    def sensitivity(self) -> str:
        return "PRIVATE_USER_CONFIRMED"

    def missing_guidance_inputs(self) -> tuple[str, ...]:
        return (
            *(f"policy.{item}" for item in self.policy.missing_guidance_inputs()),
            *(f"snapshot.{item}" for item in self.snapshot.missing_guidance_inputs()),
        )

    def can_support_guidance(self) -> bool:
        return not self.missing_guidance_inputs()

    def as_policy(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "policy": self.policy.as_policy(),
            "snapshot": self.snapshot.as_policy(),
            "sensitivity": self.sensitivity,
            "action": self.action,
        }

    def to_json(self) -> str:
        return json.dumps(self.as_policy(), ensure_ascii=False, allow_nan=False, indent=2)


def investor_policy_statement_from_payload(payload: Mapping[str, Any]) -> InvestorPolicyStatement:
    data = dict(payload)
    _reject_public_execution_keys(data)
    return InvestorPolicyStatement(
        policy_id=str(data["policy_id"]),
        policy_version=str(data["policy_version"]),
        as_of=date.fromisoformat(str(data["as_of"])),
        confirmation_status=str(data["confirmation_status"]),
        confirmed_at=datetime.fromisoformat(str(data["confirmed_at"])) if data.get("confirmed_at") else None,
        account_scope=str(data["account_scope"]),
        investable_assets_cny=_decimal(data.get("investable_assets_cny"), "investable_assets_cny"),
        minimum_cash_cny=_decimal(data.get("minimum_cash_cny"), "minimum_cash_cny"),
        emergency_cash_cny=_decimal(data.get("emergency_cash_cny"), "emergency_cash_cny"),
        liquidity_needs_cny=_decimal(data.get("liquidity_needs_cny"), "liquidity_needs_cny"),
        time_horizon_years=_decimal(data.get("time_horizon_years"), "time_horizon_years"),
        max_single_security_pct=_decimal(data.get("max_single_security_pct"), "max_single_security_pct"),
        max_single_industry_pct=_decimal(data.get("max_single_industry_pct"), "max_single_industry_pct"),
        max_cyclical_exposure_pct=_decimal(data.get("max_cyclical_exposure_pct"), "max_cyclical_exposure_pct"),
        dividend_income_goal_cny=_decimal(data.get("dividend_income_goal_cny"), "dividend_income_goal_cny"),
        risk_tolerance=str(data.get("risk_tolerance", RISK_UNKNOWN)),
        concentration_allowed=_optional_bool(data.get("concentration_allowed"), "concentration_allowed"),
        tax_regime=_optional_text(data.get("tax_regime"), "tax_regime"),
        restrictions=tuple(str(item) for item in data.get("restrictions") or ()),
        evidence_refs=tuple(dict(item) for item in data.get("evidence_refs") or ()),
        action=str(data.get("action", ACTION_NO_ORDER)),
    )


def portfolio_holding_from_payload(payload: Mapping[str, Any]) -> PortfolioHolding:
    data = dict(payload)
    return PortfolioHolding(
        symbol=str(data["symbol"]),
        exchange=str(data["exchange"]),
        quantity=_decimal(data["quantity"], "quantity"),
        cost_basis_cny=_decimal(data.get("cost_basis_cny"), "cost_basis_cny"),
        market_value_cny=_decimal(data.get("market_value_cny"), "market_value_cny"),
        quantity_source=str(data["quantity_source"]),
        corporate_action_adjusted=_required_bool(
            data["corporate_action_adjusted"],
            "corporate_action_adjusted",
        ),
        evidence_refs=tuple(dict(item) for item in data.get("evidence_refs") or ()),
    )


def portfolio_snapshot_from_payload(payload: Mapping[str, Any]) -> PortfolioSnapshot:
    data = dict(payload)
    _reject_public_execution_keys(data)
    return PortfolioSnapshot(
        snapshot_id=str(data["snapshot_id"]),
        snapshot_version=str(data["snapshot_version"]),
        as_of=date.fromisoformat(str(data["as_of"])),
        available_at=datetime.fromisoformat(str(data["available_at"])),
        account_scope=str(data["account_scope"]),
        namespace=str(data["namespace"]),
        cash_cny=_decimal(data.get("cash_cny"), "cash_cny"),
        holdings=tuple(
            portfolio_holding_from_payload(item)
            for item in data.get("holdings") or ()
        ),
        reconciliation_status=str(data["reconciliation_status"]),
        reconciled_at=datetime.fromisoformat(str(data["reconciled_at"])) if data.get("reconciled_at") else None,
        evidence_refs=tuple(dict(item) for item in data.get("evidence_refs") or ()),
        action=str(data.get("action", ACTION_NO_ORDER)),
    )


def portfolio_input_bundle_from_payload(payload: Mapping[str, Any]) -> PortfolioInputBundle:
    data = dict(payload)
    _reject_public_execution_keys(data)
    return PortfolioInputBundle(
        policy=investor_policy_statement_from_payload(data["policy"]),
        snapshot=portfolio_snapshot_from_payload(data["snapshot"]),
        action=str(data.get("action", ACTION_NO_ORDER)),
    )
