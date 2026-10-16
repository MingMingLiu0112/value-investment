"""TEST_ONLY private-account continuity across confirmed ledger days."""
from datetime import date, datetime
from decimal import Decimal

import pytest

from value_investment_agent.application.portfolio.private_portfolio_service import (
    JournalValidationError, PrivateJournal, PrivatePortfolioService,
)
from value_investment_agent.application.portfolio.private_risk_projection import review_private_risk_rehearsal


def _confirm_fill(service, revision, transaction, side, trade_date, quantity, *, next_session=None):
    fill = {"transaction_id": transaction, "side": side, "sleeve": "CORE_VALUE",
            "symbol": "600005", "exchange": "SSE", "quantity": str(quantity),
            "price_cny": "10", "fees_cny": "1", "trade_date": trade_date}
    if side == "BUY":
        fill.update(next_sell_session=next_session, trading_unit="100")
    _, digest = service.prepare_fill({"idempotency_key": transaction + "-prepare",
        "expected_revision": revision, "fill": fill})
    result, _ = service.confirm_fill({"idempotency_key": transaction + "-confirm",
        "expected_revision": revision + 1, "prepared_record_sha256": digest,
        "confirmed_at": trade_date + "T20:00:00+08:00", "confirmation_note": "TEST_ONLY"})
    return result


def test_account_isolation_and_non_top_five_holding_continues_across_days(tmp_path):
    first_path = tmp_path / "TEST_ONLY-first.jsonl"
    other_path = tmp_path / "TEST_ONLY-other.jsonl"
    service = PrivatePortfolioService(PrivateJournal(first_path))
    symbols = [f"60000{i}" for i in range(6)]
    service.initialize({"idempotency_key": "init", "expected_revision": 0,
        "account_scope": "TEST_ONLY_FIRST", "as_of": "2026-10-10", "cash_cny": "10000",
        "holdings": [{"symbol": symbol, "exchange": "SSE", "quantity": "100",
                      "cost_basis_cny": "1000"} for symbol in symbols],
        "sleeve_allocations": {symbol: {"CORE_VALUE": "100"} for symbol in symbols},
        "policy": {}, "confirmed_at": "2026-10-10T20:00:00+08:00",
        "confirmation_note": "TEST_ONLY"})
    policy = {"investable_assets_cny": "16000", "core_value_budget_cny": "12000",
        "hotspot_budget_cny": "1000", "cash_reserve_cny": "1000",
        "minimum_cash_cny": "1000", "max_single_security_pct": "30",
        "max_single_industry_pct": "60", "hotspot_single_trade_risk_pct": "1",
        "max_drawdown_pct": "20", "financing_allowed": False,
        "dividend_income_goal_cny": "100", "effective_date": "2026-10-10",
        "time_horizon_years": "5", "risk_tolerance": "BALANCED",
        "concentration_allowed": False, "max_factor_pct": "30",
        "risk_tools_allowed": False, "sleeves": {
            "CORE_VALUE": {"cash_cny": "9000", "risk_budget_cny": "1000"},
            "HOTSPOT_SATELLITE": {"cash_cny": "0", "risk_budget_cny": "0",
                                  "single_security_risk_cny": "0"}}}
    _, digest = service.prepare_policy({"idempotency_key": "ips-prepare",
        "expected_revision": 1, "policy": policy})
    service.confirm_policy({"idempotency_key": "ips-confirm", "expected_revision": 2,
        "prepared_record_sha256": digest, "confirmed_at": "2026-10-10T21:00:00+08:00",
        "confirmation_note": "TEST_ONLY"})

    bought = _confirm_fill(service, 3, "buy", "BUY", "2026-10-12", 100,
                           next_session="2026-10-13")
    assert bought["cash_cny"] == "8999"
    held = next(row for row in service.portfolio_view(today=date(2026, 10, 12))["positions"]
                if row["symbol"] == "600005")
    assert held["quantity"] == "200"
    assert held["sleeves"][0]["sellable_quantity"] == "100"
    with pytest.raises(JournalValidationError, match="insufficient sellable shares"):
        service.prepare_fill({"idempotency_key": "early-sell", "expected_revision": 5,
            "fill": {"transaction_id": "early", "side": "SELL", "sleeve": "CORE_VALUE",
                "symbol": "600005", "exchange": "SSE", "quantity": "150",
                "price_cny": "10", "fees_cny": "1", "trade_date": "2026-10-12"}})
    assert len(service.records()) == 5

    sold = _confirm_fill(service, 5, "sell", "SELL", "2026-10-13", 150)
    assert sold["cash_cny"] == "10498"
    restarted = PrivatePortfolioService(PrivateJournal(first_path))
    view = restarted.portfolio_view(today=date(2026, 10, 14))
    held = next(row for row in view["positions"] if row["symbol"] == "600005")
    assert held["quantity"] == "50"
    assert held["sleeves"][0]["sellable_quantity"] == "50"
    assert Decimal(view["realized_pnl_cny"]) == Decimal("-1.5")
    assert len(view["positions"]) == 6
    risk = review_private_risk_rehearsal(restarted.journal,
        generated_at=datetime.fromisoformat("2026-10-14T10:00:00+08:00"),
        today=date(2026, 10, 14))
    assert risk["facts"]["account_scope"] == "TEST_ONLY_FIRST"
    assert {row["symbol"] for row in risk["facts"]["positions"]} == set(symbols)
    assert risk["facts"]["cash_cny"] == "10498"
    assert risk["engine"]["position_guidance"] is None

    other = PrivatePortfolioService(PrivateJournal(other_path))
    assert other.portfolio_view()["status"] == "NOT_CONNECTED"
    assert other.records() == []
    first_bytes = first_path.read_bytes()
    other.initialize({"idempotency_key": "other-init", "expected_revision": 0,
        "account_scope": "TEST_ONLY_OTHER", "as_of": "2026-10-10", "cash_cny": "123",
        "holdings": [], "sleeve_allocations": {}, "policy": {},
        "confirmed_at": "2026-10-10T20:00:00+08:00", "confirmation_note": "TEST_ONLY"})
    assert other.portfolio_view()["cash_cny"] == "123"
    assert other.portfolio_view()["positions"] == []
    assert first_path.read_bytes() == first_bytes
    assert restarted.portfolio_view(today=date(2026, 10, 14))["cash_cny"] == "10498"


