"""Point-in-time portfolio dividend income projection for M4.

Income is kept in four non-equivalent bases: paid, declared, forward estimate
and normalized scenario. Ordinary and special distributions are never merged,
special dividends are never annualized, and unknown tax treatment remains
unknown rather than becoming a fabricated net number. No position, allocation
or order is produced.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import json
import re
from typing import Any, Mapping, Sequence

from .distribution import (
    DIVIDEND_APPROVED,
    DIVIDEND_ORDINARY,
    DIVIDEND_SPECIAL,
    DIVIDEND_TYPES,
)
from .dividend_tax import (
    RULE_VERSION,
    DividendTaxCalculation,
    calculate_dividend_tax,
)
from .investment_decision import ACTION_NO_ORDER
from .portfolio_contracts import (
    NAMESPACE_ACTUAL,
    NAMESPACE_SIMULATED,
    QUANTITY_HUMAN_CONFIRMED,
    PortfolioInputBundle,
)


SCHEMA_VERSION = "m4-dividend-income-projection-v1"

BASIS_PAID = "paid"
BASIS_DECLARED = "declared"
BASIS_FORWARD = "forward_estimate"
BASIS_NORMALIZED = "normalized_scenario"
BASIS_TYPES = frozenset(
    {BASIS_PAID, BASIS_DECLARED, BASIS_FORWARD, BASIS_NORMALIZED}
)
REQUIRED_BASES = frozenset(
    {BASIS_PAID, BASIS_DECLARED, BASIS_FORWARD, BASIS_NORMALIZED}
)

TAX_CALCULATED = "CALCULATED"
TAX_UNKNOWN = "UNKNOWN"
TAX_PENDING_DISPOSAL = "UNKNOWN_PENDING_DISPOSAL"
TAX_REVIEW_REQUIRED = "REVIEW_REQUIRED"
TAX_STATUSES = frozenset(
    {
        TAX_CALCULATED,
        TAX_UNKNOWN,
        TAX_PENDING_DISPOSAL,
        TAX_REVIEW_REQUIRED,
    }
)

STATUS_READY = "READY"
STATUS_PARTIAL = "PARTIAL"
STATUS_INCOMPLETE = "INCOMPLETE"
STATUSES = frozenset({STATUS_READY, STATUS_PARTIAL, STATUS_INCOMPLETE})

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


def _positive_decimal(value: object, field: str) -> Decimal:
    parsed = _decimal(value, field)
    if parsed <= 0:
        raise ValueError(f"{field} must be positive")
    return parsed


def _date(value: object, field: str) -> date:
    if not isinstance(value, date) or isinstance(value, datetime):
        raise ValueError(f"{field} must be a date")
    return value


def _optional_date(value: object, field: str) -> date | None:
    return None if value is None else _date(value, field)


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
        raise ValueError(f"Dividend payload contains execution keys: {', '.join(forbidden)}")


@dataclass(frozen=True)
class DividendTaxTreatment:
    """A tax result or an explicit unknown/awaiting-disposal state."""

    status: str
    rule_version: str | None = None
    effective_rate: Decimal | None = None
    taxable_income: Decimal | None = None
    initial_withholding: Decimal | None = None
    total_tax: Decimal | None = None
    additional_tax: Decimal | None = None
    note: str = ""

    def __post_init__(self) -> None:
        if self.status not in TAX_STATUSES:
            raise ValueError("Unknown dividend tax treatment status")
        object.__setattr__(
            self,
            "rule_version",
            _optional_text(self.rule_version, "rule_version"),
        )
        object.__setattr__(
            self,
            "effective_rate",
            _optional_decimal(self.effective_rate, "effective_rate"),
        )
        object.__setattr__(
            self,
            "taxable_income",
            _optional_decimal(self.taxable_income, "taxable_income"),
        )
        object.__setattr__(
            self,
            "initial_withholding",
            _optional_decimal(self.initial_withholding, "initial_withholding"),
        )
        object.__setattr__(
            self,
            "total_tax",
            _optional_decimal(self.total_tax, "total_tax"),
        )
        object.__setattr__(
            self,
            "additional_tax",
            _optional_decimal(self.additional_tax, "additional_tax"),
        )
        object.__setattr__(self, "note", _required_text(self.note, "note"))
        if self.status == TAX_CALCULATED:
            required = (
                self.rule_version,
                self.effective_rate,
                self.taxable_income,
                self.initial_withholding,
                self.total_tax,
                self.additional_tax,
            )
            if any(item is None for item in required):
                raise ValueError("Calculated tax treatment requires all tax fields")

    @classmethod
    def unknown(cls, *, note: str, pending_disposal: bool = False) -> DividendTaxTreatment:
        return cls(
            status=TAX_PENDING_DISPOSAL if pending_disposal else TAX_UNKNOWN,
            note=note,
        )

    @classmethod
    def from_calculation(
        cls,
        calculation: DividendTaxCalculation,
        *,
        note: str = "已按已处置批次计算税费",
    ) -> DividendTaxTreatment:
        return cls(
            status=TAX_CALCULATED,
            rule_version=calculation.rule_version,
            effective_rate=calculation.effective_rate,
            taxable_income=calculation.taxable_income,
            initial_withholding=calculation.initial_withholding,
            total_tax=calculation.total_tax,
            additional_tax=calculation.additional_tax,
            note=note,
        )

    def as_policy(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "rule_version": self.rule_version,
            "effective_rate": str(self.effective_rate) if self.effective_rate is not None else None,
            "taxable_income": str(self.taxable_income) if self.taxable_income is not None else None,
            "initial_withholding": str(self.initial_withholding) if self.initial_withholding is not None else None,
            "total_tax": str(self.total_tax) if self.total_tax is not None else None,
            "additional_tax": str(self.additional_tax) if self.additional_tax is not None else None,
            "note": self.note,
        }


@dataclass(frozen=True)
class DividendIncomeObservation:
    """One entitlement/estimate/scenario for one security."""

    observation_id: str
    symbol: str
    basis: str
    dividend_type: str
    gross_per_share: Decimal
    quantity: Decimal
    as_of: date
    record_date: date | None = None
    payable_date: date | None = None
    approval_status: str | None = None
    confidence: str | None = None
    scenario_id: str | None = None
    period_start: date | None = None
    period_end: date | None = None
    account_type: str | None = None
    acquired: date | None = None
    disposal_settlement: date | None = None
    tax_regime: str | None = None
    evidence_refs: tuple[dict[str, Any], ...] = ()
    action: str = ACTION_NO_ORDER
    tax_treatment: DividendTaxTreatment | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "observation_id",
            _required_text(self.observation_id, "observation_id"),
        )
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("Dividend observation symbol must contain six digits")
        if self.basis not in BASIS_TYPES:
            raise ValueError("Unknown dividend income basis")
        if self.dividend_type not in DIVIDEND_TYPES:
            raise ValueError("Unknown dividend type")
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Dividend observation must remain no_order")
        if self.dividend_type == DIVIDEND_SPECIAL and self.basis in {
            BASIS_FORWARD,
            BASIS_NORMALIZED,
        }:
            raise ValueError("Special dividends cannot be forward-estimated or normalized")
        object.__setattr__(
            self,
            "gross_per_share",
            _positive_decimal(self.gross_per_share, "gross_per_share"),
        )
        object.__setattr__(self, "quantity", _positive_decimal(self.quantity, "quantity"))
        object.__setattr__(self, "as_of", _date(self.as_of, "as_of"))
        object.__setattr__(
            self,
            "record_date",
            _optional_date(self.record_date, "record_date"),
        )
        object.__setattr__(
            self,
            "payable_date",
            _optional_date(self.payable_date, "payable_date"),
        )
        object.__setattr__(
            self,
            "approval_status",
            _optional_text(self.approval_status, "approval_status"),
        )
        object.__setattr__(
            self,
            "confidence",
            _optional_text(self.confidence, "confidence"),
        )
        object.__setattr__(
            self,
            "scenario_id",
            _optional_text(self.scenario_id, "scenario_id"),
        )
        object.__setattr__(
            self,
            "period_start",
            _optional_date(self.period_start, "period_start"),
        )
        object.__setattr__(
            self,
            "period_end",
            _optional_date(self.period_end, "period_end"),
        )
        object.__setattr__(
            self,
            "account_type",
            _optional_text(self.account_type, "account_type"),
        )
        object.__setattr__(self, "acquired", _optional_date(self.acquired, "acquired"))
        object.__setattr__(
            self,
            "disposal_settlement",
            _optional_date(self.disposal_settlement, "disposal_settlement"),
        )
        object.__setattr__(
            self,
            "tax_regime",
            _optional_text(self.tax_regime, "tax_regime"),
        )
        object.__setattr__(self, "evidence_refs", _normalize_refs(self.evidence_refs))
        if not self.evidence_refs:
            raise ValueError("Dividend observation requires evidence")
        if self.basis in {BASIS_PAID, BASIS_DECLARED}:
            if self.record_date is None or self.payable_date is None:
                raise ValueError(f"{self.basis} dividend requires record and payable dates")
            if self.payable_date < self.record_date:
                raise ValueError("Payable date cannot precede record date")
        if self.basis == BASIS_PAID and self.payable_date > self.as_of:
            raise ValueError("Paid dividend cannot have a future payable date")
        if self.basis == BASIS_DECLARED and self.approval_status != DIVIDEND_APPROVED:
            raise ValueError("Declared income requires an approved dividend")
        if self.basis in {BASIS_FORWARD, BASIS_NORMALIZED}:
            if self.period_start is None or self.period_end is None:
                raise ValueError(f"{self.basis} requires an explicit projection period")
            if self.period_end < self.period_start:
                raise ValueError("Projection period end cannot precede its start")
            if self.basis == BASIS_FORWARD and not self.confidence:
                raise ValueError("Forward estimate requires explicit confidence")
            if self.basis == BASIS_NORMALIZED and not self.scenario_id:
                raise ValueError("Normalized scenario requires a scenario id")

        tax_fields = (self.account_type, self.acquired, self.disposal_settlement)
        if self.basis != BASIS_PAID:
            if self.account_type is not None or self.acquired is not None or self.disposal_settlement is not None:
                raise ValueError("Non-paid dividends cannot carry a calculated tax lot")
            if self.tax_treatment is not None:
                raise ValueError("Non-paid tax treatment must be unknown pending disposal")
            treatment = DividendTaxTreatment.unknown(
                note="尚未到处置结算日，无法确定最终个人所得税",
                pending_disposal=True,
            )
        elif any(item is not None for item in tax_fields):
            if any(item is None for item in tax_fields) or self.record_date is None:
                raise ValueError("Paid tax lot requires account, acquisition, record and disposal dates")
            if self.tax_treatment is not None:
                raise ValueError("Paid tax lot cannot carry a separate tax treatment")
            calculation = calculate_dividend_tax(
                acquired=self.acquired,
                record_date=self.record_date,
                disposal_settlement=self.disposal_settlement,
                taxable_income=self.gross_income_cny(),
                account_type=self.account_type,
            )
            treatment = DividendTaxTreatment.from_calculation(calculation)
        else:
            if self.tax_treatment is None:
                treatment = DividendTaxTreatment.unknown(
                    note="未提供已处置批次的取得与结算日期",
                )
            else:
                treatment = self.tax_treatment
        object.__setattr__(self, "tax_treatment", treatment)

    def gross_income_cny(self) -> Decimal:
        return self.gross_per_share * self.quantity

    def net_income_cny(self) -> Decimal | None:
        treatment = self.tax_treatment
        if treatment is None or treatment.status != TAX_CALCULATED:
            return None
        if treatment.total_tax is None:
            return None
        return self.gross_income_cny() - treatment.total_tax

    def as_policy(self) -> dict[str, Any]:
        payload = {
            "observation_id": self.observation_id,
            "symbol": self.symbol,
            "basis": self.basis,
            "dividend_type": self.dividend_type,
            "gross_per_share": str(self.gross_per_share),
            "quantity": str(self.quantity),
            "gross_income_cny": str(self.gross_income_cny()),
            "net_income_cny": str(self.net_income_cny())
            if self.net_income_cny() is not None
            else None,
            "as_of": self.as_of.isoformat(),
            "record_date": self.record_date.isoformat() if self.record_date else None,
            "payable_date": self.payable_date.isoformat() if self.payable_date else None,
            "approval_status": self.approval_status,
            "confidence": self.confidence,
            "scenario_id": self.scenario_id,
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
            "tax_regime": self.tax_regime,
            "tax_treatment": self.tax_treatment.as_policy() if self.tax_treatment else None,
            "evidence_refs": [dict(ref) for ref in self.evidence_refs],
            "action": self.action,
        }
        _reject_public_execution_keys(payload)
        return payload


@dataclass(frozen=True)
class SecurityDividendIncomeProjection:
    """Four-basis income picture for one confirmed portfolio security."""

    projection_id: str
    symbol: str
    quantity: Decimal
    observations: tuple[DividendIncomeObservation, ...]
    as_of: date
    generated_at: datetime
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "projection_id",
            _required_text(self.projection_id, "projection_id"),
        )
        if not _SYMBOL.fullmatch(self.symbol):
            raise ValueError("Dividend projection symbol must contain six digits")
        object.__setattr__(
            self,
            "quantity",
            _positive_decimal(self.quantity, "quantity"),
        )
        object.__setattr__(self, "as_of", _date(self.as_of, "as_of"))
        object.__setattr__(
            self,
            "generated_at",
            _datetime(self.generated_at, "generated_at"),
        )
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Dividend projection must remain no_order")
        object.__setattr__(self, "observations", tuple(self.observations))
        if not self.observations:
            raise ValueError("Security dividend projection requires observations")
        if any(item.symbol != self.symbol for item in self.observations):
            raise ValueError("Dividend observations must share one symbol")
        if any(item.quantity != self.quantity for item in self.observations):
            raise ValueError("Dividend observation quantity must match the projection")
        if any(item.as_of > self.as_of for item in self.observations):
            raise ValueError("Projection as_of cannot precede an observation as_of")
        ids = [item.observation_id for item in self.observations]
        if len(ids) != len(set(ids)):
            raise ValueError("Dividend observation ids must be unique")

    def observations_for(self, basis: str) -> tuple[DividendIncomeObservation, ...]:
        return tuple(item for item in self.observations if item.basis == basis)

    def gross_by_basis(self) -> dict[str, Decimal]:
        return {
            basis: sum(
                (item.gross_income_cny() for item in self.observations_for(basis)),
                Decimal("0"),
            )
            for basis in sorted(BASIS_TYPES)
        }

    def net_by_basis(self) -> dict[str, Decimal | None]:
        result = {}
        for basis in sorted(BASIS_TYPES):
            observations = self.observations_for(basis)
            if not observations:
                result[basis] = None
                continue
            nets = [item.net_income_cny() for item in observations]
            result[basis] = (
                sum((value for value in nets if value is not None), Decimal("0"))
                if all(value is not None for value in nets)
                else None
            )
        return result

    def missing_bases(self) -> tuple[str, ...]:
        return tuple(
            basis
            for basis in sorted(REQUIRED_BASES)
            if not self.observations_for(basis)
        )

    def blockers(self) -> tuple[str, ...]:
        result = [
            f"missing_basis:{basis}"
            for basis in self.missing_bases()
        ]
        result.extend(
            f"{item.observation_id}:tax_{item.tax_treatment.status}"
            for item in self.observations
            if item.tax_treatment is not None
            and item.tax_treatment.status in {TAX_UNKNOWN, TAX_REVIEW_REQUIRED}
        )
        return tuple(result)

    @property
    def status(self) -> str:
        if self.missing_bases():
            return STATUS_PARTIAL
        return STATUS_READY

    @property
    def ordinary_special_separated(self) -> bool:
        bases = {
            item.basis
            for item in self.observations
            if item.dividend_type == DIVIDEND_SPECIAL
        }
        return not bases.intersection({BASIS_FORWARD, BASIS_NORMALIZED})

    def as_policy(self) -> dict[str, Any]:
        payload = {
            "projection_id": self.projection_id,
            "symbol": self.symbol,
            "quantity": str(self.quantity),
            "status": self.status,
            "missing_bases": list(self.missing_bases()),
            "blockers": list(self.blockers()),
            "gross_by_basis": {
                basis: str(value)
                for basis, value in self.gross_by_basis().items()
            },
            "net_by_basis": {
                basis: str(value) if value is not None else None
                for basis, value in self.net_by_basis().items()
            },
            "ordinary_special_separated": self.ordinary_special_separated,
            "observations": [item.as_policy() for item in self.observations],
            "as_of": self.as_of.isoformat(),
            "generated_at": self.generated_at.isoformat(),
            "action": self.action,
        }
        _reject_public_execution_keys(payload)
        return payload


@dataclass(frozen=True)
class DividendIncomeSummary:
    basis: str
    gross_income: Decimal
    net_income: Decimal | None
    tax_status: str
    goal_gap: Decimal | None

    def as_policy(self) -> dict[str, Any]:
        return {
            "basis": self.basis,
            "gross_income": str(self.gross_income),
            "net_income": str(self.net_income) if self.net_income is not None else None,
            "tax_status": self.tax_status,
            "goal_gap": str(self.goal_gap) if self.goal_gap is not None else None,
        }


@dataclass(frozen=True)
class PortfolioDividendIncomeProjection:
    """Portfolio-wide four-basis income projection and goal gap."""

    assessment_id: str
    as_of: date
    generated_at: datetime
    bundle: PortfolioInputBundle
    security_projections: Mapping[str, SecurityDividendIncomeProjection]
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
            raise ValueError("Portfolio dividend projection must remain no_order")
        if self.assessment_namespace not in {NAMESPACE_ACTUAL, NAMESPACE_SIMULATED}:
            raise ValueError("Unknown dividend projection namespace")
        if self.assessment_namespace != self.bundle.snapshot.namespace:
            raise ValueError("Dividend projection namespace must match its snapshot")
        if set(self.security_projections) != {
            holding.symbol for holding in self.bundle.snapshot.holdings
        }:
            raise ValueError("Dividend projections must exactly match snapshot holdings")
        for holding in self.bundle.snapshot.holdings:
            projection = self.security_projections[holding.symbol]
            if projection.symbol != holding.symbol:
                raise ValueError("Dividend projection symbol mismatch")
            if projection.quantity != holding.quantity:
                raise ValueError("Dividend projection quantity must match snapshot")
            if projection.as_of > self.as_of:
                raise ValueError("Portfolio dividend as_of cannot precede security projection")

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
        return tuple(dict.fromkeys(missing))

    def can_project(self) -> bool:
        return not self.missing_inputs()

    def gross_by_basis(self) -> dict[str, Decimal]:
        result = {basis: Decimal("0") for basis in sorted(BASIS_TYPES)}
        for projection in self.security_projections.values():
            for basis, value in projection.gross_by_basis().items():
                result[basis] += value
        return result

    def net_by_basis(self) -> dict[str, Decimal | None]:
        result = {}
        for basis in sorted(BASIS_TYPES):
            values = [
                projection.net_by_basis()[basis]
                for projection in self.security_projections.values()
            ]
            if not values:
                result[basis] = None
            elif any(value is None for value in values):
                result[basis] = None
            else:
                result[basis] = sum(
                    (value for value in values if value is not None),
                    Decimal("0"),
                )
        return result

    def tax_status_by_basis(self) -> dict[str, str]:
        result = {}
        for basis in sorted(BASIS_TYPES):
            statuses = {
                item.tax_treatment.status
                for projection in self.security_projections.values()
                for item in projection.observations_for(basis)
                if item.tax_treatment is not None
            }
            if not statuses:
                result[basis] = TAX_UNKNOWN
            elif statuses == {TAX_CALCULATED}:
                result[basis] = TAX_CALCULATED
            elif statuses & {TAX_REVIEW_REQUIRED}:
                result[basis] = TAX_REVIEW_REQUIRED
            else:
                result[basis] = TAX_PENDING_DISPOSAL
        return result

    def summaries(self) -> tuple[DividendIncomeSummary, ...]:
        if not self.can_project():
            return ()
        gross = self.gross_by_basis()
        net = self.net_by_basis()
        tax = self.tax_status_by_basis()
        goal = self.bundle.policy.dividend_income_goal_cny
        return tuple(
            DividendIncomeSummary(
                basis=basis,
                gross_income=gross[basis],
                net_income=net[basis],
                tax_status=tax[basis],
                goal_gap=(
                    (goal - gross[basis])
                    if goal is not None
                    else None
                ),
            )
            for basis in sorted(BASIS_TYPES)
        )

    def blockers(self) -> tuple[str, ...]:
        if not self.can_project():
            return self.missing_inputs()
        result = [
            f"{projection.symbol}:{blocker}"
            for projection in self.security_projections.values()
            for blocker in projection.blockers()
        ]
        return tuple(dict.fromkeys(result))

    @property
    def status(self) -> str:
        if not self.can_project():
            return STATUS_INCOMPLETE
        if any(
            projection.status == STATUS_PARTIAL
            for projection in self.security_projections.values()
        ):
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
            "blockers": list(self.blockers()),
            "gross_by_basis": {
                basis: str(value)
                for basis, value in self.gross_by_basis().items()
            },
            "net_by_basis": {
                basis: str(value) if value is not None else None
                for basis, value in self.net_by_basis().items()
            },
            "tax_status_by_basis": self.tax_status_by_basis(),
            "summaries": [summary.as_policy() for summary in self.summaries()],
            "security_projections": {
                symbol: projection.as_policy()
                for symbol, projection in sorted(self.security_projections.items())
            },
            "sensitivity": self.sensitivity,
            "action": self.action,
        }
        _reject_public_execution_keys(payload)
        return payload

    def to_json(self) -> str:
        return json.dumps(self.as_policy(), ensure_ascii=False, allow_nan=False, indent=2)


def dividend_tax_treatment_from_payload(
    payload: Mapping[str, Any] | None,
) -> DividendTaxTreatment | None:
    if payload is None:
        return None
    data = dict(payload)
    return DividendTaxTreatment(
        status=str(data["status"]),
        rule_version=str(data["rule_version"]) if data.get("rule_version") else None,
        effective_rate=_optional_decimal(data.get("effective_rate"), "effective_rate"),
        taxable_income=_optional_decimal(data.get("taxable_income"), "taxable_income"),
        initial_withholding=_optional_decimal(data.get("initial_withholding"), "initial_withholding"),
        total_tax=_optional_decimal(data.get("total_tax"), "total_tax"),
        additional_tax=_optional_decimal(data.get("additional_tax"), "additional_tax"),
        note=str(data.get("note", "")),
    )


def dividend_income_observation_from_payload(
    payload: Mapping[str, Any],
) -> DividendIncomeObservation:
    data = dict(payload)
    return DividendIncomeObservation(
        observation_id=str(data["observation_id"]),
        symbol=str(data["symbol"]),
        basis=str(data["basis"]),
        dividend_type=str(data["dividend_type"]),
        gross_per_share=_decimal(data["gross_per_share"], "gross_per_share"),
        quantity=_decimal(data["quantity"], "quantity"),
        as_of=date.fromisoformat(str(data["as_of"])),
        record_date=date.fromisoformat(str(data["record_date"]))
        if data.get("record_date")
        else None,
        payable_date=date.fromisoformat(str(data["payable_date"]))
        if data.get("payable_date")
        else None,
        approval_status=str(data["approval_status"])
        if data.get("approval_status")
        else None,
        confidence=str(data["confidence"]) if data.get("confidence") else None,
        scenario_id=str(data["scenario_id"]) if data.get("scenario_id") else None,
        period_start=date.fromisoformat(str(data["period_start"]))
        if data.get("period_start")
        else None,
        period_end=date.fromisoformat(str(data["period_end"]))
        if data.get("period_end")
        else None,
        account_type=str(data["account_type"]) if data.get("account_type") else None,
        acquired=date.fromisoformat(str(data["acquired"])) if data.get("acquired") else None,
        disposal_settlement=date.fromisoformat(str(data["disposal_settlement"]))
        if data.get("disposal_settlement")
        else None,
        tax_regime=str(data["tax_regime"]) if data.get("tax_regime") else None,
        evidence_refs=tuple(dict(item) for item in data.get("evidence_refs") or ()),
        action=str(data.get("action", ACTION_NO_ORDER)),
        tax_treatment=dividend_tax_treatment_from_payload(data.get("tax_treatment")),
    )


def security_dividend_income_projection_from_payload(
    payload: Mapping[str, Any],
) -> SecurityDividendIncomeProjection:
    data = dict(payload)
    return SecurityDividendIncomeProjection(
        projection_id=str(data["projection_id"]),
        symbol=str(data["symbol"]),
        quantity=_decimal(data["quantity"], "quantity"),
        observations=tuple(
            dividend_income_observation_from_payload(item)
            for item in data["observations"]
        ),
        as_of=date.fromisoformat(str(data["as_of"])),
        generated_at=datetime.fromisoformat(str(data["generated_at"])),
        action=str(data.get("action", ACTION_NO_ORDER)),
    )


def build_portfolio_dividend_income_projection(
    *,
    bundle: PortfolioInputBundle,
    security_projections: Mapping[str, SecurityDividendIncomeProjection],
    as_of: date,
    generated_at: datetime,
    assessment_id: str,
    assessment_namespace: str = NAMESPACE_ACTUAL,
) -> PortfolioDividendIncomeProjection:
    return PortfolioDividendIncomeProjection(
        assessment_id=assessment_id,
        as_of=as_of,
        generated_at=generated_at,
        bundle=bundle,
        security_projections=security_projections,
        assessment_namespace=assessment_namespace,
    )
