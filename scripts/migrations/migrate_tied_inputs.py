"""Audit-reviewed three-record retirement; dry-run rolls back all writes."""
import argparse
import hashlib
import json
import uuid
from pathlib import Path

from tied_input_resolution import CASES, plan_resolution
from value_investment_agent.db import connect, begin_run, end_run
from value_investment_agent.settings import get_settings
from value_investment_agent import cli
from decimal import Decimal


def refresh_affected(db):
    symbols = [case['symbol'] for case in CASES]
    cli._refresh_financial_quality(db, symbols)
    settings = get_settings()
    for symbol in symbols:
        points = cli.latest_points(db, symbols=[symbol])
        result = cli.evaluate(symbol, points, settings.data_max_age_hours,
                              Decimal(str(settings.price_conflict_tolerance)))
        cli.upsert_valuation(db, cli.as_valuation_row(result))
    return symbols


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    with connect(get_settings().database_url) as db:
        db.execute("SET LOCAL lock_timeout='3s'")
        db.execute("SET LOCAL statement_timeout='20s'")
        db.execute('LOCK TABLE data_points, filing_candidates IN SHARE ROW EXCLUSIVE MODE')
        ids = [uuid.UUID(c[p + '_id']) for c in CASES for p in ('old', 'new')]
        rows = db.execute('''SELECT p.*, d.sha256, d.local_path FROM data_points p
            JOIN raw_documents d ON d.document_id=p.source_id
            WHERE p.data_point_id=ANY(%s)''', (ids,)).fetchall()
        changes = plan_resolution(rows)
        for row in rows:
            path = Path(row['local_path'])
            if hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']:
                raise ValueError('Archived PDF no longer matches reviewed hash')
        run_id = begin_run(db, 'resolve-reviewed-tied-inputs')
        retired = []
        for change in changes:
            marker = {'reason': change['reason'], 'run_id': str(run_id),
                      'replacement_data_point_id': change['new_id'],
                      'sha256': change['sha256'], 'previous_metadata': change['previous_metadata']}
            db.execute('''UPDATE data_points SET metadata=metadata || %s::jsonb
                WHERE data_point_id=%s''',
                (json.dumps({'superseded_by_parser': marker, 'evidence_quarantine': marker}),
                 uuid.UUID(change['old_id'])))
            retired.append(change['old_id'])
        # Recursively retire cached outputs by exact retained input IDs, not field-name guesses.
        dependencies = []
        while True:
            affected = db.execute('''SELECT p.data_point_id,p.metadata FROM data_points p
                WHERE NOT(p.metadata ? 'superseded_by_parser')
                AND EXISTS (SELECT 1 FROM jsonb_each(COALESCE(p.metadata->'input_facts','{}')) f
                    WHERE f.value->>'data_point_id'=ANY(%s::text[]))''', (retired,)).fetchall()
            if not affected:
                break
            for row in affected:
                marker = {'reason': 'retired_reviewed_input', 'run_id': str(run_id),
                          'previous_metadata': row['metadata']}
                db.execute('UPDATE data_points SET metadata=metadata || %s::jsonb WHERE data_point_id=%s',
                           (json.dumps({'superseded_by_parser': marker, 'evidence_quarantine': marker}),
                            row['data_point_id']))
                retired.append(str(row['data_point_id']))
                dependencies.append(str(row['data_point_id']))
        refreshed = refresh_affected(db)
        result = {'run_id': str(run_id), 'applied': args.apply, 'changes': changes,
                  'refreshed_symbols': refreshed,
                  'retired_cached_outputs': dependencies, 'original_records_preserved': True}
        end_run(db, run_id, 'succeeded', result)
        if not args.apply:
            db.rollback()
    print(json.dumps(result, default=str, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
