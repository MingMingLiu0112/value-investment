"""Dry-run actual exported views; no database writes or validation promotion."""
import argparse
from collections import Counter, defaultdict
from decimal import Decimal
import hashlib
import json
from pathlib import Path

from value_investment_agent.derived_financials import build_verified_derivations, DERIVATION_VERSION


def input_changes(old, record, existing):
    retained = ((old or {}).get('metadata') or {}).get('input_facts') or {}
    changes = []
    for name, current in record.point_metadata['input_facts'].items():
        previous = retained.get(name)
        if previous == current:
            continue
        point = existing[name]
        metadata = point.get('metadata') or {}
        changes.append({
            'field': name, 'previous_input': previous, 'current_input': current,
            'current_created_at': point.get('created_at'),
            'old_output_created_at': (old or {}).get('created_at'),
            'source_url': point.get('source_url'), 'sha256': point.get('sha256'),
            'page_number': metadata.get('page_number'),
            'published_at': point.get('published_at'),
            'verification_method': metadata.get('verification_method'),
            'same_document': bool(previous and previous.get('source_id')
                                  and previous.get('source_id') == current.get('source_id')),
        })
    return changes


def audit(path):
    raw = path.read_bytes()
    payload = json.loads(raw)
    symbols = [r['symbol'] for r in payload['market_candidates']]
    proposals, errors = [], []
    for view in ('points', 'annual_points'):
        grouped = defaultdict(list)
        for point in payload.get(view, []):
            grouped[point['symbol']].append(point)
        for symbol in symbols:
            points = grouped[symbol]
            try:
                records = build_verified_derivations(points, [symbol])
                existing = {p['field_name']: p for p in points}
                for record in records:
                    old = existing.get(record.field_name)
                    same_period = old is not None and str(old['period_label']) == record.period_label
                    same_value = (same_period and old.get('unit') == record.unit
                                  and Decimal(str(old['value'])) == record.value)
                    kind = ('same_value_metadata_refresh' if same_value else
                            'same_period_value_or_unit_change' if same_period else
                            'no_same_period_output_in_view')
                    proposals.append({'symbol': symbol, 'view': view, 'field': record.field_name,
                                      'period': record.period_label, 'value': str(record.value),
                                      'unit': record.unit, 'change_kind': kind,
                                      'old_value': str(old['value']) if old else None,
                                      'old_status': old.get('validation_status') if old else None,
                                      'input_changes': input_changes(old, record, existing),
                                      'input_facts': record.point_metadata['input_facts'],
                                      'ratio_scope': record.point_metadata.get('ratio_scope')})
            except Exception as exc:
                errors.append({'symbol': symbol, 'view': view, 'error': str(exc)})
    return {'payload_sha256': hashlib.sha256(raw).hexdigest(),
            'export_generated_at': payload.get('generated_at'), 'model_version': DERIVATION_VERSION,
            'companies_examined': len(symbols), 'proposal_view_rows': len(proposals),
            'companies_with_proposals': len({p['symbol'] for p in proposals}),
            'changes': dict(Counter(p['change_kind'] for p in proposals)),
            'errors': errors, 'proposals': proposals, 'database_writes': False,
            'scope': 'Export replay only. Views can overlap; proposals are not net new verified facts.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('payload', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.payload)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in result.items() if k != 'proposals'}, ensure_ascii=False, indent=2))
    if result['errors']:
        raise SystemExit(1)
