from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from value_investment_agent.portfolio_contracts import (
    NAMESPACE_ACTUAL,
    QUANTITY_HUMAN_CONFIRMED,
    QUANTITY_PENDING_RECONCILIATION,
    RECONCILIATION_PENDING,
    RECONCILIATION_RECONCILED,
    PortfolioHolding,
    PortfolioSnapshot,
)
from value_investment_agent.portfolio_reconciliation import (
    STATUS_INCOMPLETE,
    STATUS_MATCH_PENDING_HUMAN_CONFIRMATION,
    STATUS_MISMATCH,
    reconcile_portfolio_snapshots,
)


NOW = datetime(2026, 9, 25, 9, tzinfo=timezone.utc)


def _holding(*, quantity: str = "10", exchange: str = "SSE", adjusted: bool = True, source: str = QUANTITY_HUMAN_CONFIRMED) -> PortfolioHolding:
    return PortfolioHolding(
        symbol="600519",
        exchange=exchange,
        quantity=Decimal(quantity),
        cost_basis_cny=Decimal("15000"),
        market_value_cny=Decimal("16000"),
        quantity_source=source,
        corporate_action_adjusted=adjusted,
        evidence_refs=({"id": "synthetic-holding"},),
    )


def _snapshot(*, snapshot_id: str, cash: Decimal | None = Decimal("50000"), holdings: tuple[PortfolioHolding, ...] = (_holding(),), pending: bool = False) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        snapshot_id=snapshot_id,
        snapshot_version="v1",
        as_of=date(2026, 9, 25),
        available_at=NOW,
        account_scope="synthetic-private-account",
        namespace=NAMESPACE_ACTUAL,
        cash_cny=cash,
        holdings=holdings,
        reconciliation_status=RECONCILIATION_PENDING if pending else RECONCILIATION_RECONCILED,
        reconciled_at=None if pending else NOW,
        evidence_refs=({"id": "synthetic-snapshot"},),
    )


def test_matching_snapshots_still_require_human_confirmation():
    report = reconcile_portfolio_snapshots(
        _snapshot(snapshot_id="reported", pending=True),
        _snapshot(snapshot_id="confirmed"),
        report_id="report-v1",
        generated_at=NOW,
    )

    assert report.status == STATUS_MATCH_PENDING_HUMAN_CONFIRMATION
    assert report.requires_human_confirmation is True
    assert report.differences == ()
    assert report.action == "no_order"


def test_reconciliation_reports_cash_and_holding_differences_privately():
    report = reconcile_portfolio_snapshots(
        _snapshot(snapshot_id="reported", cash=Decimal("45000"), holdings=(_holding(quantity="11", adjusted=False),), pending=True),
        _snapshot(snapshot_id="confirmed"),
        report_id="report-v2",
        generated_at=NOW,
    )

    assert report.status == STATUS_MISMATCH
    assert {item.kind for item in report.differences} == {"cash", "quantity", "corporate_action_adjustment"}
    assert report.as_private_policy()["sensitivity"] == "PRIVATE_USER_CONFIRMED"


def test_reconciliation_reports_missing_holding_and_exchange_difference():
    report = reconcile_portfolio_snapshots(
        _snapshot(snapshot_id="reported", holdings=(_holding(exchange="SZSE"),), pending=True),
        _snapshot(snapshot_id="confirmed", holdings=()),
        report_id="report-v3",
        generated_at=NOW,
    )

    assert report.status == STATUS_MISMATCH
    assert [item.kind for item in report.differences] == ["holding_missing"]

    exchange = reconcile_portfolio_snapshots(
        _snapshot(snapshot_id="reported", holdings=(_holding(exchange="SZSE"),), pending=True),
        _snapshot(snapshot_id="confirmed"),
        report_id="report-v4",
        generated_at=NOW,
    )
    assert [item.kind for item in exchange.differences] == ["exchange"]


def test_reconciliation_fails_closed_for_incomplete_or_cross_scope_inputs():
    report = reconcile_portfolio_snapshots(
        _snapshot(snapshot_id="reported", cash=None, pending=True),
        _snapshot(snapshot_id="confirmed"),
        report_id="report-v5",
        generated_at=NOW,
    )
    assert report.status == STATUS_INCOMPLETE

    with pytest.raises(ValueError, match="snapshot dates must match"):
        reconcile_portfolio_snapshots(
            _snapshot(snapshot_id="reported"),
            replace(_snapshot(snapshot_id="confirmed"), as_of=date(2026, 9, 24)),
            report_id="report-v6",
            generated_at=NOW,
        )
