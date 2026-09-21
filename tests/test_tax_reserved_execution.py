import csv
from datetime import date
from decimal import Decimal

import backtrader as bt
import pytest

from value_investment_agent.research_broker import ResearchBroker


def run(tmp_path, sizes, *, checksubmit=True, next_price=10, commission=0, sell=False):
    path = tmp_path/'prices.csv'
    with path.open('w', newline='', encoding='ascii') as stream:
        writer = csv.writer(stream)
        writer.writerow(['date', 'open', 'high', 'low', 'close', 'volume', 'oi'])
        for day, price in [('2016-06-01', 10), ('2016-06-02', next_price), ('2016-06-03', next_price)]:
            writer.writerow([day, price, price, price, price, 100000, 0])

    class Strategy(bt.Strategy):
        def __init__(self):
            self.orders = []

        def next(self):
            if len(self) == 1:
                self.broker.accrue_tax('known', Decimal('200'), day=date(2016, 6, 1), evidence_id='fixture')
                for size in sizes:
                    self.orders.append(self.buy(size=size))
            if len(self) == 2 and sell:
                self.broker.accrue_tax('more', Decimal('300'), day=date(2016, 6, 2), evidence_id='fixture')
                self.orders.append(self.close())

    engine = bt.Cerebro(stdstats=False)
    engine.setbroker(ResearchBroker(cash=1000, checksubmit=checksubmit))
    engine.broker.setcommission(commission=commission)
    engine.adddata(bt.feeds.GenericCSVData(dataname=str(path), dtformat='%Y-%m-%d'))
    engine.addstrategy(Strategy)
    return engine.run()[0]


@pytest.mark.parametrize('checksubmit', [True, False])
def test_reserved_tax_blocks_overspend_even_without_submission_check(tmp_path, checksubmit):
    s = run(tmp_path, [90], checksubmit=checksubmit)
    assert s.orders[0].status == bt.Order.Margin
    assert s.position.size == 0
    assert s.broker.getcash() == 1000
    assert s.broker.getvalue() == 800
    assert s.broker.spendable_cash() == 800


def test_sequential_orders_do_not_each_get_full_cash(tmp_path):
    s = run(tmp_path, [40, 50])
    assert [o.status for o in s.orders] == [bt.Order.Completed, bt.Order.Margin]
    assert s.position.size == 40
    assert s.broker.getcash() == 600
    assert s.broker.getvalue() == 800


def test_next_open_rechecks_reserved_cash(tmp_path):
    s = run(tmp_path, [60], next_price=15)
    assert s.orders[0].status == bt.Order.Margin
    assert s.position.size == 0
    assert s.broker.getcash() == 1000


def test_commission_cannot_spend_tax_reserve(tmp_path):
    s = run(tmp_path, [80], commission=0.001)
    assert s.orders[0].status == bt.Order.Margin


def test_tax_shortfall_does_not_prevent_selling_existing_stock(tmp_path):
    s = run(tmp_path, [80], sell=True)
    assert all(o.status == bt.Order.Completed for o in s.orders)
    assert s.position.size == 0
    assert s.broker.getcash() == 1000
    assert s.broker.getvalue() == 500
    assert s.broker.spendable_cash() == 500
