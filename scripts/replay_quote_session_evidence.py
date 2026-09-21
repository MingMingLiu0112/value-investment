"""Replay archived raw probes through the production decision-date checker."""
import base64
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from value_investment_agent.quote_sessions import evaluate_quote_session, parse_quote


QUOTES = ROOT / 'runtime/quote-session-probes/20260909T015909590543Z/manifest.json'
CALENDARS = ROOT / 'runtime/exchange-calendar-probes/20260909T020102864128Z/manifest.json'


def retained(row, directory):
    raw = (directory / row.get('raw_path', row.get('path'))).read_bytes()
    if hashlib.sha256(raw).hexdigest() != row['sha256']:
        raise ValueError('Original response changed')
    return {'source_url': row['url'], 'fetched_at': row['fetched_at'], 'sha256': row['sha256'],
            'raw_base64': base64.b64encode(raw).decode('ascii')}


def main():
    quote_manifest = json.loads(QUOTES.read_text(encoding='utf-8'))
    calendars = [retained(r, CALENDARS.parent) for r in json.loads(CALENDARS.read_text(encoding='utf-8'))]
    quotes = {r['name'].removesuffix('_quotes'): retained(r, QUOTES.parent)
              for r in quote_manifest['observations'] if r['name'].endswith('_quotes')}
    asof = '2026-09-09T10:02:00+08:00'
    rows = []
    for symbol in ('000333', '600519', '601088'):
        packet = {'symbol': symbol, 'calendar_exchange': 'SZSE',
                  'calendar_documents': calendars, **quotes}
        observed = parse_quote(quotes['tencent'], 'tencent', symbol, datetime.fromisoformat(asof))
        result = evaluate_quote_session(symbol, observed['price'], packet, asof)
        rows.append({'symbol': symbol, 'actual_tencent_quote': str(observed['price']),
                     'decision_as_of': asof, 'result': result})
    if rows[0]['result']['status'] != 'intraday_quote' or any(r['result']['passed'] for r in rows):
        raise ValueError('Real archived intraday quotes unexpectedly approved')
    result = {'scope': 'real raw-source replay, no signal or financial promotion',
              'source_manifests': [str(QUOTES), str(CALENDARS)], 'observations': rows}
    output = ROOT / 'runtime/quote-session-replay-20260909.json'
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'output': str(output), **result}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
