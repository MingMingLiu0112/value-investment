"""Retire miskeyed supplemental observations with exact snapshot proof; dry-run default."""
import argparse
import hashlib
import json
from pathlib import Path

from provider_scope import REPLACEMENTS, snapshot_proves_provider_field
from value_investment_agent.db import connect, begin_run, end_run
from value_investment_agent.settings import get_settings

parser = argparse.ArgumentParser()
parser.add_argument('--symbols', nargs='+', required=True)
parser.add_argument('--apply', action='store_true')
args = parser.parse_args()
if len(args.symbols) > 20 or any(len(s) != 6 or not s.isascii() or not s.isdigit() for s in args.symbols):
    parser.error('Provide at most 20 six-digit symbols')
changes = []
with connect(get_settings().database_url) as db:
    db.execute("SET lock_timeout='5s'")
    db.execute("SET statement_timeout='30s'")
    db.execute('LOCK TABLE data_points IN SHARE ROW EXCLUSIVE MODE')
    run = begin_run(db, 'migrate-provider-indicator-scopes')
    for old_field, new_field in REPLACEMENTS.items():
        rows = db.execute("""SELECT p.*,d.sha256,d.local_path,n.data_point_id AS replacement_id
            FROM data_points p JOIN raw_documents d ON d.document_id=p.source_id
            JOIN LATERAL (SELECT n.data_point_id FROM data_points n
                WHERE n.source_id=p.source_id AND n.symbol=p.symbol AND n.period_label=p.period_label
                  AND n.field_name=%s AND n.value=p.value AND n.unit=p.unit
                  AND n.validation_status='pending' AND NOT n.human_reviewed
                  AND NOT (n.metadata ? 'superseded_by_parser')
                  AND NOT (n.metadata ? 'evidence_quarantine')
                  AND NOT (n.metadata ? 'candidate_id')
                ORDER BY n.created_at DESC,n.data_point_id DESC LIMIT 1) n ON true
            WHERE p.symbol=ANY(%s) AND p.field_name=%s AND p.unit='percent'
              AND p.validation_status='pending' AND NOT p.human_reviewed
              AND d.source_name='AkShare / Sina financial indicators'
              AND d.local_path IS NOT NULL AND d.local_path<>''
              AND NOT (p.metadata ? 'superseded_by_parser')
              AND NOT (p.metadata ? 'evidence_quarantine') AND NOT (p.metadata ? 'candidate_id')
            ORDER BY p.symbol,p.period_label,p.data_point_id""",
            (new_field, args.symbols, old_field)).fetchall()
        for row in rows:
            raw = Path(row['local_path']).read_bytes()
            if hashlib.sha256(raw).hexdigest() != row['sha256']:
                raise ValueError('Snapshot hash mismatch')
            if not snapshot_proves_provider_field(raw, row['symbol'], row['period_label'],
                                                 old_field, row['value'], row['unit']):
                raise ValueError('Snapshot does not prove provider indicator identity')
            marker = {'reason': 'supplemental_provider_scope_is_not_canonical',
                'run_id': str(run), 'replacement_field': new_field,
                'replacement_data_point_id': str(row['replacement_id']), 'snapshot_sha256': row['sha256']}
            result = db.execute("""UPDATE data_points SET metadata=metadata || %s::jsonb
                WHERE data_point_id=%s AND validation_status='pending' AND NOT human_reviewed
                  AND NOT (metadata ? 'superseded_by_parser')""",
                (json.dumps({'superseded_by_parser': marker}), row['data_point_id']))
            if result.rowcount != 1:
                raise ValueError('Concurrent migration change')
            changes.append({'data_point_id': str(row['data_point_id']), 'symbol': row['symbol'],
                'period': row['period_label'], 'field': old_field,
                'previous_metadata': row['metadata'], **marker})
    end_run(db, run, 'succeeded', {'changes': changes, 'applied': args.apply})
    if not args.apply:
        db.rollback()
print(json.dumps({'records': len(changes), 'applied': args.apply,
    'fields': {field: sum(c['field'] == field for c in changes) for field in REPLACEMENTS},
    'run_id': str(run), 'original_values_preserved': True}, default=str))
