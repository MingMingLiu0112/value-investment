"""Bind a completed scope review to unchanged, unreferenced production candidates."""
import argparse
import csv
import hashlib
import json
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(review_path, triage_path, evidence_path, inventory_path):
    review = json.loads(review_path.read_text(encoding='utf-8'))
    if review['decision'] != 'reject_existing_field_mapping':
        raise ValueError('Explicit mapping rejection review required')
    if digest(triage_path) != review['triage_sha256'] or digest(evidence_path) != review['evidence_sha256']:
        raise ValueError('Reviewed evidence or triage changed')
    packet = json.loads(evidence_path.read_text(encoding='utf-8'))
    if packet['review_group'] != 'unpromoted_obsolete':
        raise ValueError('Wrong candidate group')
    with triage_path.open(encoding='utf-8', newline='') as stream:
        triage = list(csv.DictReader(stream))
    by_slot = {(r['symbol'], r['field_name'], int(r['page'])): r for r in triage}
    if len(by_slot) != len(triage) or len(triage) != review['expected_count']:
        raise ValueError('Duplicate or incomplete triage')
    inventory = json.loads(inventory_path.read_text(encoding='utf-8'))
    current = {r['candidate_id']: r for r in inventory['candidates']}
    reports = {r['disclosure_id']: r for r in inventory['reports']}
    referenced = {r['metadata'].get('candidate_id') for r in inventory['facts']}
    records = []
    seen = set()
    seen_slots = set()
    for evidence in packet['reviews']:
        old = evidence['original_candidate']
        identifier = old['candidate_id']
        slot = (evidence['symbol'], old['field_name'], old['page_number'])
        if slot not in by_slot or identifier in seen or slot in seen_slots:
            raise ValueError('Duplicate or unreviewed candidate')
        seen.add(identifier)
        seen_slots.add(slot)
        if current.get(identifier) != old:
            raise ValueError('Candidate changed since review: ' + identifier)
        if old['status'] != 'candidate_pending_automated_verification' or identifier in referenced:
            raise ValueError('Candidate is protected: ' + identifier)
        report = reports[old['disclosure_id']]
        for field, expected in [('symbol', evidence['symbol']),
                                ('report_period', evidence['report_period']),
                                ('sha256', evidence['sha256']), ('source_url', evidence['source_url'])]:
            if report[field] != expected:
                raise ValueError('Disclosure changed since review')
        records.append({'candidate': old, 'disclosure': report,
                        'reason': by_slot[slot]['reason']})
    if len(records) != review['expected_count'] or seen_slots != set(by_slot):
        raise ValueError('Incomplete evidence packet')
    return {'review_sha256': digest(review_path), 'inventory_sha256': digest(inventory_path),
            'evidence_sha256': digest(evidence_path), 'records': records,
            'status': 'reviewed_not_applied', 'production_updated': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('review', 'triage', 'evidence', 'inventory', 'output'):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    result = build(args.review, args.triage, args.evidence, args.inventory)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps({'output': str(args.output), 'records': len(result['records']),
                      'status': result['status']}))


if __name__ == '__main__':
    main()
