"""Bridge a pinned local financing replay to an exported evidence snapshot."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from value_investment_agent.financing_bridge import bridge_financing_rows


def audit(payload, manifest, replay):
    reports = []
    points = payload.get('points', []) + payload.get('annual_points', [])
    for source in manifest['reports']:
        matches = [r for r in replay if r['sha256'] == source['sha256']]
        if len(matches) != 1 or source.get('archive_hash_matched') is not True:
            raise ValueError('Missing or ambiguous archive replay: ' + source['symbol'])
        original = Path(matches[0]['path'])
        if hashlib.sha256(original.read_bytes()).hexdigest() != source['sha256']:
            raise ValueError('Original PDF changed: ' + source['symbol'])
        hits = [h for h in matches[0]['hits'] if h.get('parsed')]
        if len(hits) != 1:
            reports.append({'symbol': source['symbol'], 'status': 'missing_or_ambiguous_table'})
            continue
        hit = hits[0]
        result = bridge_financing_rows(hit['parsed'], points, source['symbol'],
            source['report_period'], source['sha256'], source['source_url'])
        result['physical_pages'] = hit['parsed'].get('physical_pages', [hit['physical_page']])
        reports.append(result)
    return {'generated_at': datetime.now(timezone.utc).isoformat(),
            'export_generated_at': payload.get('generated_at'), 'reports': reports,
            'complete_debt_verified': False, 'scope': 'Read-only local evidence audit; no promotion'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('payload', type=Path)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('replay', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    raw = [path.read_bytes() for path in (args.payload, args.manifest, args.replay)]
    result = audit(*(json.loads(data) for data in raw))
    result['input_sha256'] = dict(zip(('payload', 'manifest', 'replay'),
                                     (hashlib.sha256(data).hexdigest() for data in raw)))
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps([{'symbol': r['symbol'], 'matched_rows': r.get('matched_rows', 0),
                      'rows': [(x['label'], x['status']) for x in r.get('rows', [])]}
                     for r in result['reports']], ensure_ascii=False, indent=2))
