"""Synthetic engine contract tests, not A-share performance validation."""
import csv
from datetime import date

import pytest

bt = pytest.importorskip('backtrader')


class OneOrder(bt.Strategy):
    params = (('size', 100),)

    def __init__(self):
        self.executions = []
        self.outcomes = []

    def next(self):
        if len(self) == 1:
            self.buy(size=self.p.size)

    def notify_order(self, order):
        if order.status == order.Completed:
            self.executions.append({
                'date': bt.num2date(order.executed.dt).date(),
                'price': order.executed.price,
                'commission': order.executed.comm,
            })
        if order.status in (order.Completed, order.Margin, order.Rejected):
            self.outcomes.append(order.status)


def run_engine(tmp_path, cash, size=100):
    path = tmp_path / 'synthetic.csv'
    with path.open('w', newline='', encoding='ascii') as stream:
        writer = csv.writer(stream)
        writer.writerow(['date', 'open', 'high', 'low', 'close', 'volume', 'oi'])
        writer.writerows([
            ['2020-01-02', 10, 11, 9, 10, 100000, 0],
            ['2020-01-03', 12, 13, 11, 12, 100000, 0],
            ['2020-01-06', 13, 14, 12, 13, 100000, 0],
        ])
    engine = bt.Cerebro(stdstats=False)
    engine.adddata(bt.feeds.GenericCSVData(dataname=str(path), dtformat='%Y-%m-%d'))
    engine.addstrategy(OneOrder, size=size)
    engine.broker.setcash(cash)
    # Synthetic proportional fee only, not a historical Chinese fee schedule.
    engine.broker.setcommission(commission=0.001)
    engine.broker.set_coc(False)
    return engine.run()[0]


def test_signal_cannot_fill_on_same_close(tmp_path):
    strategy = run_engine(tmp_path, 10000)
    assert strategy.executions == [{
        'date': date(2020, 1, 3), 'price': 12.0, 'commission': pytest.approx(1.2),
    }]
    assert strategy.broker.getcash() == pytest.approx(8798.8)
    assert strategy.broker.getvalue() == pytest.approx(10098.8)


def test_next_open_gap_rejects_order_without_enough_cash(tmp_path):
    strategy = run_engine(tmp_path, 1100)
    assert strategy.executions == []
    assert bt.Order.Margin in strategy.outcomes
    assert strategy.broker.getcash() == 1100


class SuspensionClock(bt.Strategy):
    def __init__(self):
        self.events = []
        self.fills = []

    def next(self):
        clock_day = self.datas[0].datetime.date(0)
        stock_day = self.datas[1].datetime.date(0)
        if clock_day == date(2017, 7, 7):
            self.events.append(('record_date', clock_day, stock_day))
            self.buy(data=self.datas[1], size=100)
        if clock_day == date(2017, 7, 10):
            self.events.append(('payment_date', clock_day, stock_day))

    def notify_order(self, order):
        if order.status == order.Completed:
            self.fills.append((bt.num2date(order.executed.dt).date(), order.executed.price))


@pytest.mark.parametrize('runonce', [True, False])
def test_independent_clock_visits_suspended_event_dates_without_fake_fills(tmp_path, runonce):
    # Synthetic prices and sparse clock; dates reproduce the reviewed Shenhua case.
    clock_dates = ['2017-06-02', '2017-07-07', '2017-07-10', '2017-09-01', '2017-09-04']
    stock_dates = ['2017-06-02', '2017-09-01', '2017-09-04']
    engine = bt.Cerebro(stdstats=False)
    for name, days in [('clock', clock_dates), ('stock', stock_dates)]:
        path = tmp_path / (name + '.csv')
        with path.open('w', newline='', encoding='ascii') as stream:
            writer = csv.writer(stream)
            writer.writerow(['date', 'open', 'high', 'low', 'close', 'volume', 'oi'])
            for day in days:
                price = 20 if day < '2017-09-01' else 18
                writer.writerow([day, price, price, price, price, 100000, 0])
        engine.adddata(bt.feeds.GenericCSVData(dataname=str(path), dtformat='%Y-%m-%d'), name=name)
    engine.addstrategy(SuspensionClock)
    engine.broker.setcash(10000)
    engine.broker.set_coc(False)
    strategy = engine.run(runonce=runonce)[0]
    assert strategy.events == [
        ('record_date', date(2017, 7, 7), date(2017, 6, 2)),
        ('payment_date', date(2017, 7, 10), date(2017, 6, 2)),
    ]
    assert strategy.fills == [(date(2017, 9, 1), 18.0)]
    assert strategy.broker.getcash() == pytest.approx(8200)
