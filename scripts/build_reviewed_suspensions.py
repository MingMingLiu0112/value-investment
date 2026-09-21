"""Materialize manually read official notices; retrospective execution evidence only."""
import hashlib
import json
from pathlib import Path

from audit_historical_price_dates import audit
from collect_historical_prices import parse_bars


# Dates transcribed from the official PDF bodies, not inferred from missing bars.
REVIEWED = [
    ('sh601088', '2017-06-05', '2017-09-01', ['1203588450', '1203921881']),
    ('sh601088', '2025-08-04', '2025-08-18', ['1224369333', '1224500923']),
    ('sz000333', '2015-03-26', '2015-03-31', ['1200742027', '1200767576']),
    ('sz000333', '2016-05-18', '2016-06-01', ['1202347979']),
    ('sz000333', '2018-09-10', '2018-10-29', ['1205546211']),
    ('sz000333', '2019-02-20', '2019-02-21', ['1205842051', '1205843694']),
    ('sz000333', '2019-05-08', '2019-05-22', ['1206287791']),
]


def main():
    root = Path('runtime/historical-prices/20260908T061418761988Z')
    gap_audit = audit(root)
    dates = {}
    for entry in json.loads((root / 'manifest.json').read_text(encoding='utf-8'))['requests']:
        bars = parse_bars((root / entry['raw_file']).read_bytes(), entry['symbol'], entry['year'])
        dates.setdefault(entry['symbol'], set()).update(b['date'] for b in bars)
    notices = {}
    for path in Path('runtime/historical-filing-index').glob('20260908T*/pdfs/manifest-*.json'):
        for entry in json.loads(path.read_text(encoding='utf-8')):
            if entry['announcement_id'] in {i for *_, ids in REVIEWED for i in ids}:
                raw = Path(entry['path']).read_bytes()
                if hashlib.sha256(raw).hexdigest() != entry['sha256']:
                    raise ValueError('Official notice hash mismatch')
                notices[entry['announcement_id']] = entry
    results = []
    for symbol, start, resume, ids in REVIEWED:
        company = next(c for c in gap_audit['companies'] if c['symbol'] == symbol)
        gap = next(g for g in company['gap_runs'] if g['start'] == start)
        if any(not start <= day < resume for day in gap['dates']):
            raise ValueError('Gap outside official interval')
        if any(start <= day < resume for day in dates[symbol]):
            raise ValueError('Observed bar contradicts official suspension')
        if resume not in dates[symbol]:
            raise ValueError('Missing bar on official resume date')
        results.append({'symbol': symbol, 'suspended_from_inclusive': start,
                        'resumes_at_open': resume, 'observed_missing_peer_dates': len(gap['dates']),
                        'review_status': 'official_notice_dates_read',
                        'evidence': [notices[i] for i in ids]})
    report = {'version': 'reviewed-suspensions-v1', 'backtest_ready': False,
              'scope': 'Seven retrospective execution intervals; not a complete trading calendar',
              'lookahead_warning': 'Resume date is not available to strategy before notice publication',
              'intervals': results}
    target = root / 'reviewed-suspensions.json'
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'intervals': len(results),
                      'explained_peer_dates': sum(r['observed_missing_peer_dates'] for r in results),
                      'path': str(target)}))


if __name__ == '__main__':
    main()
