"""Find peer-date gaps, without interpreting missing bars as suspensions."""
import argparse
import hashlib
import json
from pathlib import Path

from collect_historical_prices import parse_bars


def audit(directory):
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    dates = {}
    evidence = []
    for entry in manifest['requests']:
        raw = (directory / entry['raw_file']).read_bytes()
        if hashlib.sha256(raw).hexdigest() != entry['sha256']:
            raise ValueError('Raw evidence hash mismatch')
        bars = parse_bars(raw, entry['symbol'], entry['year'])
        bucket = dates.setdefault(entry['symbol'], set())
        incoming = {r['date'] for r in bars}
        if bucket & incoming:
            raise ValueError('Overlapping annual requests')
        bucket.update(incoming)
        evidence.append(entry['sha256'])
    union = sorted(set().union(*dates.values()))
    companies = []
    for symbol, actual in sorted(dates.items()):
        gaps = []
        active = []
        for day in union:
            if day not in actual:
                active.append(day)
            elif active:
                gaps.append(active)
                active = []
        if active:
            gaps.append(active)
        companies.append({'symbol': symbol, 'observed_dates': len(actual),
            'unexplained_peer_dates': sum(map(len, gaps)),
            'gap_runs': [{'start': g[0], 'end': g[-1], 'dates': g,
                          'status': 'unexplained_not_verified_suspension'} for g in gaps]})
    return {'reference': 'Union of three secondary-provider series, not exchange calendar',
            'common_missing_dates_detectable': False, 'backtest_ready': False,
            'raw_sha256': evidence, 'union_dates': len(union), 'companies': companies}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    report = audit(args.directory)
    (args.directory / 'peer-date-audit.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    for company in report['companies']:
        print(json.dumps(company), flush=True)
