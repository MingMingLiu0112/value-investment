"""Compare archived Tencent bars with raw Sina bars without filling missing dates."""
import argparse
import hashlib
import json
import re
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import requests

from collect_historical_prices import parse_bars


FIELDS = ('open', 'high', 'low', 'close')


def sina_payload(raw, symbol):
    match = re.fullmatch(r'\s*var KLC_K2_' + re.escape(symbol)
                         + r'\s*=\s*("[^"]*")\s*;?\s*(?:/\*[\s\S]*?\*/\s*)?',
                         raw.decode('utf-8-sig'))
    if not match:
        raise ValueError('Unexpected Sina response or symbol')
    return json.loads(match[1])


def normalize_sina(rows, *, start_year=2015, end_year=2025):
    if not isinstance(rows, list) or not 1 <= len(rows) <= 20000:
        raise ValueError('Unexpected decoded historical series length')
    bars = {}
    for row in rows:
        stamp = datetime.fromisoformat(str(row['date']).replace('Z', '+00:00'))
        if stamp.hour or stamp.minute or stamp.second:
            raise ValueError(f'Unexpected decoded date convention: {row["date"]}')
        day = stamp.date()
        if not date(start_year, 1, 1) <= day <= date(end_year, 12, 31):
            continue
        key = day.isoformat()
        if key in bars:
            raise ValueError('Duplicate Sina date; no silent deduplication')
        values = {field: Decimal(str(row[field])) for field in FIELDS}
        if any(not value.is_finite() or value <= 0 for value in values.values()):
            raise ValueError('Invalid Sina price')
        if not values['low'] <= min(values['open'], values['close']) <= max(values['open'], values['close']) <= values['high']:
            raise ValueError('Invalid Sina OHLC bounds')
        bars[key] = {'date': key, **{field: str(value) for field, value in values.items()}}
    if not bars:
        raise ValueError('No Sina bars in the fixed 2015-2025 interval')
    return bars


def compare(left, right, *, tolerance=Decimal('0.000001')):
    common = sorted(left.keys() & right.keys())
    differences = []
    for day in common:
        values = {field: {'tencent': str(left[day][field]), 'sina': str(right[day][field])}
                  for field in FIELDS
                  if abs(Decimal(str(left[day][field])) - Decimal(str(right[day][field]))) > tolerance}
        if values:
            differences.append({'date': day, 'differences': values})
    return {'tencent_dates': len(left), 'sina_dates': len(right), 'common_dates': len(common),
            'only_tencent': sorted(left.keys() - right.keys()),
            'only_sina': sorted(right.keys() - left.keys()),
            'ohlc_mismatch_days': len(differences), 'differences': differences,
            'comparison_tolerance': str(tolerance),
            'volume_units_verified': False, 'exchange_calendar_verified': False,
            'backtest_ready': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tencent_directory', type=Path)
    args = parser.parse_args()
    manifest = json.loads((args.tencent_directory / 'manifest.json').read_text(encoding='utf-8'))
    symbols = sorted({row['symbol'] for row in manifest['requests']})
    if symbols != ['sh600519', 'sh601088', 'sz000333']:
        raise ValueError('This research run is limited to the three preselected cases')
    target = Path('runtime/historical-price-crosscheck') / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    target.mkdir(parents=True, exist_ok=False)
    from akshare.stock.stock_zh_a_sina import hk_js_decode, py_mini_racer, zh_sina_a_stock_hist_url
    import akshare
    results = []
    with requests.Session() as session:
        session.trust_env = False
        for symbol in symbols:
            left = {}
            evidence = []
            entries = [e for e in manifest['requests'] if e['symbol'] == symbol]
            if len(entries) != 11 or {e['year'] for e in entries} != set(range(2015, 2026)):
                raise ValueError('Missing or duplicate requested years')
            for entry in entries:
                path = args.tencent_directory / entry['raw_file']
                raw = path.read_bytes()
                if hashlib.sha256(raw).hexdigest() != entry['sha256']:
                    raise ValueError('Tencent source hash mismatch')
                for bar in parse_bars(raw, symbol, entry['year']):
                    if bar['date'] in left:
                        raise ValueError('Duplicate Tencent date')
                    left[bar['date']] = bar
                evidence.append({'path': str(path), 'sha256': entry['sha256']})
            url = zh_sina_a_stock_hist_url.format(symbol)
            with session.get(url, timeout=30, stream=True) as response:
                response.raise_for_status()
                raw = response.raw.read(5 * 1024**2 + 1, decode_content=True)
                if not raw or len(raw) > 5 * 1024**2:
                    raise ValueError('Empty or oversized Sina response')
                path = target / (symbol + '-sina.js')
                path.write_bytes(raw)
                decoder = py_mini_racer.MiniRacer()
                decoder.eval(hk_js_decode)
                decoded = decoder.call('d', sina_payload(raw, symbol))
                right = normalize_sina(decoded)
                (target / (symbol + '-sina-bars.json')).write_text(json.dumps(right, indent=2), encoding='utf-8')
                result = {'symbol': symbol, 'sina_url': url, 'sina_final_url': response.url,
                          'archive_body_encoding': 'HTTP content encoding decoded',
                          'sina_path': str(path), 'sina_sha256': hashlib.sha256(raw).hexdigest(),
                          'fetched_at': datetime.now(timezone.utc).isoformat(),
                          'decoder': 'AkShare hk_js_decode', 'akshare_version': akshare.__version__,
                          'decoder_sha256': hashlib.sha256(hk_js_decode.encode()).hexdigest(),
                          'tencent_evidence': evidence, **compare(left, right)}
                results.append(result)
                (target / 'comparison.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
                print(json.dumps({key: result[key] for key in ('symbol', 'tencent_dates', 'sina_dates',
                      'common_dates', 'ohlc_mismatch_days')}), flush=True)
    print(json.dumps({'directory': str(target), 'backtest_ready': False}))


if __name__ == '__main__':
    main()
