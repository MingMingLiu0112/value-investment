"""Feed the confirmed private journal into the existing dual-sleeve risk engine.

WEB-D2 P1. The journal is the only source of confirmed private facts, so this
adapter maps it onto the frozen `dual-sleeve-risk-input-v1` contract and lets
`review_dual_sleeve_risk` decide. It never invents an IPS field, a sleeve
budget, a risk threshold, a security risk attribute or a market value: whatever
the journal does not carry is passed through as ``None`` so the engine answers
with its exact `BLOCKED_PRIVATE_INPUT` gap list instead of a fabricated number.

Two facts are deliberately conservative:

* market value and unrealized PnL stay ``None`` until an admitted quote bridge
  exists, so the engine reports `holding_market_value` as a gap;
* a journal that has no `RECONCILED_CONFIRMED` record projects a
  `PENDING_RECONCILIATION` snapshot, so the engine reports `reconciliation`.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from ...domain.portfolio.dual_sleeve_risk import review_dual_sleeve_risk
from ...portfolio_contracts import (
    NAMESPACE_ACTUAL,
    QUANTITY_HUMAN_CONFIRMED,
    RECONCILIATION_PENDING,
    RECONCILIATION_RECONCILED,
    RISK_UNKNOWN,
    SCHEMA_VERSION,
    PortfolioHolding,
    PortfolioSnapshot,
    portfolio_snapshot_from_payload,
)
from .private_portfolio_service import PrivateJournal, PrivatePortfolioService, ReplayedPortfolio

RISK_INPUT_SCHEMA = "dual-sleeve-risk-input-v1"
PRICE_ADMISSION_REASON = "尚未接入经核验的当前行情，无法计算市值、浮动盈亏与仓位权重"
_POLICY_AMOUNT_FIELDS = (
    "investable_assets_cny",
    "minimum_cash_cny",
    "emergency_cash_cny",
    "liquidity_needs_cny",
    "max_single_security_pct",
    "max_single_industry_pct",
    "max_cyclical_exposure_pct",
    "dividend_income_goal_cny",
)


def _evidence(replayed: ReplayedPortfolio) -> dict[str, str]:
    state = replayed.state
    if state.confirmation_evidence:
        return dict(state.confirmation_evidence)
    if state.baseline.evidence_refs:
        return dict(state.baseline.evidence_refs[0])
    return {"id": f"private-journal-{state.baseline.account_scope}", "kind": "user_confirmation"}


def _policy_payload(replayed: ReplayedPortfolio) -> dict[str, Any]:
    """Map the journal's confirmed IPS subset onto the frozen policy contract."""
    state = replayed.state
    stored = dict(replayed.policy)
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "policy_id": f"private-journal:{state.baseline.account_scope}",
        "policy_version": f"v{state.version}",
        "as_of": state.baseline.as_of.isoformat(),
        "confirmation_status": "HUMAN_CONFIRMED",
        "confirmed_at": (state.confirmed_at or state.baseline.available_at).isoformat(),
        "account_scope": state.baseline.account_scope,
    }
    for field in _POLICY_AMOUNT_FIELDS:
        payload[field] = stored.get(field)
    payload["time_horizon_years"] = None
    payload["risk_tolerance"] = stored.get("risk_tolerance") or RISK_UNKNOWN
    payload["concentration_allowed"] = None
    payload["tax_regime"] = None
    payload["restrictions"] = list(stored.get("restrictions") or ["no_order"])
    payload["evidence_refs"] = [_evidence(replayed)]
    payload["sensitivity"] = "PRIVATE_USER_CONFIRMED"
    payload["action"] = "no_order"
    return payload


def _holdings(replayed: ReplayedPortfolio, evidence: dict[str, str]) -> tuple[PortfolioHolding, ...]:
    grouped: dict[tuple[str, str], tuple[Decimal, Decimal]] = {}
    for lot in replayed.state.lots:
        key = (lot.symbol, lot.exchange)
        quantity, cost = grouped.get(key, (Decimal(0), Decimal(0)))
        grouped[key] = (quantity + lot.quantity, cost + lot.cost_cny)
    return tuple(
        PortfolioHolding(symbol, exchange, quantity, cost, None,
                         QUANTITY_HUMAN_CONFIRMED, False, (evidence,))
        for (symbol, exchange), (quantity, cost) in sorted(grouped.items())
    )


