"""Audit bounded candidate annual PDFs against exported archive hashes."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import urllib.request

from audit_local_financing_tables import inspect


def select_reports(payload, limit, offset=0):
    if limit < 1 or offset < 0:
        raise ValueError('Positive limit and nonnegative offset required')
    members = {row['symbol'] for row in payload['market_candidates']}
    reports = {}
    for row in payload.get('disclosures', []) + payload.get('filing_candidates', []):
        if row['symbol'] not in members or row.get('report_kind') != 'annual':
            continue
        if row.get('report_period') != '2025-12-31':
            continue
        url, digest = row.get('source_url', ''), row.get('sha256', '')
        if not re.fullmatch(r'https://static\.cninfo\.com\.cn/finalpage/\d{4}-\d{2}-\d{2}/\d+\.[Pp][Dd][Ff]', url):
            continue
        if not re.fullmatch('[0-9a-f]{64}', digest):
            continue
        reports[(row['symbol'], url, digest)] = row
    priorities = {}
    for row in payload.get('financial_quality', []):
        details = row.get('calculation_details') or {}
        required = set(details.get('required_fields', []))
        missing = required - set(details.get('accepted_fields', []))
        if 'interest_bearing_debt' in missing:
            priorities[row['symbol']] = len(missing)
    eligible = [row for row in reports.values() if row['symbol'] in priorities]
    eligible.sort(key=lambda row: (priorities[row['symbol']], row['symbol'], row['source_url']))
    # Multiple versions are kept for a later revision review, not chosen silently.
    counts = {}
    for row in eligible:
        counts[row['symbol']] = counts.get(row['symbol'], 0) + 1
    return [row for row in eligible if counts[row['symbol']] == 1][offset:offset + limit]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('payload', type=Path)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--limit', type=int, default=5, choices=range(1, 11))
    parser.add_argument('--offset', type=int, default=0)
    args = parser.parse_args()
    if args.offset < 0:
        parser.error('offset must be nonnegative')
    raw = args.payload.read_bytes()
    selected = select_reports(json.loads(raw), args.limit, args.offset)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    manifest = {'payload_sha256': hashlib.sha256(raw).hexdigest(),
                'selection_offset': args.offset, 'selection_limit': args.limit,
                'selected_symbols': [row['symbol'] for row in selected],
                'started_at': datetime.now(timezone.utc).isoformat(),
                'scope': 'Local research only; no production fact promotion', 'reports': []}
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for source in selected:
        row = {key: source.get(key) for key in
               ('symbol', 'report_period', 'source_url', 'sha256')}
        row['complete_debt_verified'] = False
        try:
            with opener.open(source['source_url'], timeout=60) as response:
                if not response.geturl().startswith('https://static.cninfo.com.cn/'):
                    raise ValueError('Unexpected redirect')
                data = response.read(40 * 1024 * 1024 + 1)
            if len(data) > 40 * 1024 * 1024 or not data.startswith(b'%PDF-'):
                raise ValueError('Oversized or non-PDF response')
            if hashlib.sha256(data).hexdigest() != source['sha256']:
                raise ValueError('Exported archive hash mismatch')
            target = args.output_dir / (source['symbol'] + '-' + source['sha256'][:12] + '.pdf')
            with target.open('xb') as stream:
                stream.write(data)
            row['archive_hash_matched'] = True
            row['audit'] = inspect(target)
            row['status'] = 'audited_scope_unverified'
        except Exception as exc:
            row['status'] = 'failed'
            row['error'] = type(exc).__name__ + ': ' + str(exc)
        manifest['reports'].append(row)
        (args.output_dir / 'manifest.json').write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'symbol': row['symbol'], 'status': row['status'],
                          'hits': len(row.get('audit', {}).get('hits', [])),
                          'error': row.get('error')}, ensure_ascii=False), flush=True)
    if not selected:
        raise SystemExit('No unambiguous eligible annual reports; no coverage claim')


if __name__ == '__main__':
    main()
