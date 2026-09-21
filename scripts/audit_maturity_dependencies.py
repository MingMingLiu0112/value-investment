"""Persist the exact production dependency closure for reviewed maturity sources."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from value_investment_agent.evidence_dependencies import affected_point_ids


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inventory', type=Path)
    parser.add_argument('review', type=Path)
    args = parser.parse_args()
    inventory = json.loads(args.inventory.read_text(encoding='utf-8'))
    review = json.loads(args.review.read_text(encoding='utf-8'))
    points = {r['data_point_id']: r for r in inventory['dependency_points'] + inventory['facts']}
    initial = []
    for record in review['records']:
        for identifier in record['fact_ids']:
            point = points[identifier]
            candidate = record['candidate']
            if (point['symbol'], point['period_label'], point['field_name'],
                point['metadata'].get('candidate_id'), point['metadata'].get('official_file_sha256')) != (
                    record['symbol'], record['report_period'], candidate['field_name'],
                    candidate['candidate_id'], record['official_sha256']):
                raise ValueError('Reviewed production identity or provenance changed')
            initial.append(identifier)
    affected = affected_point_ids(list(points.values()), initial)
    rows = [points[identifier] for identifier in sorted(affected)]
    output = {'inventory_sha256': hashlib.sha256(args.inventory.read_bytes()).hexdigest(),
              'review_sha256': hashlib.sha256(args.review.read_bytes()).hexdigest(),
              'initial_ids': initial, 'affected_points': rows,
              'fields': dict(Counter(r['field_name'] for r in rows)),
              'symbols': sorted({r['symbol'] for r in rows}),
              'production_updated': False, 'rehearsal_completed': False,
              'required_refresh': ['financial_quality', 'valuations', 'export_and_canonical_excel']}
    target = Path('runtime') / ('maturity-dependency-audit-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json')
    with target.open('x', encoding='utf-8') as stream:
        json.dump(output, stream, ensure_ascii=False, indent=2)
    print(json.dumps({'report': str(target), 'initial': len(initial),
                      'affected': len(rows), 'fields': output['fields']}))


if __name__ == '__main__':
    main()
