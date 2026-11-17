"""Pure private portfolio reconciliation rehearsal; no journal or order authority."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from typing import Mapping

from ...portfolio_contracts import (
    PortfolioHolding, PortfolioSnapshot, QUANTITY_HUMAN_CONFIRMED,
    RECONCILIATION_RECONCILED,
)

SLEEVES = frozenset({"CORE_VALUE", "HOTSPOT_SATELLITE"})


def _amount(value: Decimal, name: str, *, positive: bool = False) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0 or (positive and value == 0):
        raise ValueError(f"{name} requires a finite {'positive' if positive else 'nonnegative'} Decimal")
    return value


def _shares(value: Decimal) -> Decimal:
    _amount(value, "quantity", positive=True)
    if value != value.to_integral_value():
        raise ValueError("quantity requires whole shares")
    return value


@dataclass(frozen=True)
class Lot:
    sleeve: str
    symbol: str
    exchange: str
    quantity: Decimal
    cost_cny: Decimal
    sellable_on: date


@dataclass(frozen=True)
class Fill:
    transaction_id: str
    side: str
    sleeve: str
    symbol: str
    exchange: str
    quantity: Decimal
    price_cny: Decimal
    fees_cny: Decimal
    trade_date: date
    next_sell_session: date | None = None
    trading_unit: Decimal | None = None
    corporate_action: bool = False


@dataclass(frozen=True)
class Reconciliation:
    baseline: PortfolioSnapshot
    version: int
    cash_cny: Decimal
    realized_pnl_cny: Decimal
    lots: tuple[Lot, ...]
    transaction_ids: frozenset[str]
    status: str
    last_trade_date: date
    confirmed_at: datetime | None = None
    confirmation_evidence: dict[str, str] | None = None


def initialize(snapshot: PortfolioSnapshot, allocations: Mapping[tuple[str, str], Decimal]) -> Reconciliation:
    """Start from a user-confirmed snapshot and explicit per-sleeve share counts."""
    if snapshot.reconciliation_status != RECONCILIATION_RECONCILED or snapshot.cash_cny is None:
        raise ValueError("initialization requires a user-confirmed reconciled snapshot")
    if not snapshot.evidence_refs or snapshot.account_scope == "missing":
        raise ValueError("initialization requires account and reconciliation evidence")
    holdings = {holding.symbol: holding for holding in snapshot.holdings}
    if any(sleeve not in SLEEVES or symbol not in holdings for sleeve, symbol in allocations):
        raise ValueError("unknown sleeve or holding allocation")
    lots = []
    for holding in snapshot.holdings:
        if holding.quantity_source != QUANTITY_HUMAN_CONFIRMED or holding.cost_basis_cny is None:
            raise ValueError("initial holdings require confirmed quantity and cost")
        shares = [(sleeve, _amount(quantity, "allocation")) for (sleeve, symbol), quantity in allocations.items()
                  if symbol == holding.symbol and quantity != 0]
        if any(quantity != quantity.to_integral_value() for _, quantity in shares):
            raise ValueError("allocation requires whole shares")
        if sum((quantity for _, quantity in shares), Decimal(0)) != holding.quantity:
            raise ValueError("sleeve allocations must equal confirmed holdings")
        remaining_cost = holding.cost_basis_cny
        for index, (sleeve, quantity) in enumerate(shares):
            if quantity == 0:
                continue
            cost = (holding.cost_basis_cny * quantity / holding.quantity) if index < len(shares) - 1 else remaining_cost
            remaining_cost -= cost
            lots.append(Lot(sleeve, holding.symbol, holding.exchange, quantity, cost, snapshot.as_of))
    return Reconciliation(snapshot, 0, snapshot.cash_cny, Decimal(0), tuple(lots), frozenset(),
                          "CONFIRMED_IN_MEMORY", snapshot.as_of)


def prepare(state: Reconciliation, fill: Fill, *, expected_version: int) -> Reconciliation:
    """Calculate a draft without mutating the confirmed input state."""
    if state.status != "CONFIRMED_IN_MEMORY" or expected_version != state.version:
        raise ValueError("reconciliation version conflict or unconfirmed predecessor")
    if not isinstance(fill.transaction_id, str) or not fill.transaction_id.strip():
        raise ValueError("transaction ID required")
    if fill.transaction_id in state.transaction_ids:
        raise ValueError("duplicate transaction ID")
    if fill.corporate_action:
        raise ValueError("corporate actions require separate reconciliation")
    if fill.side not in {"BUY", "SELL"} or fill.sleeve not in SLEEVES:
        raise ValueError("unsupported side or sleeve")
    if not isinstance(fill.trade_date, date) or fill.trade_date < state.last_trade_date:
        raise ValueError("trade date precedes confirmed state")
    quantity = _shares(fill.quantity)
    price = _amount(fill.price_cny, "price", positive=True)
    fees = _amount(fill.fees_cny, "fees")
    if len(fill.symbol) != 6 or not fill.symbol.isdigit() or fill.exchange not in {"SSE", "SZSE", "BSE"}:
        raise ValueError("invalid security identity")
    gross = quantity * price
    lots = list(state.lots)
    if fill.side == "BUY":
        if fill.trading_unit is None or quantity % _shares(fill.trading_unit) != 0:
            raise ValueError("BUY requires an explicit trading unit dividing quantity")
        if fill.next_sell_session is None or fill.next_sell_session <= fill.trade_date:
            raise ValueError("BUY requires an explicit later sell session")
        if state.cash_cny < gross + fees:
            raise ValueError("insufficient cash")
        if any(lot.symbol == fill.symbol and lot.exchange != fill.exchange for lot in lots):
            raise ValueError("exchange mismatch")
        lots.append(Lot(fill.sleeve, fill.symbol, fill.exchange, quantity, gross + fees,
                        fill.next_sell_session))
        cash = state.cash_cny - gross - fees
        realized = state.realized_pnl_cny
    else:
        if fill.next_sell_session is not None:
            raise ValueError("SELL cannot specify next sell session")
        if gross < fees:
            raise ValueError("fees exceed proceeds")
        available = sum((lot.quantity for lot in lots if lot.sleeve == fill.sleeve
                         and lot.symbol == fill.symbol and lot.exchange == fill.exchange
                         and lot.sellable_on <= fill.trade_date), Decimal(0))
        if available < quantity:
            raise ValueError("insufficient sellable shares")
        remaining = quantity
        sold_cost = Decimal(0)
        updated = []
        for lot in lots:
            if remaining and lot.sleeve == fill.sleeve and lot.symbol == fill.symbol and lot.exchange == fill.exchange and lot.sellable_on <= fill.trade_date:
                sold = min(remaining, lot.quantity)
                removed_cost = lot.cost_cny * sold / lot.quantity
                sold_cost += removed_cost
                retained = lot.quantity - sold
                if retained:
                    updated.append(replace(lot, quantity=retained,
                                           cost_cny=lot.cost_cny - removed_cost))
                remaining -= sold
            else:
                updated.append(lot)
        lots = updated
        cash = state.cash_cny + gross - fees
        realized = state.realized_pnl_cny + gross - fees - sold_cost
    return replace(state, cash_cny=cash, realized_pnl_cny=realized, lots=tuple(lots),
                   transaction_ids=state.transaction_ids | {fill.transaction_id},
                   last_trade_date=fill.trade_date, status="DRAFT_UNRECONCILED",
                   confirmed_at=None, confirmation_evidence=None)


def confirm(draft: Reconciliation, *, expected_version: int, confirmed_at: datetime,
            evidence_ref: dict[str, str]) -> Reconciliation:
    """Explicit user confirmation advances only this in-memory version."""
    if draft.status != "DRAFT_UNRECONCILED" or draft.version != expected_version:
        raise ValueError("draft version conflict")
    if confirmed_at.utcoffset() is None or confirmed_at.date() < draft.last_trade_date:
        raise ValueError("confirmation requires a timezone-aware time after trade")
    if not isinstance(evidence_ref, dict) or not isinstance(evidence_ref.get("id"), str) or not evidence_ref["id"].strip():
        raise ValueError("confirmation evidence required")
    return replace(draft, version=draft.version + 1, status="CONFIRMED_IN_MEMORY",
                   confirmed_at=confirmed_at, confirmation_evidence=dict(evidence_ref))


def portfolio_snapshot(state: Reconciliation, *, snapshot_id: str, available_at: datetime,
                       evidence_ref: dict[str, str]) -> PortfolioSnapshot:
    """Project an accounting view; prices remain unknown and no ACTUAL storage is claimed."""
    if state.status != "CONFIRMED_IN_MEMORY" or state.version == 0 or state.confirmation_evidence != evidence_ref:
        raise ValueError("only an explicitly confirmed transition can be projected")
    if available_at.utcoffset() is None or state.confirmed_at is None or available_at < state.confirmed_at:
        raise ValueError("snapshot cannot predate confirmation")
    grouped: dict[tuple[str, str], tuple[Decimal, Decimal]] = {}
    for lot in state.lots:
        key = (lot.symbol, lot.exchange)
        quantity, cost = grouped.get(key, (Decimal(0), Decimal(0)))
        grouped[key] = (quantity + lot.quantity, cost + lot.cost_cny)
    holdings = tuple(PortfolioHolding(symbol, exchange, quantity, cost, None,
                                      QUANTITY_HUMAN_CONFIRMED, False, (evidence_ref,))
                     for (symbol, exchange), (quantity, cost) in sorted(grouped.items()))
    return PortfolioSnapshot(snapshot_id, str(state.version), state.last_trade_date,
                             available_at, state.baseline.account_scope, state.baseline.namespace,
                             state.cash_cny, holdings, RECONCILIATION_RECONCILED,
                             available_at, (evidence_ref,))
