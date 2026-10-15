"""Fixed IPS cash amounts through the unchanged fraction-based domain engine."""
from datetime import datetime
from decimal import Decimal as D

import pytest

from test_private_ips_policy import service, full_policy
from test_portfolio_risk_assessment import _attributes
from value_investment_agent.application.portfolio import private_risk_projection as projection
from value_investment_agent.domain.portfolio.dual_sleeve_risk import review_dual_sleeve_risk

NOW = datetime.fromisoformat("2026-10-15T10:00:00+08:00")


def account(service):
    # This synthetic baseline deliberately differs from the latest confirmed IPS.
    records = service.records()
    replayed = service._replay(records)
    from dataclasses import replace
    from value_investment_agent.application.portfolio.web_reconciliation import Lot
    state = replace(replayed.state, cash_cny=D("10190"), lots=(
        Lot("HOTSPOT_SATELLITE", "300364", "SZSE", D("100"), D("2000"), NOW.date()),))
    policy = full_policy()
    policy.update(investable_assets_cny="12000", core_value_budget_cny="7000",
        hotspot_budget_cny="4000", cash_reserve_cny="1000", minimum_cash_cny="1000",
        _confirmed_at="2026-10-14T20:00:00+08:00", _record_sha256="a" * 64, _state_version=0)
    policy["sleeves"]["CORE_VALUE"]["cash_cny"] = "6190"
    policy["sleeves"]["HOTSPOT_SATELLITE"]["cash_cny"] = "3000"
    # Reconciliation remains a synthetic, explicit input, not a production write.
    snapshot = replace(state.baseline, cash_cny=state.cash_cny,
        holdings=projection._holdings(replace(replayed, state=state), {"id": "SYNTHETIC"}))
    return replace(replayed, state=state, policy=policy, snapshot=snapshot.as_policy(), snapshot_version=0)


def payload(service, monkeypatch, price):
    replayed = account(service)
    monkeypatch.setattr(projection, "_verified_attributes", lambda *args, **kwargs:
        [_attributes(symbol="300364", common_factors=("SYNTHETIC",)).as_policy()])
    prices = {} if price is None else {"300364": {"price_cny": price, "trade_date": "2026-10-14"}}
    return projection.build_risk_input(replayed, sellable_as_of=NOW.date(), generated_at=NOW, _prices=prices)


@pytest.mark.parametrize("price", ["26.58", "20", "1", "100"])
def test_fixed_reserve_does_not_rise_with_marked_equity_and_caps_remain_valid(service, monkeypatch, price):
    data = payload(service, monkeypatch, price)
    equity = D("10190") + D("100") * D(price)
    floor = D(data["shared_budget"]["cash_floor"])
    assert equity * floor <= D("1000")
    assert abs(equity * floor - D("1000")) < D("1e-20")
    assert data["cash_reserve_cny"] == "1000"
    assert data["sleeves"]["HOTSPOT_SATELLITE"]["capital_budget_cny"] == "4000"
    assert sum(D(data["shared_budget"][key]) for key in
        ("core_value_budget", "tactical_hotspot_budget", "cash_floor")) <= 1
    report = review_dual_sleeve_risk(data, generated_at=NOW)
    assert "shared:cash_floor_violation" not in report["blockers"]
    assert report["aggregate"]["reserve_cny"] == "1000"
    if price == "26.58":
        assert "HOTSPOT_SATELLITE:budget_exceeded" in report["blockers"]
        assert D(report["sleeves"]["HOTSPOT_SATELLITE"]["equity_cny"]) == D("5658")
        assert D(report["sleeves"]["HOTSPOT_SATELLITE"]["budget_cny"]) == D("4000")


def test_missing_quote_still_blocks_instead_of_assuming_equity(service, monkeypatch):
    data = payload(service, monkeypatch, None)
    assert data["portfolio"]["snapshot"]["holdings"][0]["market_value_cny"] is None
    report = review_dual_sleeve_risk(data, generated_at=NOW)
    assert report["status"] == "BLOCKED_PRIVATE_INPUT"
    assert "holding_market_value" in report["blockers"]


def test_actual_cash_shortfall_remains_blocked(service, monkeypatch):
    data = payload(service, monkeypatch, "26.58")
    data["portfolio"]["policy"]["minimum_cash_cny"] = "11000"
    report = review_dual_sleeve_risk(data, generated_at=NOW)
    assert any("reserved_cash" in code for code in report["blockers"])
