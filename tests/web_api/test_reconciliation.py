from datetime import date, datetime, timezone
from decimal import Decimal as D

import pytest

from value_investment_agent.application.portfolio.web_reconciliation import (
    Fill, confirm, initialize, portfolio_snapshot, prepare,
)
from value_investment_agent.portfolio_contracts import PortfolioHolding, PortfolioSnapshot


NOW = datetime(2026, 10, 12, 12, tzinfo=timezone.utc)
EVIDENCE = {"id": "synthetic-user-confirmation"}


def baseline():
    return PortfolioSnapshot("synthetic", "v1", date(2026, 10, 9), NOW,
                             "synthetic-account", "SIMULATED", D("1000"), (),
                             "RECONCILED", NOW, (EVIDENCE,))


def buy(**changes):
    args = dict(transaction_id="b1", side="BUY", sleeve="CORE_VALUE",
                symbol="600519", exchange="SSE", quantity=D("100"),
                price_cny=D("2"), fees_cny=D("0"), trade_date=date(2026, 10, 12),
                next_sell_session=date(2026, 10, 13), trading_unit=D("100"))
    args.update(changes)
    return Fill(**args)


def sell(**changes):
    args = dict(transaction_id="s1", side="SELL", sleeve="CORE_VALUE",
                symbol="600519", exchange="SSE", quantity=D("100"),
                price_cny=D("3"), fees_cny=D("0"), trade_date=date(2026, 10, 13))
    args.update(changes)
    return Fill(**args)


def confirmed(state):
    return confirm(state, expected_version=state.version,
                   confirmed_at=datetime(2026, 10, 14, tzinfo=timezone.utc),
                   evidence_ref=EVIDENCE)


def test_cash_cost_realized_pnl_and_snapshot():
    start = initialize(baseline(), {})
    draft = prepare(start, buy(), expected_version=0)
    assert draft.status == "DRAFT_UNRECONCILED"
    assert (start.cash_cny, draft.cash_cny) == (D("1000"), D("800"))
    after_buy = confirmed(draft)
    sold = prepare(after_buy, sell(), expected_version=1)
    assert sold.cash_cny == D("1100")
    assert sold.realized_pnl_cny == D("100")
    final = confirmed(sold)
    projection = portfolio_snapshot(final, snapshot_id="in-memory", available_at=datetime(2026, 10, 14, tzinfo=timezone.utc),
                                    evidence_ref=EVIDENCE)
    assert projection.cash_cny == D("1100")
    assert projection.holdings == ()
    assert projection.action == "no_order"


def test_duplicate_version_and_draft_are_rejected():
    start = initialize(baseline(), {})
    draft = prepare(start, buy(), expected_version=0)
    with pytest.raises(ValueError, match="unconfirmed predecessor"):
        prepare(draft, sell(), expected_version=0)
    after_buy = confirmed(draft)
    with pytest.raises(ValueError, match="duplicate"):
        prepare(after_buy, buy(), expected_version=1)
    with pytest.raises(ValueError, match="version"):
        prepare(after_buy, sell(), expected_version=0)


def test_cash_sellable_and_cross_sleeve():
    start = initialize(baseline(), {})
    with pytest.raises(ValueError, match="cash"):
        prepare(start, buy(price_cny=D("11")), expected_version=0)
    after_buy = confirmed(prepare(start, buy(), expected_version=0))
    with pytest.raises(ValueError, match="sellable"):
        prepare(after_buy, sell(trade_date=date(2026, 10, 12)), expected_version=1)
    with pytest.raises(ValueError, match="sellable"):
        prepare(after_buy, sell(sleeve="HOTSPOT_SATELLITE"), expected_version=1)
    with pytest.raises(ValueError, match="sellable"):
        prepare(after_buy, sell(quantity=D("101")), expected_version=1)


def test_buy_unit_fees_and_corporate_action_fail_closed():
    start = initialize(baseline(), {})
    with pytest.raises(ValueError, match="trading unit"):
        prepare(start, buy(trading_unit=None), expected_version=0)
    with pytest.raises(ValueError, match="trading unit"):
        prepare(start, buy(quantity=D("50")), expected_version=0)
    with pytest.raises(ValueError, match="corporate actions"):
        prepare(start, buy(corporate_action=True), expected_version=0)
    after_buy = confirmed(prepare(start, buy(fees_cny=D("2")), expected_version=0))
    sold = prepare(after_buy, sell(fees_cny=D("3")), expected_version=1)
    assert sold.cash_cny == D("1095")
    assert sold.realized_pnl_cny == D("95")


def test_opening_1000_shares_buy_200_sell_300_and_sleeve_counts():
    opening = PortfolioHolding("600519", "SSE", D("1000"), D("1000"), None,
                               "HUMAN_CONFIRMED", False, (EVIDENCE,))
    snapshot = PortfolioSnapshot("opening", "v1", date(2026, 10, 9), NOW,
                                 "synthetic-account", "SIMULATED", D("1000"),
                                 (opening,), "RECONCILED", NOW, (EVIDENCE,))
    start = initialize(snapshot, {("CORE_VALUE", "600519"): D("600"),
                                  ("HOTSPOT_SATELLITE", "600519"): D("400")})
    bought = confirmed(prepare(start, buy(quantity=D("200"), price_cny=D("1")), expected_version=0))
    with pytest.raises(ValueError, match="sellable"):
        prepare(bought, sell(sleeve="HOTSPOT_SATELLITE", quantity=D("500")), expected_version=1)
    sold = prepare(bought, sell(quantity=D("300"), price_cny=D("2")), expected_version=1)
    assert sold.cash_cny == D("1400")
    assert sold.realized_pnl_cny == D("300")
    assert sum(lot.quantity for lot in sold.lots if lot.sleeve == "CORE_VALUE") == D("500")
    assert sum(lot.quantity for lot in sold.lots if lot.sleeve == "HOTSPOT_SATELLITE") == D("400")
