"""Register a reviewed scanned statement as pending, never as a verified fact."""
import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import uuid

from value_investment_agent.db import connect, begin_run, end_run
from value_investment_agent.settings import get_settings


def validate(review, image):
    if (review['scope'] != 'consolidated' or review['unit'] != 'CNY'
            or review['field_name'] != 'current_portion_long_term_debt'
            or review['status'] != 'candidate_pending_automated_verification'
            or review['same_pdf_is_not_independent_source'] is not True):
        raise ValueError('Unexpected review scope')
    if type(review['page_number']) is not int or review['page_number'] < 1:
        raise ValueError('Invalid page')
    values = [Decimal(value) for value in review['note_components_cny']]
    total = Decimal(review['value'])
    if not values or not total.is_finite() or total < 0 or any(not v.is_finite() or v < 0 for v in values):
        raise ValueError('Invalid amounts')
    if sum(values) != total or Decimal(review['note_total_cny']) != total:
        raise ValueError('Note does not reconcile')
    if hashlib.sha256(image.read_bytes()).hexdigest() != review['image_sha256']:
        raise ValueError('Reviewed image changed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('review', type=Path)
    parser.add_argument('image', type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    raw = args.review.read_bytes()
    review = json.loads(raw)
    validate(review, args.image)
    review_hash = hashlib.sha256(raw).hexdigest()
    excerpt = review['excerpt'] + '\n图像SHA-256：' + review['image_sha256'] + '\n阅核清单SHA-256：' + review_hash
    if len(excerpt) > 1000:
        raise ValueError('Evidence excerpt too long')
    with connect(get_settings().database_url) as db:
        db.execute("SET LOCAL lock_timeout='3s'")
        db.execute("SET LOCAL statement_timeout='20s'")
        db.execute('LOCK TABLE filing_candidates, official_disclosures, data_points IN SHARE ROW EXCLUSIVE MODE')
        reports = db.execute('''SELECT * FROM official_disclosures
            WHERE symbol=%s AND report_period=%s AND sha256=%s AND source_url=%s AND report_kind=%s''',
            (review['symbol'], review['report_period'], review['official_sha256'], review['source_url'], review['report_kind'])).fetchall()
        if len(reports) != 1:
            raise ValueError('Ambiguous or changed disclosure')
        report = reports[0]
        with Path(report['local_path']).open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != review['official_sha256']:
                raise ValueError('Original PDF changed')
        did = report['disclosure_id']
        existing = db.execute('''SELECT * FROM filing_candidates WHERE disclosure_id=%s
            AND field_name=%s AND page_number=%s AND source_label=%s''',
            (did, review['field_name'], review['page_number'], review['source_label'])).fetchone()
        if existing:
            raise ValueError('Candidate slot occupied; inspect before proceeding')
        def snapshot():
            return json.dumps({
                'candidates': db.execute('SELECT * FROM filing_candidates WHERE disclosure_id=%s ORDER BY candidate_id', (did,)).fetchall(),
                'facts': db.execute('SELECT * FROM data_points WHERE symbol=%s ORDER BY data_point_id', (review['symbol'],)).fetchall()
            }, default=str, sort_keys=True)
        before = snapshot()
        cid = uuid.uuid4()
        def mutate():
            run_id = begin_run(db, 'register-visual-debt-candidate')
            db.execute('''INSERT INTO filing_candidates(candidate_id,disclosure_id,field_name,value,unit,
                page_number,source_label,excerpt,parser_version,status)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                (cid,did,review['field_name'],Decimal(review['value']),review['unit'],review['page_number'],
                 review['source_label'],excerpt,'visual-filing-review-v1',review['status']))
            end_run(db, run_id, 'succeeded', {'review': review, 'review_sha256': review_hash,
                    'candidate_id': str(cid), 'verified_facts_added': 0})
            return run_id
        db.execute('SAVEPOINT visual_rehearsal')
        rehearsal = mutate()
        db.execute('ROLLBACK TO SAVEPOINT visual_rehearsal')
        if snapshot() != before or db.execute('SELECT 1 FROM task_runs WHERE run_id=%s', (rehearsal,)).fetchone():
            raise ValueError('Rollback mismatch')
        run_id = mutate() if args.apply else None
        if not args.apply:
            db.rollback()
    print(json.dumps({'applied': args.apply, 'rollback_verified': True,
                      'candidate_id': str(cid), 'run_id': str(run_id) if run_id else None,
                      'verified_facts_added': 0}))


if __name__ == '__main__':
    main()
