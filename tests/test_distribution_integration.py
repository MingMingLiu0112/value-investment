"""Synthetic executed-position tests, not historical investment returns."""
import csv
from datetime import date

import pytest

bt = pytest.importorskip('backtrader')
from value_investment_agent.distribution_entitlements import DistributionEntitlements
from value_investment_agent.research_broker import ResearchBroker


EVENT = {'symbol': 'TEST', 'record_date': '2021-06-01', 'ex_date': '2021-06-02',
         'cash_payment_date': '2021-06-03', 'cash_amount': '1', 'per_shares': '1',
         'cash_per_share': '1', 'amount_basis': 'implemented_gross_entitlement',
         'evidence': [{'synthetic': True}]}


class DistributionStrategy(bt.Strategy):
    params = (('late_buyer', False),)

    def __init__(self):
        self.entitlements = DistributionEntitlements()
        self.fills = []
        self.payment_position = None
        self.ex_date_value = None
        self.ex_date_cash = None

    def next(self):
        day = self.data.datetime.date(0)
        if day == date(2021, 5, 28) and not self.p.late_buyer:
            self.buy(size=100)
        if day == date(2021, 6, 1):
            # Default next() is after this bar's broker processing, at bar close.
            self.entitlements.record_close('event', EVENT, day, self.position.size)
            if self.p.late_buyer:
                self.buy(size=100)
            else:
                self.close()
        if day == date(2021, 6, 2):
            self.entitlements.accrue('event', day, self.broker)
            self.ex_date_value = self.broker.getvalue()
            self.ex_date_cash = self.broker.getcash()
        if day == date(2021, 6, 3):
            self.payment_position = self.position.size
            self.entitlements.pay('event', day, self.broker)

    def notify_order(self, order):
        if order.status == order.Completed:
            self.fills.append((bt.num2date(order.executed.dt).date(), order.executed.size))


@pytest.mark.parametrize('late_buyer', [False, True])
def test_actual_execution_positions_drive_record_date_entitlement(tmp_path, late_buyer):
    path = tmp_path / 'bars.csv'
    with path.open('w', newline='', encoding='ascii') as stream:
        writer = csv.writer(stream)
        writer.writerow(['date', 'open', 'high', 'low', 'close', 'volume', 'oi'])
        for day in ('2021-05-28', '2021-05-31', '2021-06-01', '2021-06-02', '2021-06-03', '2021-06-04'):
            price = 10 if day < '2021-06-02' else 9
            writer.writerow([day, price, price, price, price, 100000, 0])
    engine = bt.Cerebro(stdstats=False)
    engine.setbroker(ResearchBroker())
    engine.broker.setcash(10000)
    engine.broker.set_coc(False)
    engine.adddata(bt.feeds.GenericCSVData(dataname=str(path), dtformat='%Y-%m-%d'))
    engine.addstrategy(DistributionStrategy, late_buyer=late_buyer)
    strategy = engine.run()[0]
    if late_buyer:
        assert strategy.fills == [(date(2021, 6, 2), 100)]
        assert strategy.payment_position == 100
        assert strategy.broker.income_events['event'] == 0
        assert strategy.broker.getcash() == pytest.approx(9100)
    else:
        assert strategy.fills == [(date(2021, 5, 31), 100), (date(2021, 6, 2), -100)]
        assert strategy.payment_position == 0
        assert strategy.broker.income_events['event'] == 100
        assert strategy.broker.getcash() == pytest.approx(10000)
    assert strategy.broker.fundshares == 100
    assert strategy.ex_date_value == pytest.approx(10000)
    assert strategy.ex_date_cash == pytest.approx(9100 if late_buyer else 9900)
    assert strategy.broker.getvalue() == pytest.approx(10000)
