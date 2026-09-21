"""Build read-only review packets; matching values alone never approve a source."""
import argparse
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path

from value_investment_agent.pdf_text import extract_pages


def build_packet(inventory_path, plan_path, manifests, group='fact_backed_requires_audit'):
    if group not in {'fact_backed_requires_audit', 'unpromoted_obsolete'}:
        raise ValueError('Unsupported review group')
    inventory = json.loads(inventory_path.read_text(encoding='utf-8'))
    plan = json.loads(plan_path.read_text(encoding='utf-8'))
    if hashlib.sha256(inventory_path.read_bytes()).hexdigest() != plan['inventory_sha256']:
        raise ValueError('Inventory does not match release plan')
    originals = {}
    for manifest in manifests:
        for row in json.loads(manifest.read_text(encoding='utf-8'))['results']:
            originals[(row['symbol'], row['period'], row['official_sha256'])] = manifest.parent / (row['symbol'] + '.pdf')
    candidates = {str(row['candidate_id']): row for row in inventory['candidates']}
    reports = {row['disclosure_id']: row for row in inventory['reports']}
    reviews = []
    for result in plan['results']:
        identifiers = result.get('plan', {}).get(group, [])
        if not identifiers:
            continue
        report = reports[result['disclosure_id']]
        key = (report['symbol'], report['report_period'], report['sha256'])
        path = originals[key]
        if hashlib.sha256(path.read_bytes()).hexdigest() != report['sha256']:
            raise ValueError('Original PDF hash mismatch')
        pages = extract_pages(path)
        for identifier in identifiers:
            old = candidates[identifier]
            if old['disclosure_id'] != report['disclosure_id']:
                raise ValueError('Candidate/report mismatch')
            matches = [row for row in result['revised_candidates']
                       if row['field_name'] == old['field_name']
                       and row['unit'] == old['unit']
                       and Decimal(str(row['value'])) == Decimal(str(old['value']))]
            selected_pages = {old['page_number']}
            for row in matches:
                selected_pages.add(row['page'])
                if row.get('unit_evidence_page'):
                    selected_pages.add(row['unit_evidence_page'])
            # Include preceding pages to expose continuing headers and scope.
            selected_pages |= {page - 1 for page in selected_pages if page > 1}
            reviews.append({
                'candidate_id': identifier, 'symbol': report['symbol'],
                'report_period': report['report_period'], 'source_url': report['source_url'],
                'sha256': report['sha256'], 'original_candidate': old,
                'same_value_candidates': matches,
                'pages': {str(page): pages[page - 1] for page in sorted(selected_pages)},
                'decision': 'scope_review_required',
                'independent_source_verification': False,
            })
    return {'created_at': datetime.now(timezone.utc).isoformat(),
            'inventory_sha256': plan['inventory_sha256'],
            'plan_sha256': hashlib.sha256(plan_path.read_bytes()).hexdigest(),
            'production_updated': False, 'review_group': group, 'reviews': reviews}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inventory', type=Path)
    parser.add_argument('plan', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('manifests', nargs='+', type=Path)
    parser.add_argument('--group', choices=['fact_backed_requires_audit', 'unpromoted_obsolete'],
                        default='fact_backed_requires_audit')
    args = parser.parse_args()
    packet = build_packet(args.inventory, args.plan, args.manifests, args.group)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(packet, stream, ensure_ascii=False, indent=2)
    print(json.dumps({'output': str(args.output), 'reviews': len(packet['reviews']),
                      'matched': sum(bool(row['same_value_candidates']) for row in packet['reviews']),
                      'production_updated': False}))


if __name__ == '__main__':
    main()
