"""Synthetic partial quote failures must not erase verified account facts."""
from datetime import date, datetime
from types import SimpleNamespace

import pytest

from test_private_ips_policy import service
from value_investment_agent.application.portfolio import private_risk_projection as projection

NOW = datetime.fromisoformat("2026-10-15T10:00:00+08:00")


@pytest.mark.parametrize("fallback", ["unavailable", "malformed", "stale"])
def test_quote_failure_is_isolated_to_affected_symbol(tmp_path, monkeypatch, fallback):
    from value_investment_agent.application.product import quote_bridge
    from value_investment_agent.application.hotspot import current_registry

    replayed = SimpleNamespace(state=SimpleNamespace(
        lots=[SimpleNamespace(symbol=symbol) for symbol in ("300364", "600519")],
        last_trade_date=date(2026, 10, 13)))

    def quote(root, symbol, **kwargs):
        if symbol == "600519":
            raise ValueError("TEST_ONLY corrupt quote evidence")
        return {"compatibility": {"verified_quote": {"eligible": True}}, "quote": {
            "quote_date": "2026-10-14", "latest_completed_session": "2026-10-14",
            "display_price": "30", "bundle_sha256": "a" * 64}}

    def conditions(*args, **kwargs):
        if fallback == "unavailable":
            raise OSError("TEST_ONLY unavailable registry")
        return {"items": [{"symbol": "600519", "price_action_plan": {
            "current_reference_price": "invalid" if fallback == "malformed" else "1000",
            "market_trade_date": "2026-10-12", "case_sha256": "b" * 64}}]}

    monkeypatch.setattr(quote_bridge, "execute_quote_bridge_for_symbol", quote)
    monkeypatch.setattr(current_registry, "load_price_conditions", conditions)
    prices = projection._verified_prices(tmp_path, replayed, NOW)
    assert set(prices) == {"300364"}
    assert prices["300364"]["price_cny"] == "30"


def test_confirmed_fill_immediately_updates_account_date_and_facts(service, tmp_path):
    _, digest = service.prepare_fill({"idempotency_key": "buy", "expected_revision": 1,
        "fill": {"transaction_id": "TEST_ONLY-buy", "side": "BUY", "sleeve": "CORE_VALUE",
            "symbol": "300364", "exchange": "SZSE", "quantity": "100", "price_cny": "30",
            "fees_cny": "5", "trade_date": "2026-10-13", "next_sell_session": "2026-10-14",
            "trading_unit": "100"}})
    service.confirm_fill({"idempotency_key": "confirm", "expected_revision": 2,
        "prepared_record_sha256": digest, "confirmed_at": "2026-10-13T21:00:00+08:00",
        "confirmation_note": "TEST_ONLY confirmed fill"})
    before = service.journal.path.read_bytes()
    view = service.portfolio_view()
    result = projection.review_private_risk_rehearsal(service.journal,
        repository_root=tmp_path, generated_at=NOW)
    assert view["as_of"] == result["facts"]["as_of"] == "2026-10-13"
    assert view["cash_cny"] == result["facts"]["cash_cny"] == "4995"
    assert result["facts"]["positions"][0]["quantity"] == "200"
    assert result["facts"]["cost_basis_total_cny"] == "5005"
    assert result["engine"]["position_guidance"] is None
    assert service.journal.path.read_bytes() == before


