"""Join production inventory to hash-matched local originals without database writes."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from value_investment_agent.candidate_migration import plan_candidate_supersession
from value_investment_agent.filing_extract import extract_candidates, ANNUAL_BACKFILL_PARSER_VERSION


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('inventory', type=Path)
    parser.add_argument('manifests', type=Path, nargs='+')
    args = parser.parse_args()
    inventory = json.loads(args.inventory.read_text(encoding='utf-8'))
    originals = {}
    for manifest in args.manifests:
        for row in json.loads(manifest.read_text(encoding='utf-8'))['results']:
            originals[(row['symbol'], row['period'], row['official_sha256'])] = manifest.parent / (row['symbol'] + '.pdf')
    fact_ids = {row['metadata']['candidate_id'] for row in inventory['facts']}
    results = []
    for report in inventory['reports']:
        key = (report['symbol'], report['report_period'], report['sha256'])
        if key not in originals:
            results.append({'disclosure_id': report['disclosure_id'], 'symbol': report['symbol'],
                            'status': 'missing_hash_matched_original'})
            continue
        packet = extract_candidates(originals[key])
        if packet['sha256'] != report['sha256']:
            raise ValueError('Original changed during planning')
        existing = [row for row in inventory['candidates'] if row['disclosure_id'] == report['disclosure_id']]
        plan = plan_candidate_supersession(existing, packet['candidates'], fact_ids)
        result = {'disclosure_id': report['disclosure_id'], 'symbol': report['symbol'],
                  'period': report['report_period'], 'sha256': report['sha256'],
                  'status': 'planned_not_applied', 'plan': plan, 'revised_candidates': packet['candidates']}
        results.append(result)
        print(json.dumps({'symbol': report['symbol'], **{k: len(v) for k, v in plan.items()}}), flush=True)
    target = Path('runtime') / ('candidate-release-plan-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json')
    with target.open('x', encoding='utf-8') as stream:
        json.dump({'inventory': str(args.inventory),
                   'inventory_sha256': hashlib.sha256(args.inventory.read_bytes()).hexdigest(),
                   'parser': ANNUAL_BACKFILL_PARSER_VERSION, 'results': results,
                   'production_updated': False}, stream, ensure_ascii=False, indent=2)
    print(str(target))


if __name__ == '__main__':
    main()
