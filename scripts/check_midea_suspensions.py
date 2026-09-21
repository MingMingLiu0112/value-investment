"""Reconcile reviewed original suspension notices with archived peer-date gaps."""
import hashlib
import json
from pathlib import Path

from collect_historical_prices import parse_bars

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / 'runtime/historical-filing-index/20260908T161018674043Z/pdfs'
PRICES = ROOT / 'runtime/historical-prices/20260908T061418761988Z'
# Dates are manually reviewed disclosure facts, not inferred from missing bars.
EVENTS = [
    ('2015-03-26', '2015-03-31', '1200767576', '183d584cd425e0d2c1890cf769a0abcba734fb19110b68adf90f2e944253950e'),
    ('2016-05-18', '2016-06-01', '1202347979', 'f0cd87aea743c3bb1a2fcff6286f732e91bd5f99811725a5c2d2bd79ad6f0179'),
    ('2018-09-10', '2018-10-29', '1205546211', '1598465ac494fb404a5148abf6a791ebb08a5e6b6134d3818d2569d791c03242'),
    ('2019-02-20', '2019-02-21', '1205843694', '56847b1f54466c182fc23165d804468090450d4efdbe5133749fa55b555dacc4'),
    ('2019-05-08', '2019-05-22', '1206287791', '4ce5d89ddefaf19dba73e5898c31913aa1e001e4e6418888387f3dd6aa76dfa3'),
]


def evidence(path, digest, publication_date, ident):
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError('Original notice hash mismatch: ' + ident)
    return {'path': str(path.relative_to(ROOT)), 'sha256': digest,
            'url': f'https://static.cninfo.com.cn/finalpage/{publication_date}/{ident}.PDF',
            'page': 1, 'publication_date': publication_date}


def reconcile(dates, events):
    observed = dates['sz000333']
    peers = set().union(*dates.values())
    explained = set()
    rows = []
    for event in events:
        start, end = event['start_date'], event['resume_date']
        if start >= end:
            raise ValueError('Invalid suspension interval')
        if any(start <= day < end for day in observed):
            raise ValueError('Observed daily bar conflicts with full-day suspension')
        if end not in observed:
            raise ValueError('Resumption-day bar missing')
        missing = {d for d in peers - observed if start <= d < end}
        if missing & explained:
            raise ValueError('Overlapping evidence intervals')
        explained.update(missing)
        rows.append({**event, 'explained_peer_dates': sorted(missing)})
    return {'events': rows, 'explained_peer_date_count': len(explained),
            'unexplained_peer_dates': sorted(peers - observed - explained),
            'complete_exchange_calendar_verified': False, 'backtest_ready': False}


def main():
    events = []
    for start, end, ident, digest in EVENTS:
        source = evidence(ARCHIVE / f'000333-{ident}.pdf', digest, end, ident)
        sources = [source]
        if start == '2019-02-20':
            sources.append(evidence(ROOT / 'runtime/historical-filing-index/20260908T161158616568Z/pdfs/000333-1205842051.pdf',
                'd75a48e0f5ba1ca7ff5e2b31adab1f28562b5d336b79c4367c42f1f661007135', start, '1205842051'))
        events.append({'symbol': '000333', 'start_date': start, 'start_session': 'morning_open',
            'resume_date': end, 'resume_session': 'morning_open', 'sources': sources,
            'use': 'retrospective_execution_constraint_not_signal_input'})
    dates = {}
    manifest = json.loads((PRICES / 'manifest.json').read_text(encoding='utf-8'))
    for entry in manifest['requests']:
        raw = (PRICES / entry['raw_file']).read_bytes()
        if hashlib.sha256(raw).hexdigest() != entry['sha256']:
            raise ValueError('Price evidence hash mismatch')
        incoming = {b['date'] for b in parse_bars(raw, entry['symbol'], entry['year'])}
        bucket = dates.setdefault(entry['symbol'], set())
        if bucket & incoming:
            raise ValueError('Overlapping price windows')
        bucket.update(incoming)
    result = reconcile(dates, events)
    partial = evidence(ARCHIVE / '000333-1202372209.pdf',
        'b062b6285ae31b52ee53b1855ac25766866b06debaaa356e30d450d84208c37b', '2016-06-17', '1202372209')
    result['partial_session_suspensions'] = [{'start_date': '2016-06-16',
        'start_session': 'afternoon_open', 'resume_date': '2016-06-17',
        'resume_session': 'morning_open', 'source': partial,
        'daily_bar_present': '2016-06-16' in dates['sz000333'],
        'intraday_execution_verified': False}]
    result['limitations'] = ['Peer union cannot detect common missing trading dates',
        'No engine input ledger has been approved',
        'Disclosure contents must not be backfilled into earlier strategy information',
        'Daily bars do not establish full-session executability']
    output = ROOT / 'runtime/midea-suspension-reconciliation-20260909.json'
    output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