@pytest.mark.parametrize("with_holding", [False, True])
@pytest.mark.parametrize("as_of,confirmed_at,blocker", [
    ("2026-10-16", "2026-10-15T09:00:00+08:00", "ACCOUNT_AS_OF_IN_FUTURE"),
    ("2026-10-15", "2026-10-15T11:00:00+08:00", "ACCOUNT_FACTS_NOT_YET_AVAILABLE"),
])
def test_future_account_keeps_ledger_facts_but_never_current_equity(tmp_path, monkeypatch, with_holding,
        as_of, confirmed_at, blocker):
    from value_investment_agent.application.portfolio.private_portfolio_service import PrivateJournal, PrivatePortfolioService
    service = PrivatePortfolioService(PrivateJournal(tmp_path / "TEST_ONLY-future.jsonl"))
    service.initialize({"idempotency_key": "init", "expected_revision": 0,
        "account_scope": "TEST_ONLY_FUTURE", "as_of": as_of, "cash_cny": "8000",
        "holdings": [{"symbol": "300364", "exchange": "SZSE", "quantity": "100",
            "cost_basis_cny": "2000"}] if with_holding else [],
        "sleeve_allocations": {"300364": {"CORE_VALUE": "100"}} if with_holding else {},
        "policy": {}, "confirmed_at": confirmed_at, "confirmation_note": "TEST_ONLY future facts"})
    monkeypatch.setattr(projection, "_verified_prices", lambda *args: {
        "300364": {"price_cny": "30", "trade_date": as_of}})
    before = service.journal.path.read_bytes()
    view = service.portfolio_view(repository_root=tmp_path, generated_at=NOW)
    risk = projection.review_private_risk_rehearsal(service.journal, repository_root=tmp_path, generated_at=NOW)
    facts = risk["facts"]
    assert view["cash_cny"] == facts["cash_cny"] == "8000"
    assert view["as_of"] == facts["as_of"] == as_of
    assert facts["cost_basis_total_cny"] == ("2000" if with_holding else "0")
    assert blocker in view["blockers"]
    assert blocker in risk["blockers"]
    assert blocker in facts["valuation_blockers"]
    assert view["valuation"]["status"] == facts["price_status"] == "PRICE_NOT_ADMITTED"
    for field in ("total_equity_cny", "market_value_total_cny", "unrealized_pnl_total_cny"):
        assert view[field] is facts[field] is None
    assert view["total_position_weight_pct"] is None
    assert all(row["market_value_cny"] is None for row in view["sleeve_summaries"])
    if with_holding:
        assert facts["positions"][0]["quantity"] == "100"
        assert facts["positions"][0]["market_value_cny"] is None
        assert facts["positions"][0]["quote_binding"] is None
    assert risk["engine"]["position_guidance"] is None
    assert service.journal.path.read_bytes() == before


def test_cash_only_current_shanghai_day_remains_complete_without_quote(tmp_path):
    from value_investment_agent.application.portfolio.private_portfolio_service import PrivateJournal, PrivatePortfolioService
    service = PrivatePortfolioService(PrivateJournal(tmp_path / "TEST_ONLY-current-cash.jsonl"))
    service.initialize({"idempotency_key": "init", "expected_revision": 0,
        "account_scope": "TEST_ONLY_CURRENT", "as_of": "2026-10-15", "cash_cny": "8000",
        "holdings": [], "sleeve_allocations": {}, "policy": {},
        "confirmed_at": "2026-10-15T00:00:00+08:00", "confirmation_note": "TEST_ONLY"})
    # The UTC date is still Oct14, but the account is current in Shanghai.
    now = datetime.fromisoformat("2026-10-14T16:00:00+00:00")
    view = service.portfolio_view(generated_at=now)
    assert view["valuation"]["status"] == "CASH_ONLY_NO_QUOTE_REQUIRED"
    assert view["total_equity_cny"] == "8000"
    assert view["market_value_total_cny"] == "0"
    assert view["blockers"] == []


def test_future_confirmed_fill_cannot_make_future_balances_current(service, tmp_path):
    _, digest = service.prepare_fill({"idempotency_key": "future-buy", "expected_revision": 1,
        "fill": {"transaction_id": "TEST_ONLY-future-buy", "side": "BUY", "sleeve": "CORE_VALUE",
            "symbol": "300364", "exchange": "SZSE", "quantity": "100", "price_cny": "30",
            "fees_cny": "5", "trade_date": "2026-10-16", "next_sell_session": "2026-10-19",
            "trading_unit": "100"}})
    service.confirm_fill({"idempotency_key": "confirm-future", "expected_revision": 2,
        "prepared_record_sha256": digest, "confirmed_at": "2026-10-16T16:00:00+08:00",
        "confirmation_note": "TEST_ONLY future fill"})
    before = service.journal.path.read_bytes()
    view = service.portfolio_view(generated_at=NOW)
    risk = projection.review_private_risk_rehearsal(service.journal, repository_root=tmp_path, generated_at=NOW)
    assert view["cash_cny"] == risk["facts"]["cash_cny"] == "4995"
    assert risk["facts"]["positions"][0]["quantity"] == "200"
    assert {"ACCOUNT_AS_OF_IN_FUTURE", "ACCOUNT_FACTS_NOT_YET_AVAILABLE"} <= set(view["blockers"])
    assert view["total_equity_cny"] is risk["facts"]["total_equity_cny"] is None
    assert view["trades"][0]["trade_date"] == "2026-10-16"
    assert service.journal.path.read_bytes() == before
