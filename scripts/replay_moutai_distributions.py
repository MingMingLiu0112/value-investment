"""Replay real 2015-2025 bars and distributions against a declared opening holding.

Gross entitlement accounting only: no executed entry, dividend tax, strategy
return or economic approval. Reuses the project Backtrader broker components.
"""
import argparse
import csv
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import sys

import backtrader as bt
import pandas as pd

from value_investment_agent.corporate_actions import validate_cash_distribution
from value_investment_agent.distribution_entitlements import DistributionEntitlements
from value_investment_agent.share_action_broker import ShareActionResearchBroker


VERSION = 'moutai-gross-distribution-replay-v2-with-annual-warmup'
PRICE_DIR = 'runtime/historical-prices/20260908T061418761988Z'
ANNUAL_DIR = 'runtime/strategy-validation/moutai-warmup-20260909T062823719664Z'
ANNUAL_HASH = '41f7d1fb196adc6840ea43bb58ddf57a38116334410a4ee61b589ac4bfc231fc'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2,
                               default=str), encoding='utf-8')


def load_inputs(root):
    sys.path.insert(0, str(root / 'scripts'))
    from collect_historical_prices import parse_bars
    price_root = root / PRICE_DIR
    manifest = json.loads((price_root / 'manifest.json').read_text(encoding='utf-8'))
    references, bars = [], []
    for year in range(2015, 2026):
        entries = [r for r in manifest['requests'] if r['symbol'] == 'sh600519' and r['year'] == year]
        if len(entries) != 1:
            raise ValueError('Missing or duplicate annual price response')
        entry = entries[0]
        path = (price_root / entry['raw_file']).resolve()
        if not path.is_relative_to(price_root.resolve()) or digest(path) != entry['sha256']:
            raise ValueError('Price evidence path/hash mismatch')
        bars.extend(parse_bars(path.read_bytes(), 'sh600519', year))
        references.append({'kind': 'prices', 'path': str(path.relative_to(root)),
                           'sha256': entry['sha256'], 'url': entry['url']})
    dates = [b['date'] for b in bars]
    if dates != sorted(set(dates)):
        raise ValueError('Unordered or duplicate historical price dates')
    event_path = root / 'docs/reviewed-cash-distributions.json'
    events = sorted([e for e in json.loads(event_path.read_text(encoding='utf-8'))['events']
                     if e['symbol'] == '600519'], key=lambda e: e['record_date'])
    if len(events) != 15 or len({e['record_date'] for e in events}) != len(events):
        raise ValueError('Reviewed distribution inventory changed; reconcile before replay')
    for event in events:
        validate_cash_distribution(event)
        required = [event[k] for k in ('record_date', 'ex_date', 'cash_payment_date')]
        if event.get('bonus_shares_per_share'):
            required.append(event['bonus_listing_date'])
        if not set(required) <= set(dates):
            raise ValueError('Price clock misses a distribution date; never defer accounting')
        for source in event['evidence']:
            path = (root / source['path']).resolve()
            if not path.is_relative_to(root) or digest(path) != source['sha256']:
                raise ValueError('Distribution original path/hash mismatch')
            references.append({'kind': 'distribution', **source})
    annual_path = root / ANNUAL_DIR / 'annual-inputs.json'
    if digest(annual_path) != ANNUAL_HASH:
        raise ValueError('Reviewed annual input package changed')
    annual = json.loads(annual_path.read_text(encoding='utf-8'))
    for row in annual:
        path = (root / row['source_path']).resolve()
        if not path.is_relative_to(root) or digest(path) != row['raw_file_hash']:
            raise ValueError('Annual original changed')
    references.extend([{'kind': 'reviewed_event_registry', 'path': str(event_path.relative_to(root)),
                        'sha256': digest(event_path)},
                       {'kind': 'annual_inputs', 'path': str(annual_path.relative_to(root)), 'sha256': ANNUAL_HASH}])
    return bars, events, annual, references


