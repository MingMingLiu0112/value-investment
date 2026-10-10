"""Retire reviewed unreferenced candidates after an in-transaction rollback rehearsal."""
import argparse
import hashlib
import json
from pathlib import Path
import uuid

from value_investment_agent.db import connect, begin_run, end_run
from value_investment_agent.settings import get_settings


def canonical(value):
    return json.dumps(value, default=str, sort_keys=True, ensure_ascii=False)


def snapshot(db, disclosure_ids, symbols):
    candidates = db.execute('SELECT * FROM filing_candidates WHERE disclosure_id=ANY(%s)',
                            (disclosure_ids,)).fetchall()
    facts = db.execute('SELECT * FROM data_points WHERE symbol=ANY(%s)', (symbols,)).fetchall()
    return {'candidates': sorted(canonical(r) for r in candidates),
            'facts': sorted(canonical(r) for r in facts)}


def mutate(db, identifiers, manifest, manifest_hash):
    run_id = begin_run(db, 'retire-reviewed-unpromoted-candidates')
    rows = db.execute('''UPDATE filing_candidates c SET status='superseded_by_parser'
        WHERE candidate_id=ANY(%s) AND status='candidate_pending_automated_verification'
        AND NOT EXISTS (SELECT 1 FROM data_points p
            WHERE p.metadata->>'candidate_id'=c.candidate_id::text)
        RETURNING candidate_id''', (identifiers,)).fetchall()
    if {r['candidate_id'] for r in rows} != set(identifiers):
        raise ValueError('Retirement preconditions changed')
    end_run(db, run_id, 'succeeded', {'manifest_sha256': manifest_hash,
            'review_sha256': manifest['review_sha256'], 'records': manifest['records'],
            'retired_count': len(rows), 'values_preserved': True})
    return run_id


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('review', type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    manifest_bytes = args.manifest.read_bytes()
    manifest = json.loads(manifest_bytes)
    review = json.loads(args.review.read_text(encoding='utf-8'))
    if hashlib.sha256(args.review.read_bytes()).hexdigest() != manifest['review_sha256']:
        raise ValueError('Review changed')
    if review['decision'] != 'reject_existing_field_mapping' or len(manifest['records']) != review['expected_count']:
        raise ValueError('Review scope mismatch')
    records = manifest['records']
    identifiers = [uuid.UUID(r['candidate']['candidate_id']) for r in records]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError('Duplicate candidate')
    disclosures = list({uuid.UUID(r['disclosure']['disclosure_id']) for r in records})
    symbols = sorted({r['disclosure']['symbol'] for r in records})
    manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
    with connect(get_settings().database_url) as db:
        db.execute("SET LOCAL lock_timeout='3s'")
        db.execute("SET LOCAL statement_timeout='30s'")
        db.execute('LOCK TABLE filing_candidates, data_points, official_disclosures IN SHARE ROW EXCLUSIVE MODE')
        checked = set()
        for record in records:
            old = record['candidate']
            live = db.execute('SELECT * FROM filing_candidates WHERE candidate_id=%s',
                              (uuid.UUID(old['candidate_id']),)).fetchone()
            if canonical(live) != canonical(old):
                raise ValueError('Candidate changed: ' + old['candidate_id'])
            disclosure = record['disclosure']
            did = uuid.UUID(disclosure['disclosure_id'])
            if did in checked:
                continue
            live_report = db.execute('SELECT * FROM official_disclosures WHERE disclosure_id=%s', (did,)).fetchone()
            if live_report is None or any(canonical(live_report[k]) != canonical(v) for k, v in disclosure.items()):
                raise ValueError('Disclosure changed')
            with Path(live_report['local_path']).open('rb') as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != disclosure['sha256']:
                    raise ValueError('Original PDF changed')
            checked.add(did)
        before = snapshot(db, disclosures, symbols)
        db.execute('SAVEPOINT candidate_rehearsal')
        rehearsal_id = mutate(db, identifiers, manifest, manifest_hash)
        after = snapshot(db, disclosures, symbols)
        expected = []
        for serialized in before['candidates']:
            row = json.loads(serialized)
            if uuid.UUID(row['candidate_id']) in identifiers:
                row['status'] = 'superseded_by_parser'
            expected.append(canonical(row))
        if after != {'candidates': sorted(expected), 'facts': before['facts']}:
            raise ValueError('Unexpected data mutation')
        db.execute('ROLLBACK TO SAVEPOINT candidate_rehearsal')
        if snapshot(db, disclosures, symbols) != before:
            raise ValueError('Rollback snapshot mismatch')
        if db.execute('SELECT 1 FROM task_runs WHERE run_id=%s', (rehearsal_id,)).fetchone():
            raise ValueError('Rehearsal audit survived rollback')
        run_id = None
        if args.apply:
            run_id = mutate(db, identifiers, manifest, manifest_hash)
            if snapshot(db, disclosures, symbols) != after:
                raise ValueError('Apply differs from rehearsed result')
        else:
            db.rollback()
    print(json.dumps({'applied': args.apply, 'run_id': str(run_id) if run_id else None,
                      'rehearsal_id': str(rehearsal_id), 'rollback_verified': True,
                      'candidate_count': len(identifiers), 'manifest_sha256': manifest_hash,
                      'before_snapshot_sha256': hashlib.sha256(canonical(before).encode()).hexdigest()}))


if __name__ == '__main__':
    main()
