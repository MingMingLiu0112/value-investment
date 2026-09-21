"""Archive secondary unadjusted daily bars; never declare backtest readiness."""
import argparse
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path

import requests

URL = 'https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get'
SYMBOLS = ('sh600519', 'sz000333', 'sh601088')


def parse_bars(raw, symbol, year):
    payload = json.loads(raw)
    if payload.get('code') != 0:
        raise ValueError('Provider error')
    rows = payload['data'][symbol]['day']
    if not rows or (len(rows) >= 640 and date.fromisoformat(rows[0][0]) >= date(year, 1, 1)):
        raise ValueError('Empty or potentially truncated response')
    result = []
    previous = None
    for row in rows:
        day = date.fromisoformat(row[0])
        if previous is not None and day <= previous:
            raise ValueError('Duplicate or unordered trading date')
        previous = day
        values = [Decimal(str(v)) for v in row[1:6]]
        if any(not v.is_finite() for v in values):
            raise ValueError('Nonfinite bar')
        opening, close, high, low, volume = values
        if not (0 < low <= min(opening, close) <= max(opening, close) <= high) or volume < 0:
            raise ValueError('Invalid OHLC or volume')
        if day.year == year:
            result.append(dict(zip(('date', 'open', 'close', 'high', 'low', 'volume_raw'),
                                   [day.isoformat(), *map(str, values)])))
    if not result:
        raise ValueError('Requested year absent')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start-year', type=int, default=2015)
    parser.add_argument('--end-year', type=int, default=2025)
    parser.add_argument('--replay', type=Path)
    args = parser.parse_args()
    if args.replay:
        manifest = json.loads((args.replay / 'manifest.json').read_text(encoding='utf-8'))
        results = []
        for entry in manifest['requests']:
            result = {'symbol': entry['symbol'], 'year': entry['year']}
            try:
                raw = (args.replay / entry['raw_file']).read_bytes()
                if hashlib.sha256(raw).hexdigest() != entry['sha256']:
                    raise ValueError('Raw evidence hash mismatch')
                bars = parse_bars(raw, entry['symbol'], entry['year'])
                name = f"{entry['symbol']}-{entry['year']}-bars-v2.json"
                (args.replay / name).write_text(json.dumps(bars, indent=2), encoding='utf-8')
                result.update(status='structurally_valid_unverified', rows=len(bars),
                              first_date=bars[0]['date'], last_date=bars[-1]['date'],
                              raw_sha256=entry['sha256'], bars_file=name)
            except (ValueError, KeyError, TypeError, IndexError) as exc:
                result.update(status='failed', error=str(exc))
            results.append(result)
        report = {'parser_version': 'tencent-unadjusted-v2-window-check',
                  'backtest_ready': False, 'cross_verified': False, 'results': results}
        (args.replay / 'replay-v2.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report, indent=2))
        return int(any(r['status'] == 'failed' for r in results))
    if not 2014 <= args.start_year <= args.end_year <= 2025:
        parser.error('Research window is 2014 through 2025')
    root = Path('runtime/historical-prices') / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    root.mkdir(parents=True, exist_ok=False)
    manifest = {'provider': 'Tencent secondary market data', 'adjustment': 'unadjusted',
                'backtest_ready': False, 'cross_verified': False,
                'limitations': ['Trading calendar gaps unaudited', 'Corporate actions missing',
                                'Volume units unverified', 'Historical revisions unaudited'], 'requests': []}
    with requests.Session() as session:
        session.trust_env = False
        for symbol in SYMBOLS:
            for year in range(args.start_year, args.end_year + 1):
                entry = {'symbol': symbol, 'year': year}
                try:
                    response = session.get(URL, params={'param': f'{symbol},day,{year}-01-01,{year}-12-31,640,'},
                                           timeout=(10, 25))
                    raw = response.content
                    digest = hashlib.sha256(raw).hexdigest()
                    name = f'{symbol}-{year}-{digest}.json'
                    (root / name).write_bytes(raw)
                    entry.update(url=response.url, fetched_at=datetime.now(timezone.utc).isoformat(),
                                 sha256=digest, raw_file=name, http_status=response.status_code)
                    response.raise_for_status()
                    bars = parse_bars(raw, symbol, year)
                    (root / f'{symbol}-{year}-bars.json').write_text(
                        json.dumps(bars, indent=2), encoding='utf-8')
                    entry.update(status='structurally_valid_unverified', rows=len(bars),
                                 first_date=bars[0]['date'], last_date=bars[-1]['date'])
                except (requests.RequestException, ValueError, KeyError, TypeError, IndexError) as exc:
                    entry.update(status='failed', error=str(exc))
                manifest['requests'].append(entry)
                (root / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
                print(json.dumps(entry), flush=True)
    print(str(root), flush=True)
    return int(any(e['status'] == 'failed' for e in manifest['requests']))


if __name__ == '__main__':
    raise SystemExit(main())