class EntitlementReplay(bt.Strategy):
    params = (('events', None), ('annual', None), ('opening_shares', 100))

    def __init__(self):
        self.entitlements = DistributionEntitlements()
        self.rows, self.cash_events = [], []
        self.initialized = False

    def next(self):
        from build_moutai_annual_inputs import select_original_vintage
        day = self.data.datetime.date(0)
        if not self.initialized:
            # Declared opening inventory, not a buy filled at the first close.
            self.position.fix(self.p.opening_shares, self.data.close[0])
            self.broker._get_value()
            self.initialized = True
        for event in self.p.events:
            event_id = '600519:' + event['record_date']
            if day.isoformat() == event['record_date']:
                self.entitlements.record_close(event_id, event, day, self.position.size)
                if event.get('bonus_shares_per_share'):
                    self.broker.record_share_distribution(event_id, self.data, self.data, {
                        'record_date': event['record_date'], 'ex_date': event['ex_date'],
                        'listing_date': event['bonus_listing_date'],
                        'shares_per_share': event['bonus_shares_per_share'], 'evidence': event['evidence']})
            if day.isoformat() == event['ex_date']:
                self.entitlements.accrue(event_id, day, self.broker)
            if day.isoformat() == event['cash_payment_date']:
                self.entitlements.pay(event_id, day, self.broker)
                snap = self.entitlements.snapshots[event_id]
                self.cash_events.append({'event_id': event_id, 'record_date': event['record_date'],
                    'ex_date': event['ex_date'], 'payment_date': day.isoformat(),
                    'record_shares': snap['shares'], 'gross_cash': str(snap['gross_amount']),
                    'cash_per_share': event['cash_per_share'],
                    'ex_reference_cash_per_share': event.get('ex_reference_cash_per_share'),
                    'originals': event['evidence']})
        vintage = select_original_vintage(self.p.annual, day.isoformat() + 'T15:00:00+08:00')
        self.rows.append({'date': day.isoformat(), 'close': self.data.close[0],
            'shares': self.position.size, 'sellable_shares': self.broker.sellable_shares(self.data),
            'cash_gross': self.broker.getcash(),
            'receivable_gross': float(sum(self.broker.receivables.values(), Decimal(0))),
            'marked_equity_gross': self.broker.getvalue(),
            'annual_original_source_id': vintage[0]['source_id'] if vintage else None,
            'trade_value_approved': False})