def test_same_symbol_in_two_sleeves_survives_one_sleeve_buy_and_sell(tmp_path):
    path = tmp_path / "TEST_ONLY-two-sleeves.jsonl"
    service = PrivatePortfolioService(PrivateJournal(path))
    service.initialize({"idempotency_key": "init-two", "expected_revision": 0,
        "account_scope": "TEST_ONLY_TWO_SLEEVES", "as_of": "2026-10-10", "cash_cny": "10000",
        "holdings": [{"symbol": "600005", "exchange": "SSE", "quantity": "100",
                      "cost_basis_cny": "1000"}],
        "sleeve_allocations": {"600005": {"CORE_VALUE": "60", "HOTSPOT_SATELLITE": "40"}},
        "policy": {}, "confirmed_at": "2026-10-10T20:00:00+08:00",
        "confirmation_note": "TEST_ONLY"})
    _confirm_fill(service, 1, "buy-two", "BUY", "2026-10-12", 100,
                  next_session="2026-10-13")
    _confirm_fill(service, 3, "sell-two", "SELL", "2026-10-13", 100)
    restarted = PrivatePortfolioService(PrivateJournal(path))
    position = restarted.portfolio_view(today=date(2026, 10, 14))["positions"][0]
    assert position["symbol"] == "600005" and position["quantity"] == "100"
    assert {row["sleeve"]: row["quantity"] for row in position["sleeves"]} == {
        "CORE_VALUE": "60", "HOTSPOT_SATELLITE": "40"}
