"""Read-only production-runtime replay of a hash-pinned parser release."""
import argparse
from collections import Counter
from decimal import Decimal
import hashlib
import json
import sys
from pathlib import Path

import value_investment_agent

# The probe is staged beside the four replacement modules; other dependencies
# continue to load from the read-only production package.
if '--installed' not in sys.argv:
    value_investment_agent.__path__.insert(0, str(Path(__file__).resolve().parent))
from value_investment_agent import db, candidate_review, filing_extract


def signature(row):
    return (row['field_name'], row['source_label'], row['page'],
            str(Decimal(row['value']).normalize()), row['unit'],
            row.get('unit_evidence_page'), row.get('unit_evidence_excerpt'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    parser.add_argument('plan', type=Path)
    parser.add_argument('inventory', type=Path)
    parser.add_argument('--installed', action='store_true')
    args = parser.parse_args()
    manifest = json.loads((args.bundle / 'manifest.json').read_text(encoding='utf-8'))
    for row in manifest['files']:
        loaded_path = Path(filing_extract.__file__).parent / row['name']
        if hashlib.sha256(loaded_path.read_bytes()).hexdigest() != row['after_sha256']:
            raise ValueError('Unexpected loaded module: ' + row['name'])
    plan = json.loads(args.plan.read_text(encoding='utf-8'))
    if hashlib.sha256(args.inventory.read_bytes()).hexdigest() != plan['inventory_sha256']:
        raise ValueError('Inventory mismatch')
    if filing_extract.ANNUAL_BACKFILL_PARSER_VERSION != plan['parser']:
        raise ValueError('Parser version mismatch')
    inventory = json.loads(args.inventory.read_text(encoding='utf-8'))
    for case in manifest.get('regression_cases', []):
        packet = filing_extract.extract_candidates(Path(case['path']))
        if packet['sha256'] != case['sha256']:
            raise ValueError('Regression PDF hash mismatch')
        rows = [r for r in packet['candidates'] if r['field_name'] == case['field_name']]
        if (len(rows) != 1 or rows[0]['value'] != case['value']
                or rows[0]['page'] != case['page']
                or case['excerpt_contains'] not in db.candidate_evidence_excerpt(rows[0])):
            raise ValueError('Real-PDF regression or stored lineage failed')
        print(json.dumps({'regression_case': case['path'], 'passed': True}), flush=True)
    originals = {r['disclosure_id']: r for r in inventory['reports']}
    results = []
    for report in plan['results']:
        original = originals[report['disclosure_id']]
        packet = filing_extract.extract_candidates(Path(original['local_path']))
        if packet['sha256'] != report['sha256']:
            raise ValueError('Original hash mismatch')
        if Counter(map(signature, packet['candidates'])) != Counter(map(signature, report['revised_candidates'])):
            raise ValueError('Server replay differs: ' + report['symbol'])
        unit_count = 0
        for row in packet['candidates']:
            excerpt = db.candidate_evidence_excerpt(row)
            if row.get('unit_evidence_page'):
                if row['unit_evidence_excerpt'] not in excerpt:
                    raise ValueError('Unit lineage lost')
                unit_count += 1
        results.append({'symbol': report['symbol'], 'candidates': len(packet['candidates']),
                        'report_unit_candidates': unit_count})
        print(json.dumps(results[-1]), flush=True)
    print(json.dumps({'reports': len(results), 'candidates': sum(r['candidates'] for r in results),
                      'server_replay_matches': True, 'database_written': False,
                      'results': results}))


if __name__ == '__main__':
    main()
