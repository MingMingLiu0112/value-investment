"""Private, no-order comparison of two actual portfolio snapshots for M4.

This module exposes differences that a human must resolve before marking a
portfolio snapshot reconciled.  It never changes a snapshot's reconciliation
status, selects a position, or serializes personal holdings for public use.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from .investment_decision import ACTION_NO_ORDER
from .portfolio_contracts import NAMESPACE_ACTUAL, PortfolioHolding, PortfolioSnapshot


SCHEMA_VERSION = "m4-portfolio-reconciliation-v1"
STATUS_MATCH_PENDING_HUMAN_CONFIRMATION = "MATCH_PENDING_HUMAN_CONFIRMATION"
STATUS_MISMATCH = "MISMATCH"
STATUS_INCOMPLETE = "INCOMPLETE"
RECONCILIATION_STATUSES = frozenset(
    {
        STATUS_MATCH_PENDING_HUMAN_CONFIRMATION,
        STATUS_MISMATCH,
        STATUS_INCOMPLETE,
    }
)

KIND_CASH = "cash"
KIND_HOLDING_MISSING = "holding_missing"
KIND_EXCHANGE = "exchange"
KIND_QUANTITY = "quantity"
KIND_COST_BASIS = "cost_basis"
KIND_MARKET_VALUE = "market_value"
KIND_CORPORATE_ACTION = "corporate_action_adjustment"
DIFFERENCE_KINDS = frozenset(
    {
        KIND_CASH,
        KIND_HOLDING_MISSING,
        KIND_EXCHANGE,
        KIND_QUANTITY,
        KIND_COST_BASIS,
        KIND_MARKET_VALUE,
        KIND_CORPORATE_ACTION,
    }
)


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


@dataclass(frozen=True)
class PortfolioReconciliationDifference:
    """One private, human-reviewable discrepancy; values stay in private memory."""

    kind: str
    subject: str
    reported_value: str | None
    confirmed_value: str | None
    reason: str

    def __post_init__(self) -> None:
        if self.kind not in DIFFERENCE_KINDS:
            raise ValueError("Unknown portfolio reconciliation difference kind")
        object.__setattr__(self, "subject", _required_text(self.subject, "subject"))
        object.__setattr__(self, "reason", _required_text(self.reason, "reason"))

    def as_private_policy(self) -> dict[str, str | None]:
        return {
            "kind": self.kind,
            "subject": self.subject,
            "reported_value": self.reported_value,
            "confirmed_value": self.confirmed_value,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class PortfolioReconciliationReport:
    """A private comparison result that deliberately cannot certify reconciliation."""

    report_id: str
    generated_at: datetime
    reported_snapshot_id: str
    confirmed_snapshot_id: str
    account_scope: str
    as_of: str
    status: str
    differences: tuple[PortfolioReconciliationDifference, ...]
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        object.__setattr__(self, "report_id", _required_text(self.report_id, "report_id"))
        if not isinstance(self.generated_at, datetime) or self.generated_at.tzinfo is None:
            raise ValueError("generated_at must be timezone-aware")
        object.__setattr__(
            self,
            "reported_snapshot_id",
            _required_text(self.reported_snapshot_id, "reported_snapshot_id"),
        )
        object.__setattr__(
            self,
            "confirmed_snapshot_id",
            _required_text(self.confirmed_snapshot_id, "confirmed_snapshot_id"),
        )
        object.__setattr__(self, "account_scope", _required_text(self.account_scope, "account_scope"))
        object.__setattr__(self, "as_of", _required_text(self.as_of, "as_of"))
        if self.status not in RECONCILIATION_STATUSES:
            raise ValueError("Unknown portfolio reconciliation status")
        object.__setattr__(self, "differences", tuple(self.differences))
        if any(not isinstance(item, PortfolioReconciliationDifference) for item in self.differences):
            raise ValueError("differences must contain PortfolioReconciliationDifference")
        if self.status == STATUS_MISMATCH and not self.differences:
            raise ValueError("Mismatch reconciliation requires differences")
        if self.status == STATUS_MATCH_PENDING_HUMAN_CONFIRMATION and self.differences:
            raise ValueError("Matching reconciliation cannot carry differences")
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Portfolio reconciliation must remain no_order")

    @property
    def requires_human_confirmation(self) -> bool:
        return True

    def as_private_policy(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "report_id": self.report_id,
            "generated_at": self.generated_at.isoformat(),
            "reported_snapshot_id": self.reported_snapshot_id,
            "confirmed_snapshot_id": self.confirmed_snapshot_id,
            "account_scope": self.account_scope,
            "as_of": self.as_of,
            "status": self.status,
            "differences": [item.as_private_policy() for item in self.differences],
            "requires_human_confirmation": self.requires_human_confirmation,
            "sensitivity": "PRIVATE_USER_CONFIRMED",
            "action": self.action,
        }


def _holding_map(snapshot: PortfolioSnapshot) -> dict[str, PortfolioHolding]:
    return {holding.symbol: holding for holding in snapshot.holdings}


def _comparison_value(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def _holding_differences(
    symbol: str,
    reported: PortfolioHolding | None,
    confirmed: PortfolioHolding | None,
) -> list[PortfolioReconciliationDifference]:
    if reported is None or confirmed is None:
        return [
            PortfolioReconciliationDifference(
                kind=KIND_HOLDING_MISSING,
                subject=symbol,
                reported_value="present" if reported else "missing",
                confirmed_value="present" if confirmed else "missing",
                reason="holding membership differs between the two actual snapshots",
            )
        ]
    differences = []
    for kind, reported_value, confirmed_value, reason in (
        (KIND_EXCHANGE, reported.exchange, confirmed.exchange, "exchange differs"),
        (KIND_QUANTITY, reported.quantity, confirmed.quantity, "confirmed quantity differs"),
        (KIND_COST_BASIS, reported.cost_basis_cny, confirmed.cost_basis_cny, "cost basis differs"),
        (KIND_MARKET_VALUE, reported.market_value_cny, confirmed.market_value_cny, "market value differs"),
        (
            KIND_CORPORATE_ACTION,
            reported.corporate_action_adjusted,
            confirmed.corporate_action_adjusted,
            "corporate-action adjustment state differs",
        ),
    ):
        if reported_value != confirmed_value:
            differences.append(
                PortfolioReconciliationDifference(
                    kind=kind,
                    subject=symbol,
                    reported_value=_comparison_value(reported_value),
                    confirmed_value=_comparison_value(confirmed_value),
                    reason=reason,
                )
            )
    return differences


def reconcile_portfolio_snapshots(
    reported_snapshot: PortfolioSnapshot,
    confirmed_snapshot: PortfolioSnapshot,
    *,
    report_id: str,
    generated_at: datetime,
) -> PortfolioReconciliationReport:
    """Compare equal-date actual snapshots without declaring either reconciled."""
    if not isinstance(reported_snapshot, PortfolioSnapshot) or not isinstance(confirmed_snapshot, PortfolioSnapshot):
        raise ValueError("reported_snapshot and confirmed_snapshot must be PortfolioSnapshot")
    if reported_snapshot.namespace != NAMESPACE_ACTUAL or confirmed_snapshot.namespace != NAMESPACE_ACTUAL:
        raise ValueError("Portfolio reconciliation requires ACTUAL snapshots")
    if reported_snapshot.account_scope != confirmed_snapshot.account_scope:
        raise ValueError("Portfolio reconciliation account scopes must match")
    if reported_snapshot.as_of != confirmed_snapshot.as_of:
        raise ValueError("Portfolio reconciliation snapshot dates must match")
    if not isinstance(generated_at, datetime) or generated_at.tzinfo is None:
        raise ValueError("generated_at must be timezone-aware")

    differences: list[PortfolioReconciliationDifference] = []
    if reported_snapshot.cash_cny is None or confirmed_snapshot.cash_cny is None:
        status = STATUS_INCOMPLETE
    else:
        if reported_snapshot.cash_cny != confirmed_snapshot.cash_cny:
            differences.append(
                PortfolioReconciliationDifference(
                    kind=KIND_CASH,
                    subject="cash_cny",
                    reported_value=_comparison_value(reported_snapshot.cash_cny),
                    confirmed_value=_comparison_value(confirmed_snapshot.cash_cny),
                    reason="cash balance differs",
                )
            )
        reported_holdings = _holding_map(reported_snapshot)
        confirmed_holdings = _holding_map(confirmed_snapshot)
        for symbol in sorted(set(reported_holdings) | set(confirmed_holdings)):
            differences.extend(
                _holding_differences(
                    symbol,
                    reported_holdings.get(symbol),
                    confirmed_holdings.get(symbol),
                )
            )
        missing_market_value = any(
            holding.market_value_cny is None
            for holding in (*reported_snapshot.holdings, *confirmed_snapshot.holdings)
        )
        status = (
            STATUS_INCOMPLETE
            if missing_market_value
            else STATUS_MISMATCH
            if differences
            else STATUS_MATCH_PENDING_HUMAN_CONFIRMATION
        )

    return PortfolioReconciliationReport(
        report_id=report_id,
        generated_at=generated_at,
        reported_snapshot_id=reported_snapshot.snapshot_id,
        confirmed_snapshot_id=confirmed_snapshot.snapshot_id,
        account_scope=reported_snapshot.account_scope,
        as_of=reported_snapshot.as_of.isoformat(),
        status=status,
        differences=tuple(differences),
    )