def verify_accounting(rows, payments, bars, events, opening_shares, opening_cash):
    """Independent Decimal ledger; does not call broker entitlement methods."""
    shares = opening_shares
    cash = Decimal(str(opening_cash))
    receivable = Decimal(0)
    snapshots, pending, expected_payments = {}, {}, []
    if len(rows) != len(bars):
        raise ValueError('Replay omitted historical bars')
    for row, bar in zip(rows, bars):
        day = bar['date']
        if row['date'] != day:
            raise ValueError('Replay date mismatch')
        for event in events:
            key = event['record_date']
            if day == event['ex_date']:
                amount = Decimal(event['cash_amount']) / Decimal(event['per_shares']) * snapshots[key]
                receivable += amount
                if event.get('bonus_shares_per_share'):
                    added = Decimal(snapshots[key]) * Decimal(event['bonus_shares_per_share'])
                    if added != added.to_integral_value():
                        raise ValueError('Fractional entitlement unsupported')
                    shares += int(added)
                    pending[key] = (int(added), event['bonus_listing_date'])
            if day == event['cash_payment_date']:
                amount = Decimal(event['cash_amount']) / Decimal(event['per_shares']) * snapshots[key]
                cash += amount
                receivable -= amount
                expected_payments.append((key, str(amount), snapshots[key]))
            if day == event['record_date']:
                snapshots[key] = shares
        locked = sum(n for n, release in pending.values() if day < release)
        if (row['shares'], row['sellable_shares']) != (shares, shares - locked):
            raise ValueError('Share credit or listing lock mismatch')
        equity = cash + receivable + Decimal(bar['close']) * shares
        for name, expected in [('cash_gross', cash), ('receivable_gross', receivable),
                               ('marked_equity_gross', equity)]:
            if not math.isclose(row[name], float(expected), rel_tol=0, abs_tol=1e-7):
                raise ValueError(f'{day}: independent {name} mismatch')
    actual_payments = [(p['record_date'], p['gross_cash'], p['record_shares']) for p in payments]
    if [(k, Decimal(v), n) for k, v, n in actual_payments] != [(k, Decimal(v), n) for k, v, n in expected_payments]:
        raise ValueError('Dividend account differs from actual cash entitlement')
    return {'checked_daily_rows': len(rows), 'checked_distributions': len(payments),
            'ending_shares': shares, 'gross_distributions_cny': str(cash - Decimal(str(opening_cash)))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    out = args.output or root / 'runtime/strategy-validation' / ('moutai-distributions-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(parents=True, exist_ok=False)
    config = {'version': VERSION, 'registered_at': datetime.now(timezone.utc).isoformat(),
              'opening_shares': 100, 'opening_cash_cny': '10000',
              'opening_basis': 'Declared inventory on first archived bar, not an executed purchase',
              'window': ['2015-01-01', '2025-12-31'], 'entry_exit_trades': False,
              'purpose': 'Full archived-window gross entitlement and share-lock reconciliation',
              'dividend_reinvestment': False, 'dividend_tax': 'not_modelled_not_assumed_exempt'}
    write_json(out / 'config.json', config)
    try:
        bars, events, annual, references = load_inputs(root)
        frame = pd.DataFrame(bars).set_index('date')
        frame.index = pd.to_datetime(frame.index)
        for field in ('open', 'close', 'high', 'low'):
            frame[field] = frame[field].astype(float)
        engine = bt.Cerebro(stdstats=False)
        engine.setbroker(ShareActionResearchBroker())
        engine.broker.setcash(float(config['opening_cash_cny']))
        engine.adddata(bt.feeds.PandasData(dataname=frame, volume=None, openinterest=None))
        engine.addstrategy(EntitlementReplay, events=events, annual=annual, opening_shares=config['opening_shares'])
        strategy = engine.run(runonce=False)[0]
        checks = verify_accounting(strategy.rows, strategy.cash_events, bars, events,
                                   config['opening_shares'], config['opening_cash_cny'])
        with (out / 'daily-accounting.csv').open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(strategy.rows[0]))
            writer.writeheader()
            writer.writerows(strategy.rows)
        write_json(out / 'cash-events.json', strategy.cash_events)
        write_json(out / 'input-references.json', references)
        result = {'run_id': out.name, 'version': VERSION, 'engine_version': bt.__version__,
                  'status': 'gross_entitlement_replay_reconciled', **checks,
                  'first_bar': bars[0]['date'], 'last_bar': bars[-1]['date'],
                  'annual_vintages_seen': len({r['annual_original_source_id'] for r in strategy.rows if r['annual_original_source_id']}),
                  'days_without_available_annual_original': sum(not r['annual_original_source_id'] for r in strategy.rows),
                  'strategy_backtest_complete': False, 'economic_evidence': 'not_evaluated',
                  'limitations': ['Opening inventory is assumed; no acquisition date or trade execution',
                      'Gross cash only; dividend tax and investor cost basis unresolved',
                      'No certification of complete corporate actions or official calendar/price truth',
                      'Annual reference identity is attached but daily tradable valuation not approved',
                      'No investment return, benchmark advantage, or strategy admission claimed'],
                  'script_sha256': digest(Path(__file__)),
                  'dependencies': {name: digest(root / 'src/value_investment_agent' / name) for name in
                      ['research_broker.py', 'share_action_broker.py', 'distribution_entitlements.py', 'corporate_actions.py', 'historical_asof.py']},
                  'input_scripts': {name: digest(root / 'scripts' / name) for name in
                      ['collect_historical_prices.py', 'build_moutai_annual_inputs.py']}}
        write_json(out / 'result.json', result)
        write_json(out / 'manifest.json', {'outputs': {p.name: digest(p) for p in out.iterdir() if p.is_file()}})
        print(json.dumps({'output': str(out), **result}, ensure_ascii=True))
    except Exception as exc:
        write_json(out / 'failure.json', {'type': type(exc).__name__, 'error': str(exc)})
        raise


if __name__ == '__main__':
    main()
