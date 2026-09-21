"""Insert only missing candidates from the replayed cohort, with rollback rehearsal."""
import argparse
from collections import Counter
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import uuid

from value_investment_agent.db import connect, begin_run, end_run, store_filing_candidates
from value_investment_agent.filing_extract import extract_candidates, ANNUAL_BACKFILL_PARSER_VERSION
from value_investment_agent.settings import get_settings


def canonical(value):
    return json.dumps(value, default=str, sort_keys=True, ensure_ascii=False)


def slot(row):
    return (row['field_name'], row.get('page', row.get('page_number')), row['source_label'])


def signature(row):
    return (*slot(row), Decimal(str(row['value'])), row['unit'],
            row.get('unit_evidence_page'), row.get('unit_evidence_excerpt'))


def missing_candidates(existing, revised):
    old = {slot(row): row for row in existing}
    if len(old) != len(existing) or len({slot(row) for row in revised}) != len(revised):
        raise ValueError('Duplicate candidate slot')
    missing = []
    for row in revised:
        previous = old.get(slot(row))
        if previous is None:
            missing.append(row)
        elif (Decimal(str(previous['value'])), previous['unit']) != (Decimal(str(row['value'])), row['unit']):
            raise ValueError('Occupied candidate slot differs')
        elif previous['status'] == 'superseded_by_parser':
            raise ValueError('Revised parser reproduces a retired slot; review required')
    return missing


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan', type=Path)
    parser.add_argument('inventory', type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text(encoding='utf-8'))
    inventory = json.loads(args.inventory.read_text(encoding='utf-8'))
    if hashlib.sha256(args.inventory.read_bytes()).hexdigest() != plan['inventory_sha256']:
        raise ValueError('Plan inventory mismatch')
    if plan['parser'] != ANNUAL_BACKFILL_PARSER_VERSION:
        raise ValueError('Parser differs from reviewed release')
    reports = {r['disclosure_id']: r for r in inventory['reports']}
    packets = {}
    for report in plan['results']:
        original = reports[report['disclosure_id']]
        packet = extract_candidates(Path(original['local_path']))
        if packet['sha256'] != report['sha256'] or Counter(map(signature, packet['candidates'])) != Counter(map(signature, report['revised_candidates'])):
            raise ValueError('Original or extracted candidates differ from replay')
        packets[report['disclosure_id']] = packet['candidates']
    ids = [uuid.UUID(value) for value in packets]
    with connect(get_settings().database_url) as db:
        db.execute("SET LOCAL lock_timeout='3s'")
        db.execute("SET LOCAL statement_timeout='30s'")
        db.execute('LOCK TABLE filing_candidates, official_disclosures, data_points IN SHARE ROW EXCLUSIVE MODE')
        def snapshot():
            result = {}
            for table, clause in [('filing_candidates', 'disclosure_id=ANY(%s)'),
                                  ('official_disclosures', 'disclosure_id=ANY(%s)')]:
                result[table] = sorted(canonical(r) for r in db.execute('SELECT * FROM ' + table + ' WHERE ' + clause, (ids,)).fetchall())
            result['facts'] = sorted(canonical(r) for r in db.execute('''SELECT * FROM data_points
                WHERE symbol=ANY(%s)''', (sorted({reports[value]['symbol'] for value in packets}),)).fetchall())
            return result
        before = snapshot()
        existing = [json.loads(r) for r in before['filing_candidates']]
        additions = {}
        for did, revised in packets.items():
            live = db.execute('SELECT * FROM official_disclosures WHERE disclosure_id=%s', (uuid.UUID(did),)).fetchone()
            if live is None or live['extraction_status'] == 'processing':
                raise ValueError('Disclosure missing or processing')
            for key in ('symbol', 'report_period', 'sha256', 'source_url', 'local_path'):
                if canonical(live[key]) != canonical(reports[did][key]):
                    raise ValueError('Disclosure identity changed')
            additions[did] = missing_candidates([r for r in existing if r['disclosure_id'] == did], revised)
        def mutate():
            run_id = begin_run(db, 'insert-reviewed-parser-v32-candidates')
            for did, rows in additions.items():
                store_filing_candidates(db, uuid.UUID(did), rows)
            after = snapshot()
            if after['facts'] != before['facts'] or after['official_disclosures'] != before['official_disclosures']:
                raise ValueError('Unexpected fact or disclosure mutation')
            if not set(before['filing_candidates']).issubset(after['filing_candidates']):
                raise ValueError('Existing candidates changed')
            if len(after['filing_candidates']) - len(before['filing_candidates']) != sum(map(len, additions.values())):
                raise ValueError('Inserted count differs')
            end_run(db, run_id, 'succeeded', {'parser': ANNUAL_BACKFILL_PARSER_VERSION,
                'plan_sha256': hashlib.sha256(args.plan.read_bytes()).hexdigest(),
                'inserted_by_disclosure': {k: len(v) for k, v in additions.items()},
                'new_candidates_pending_verification': True, 'existing_records_preserved': True})
            return run_id
        db.execute('SAVEPOINT insertion_rehearsal')
        rehearsal = mutate()
        db.execute('ROLLBACK TO SAVEPOINT insertion_rehearsal')
        if snapshot() != before or db.execute('SELECT 1 FROM task_runs WHERE run_id=%s', (rehearsal,)).fetchone():
            raise ValueError('Rollback failed')
        run_id = mutate() if args.apply else None
        if not args.apply:
            db.rollback()
    print(json.dumps({'applied': args.apply, 'rollback_verified': True,
                      'run_id': str(run_id) if run_id else None, 'rehearsal_id': str(rehearsal),
                      'inserted_candidates': sum(map(len, additions.values())),
                      'verified_facts_added': 0, 'existing_candidates_unchanged': True}))


if __name__ == '__main__':
    main()
