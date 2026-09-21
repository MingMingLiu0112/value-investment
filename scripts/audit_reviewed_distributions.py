"""Recheck archived entitlement evidence; does not certify historical coverage."""
import hashlib
import argparse
import json
from pathlib import Path

from pypdf import PdfReader
from value_investment_agent.corporate_actions import validate_cash_distribution


def reconcile_inventory(events, reports):
    by_id = {}
    for report in reports:
        key = (report['symbol'], str(report['announcement_id']))
        if key in by_id and any(by_id[key][f] != report[f] for f in ('sha256', 'url', 'title')):
            raise ValueError('Conflicting archive versions under one announcement ID')
        by_id[key] = report
    references = {(event['symbol'], evidence['url'], evidence['sha256'])
                  for event in events for evidence in event['evidence']}
    archived = {(r['symbol'], r['url'], r['sha256']) for r in by_id.values()}
    if references - archived:
        raise ValueError('Reviewed evidence missing from supplied archive manifests')
    superseded = {(event['symbol'], str(event['superseded_document_id']))
                  for event in events if event.get('superseded_document_id')}
    rows = []
    for key, report in sorted(by_id.items()):
        linked = (report['symbol'], report['url'], report['sha256']) in references
        replaced = key in superseded
        if linked and replaced:
            raise ValueError('Superseded document cannot also approve an entitlement')
        status = ('reviewed_evidence' if linked else
                  'superseded_retained' if replaced else 'unreviewed')
        rows.append({'symbol': key[0], 'announcement_id': key[1],
                     'title': report['title'], 'status': status})
    if superseded - set(by_id):
        raise ValueError('Superseded document missing from archive')
    return {'documents': len(rows), 'events': len(events),
            'unreviewed_documents': sum(r['status'] == 'unreviewed' for r in rows),
            'historical_coverage_certified': False, 'rows': rows}


def audit(path):
    packet = json.loads(path.read_text(encoding='utf-8'))
    seen = set()
    evidence_count = 0
    for event in packet['events']:
        validate_cash_distribution(event)
        key = (event['symbol'], event['record_date'])
        if key in seen:
            raise ValueError('Duplicate entitlement requires explicit event linkage')
        seen.add(key)
        for evidence in event['evidence']:
            raw_path = Path(evidence['path'])
            if hashlib.sha256(raw_path.read_bytes()).hexdigest() != evidence['sha256']:
                raise ValueError(f'Evidence hash mismatch: {raw_path}')
            count = len(PdfReader(raw_path).pages)
            if not evidence['pages'] or any(type(p) is not int or not 1 <= p <= count
                                            for p in evidence['pages']):
                raise ValueError('Invalid evidence page reference')
            evidence_count += 1
    return {'events': len(seen), 'evidence_references': evidence_count,
            'scope': 'Arithmetic, chronology, raw hashes and page bounds only',
            'strategy_approved': False, 'historical_coverage_certified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest-directory', type=Path, action='append', default=[])
    args = parser.parse_args()
    path = Path('docs/reviewed-cash-distributions.json')
    result = audit(path)
    if args.manifest_directory:
        reports = []
        for directory in args.manifest_directory:
            manifests = list(directory.glob('manifest-*.json'))
            if not manifests:
                raise ValueError(f'No manifests found: {directory}')
            for manifest in manifests:
                reports.extend(json.loads(manifest.read_text(encoding='utf-8')))
        result['archive_inventory'] = reconcile_inventory(
            json.loads(path.read_text(encoding='utf-8'))['events'], reports)
    print(json.dumps(result, ensure_ascii=False, indent=2))
