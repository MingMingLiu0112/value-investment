"""Real-bar execution plumbing experiment, NOT a financial strategy backtest."""
import hashlib
import json
import math
from decimal import Decimal
from pathlib import Path

import backtrader as bt
import pandas as pd

from collect_historical_prices import parse_bars
from check_midea_suspensions import PRICES, ROOT
from value_investment_agent.research_commission import DatedResearchCommission


class PendingOrder(bt.Strategy):
    def __init__(self):
        self.submitted = False
        self.visited = []
        self.fills = []

    def next(self):
        day = self.datas[0].datetime.date(0).isoformat()
        stock_day = self.datas[1].datetime.date(0).isoformat()
        self.visited.append({'clock_date': day, 'stock_bar_date': stock_day})
        if day == '2018-09-07' and not self.submitted:
            self.buy(data=self.datas[1], size=100)
            self.submitted = True

    def notify_order(self, order):
        if order.status == order.Completed:
            fill = {'date': bt.num2date(order.executed.dt).date().isoformat(),
                    'price': order.executed.price, 'shares': order.executed.size,
                    'charged_commission': order.executed.comm}
            commission = self.broker.getcommissioninfo(order.data)
            if isinstance(commission, DatedResearchCommission):
                breakdown = commission.fee_breakdown(order.executed.size, order.executed.price)
                if breakdown['traded_on'] != fill['date']:
                    raise ValueError('Fee evidence date differs from execution date')
                fill['fee_breakdown'] = breakdown
            self.fills.append(fill)


def run_case(bars, *, runonce, dated_fees=False):
    engine = bt.Cerebro(stdstats=False)
    for symbol in ('sh600519', 'sz000333'):
        frame = pd.DataFrame(bars[symbol]).set_index('date')
        frame.index = pd.to_datetime(frame.index)
        for field in ('open', 'high', 'low', 'close'):
            frame[field] = frame[field].astype(float)
        feed = bt.feeds.PandasData(dataname=frame, volume=None, openinterest=None)
        engine.adddata(feed, name=symbol)
        if symbol == 'sz000333' and dated_fees:
            engine.broker.addcommissioninfo(DatedResearchCommission(
                feed, 'SZSE', Decimal('0.0003'), Decimal('5'),
                'midea-real-bars-unrounded-per-fill-research-v1'), name=symbol)
    engine.addstrategy(PendingOrder)
    engine.broker.setcash(100000)
    engine.broker.setcommission(commission=0)
    engine.broker.set_coc(False)
    engine.broker.set_coo(False)
    strategy = engine.run(runonce=runonce)[0]
    if not strategy.submitted:
        raise ValueError('Experiment order not submitted')
    return {'runonce': runonce, 'dated_fee_scenario': dated_fees,
            'ending_cash': strategy.broker.getcash(),
            'clock_visits': strategy.visited, 'hypothetical_fills': strategy.fills}


def main():
    ledger_path = ROOT / 'runtime/midea-suspension-reconciliation-20260909.json'
    ledger_raw = ledger_path.read_bytes()
    ledger = json.loads(ledger_raw)
    event = [e for e in ledger['events'] if e['start_date'] == '2018-09-10']
    if len(event) != 1 or event[0]['resume_date'] != '2018-10-29':
        raise ValueError('Reviewed suspension interval mismatch')
    for source in event[0]['sources']:
        if hashlib.sha256((ROOT / source['path']).read_bytes()).hexdigest() != source['sha256']:
            raise ValueError('Suspension original hash mismatch')
    manifest = json.loads((PRICES / 'manifest.json').read_text(encoding='utf-8'))
    bars, sources = {}, []
    for symbol in ('sh600519', 'sz000333'):
        entries = [e for e in manifest['requests'] if e['symbol'] == symbol and e['year'] == 2018]
        if len(entries) != 1:
            raise ValueError('Missing or duplicate price archive')
        entry = entries[0]
        raw = (PRICES / entry['raw_file']).read_bytes()
        if hashlib.sha256(raw).hexdigest() != entry['sha256']:
            raise ValueError('Price archive hash mismatch')
        bars[symbol] = [b for b in parse_bars(raw, symbol, 2018)
                        if '2018-09-07' <= b['date'] <= '2018-10-30']
        sources.append({'symbol': symbol, 'sha256': entry['sha256'], 'url': entry['url']})
    stock = {b['date']: b for b in bars['sz000333']}
    if any('2018-09-10' <= d < '2018-10-29' for d in stock):
        raise ValueError('Daily stock bar conflicts with full-day suspension')
    results = [run_case(bars, runonce=mode, dated_fees=fees)
               for fees in (False, True) for mode in (True, False)]
    for result in results:
        expected = [{'date': '2018-10-29', 'price': float(stock['2018-10-29']['open']), 'shares': 100}]
        actual = [{k: f[k] for k in ('date', 'price', 'shares')} for f in result['hypothetical_fills']]
        if actual != expected:
            raise ValueError('Unexpected fill before resumption or wrong next-bar execution')
        fill = result['hypothetical_fills'][0]
        turnover = Decimal(stock['2018-10-29']['open']) * 100
        expected_fee = (max(turnover * Decimal('0.0003'), Decimal('5'))
                        + turnover * Decimal('0.00002')) if result['dated_fee_scenario'] else Decimal(0)
        if not math.isclose(fill['charged_commission'], float(expected_fee), abs_tol=1e-9):
            raise ValueError('Incorrect historical research charge')
        if not math.isclose(result['ending_cash'], 100000 - float(turnover + expected_fee), abs_tol=1e-8):
            raise ValueError('Cash accounting mismatch')
        visits = {v['clock_date'] for v in result['clock_visits']}
        if not set(event[0]['explained_peer_dates']) <= visits:
            raise ValueError('Clock skipped a reviewed suspension date')
    output = {'experiment': 'Artificial pending order on authentic archived bars',
        'signal_date': '2018-09-07', 'engine_version': bt.__version__,
        'ledger_sha256': hashlib.sha256(ledger_raw).hexdigest(), 'sources': sources,
        'results': results, 'execution_plumbing_passed': True,
        'strategy_validated': False, 'realistic_fill_verified': False,
        'limitations': ['Zero-fee control and explicit unrounded research fee scenario; not personal-account fees',
            'No price-limit or volume participation model; resumption fill is hypothetical',
            'Peer stock clock is not an independently verified exchange calendar',
            'Persistent simulated order is not evidence of broker order validity across sessions',
            'Artificial order is not a valuation signal; no strategy returns are reported']}
    path = ROOT / 'runtime/midea-suspension-engine-replay-20260909.json'
    path.write_text(json.dumps(output, indent=2, default=str), encoding='utf-8')
    print(json.dumps({k: v for k, v in output.items() if k != 'results'}, indent=2))
    print(json.dumps([{'runonce': r['runonce'], 'dated_fees': r['dated_fee_scenario'],
                      'ending_cash': r['ending_cash'], 'visits': len(r['clock_visits']),
                      'fills': r['hypothetical_fills']} for r in results], default=str))


if __name__ == '__main__':
    main()
