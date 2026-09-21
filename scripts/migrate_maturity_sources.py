"""Hash-reviewed maturity evidence retirement; default execution rolls back."""
import argparse
import hashlib
import json
from pathlib import Path
from decimal import Decimal
import uuid

from evidence_dependencies import affected_point_ids
from value_investment_agent import cli
from value_investment_agent.db import connect, begin_run, end_run
from value_investment_agent.settings import get_settings


def canonical(value):
    return json.dumps(value, default=str, sort_keys=True, ensure_ascii=False)


def snapshot(db, symbols):
    output = {}
    for table in ('data_points', 'valuation_results', 'financial_quality_results'):
        rows = db.execute('SELECT * FROM ' + table + ' WHERE symbol=ANY(%s)', (symbols,)).fetchall()
        output[table] = sorted(canonical(row) for row in rows)
    rows = db.execute('''SELECT c.* FROM filing_candidates c JOIN official_disclosures o
        ON o.disclosure_id=c.disclosure_id WHERE o.symbol=ANY(%s)''', (symbols,)).fetchall()
    output['filing_candidates'] = sorted(canonical(row) for row in rows)
    return hashlib.sha256(canonical(output).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('audit', type=Path)
    parser.add_argument('review', type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    audit = json.loads(args.audit.read_text(encoding='utf-8'))
    if hashlib.sha256(args.review.read_bytes()).hexdigest() != audit['review_sha256']:
        raise ValueError('Reviewed source manifest changed')
    review = json.loads(args.review.read_text(encoding='utf-8'))
    settings = get_settings()
    expected = {r['data_point_id']: r for r in audit['affected_points']}
    initial = set(audit['initial_ids'])
    with connect(settings.database_url) as db:
        db.execute("SET LOCAL lock_timeout='3s'")
        db.execute("SET LOCAL statement_timeout='30s'")
        db.execute('LOCK TABLE data_points, filing_candidates, valuation_results, financial_quality_results IN SHARE ROW EXCLUSIVE MODE')
        points = db.execute('''SELECT data_point_id,source_id,symbol,field_name,period_label,
            validation_status,metadata FROM data_points WHERE metadata ?| ARRAY[
                'secondary_data_point_id','input_source_ids','input_facts','input_data_point_ids']
            OR data_point_id=ANY(%s)''', ([uuid.UUID(v) for v in initial],)).fetchall()
        closure = affected_point_ids(points, initial)
        if closure != set(expected):
            raise ValueError('Dependency closure changed; regenerate and review audit')
        selected = [r for r in points if str(r['data_point_id']) in closure]
        for point in selected:
            old = expected[str(point['data_point_id'])]
            if any(canonical(point[k]) != canonical(old[k]) for k in point):
                raise ValueError('Production precondition changed: ' + str(point['data_point_id']))
            if point['metadata'].get('evidence_quarantine'):
                raise ValueError('Existing quarantine requires separate review')
        candidate_ids = []
        for record in review['records']:
            candidate = record['candidate']
            live = db.execute('''SELECT c.*, o.sha256 AS original_sha256,o.local_path,o.symbol,o.report_period
                FROM filing_candidates c JOIN official_disclosures o ON o.disclosure_id=c.disclosure_id
                WHERE c.candidate_id=%s''', (uuid.UUID(candidate['candidate_id']),)).fetchone()
            if live is None or any(canonical(live[k]) != canonical(v) for k, v in candidate.items()):
                raise ValueError('Candidate precondition changed')
            if (live['symbol'], live['report_period'], live['original_sha256']) != (
                    record['symbol'], record['report_period'], record['official_sha256']):
                raise ValueError('Disclosure precondition changed')
            with Path(live['local_path']).open('rb') as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != live['original_sha256']:
                    raise ValueError('Server original PDF hash changed')
            candidate_ids.append(uuid.UUID(candidate['candidate_id']))
        symbols = sorted({r['symbol'] for r in selected})
        before = snapshot(db, symbols)
        db.execute('SAVEPOINT maturity_rehearsal')
        run_id = begin_run(db, 'retire-reviewed-maturity-evidence')
        for point in selected:
            marker = {'reason': 'undiscounted_maturity_cashflow_not_carrying_amount_evidence'
                      if str(point['data_point_id']) in initial else 'depends_on_retired_maturity_evidence',
                      'run_id': str(run_id), 'previous_metadata': point['metadata'],
                      'previous_validation_status': point['validation_status']}
            db.execute('UPDATE data_points SET metadata=metadata || %s::jsonb WHERE data_point_id=%s',
                       (json.dumps({'superseded_by_parser': marker, 'evidence_quarantine': marker,
                                    'automatic_cross_source_verification': False}), point['data_point_id']))
        db.execute("UPDATE filing_candidates SET status='superseded_by_parser' WHERE candidate_id=ANY(%s)", (candidate_ids,))
        cli._refresh_financial_quality(db, symbols)
        for symbol in symbols:
            current = cli.latest_points(db, symbols=[symbol])
            if any(str(p['data_point_id']) in closure for p in current):
                raise ValueError('Retired input still eligible for latest view')
            verdict = cli.evaluate(symbol, current, settings.data_max_age_hours,
                                   Decimal(str(settings.price_conflict_tolerance)))
            cli.upsert_valuation(db, cli.as_valuation_row(verdict))
        result = {'run_id': str(run_id), 'affected': len(selected), 'candidates_retired': len(candidate_ids),
                  'symbols': symbols, 'applied': args.apply, 'before_snapshot_sha256': before,
                  'records_preserved': True}
        end_run(db, run_id, 'succeeded', result)
        if not args.apply:
            db.execute('ROLLBACK TO SAVEPOINT maturity_rehearsal')
            if snapshot(db, symbols) != before:
                raise ValueError('Rollback snapshot differs')
            if db.execute('SELECT count(*) AS n FROM task_runs WHERE run_id=%s', (run_id,)).fetchone()['n']:
                raise ValueError('Rehearsal audit row survived rollback')
            result['rollback_verified'] = True
            db.rollback()
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
