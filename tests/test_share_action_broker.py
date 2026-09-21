"""Synthetic prices with the reviewed 2015 Moutai action date pattern."""
import csv
from datetime import date
from types import SimpleNamespace

import pytest

bt = pytest.importorskip('backtrader')
from value_investment_agent.share_action_broker import ShareActionResearchBroker


EVENT = {'symbol': 'TEST', 'record_date': '2015-07-16', 'ex_date': '2015-07-17',
         'listing_date': '2015-07-20', 'shares_per_share': '0.1',
         'evidence': [{'synthetic_test_fixture': True}]}


class ShareStrategy(bt.Strategy):
    params = (('first_sale', 110),)

    def __init__(self):
        self.fills = []
        self.rejected = []
        self.ex_state = None

    def next(self):
        day = self.data.datetime.date(0)
        if day == date(2015, 7, 14):
            self.buy(size=100)
        if day == date(2015, 7, 16):
            self.broker.record_share_distribution('action', self.data, self.data, EVENT)
            self.sell(size=self.p.first_sale)
        if day == date(2015, 7, 17):
            self.ex_state = (self.position.size, self.broker.sellable_shares(self.data),
                             self.broker.getvalue(), self.broker.fundshares)
            self.close()

    def notify_order(self, order):
        if order.status == order.Completed:
            self.fills.append((bt.num2date(order.executed.dt).date(), order.executed.size))
        if order.status == order.Rejected:
            self.rejected.append(order.info.rejection_reason)


@pytest.mark.parametrize('first_sale', [100, 110])
def test_ex_date_value_and_listing_day_sale_lock(tmp_path, first_sale):
    path = tmp_path / 'synthetic.csv'
    with path.open('w', newline='', encoding='ascii') as stream:
        writer = csv.writer(stream)
        writer.writerow(['date', 'open', 'high', 'low', 'close', 'volume', 'oi'])
        for day in ('2015-07-14', '2015-07-15', '2015-07-16', '2015-07-17', '2015-07-20'):
            price = 100 if day < '2015-07-17' else 100 / 1.1
            writer.writerow([day, price, price, price, price, 100000, 0])
    engine = bt.Cerebro(stdstats=False)
    engine.setbroker(ShareActionResearchBroker())
    engine.broker.setcash(20000)
    engine.broker.set_coc(False)
    engine.adddata(bt.feeds.GenericCSVData(dataname=str(path), dtformat='%Y-%m-%d'))
    engine.addstrategy(ShareStrategy, first_sale=first_sale)
    strategy = engine.run()[0]
    assert strategy.ex_state[2] == pytest.approx(20000)
    assert strategy.ex_state[3] == 200
    assert strategy.broker.getvalue() == pytest.approx(20000)
    assert strategy.broker.getcash() == pytest.approx(20000)
    if first_sale == 110:
        assert len(strategy.rejected) == 1
        assert strategy.ex_state[:2] == (110, 100)
        assert strategy.fills == [(date(2015, 7, 15), 100), (date(2015, 7, 20), -110)]
    else:
        assert not strategy.rejected
        assert strategy.ex_state[:2] == (10, 0)
        assert strategy.fills == [(date(2015, 7, 15), 100), (date(2015, 7, 17), -100),
                                  (date(2015, 7, 20), -10)]


def test_fractional_entitlement_rejected_without_inventing_allocation():
    broker = ShareActionResearchBroker()
    broker.start()
    data = object()
    broker.getposition(data).fix(101, 100)
    clock = SimpleNamespace(datetime=SimpleNamespace(date=lambda _: date(2015, 7, 16)))
    with pytest.raises(ValueError, match='Fractional'):
        broker.record_share_distribution('action', data, clock, EVENT)
    assert not broker.share_events
    assert broker.getposition(data).size == 101


def test_duplicate_record_does_not_double_credit_and_conflict_rejects():
    broker = ShareActionResearchBroker()
    broker.start()
    data = object()
    broker.getposition(data).fix(100, 100)
    clock = SimpleNamespace(datetime=SimpleNamespace(date=lambda _: date(2015, 7, 16)))
    assert broker.record_share_distribution('action', data, clock, EVENT)
    assert not broker.record_share_distribution('action', data, clock, EVENT)
    with pytest.raises(ValueError):
        broker.record_share_distribution('action', data, clock, {**EVENT, 'shares_per_share': '0.5'})


def test_suspended_ex_date_never_values_added_shares_at_stale_price():
    broker = ShareActionResearchBroker()
    broker.start()
    data = bt.feeds.GenericCSVData(dataname='unused.csv')
    data.datetime.date = lambda _: date(2015, 7, 16)
    broker.getposition(data).fix(100, 100)
    day = [date(2015, 7, 16)]
    clock = SimpleNamespace(datetime=SimpleNamespace(date=lambda _: day[0]))
    broker.record_share_distribution('action', data, clock, EVENT)
    day[0] = date(2015, 7, 17)
    with pytest.raises(ValueError, match='stale price'):
        broker.next()
    assert broker.getposition(data).size == 100
    assert not broker.share_events['action']['credited']


def test_missing_event_date_is_not_silently_deferred_to_reopening():
    broker = ShareActionResearchBroker()
    broker.start()
    data = object()
    broker.getposition(data).fix(100, 100)
    day = [date(2015, 7, 16)]
    clock = SimpleNamespace(datetime=SimpleNamespace(date=lambda _: day[0]))
    broker.record_share_distribution('action', data, clock, EVENT)
    day[0] = date(2015, 7, 20)
    with pytest.raises(ValueError, match='skipped'):
        broker.next()
    assert broker.getposition(data).size == 100
