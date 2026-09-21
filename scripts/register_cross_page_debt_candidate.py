"""Register the reviewed 600496 cross-page candidate, pending verification only."""
import argparse
import json
from pathlib import Path

from value_investment_agent.db import connect, begin_run, end_run, store_filing_candidates
from value_investment_agent.filing_extract import extract_candidates, ANNUAL_BACKFILL_PARSER_VERSION
from value_investment_agent.settings import get_settings
from insert_reviewed_parser_candidates import missing_candidates, canonical


PDF_HASH = '7063bee136b03667ca138335ce8ac0950406762e64b707f5771483b239d4fa03'
URL = 'https://static.cninfo.com.cn/finalpage/2026-04-18/1225120796.PDF'
FIELD = 'current_portion_long_term_debt'


def reviewed_row(packet):
    if packet['sha256'] != PDF_HASH:
        raise ValueError('Unexpected original PDF')
    rows = [r for r in packet['candidates'] if r['field_name'] == FIELD]
    if (len(rows) != 1 or rows[0]['value'] != '468249668.22'
            or rows[0]['unit'] != 'CNY' or rows[0]['page'] != 80
            or 'PDF第81页' not in rows[0]['excerpt']):
        raise ValueError('Reviewed candidate or cross-page evidence changed')
    return rows[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if ANNUAL_BACKFILL_PARSER_VERSION != 'filing-extract-v33-cross-page-current-debt':
        raise ValueError('Unexpected production parser')
    with connect(get_settings().database_url) as db:
        db.execute("SET LOCAL lock_timeout='3s'")
        db.execute("SET LOCAL statement_timeout='30s'")
        db.execute('LOCK TABLE filing_candidates, official_disclosures, data_points IN SHARE ROW EXCLUSIVE MODE')
        reports = db.execute('''SELECT * FROM official_disclosures WHERE symbol='600496'
            AND report_period='2025-12-31' AND report_kind='annual'
            AND sha256=%s AND source_url=%s''', (PDF_HASH, URL)).fetchall()
        if len(reports) != 1 or reports[0]['extraction_status'] == 'processing':
            raise ValueError('Expected one idle matching disclosure')
        report = reports[0]
        path = Path(report['local_path'])
        if path != Path('/app/evidence/600496/2025-12-31-annual.pdf'):
            raise ValueError('Unexpected evidence path')
        row = reviewed_row(extract_candidates(path))
        did = report['disclosure_id']

        def snapshot():
            return {
                'candidates': sorted(canonical(r) for r in db.execute(
                    'SELECT * FROM filing_candidates WHERE disclosure_id=%s', (did,)).fetchall()),
                'facts': sorted(canonical(r) for r in db.execute(
                    "SELECT * FROM data_points WHERE symbol='600496'").fetchall()),
                'disclosure': canonical(db.execute(
                    'SELECT * FROM official_disclosures WHERE disclosure_id=%s', (did,)).fetchone())}

        before = snapshot()
        additions = missing_candidates([json.loads(r) for r in before['candidates']], [row])
        if len(additions) != 1:
            raise ValueError('Candidate already exists; inspect instead of rerunning')

        def mutate():
            run = begin_run(db, 'register-reviewed-cross-page-debt-v33')
            store_filing_candidates(db, did, additions)
            after = snapshot()
            if after['facts'] != before['facts'] or after['disclosure'] != before['disclosure']:
                raise ValueError('Unexpected fact or disclosure mutation')
            added = set(after['candidates']) - set(before['candidates'])
            if len(added) != 1 or not set(before['candidates']).issubset(after['candidates']):
                raise ValueError('Existing candidates changed')
            candidate = json.loads(added.pop())
            if candidate['status'] != 'candidate_pending_automated_verification':
                raise ValueError('Candidate was not pending')
            end_run(db, run, 'succeeded', {'candidate_id': candidate['candidate_id'],
                'parser': ANNUAL_BACKFILL_PARSER_VERSION, 'pdf_sha256': PDF_HASH,
                'pending_only': True, 'facts_unchanged': True})
            return run, candidate['candidate_id']

        db.execute('SAVEPOINT rehearsal')
        rehearsal, _ = mutate()
        db.execute('ROLLBACK TO SAVEPOINT rehearsal')
        if snapshot() != before or db.execute('SELECT 1 FROM task_runs WHERE run_id=%s', (rehearsal,)).fetchone():
            raise ValueError('Rollback verification failed')
        run, candidate = mutate() if args.apply else (None, None)
        if not args.apply:
            db.rollback()
    print(json.dumps({'applied': args.apply, 'rollback_verified': True,
                      'run_id': str(run), 'candidate_id': candidate, 'verified_facts_added': 0}))


if __name__ == '__main__':
    main()
