"""Fetch bounded third-provider records for existing historical close conflicts."""
import argparse
import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
import time

import requests
from bs4 import BeautifulSoup


RULE_URL = 'https://www.sse.com.cn/aboutus/mediacenter/hotandd/c/c_20180806_4607055.shtml'


def parse_sohu(raw, symbol, day):
    if isinstance(raw, bytes):
        raw = raw.decode('gb18030')
    packet = json.loads(raw)
    if not isinstance(packet, list) or len(packet) != 1:
        raise ValueError('Unexpected Sohu envelope')
    result = packet[0]
    if result.get('status') != 0 or result.get('code') != 'cn_' + symbol:
        raise ValueError('Wrong symbol or failed Sohu request')
    rows = result.get('hq') or []
    if len(rows) != 1 or len(rows[0]) != 10 or rows[0][0] != day:
        raise ValueError('Missing, duplicate or wrong requested day')
    row = rows[0]
    values = {field: Decimal(str(row[index])) for field, index in
              (('open', 1), ('close', 2), ('low', 5), ('high', 6))}
    if any(not value.is_finite() or value <= 0 for value in values.values()):
        raise ValueError('Invalid Sohu price')
    if not values['low'] <= min(values['open'], values['close']) <= max(values['open'], values['close']) <= values['high']:
        raise ValueError('Invalid Sohu OHLC bounds')
    return {'date': day, **{field: str(value) for field, value in values.items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('comparison', type=Path)
    args = parser.parse_args()
    raw_comparison = args.comparison.read_bytes()
    comparisons = json.loads(raw_comparison)
    conflicts = [(entry, row) for entry in comparisons for row in entry['differences']]
    if not 1 <= len(conflicts) <= 20:
        raise ValueError('Expected a bounded conflict set')
    target = Path('runtime/historical-price-third-source') / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    target.mkdir(parents=True, exist_ok=False)
    output = {'comparison_path': str(args.comparison),
              'comparison_sha256': hashlib.sha256(raw_comparison).hexdigest(),
              'scope': 'Third-provider corroboration, not official close certification',
              'backtest_ready': False, 'results': []}
    with requests.Session() as session:
        session.trust_env = False
        response = session.get(RULE_URL, timeout=30)
        response.raise_for_status()
        text = ''.join(BeautifulSoup(response.content, 'html.parser').get_text().split())
        if not all(s in text for s in ('2018年8月20日', '收盘集合竞价', '14:57')):
            raise ValueError('Official rule page changed or unavailable')
        (target / 'sse-closing-rule.html').write_bytes(response.content)
        output['official_rule'] = {'url': response.url, 'sha256': hashlib.sha256(response.content).hexdigest(),
                                   'path': str(target / 'sse-closing-rule.html'),
                                   'fetched_at': datetime.now(timezone.utc).isoformat()}
        for entry, conflict in conflicts:
            symbol = entry['symbol'][2:]
            day = date.fromisoformat(conflict['date']).isoformat()
            if set(conflict['differences']) != {'close'}:
                raise ValueError('This audit requires explicit close-only conflicts')
            url = 'https://q.stock.sohu.com/hisHq'
            params = {'code': 'cn_' + symbol, 'start': day.replace('-', ''),
                      'end': day.replace('-', ''), 'stat': '1', 'order': 'D', 'period': 'd', 'rt': 'json'}
            result = {'symbol': symbol, 'date': day, 'query': params, 'requested_url': url}
            try:
                for attempt in range(3):
                    response = session.get(url, params=params, timeout=20)
                    if response.status_code not in {502, 503, 504} or attempt == 2:
                        break
                    time.sleep(attempt + 1)
                response.raise_for_status()
                if len(response.content) > 1024**2:
                    raise ValueError('Unexpected oversized response')
                path = target / (symbol + '-' + day + '.json')
                path.write_bytes(response.content)
                result.update(source_url=response.url, raw_path=str(path),
                              sha256=hashlib.sha256(response.content).hexdigest(),
                              fetched_at=datetime.now(timezone.utc).isoformat(),
                              body_decoding='gb18030', http_content_type=response.headers.get('Content-Type'))
                values = parse_sohu(response.content, symbol, day)
                existing = conflict['differences']['close']
                close = Decimal(values['close'])
                result.update(status='corroboration_only', values=values,
                              tencent_close=existing['tencent'], sina_close=existing['sina'],
                              matches_tencent_close=close == Decimal(existing['tencent']),
                              matches_sina_close=close == Decimal(existing['sina']),
                              adjustment_request='provider_default',
                              source_url=response.url, raw_path=str(path),
                              sha256=hashlib.sha256(response.content).hexdigest(),
                              fetched_at=datetime.now(timezone.utc).isoformat(),
                              official_close_verified=False)
            except Exception as error:
                result.update(status='failed', error=str(error))
            output['results'].append(result)
            (target / 'audit.json').write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps(result, ensure_ascii=False), flush=True)
            time.sleep(1)
    print(json.dumps({'directory': str(target)}))
    if any(r['status'] == 'failed' for r in output['results']):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
