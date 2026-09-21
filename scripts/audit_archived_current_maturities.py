"""Bounded sequential replay of already archived annual debt notes."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

from audit_current_maturity_notes import inspect as inspect_notes, reconcile
from audit_local_financing_tables import inspect as inspect_financing


def select(manifests):
    selected = {}
    for manifest in manifests:
        for source in manifest['reports']:
            symbol = source['symbol']
            if source.get('archive_hash_matched') is not True or not source.get('audit', {}).get('path'):
                raise ValueError('Unverified archive identity: ' + symbol)
            if symbol in selected and selected[symbol] != source:
                raise ValueError('Ambiguous report versions: ' + symbol)
            selected[symbol] = source
    if not 1 <= len(selected) <= 50:
        raise ValueError('Select 1-50 unique explicitly archived companies')
    return list(selected.values())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('payload', type=Path)
    parser.add_argument('manifests', nargs='+', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    payload_raw = args.payload.read_bytes()
    payload = json.loads(payload_raw)
    raw = [p.read_bytes() for p in args.manifests]
    selected = select([json.loads(data) for data in raw])
    points = payload.get('points', []) + payload.get('annual_points', [])
    result = {'started_at': datetime.now(timezone.utc).isoformat(),
              'scope': 'Local archived research only; no network or data promotion',
              'payload_sha256': hashlib.sha256(payload_raw).hexdigest(),
              'manifest_sha256': {str(p): hashlib.sha256(data).hexdigest() for p, data in zip(args.manifests, raw)},
              'reports': []}
    started = time.monotonic()
    for source in selected:
        row = {key: source[key] for key in ('symbol', 'report_period', 'source_url', 'sha256')}
        row['complete_debt_verified'] = False
        try:
            original = Path(source['audit']['path'])
            if hashlib.sha256(original.read_bytes()).hexdigest() != source['sha256']:
                raise ValueError('Original hash changed')
            financing = inspect_financing(original)
            notes = inspect_notes(original)
            row.update(notes=notes, financing=financing)
            parsed = [h['parsed'] for h in financing['hits'] if h.get('parsed')]
            row['status'] = 'notes_missing_or_ambiguous'
            if len(notes) == 1:
                row['status'] = 'note_extracted_scope_unverified'
                row['reconciliation'] = reconcile(source, notes[0], parsed[0] if len(parsed) == 1 else {'rows': []}, points)
                row['financing_table_unique'] = len(parsed) == 1
        except Exception as exc:
            row.update(status='failed', error=type(exc).__name__ + ': ' + str(exc))
        result['reports'].append(row)
        print(json.dumps({'symbol': row['symbol'], 'status': row['status'],
            'aggregate_matches': row.get('reconciliation', {}).get('aggregate_bridge', {}).get('matched_rows', 0)}), flush=True)
    result['elapsed_seconds'] = time.monotonic() - started
    result['finished_at'] = datetime.now(timezone.utc).isoformat()
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
