"""Synthetic account only: first use through restart and risk review."""
from datetime import datetime

from value_investment_agent.application.portfolio.private_portfolio_service import PrivateJournal, PrivatePortfolioService
from value_investment_agent.application.portfolio.private_risk_projection import review_private_risk_rehearsal
from test_private_ips_policy import full_policy, service


def test_cash_account_policy_buy_sell_and_restart(tmp_path):
    journal = PrivateJournal(tmp_path / "TEST_ONLY-P6.jsonl")
    service = PrivatePortfolioService(journal)
    service.initialize({"idempotency_key": "init", "expected_revision": 0,
        "account_scope": "TEST_ONLY_SYNTHETIC_P6", "as_of": "2026-10-12",
        "cash_cny": "10000", "holdings": [], "sleeve_allocations": {}, "policy": {},
        "confirmed_at": "2026-10-12T20:00:00+08:00", "confirmation_note": "TEST ONLY"})
    policy = full_policy()
    policy["sleeves"]["CORE_VALUE"]["cash_cny"] = "7000"
    prepared, _ = service.prepare_policy({"idempotency_key": "policy", "expected_revision": 1, "policy": policy})
    assert service.portfolio_view()["cash_cny"] == "10000"
    assert service.portfolio_view()["total_equity_cny"] == "10000"
    assert service.portfolio_view()["confirmed_cash_reserve_cny"] is None
    service = PrivatePortfolioService(PrivateJournal(journal.path))
    pending = service.policy_view()["pending_policy"]
    service.confirm_policy({"idempotency_key": "policy-confirm", "expected_revision": len(service.records()),
        "prepared_record_sha256": pending["prepared_record_sha256"],
        "confirmed_at": "2026-10-12T20:01:00+08:00", "confirmation_note": "TEST ONLY"})
    assert service.portfolio_view()["confirmed_cash_reserve_cny"] == "1000"
    for side, price, day, cash in [("BUY", "20", "2026-10-12", "7995"), ("SELL", "22", "2026-10-14", "10190")]:
        before = service.portfolio_view()["cash_cny"]
        service.prepare_fill({"idempotency_key": side, "expected_revision": len(service.records()),
            "fill": {"transaction_id": side, "symbol": "300364", "exchange": "SZSE",
                "side": side, "sleeve": "CORE_VALUE", "quantity": "100", "price_cny": price,
                "fees_cny": "5", "trade_date": day, "trading_unit": "100" if side == "BUY" else None,
                "next_sell_session": "2026-10-13" if side == "BUY" else None}})
        assert service.portfolio_view()["cash_cny"] == before
        service = PrivatePortfolioService(PrivateJournal(journal.path))
        draft = service.portfolio_view()["pending_draft"]
        confirmation = {"idempotency_key": side + "-confirm", "expected_revision": len(service.records()),
            "prepared_record_sha256": draft["prepared_record_sha256"],
            "confirmed_at": day + "T20:00:00+08:00", "confirmation_note": "TEST ONLY"}
        result = service.confirm_fill(confirmation)
        assert service.confirm_fill(confirmation) == result
        assert result[0]["cash_cny"] == cash
    service = PrivatePortfolioService(PrivateJournal(journal.path))
    view = service.portfolio_view()
    assert view["realized_pnl_cny"] == "190"
    assert len(view["trades"]) == 2
    assert view["positions"] == []
    risk = review_private_risk_rehearsal(service.journal,
        generated_at=datetime.fromisoformat("2026-10-14T20:00:00+08:00"))
    assert risk["facts"]["cash_cny"] == "10190"
    assert risk["facts"]["confirmed_fill_count"] == 2
    assert risk["engine"]["trade_eligible"] is False


def test_sleeve_summaries_require_verified_prices(service, tmp_path, monkeypatch):
    from test_private_ips_policy import quotes
    unmarked = service.portfolio_view()
    assert unmarked["cost_basis_total_cny"] == "2000"
    assert unmarked["sleeve_summaries"][0]["cost_basis_cny"] == "2000"
    assert unmarked["sleeve_summaries"][0]["market_value_cny"] is None
    assert unmarked["total_position_weight_pct"] is None
    quotes(monkeypatch)
    marked = service.portfolio_view(repository_root=tmp_path,
        generated_at=datetime.fromisoformat("2026-10-14T20:00:00+08:00"))
    assert marked["total_equity_cny"] == "11000"
    assert marked["sleeve_summaries"][0]["market_value_cny"] == "3000"
    assert marked["sleeve_summaries"][0]["weight_pct"] == marked["total_position_weight_pct"]
    assert marked["sleeve_summaries"][1]["market_value_cny"] == "0"
    quotes(monkeypatch, stale=True)
    stale = service.portfolio_view(repository_root=tmp_path,
        generated_at=datetime.fromisoformat("2026-10-14T20:00:00+08:00"))
    assert stale["total_equity_cny"] is None
    assert stale["sleeve_summaries"][0]["market_value_cny"] is None
