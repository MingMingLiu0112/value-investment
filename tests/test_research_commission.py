"""Synthetic execution contracts, never real strategy performance."""
import csv
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

bt = pytest.importorskip('backtrader')
from value_investment_agent.research_commission import DatedResearchCommission


def commission(feed=None, **overrides):
    options = {'price_feed': feed if feed is not None else SimpleNamespace(datetime=SimpleNamespace(date=lambda _: date(2023, 8, 28))),
               'exchange': 'SSE', 'commission_rate': Decimal('0.0003'),
               'minimum_commission': Decimal('5'), 'scenario_id': 'synthetic-unrounded-per-fill-v1'}
    options.update(overrides)
    return DatedResearchCommission(**options)


class RoundTrip(bt.Strategy):
    def __init__(self):
        self.fills = []
        self.outcomes = []

    def next(self):
        if len(self) == 1:
            self.buy(size=100)
        elif len(self) == 2 and self.position:
            self.close()

    def notify_order(self, order):
        if order.status == order.Completed:
            self.fills.append((bt.num2date(order.executed.dt).date(), order.executed.comm))
        if order.status in (order.Completed, order.Margin):
            self.outcomes.append(order.status)


def run(tmp_path, cash):
    path = tmp_path / 'synthetic.csv'
    with path.open('w', newline='', encoding='ascii') as stream:
        writer = csv.writer(stream)
        writer.writerow(['date', 'open', 'high', 'low', 'close', 'volume', 'oi'])
        for day in ('2023-08-24', '2023-08-25', '2023-08-28'):
            writer.writerow([day, 1000, 1000, 1000, 1000, 100000, 0])
    engine = bt.Cerebro(stdstats=False)
    feed = bt.feeds.GenericCSVData(dataname=str(path), dtformat='%Y-%m-%d')
    engine.adddata(feed, name='stock')
    engine.broker.addcommissioninfo(commission(feed), name='stock')
    engine.broker.setcash(cash)
    engine.broker.set_coc(False)
    engine.addstrategy(RoundTrip)
    return engine.run()[0]


def test_friday_sell_signal_uses_monday_fill_tax_not_signal_tax(tmp_path):
    strategy = run(tmp_path, 200000)
    assert strategy.fills == [(date(2023, 8, 25), 31.0), (date(2023, 8, 28), 81.0)]
    assert strategy.broker.getcash() == pytest.approx(199888)
    assert strategy.broker.getvalue() == pytest.approx(199888)


def test_commission_is_included_in_buy_affordability(tmp_path):
    strategy = run(tmp_path, 100030)
    assert not strategy.fills
    assert bt.Order.Margin in strategy.outcomes
    assert strategy.broker.getcash() == 100030


def test_estimates_do_not_multiply_charges_or_change_scenario():
    c = commission()
    assert c.getcommission(100, 10) == pytest.approx(5.01)
    assert c.getcommission(100, 10) == c.confirmexec(100, 10)
    result = c.fee_breakdown(-100, 10)
    assert result['stamp_duty_unrounded_cny'] == Decimal('0.5')
    assert result['total_unrounded_cny'] == Decimal('5.51')
    assert result['scenario_id'] == 'synthetic-unrounded-per-fill-v1'
    assert not result['full_cost_verified']


@pytest.mark.parametrize('overrides', [
    {'commission_rate': 0.0003}, {'commission_rate': Decimal('NaN')},
    {'minimum_commission': Decimal('-1')}, {'scenario_id': ''}, {'exchange': 'BSE'},
])
def test_missing_or_invalid_assumptions_fail(overrides):
    with pytest.raises(ValueError):
        commission(**overrides)


def test_early_shanghai_cannot_silently_omit_legacy_fee():
    feed = SimpleNamespace(datetime=SimpleNamespace(date=lambda _: date(2015, 7, 31)))
    with pytest.raises(ValueError, match='broker-retained'):
        commission(feed).fee_breakdown(100, 10)