def _snapshot_payload(replayed: ReplayedPortfolio) -> dict[str, Any]:
    """Prefer the user-confirmed reconciliation record; otherwise project pending."""
    if replayed.snapshot is not None:
        return portfolio_snapshot_from_payload(replayed.snapshot).as_policy()
    state = replayed.state
    evidence = _evidence(replayed)
    snapshot = PortfolioSnapshot(
        snapshot_id=f"private-journal-projection-{state.version}",
        snapshot_version=f"v{state.version}",
        as_of=state.last_trade_date,
        available_at=state.confirmed_at or state.baseline.available_at,
        account_scope=state.baseline.account_scope,
        namespace=NAMESPACE_ACTUAL,
        cash_cny=state.cash_cny,
        holdings=_holdings(replayed, evidence),
        reconciliation_status=RECONCILIATION_PENDING,
        reconciled_at=None,
        evidence_refs=(evidence,),
    )
    return snapshot.as_policy()


def _allocations_payload(replayed: ReplayedPortfolio, sellable_as_of: date) -> list[dict[str, Any]]:
    """Real per-sleeve share counts straight from the replayed lots."""
    rows: list[dict[str, Any]] = []
    for lot in replayed.state.lots:
        rows.append({
            "sleeve": lot.sleeve,
            "symbol": lot.symbol,
            "quantity": str(lot.quantity),
            "sellable_quantity": str(lot.quantity if lot.sellable_on <= sellable_as_of else 0),
            "committed_risk_cny": None,
            "evidence_ref": {"id": f"private-lot-{lot.symbol}-{lot.sleeve}", "kind": "user_confirmation"},
        })
    return rows


def build_risk_input(
    replayed: ReplayedPortfolio,
    *,
    sellable_as_of: date,
    namespace: str = NAMESPACE_ACTUAL,
) -> dict[str, Any]:
    return {
        "schema_version": RISK_INPUT_SCHEMA,
        "action": "no_order",
        "namespace": namespace,
        "portfolio": {
            "policy": _policy_payload(replayed),
            "snapshot": _snapshot_payload(replayed),
            "action": "no_order",
        },
        "shared_budget": None,
        "sleeves": None,
        "cash_reserve_cny": None,
        "allocations": _allocations_payload(replayed, sellable_as_of),
        "security_attributes": None,
        "hotspot_request": None,
    }


def _facts(replayed: ReplayedPortfolio) -> dict[str, Any]:
    state = replayed.state
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for lot in state.lots:
        entry = grouped.setdefault((lot.symbol, lot.exchange), {
            "symbol": lot.symbol, "exchange": lot.exchange,
            "quantity": Decimal(0), "cost_basis_cny": Decimal(0), "sleeves": {},
        })
        entry["quantity"] += lot.quantity
        entry["cost_basis_cny"] += lot.cost_cny
        sleeve = entry["sleeves"].setdefault(lot.sleeve, {"sleeve": lot.sleeve, "quantity": Decimal(0)})
        sleeve["quantity"] += lot.quantity
    positions = []
    for key in sorted(grouped):
        entry = grouped[key]
        positions.append({
            "symbol": entry["symbol"],
            "exchange": entry["exchange"],
            "quantity": str(entry["quantity"]),
            "cost_basis_cny": str(entry["cost_basis_cny"]),
            "market_value_cny": None,
            "unrealized_pnl_cny": None,
            "sleeves": [{"sleeve": row["sleeve"], "quantity": str(row["quantity"])}
                        for row in sorted(entry["sleeves"].values(), key=lambda item: item["sleeve"])],
        })
    return {
        "revision": replayed.revision,
        "account_scope": state.baseline.account_scope,
        "as_of": state.last_trade_date.isoformat(),
        "cash_cny": str(state.cash_cny),
        "realized_pnl_cny": str(state.realized_pnl_cny),
        "cost_basis_total_cny": str(sum((lot.cost_cny for lot in state.lots), Decimal(0))),
        "positions": positions,
        "confirmed_fill_count": state.version,
        "reconciliation_status": (RECONCILIATION_RECONCILED if replayed.snapshot is not None
                                  else RECONCILIATION_PENDING),
        "price_status": "PRICE_NOT_ADMITTED",
        "price_reason": PRICE_ADMISSION_REASON,
    }


def review_private_risk_rehearsal(
    journal: PrivateJournal,
    *,
    generated_at: datetime,
    today: date | None = None,
) -> dict[str, Any]:
    """Run the real engine on real confirmed facts; report the exact gaps."""
    service = PrivatePortfolioService(journal)
    records = service.records()
    if not records:
        return {
            "action": "no_order",
            "status": "NOT_CONNECTED",
            "blockers": ["PRIVATE_PORTFOLIO_NOT_CONNECTED"],
            "engine": None,
            "facts": None,
        }
    replayed = service._replay(records)
    assert replayed is not None
    sellable_as_of = max(replayed.state.last_trade_date, today or datetime.now().astimezone().date())
    report = review_dual_sleeve_risk(
        build_risk_input(replayed, sellable_as_of=sellable_as_of), generated_at=generated_at)
    return {
        "action": "no_order",
        "status": report["status"],
        "blockers": list(report.get("blockers") or ()),
        "engine": report,
        "facts": _facts(replayed),
    }
