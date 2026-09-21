"""Retain official SZSE monthly calendars for session-contract research."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import requests


def main():
    root = Path(__file__).resolve().parents[1]
    target = root / 'runtime' / 'exchange-calendar-probes' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    target.mkdir(parents=True)
    records = []
    with requests.Session() as session:
        session.trust_env = False
        for month in ('2026-08', '2026-09'):
            row = {'month': month, 'scope': 'SZSE monthly calendar; other exchange scope not assumed'}
            try:
                response = session.get('https://www.szse.cn/api/report/exchange/onepersistenthour/monthList',
                                       params={'month': month}, headers={'Referer': 'https://www.szse.cn/'},
                                       timeout=(10, 15))
                raw = response.content
                path = month + '.bin'
                (target / path).write_bytes(raw)
                row.update(url=response.url, http_status=response.status_code, path=path,
                           fetched_at=datetime.now(timezone.utc).isoformat(),
                           sha256=hashlib.sha256(raw).hexdigest())
                response.raise_for_status()
                row['decoded'] = response.json()
            except (requests.RequestException, ValueError) as error:
                row['error'] = str(error)
            records.append(row)
    manifest = target / 'manifest.json'
    manifest.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'path': str(manifest), 'records': records}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
