"""Pin reviewed maturity-table evidence; do not mutate production facts."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from value_investment_agent.pdf_text import extract_pages

REVIEWED = {
    '6370821e-02dc-4f0b-b87b-01f61115d894': ('000027', 220),
    '70b13e74-1b41-43aa-855c-c0e8d5bb51d6': ('000550', 121),
    '10214eb4-a29a-451b-827d-4e336b70d23a': ('000729', 125),
    '3bd89ab9-b59c-4a05-bbcc-2898437b2590': ('000729', 125),
    'a4efa1eb-6375-4edd-b44d-0462d691e42e': ('000786', 177),
    '7cde81fb-3aba-44b9-b622-e060c031c74e': ('000786', 177),
}


def main():
    inventory_path = Path('runtime/candidate-release-inventory-20260908T200809243186Z.json')
    inventory = json.loads(inventory_path.read_text(encoding='utf-8'))
    reports = {r['disclosure_id']: r for r in inventory['reports']}
    originals = {}
    for folder in ('20260908T190624995858Z', '20260908T193116910096Z', '20260908T193617298492Z'):
        for path in (Path('runtime/income-gap-crosschecks') / folder).glob('*.pdf'):
            originals[hashlib.sha256(path.read_bytes()).hexdigest()] = path
    results = []
    for identifier, (symbol, number) in REVIEWED.items():
        candidate = next(r for r in inventory['candidates'] if r['candidate_id'] == identifier)
        report = reports[candidate['disclosure_id']]
        if (report['symbol'], candidate['page_number']) != (symbol, number):
            raise ValueError('Reviewed candidate identity changed')
        path = originals[report['sha256']]
        pages = extract_pages(path)
        page = pages[number - 1]
        compact = ''.join(page.split())
        if not any(marker in compact for marker in ('未折现的合同现金流量', '未折现剩余合同义务', '未经折现的合同现金流量')):
            raise ValueError('Reviewed maturity context missing')
        references = [r for r in inventory['facts'] if r['metadata']['candidate_id'] == identifier]
        if not references:
            raise ValueError('Expected fact reference missing')
        results.append({'candidate': candidate, 'symbol': symbol, 'report_period': report['report_period'],
                        'official_url': report['source_url'], 'official_sha256': report['sha256'],
                        'evidence_path': str(path), 'page': number, 'page_text': page,
                        'fact_ids': [r['data_point_id'] for r in references],
                        'reason': 'undiscounted_maturity_cashflow_not_carrying_amount_evidence',
                        'decision': 'quarantine_source_eligibility_after_transaction_rehearsal'})
    target = Path('runtime') / ('reviewed-maturity-facts-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json')
    with target.open('x', encoding='utf-8') as stream:
        json.dump({'inventory_sha256': hashlib.sha256(inventory_path.read_bytes()).hexdigest(),
                   'records': results, 'production_updated': False,
                   'remaining_protected_candidates': 'not classified by this focused review'},
                  stream, ensure_ascii=False, indent=2)
    print(json.dumps({'report': str(target), 'reviewed': len(results),
                      'fact_references': sum(len(r['fact_ids']) for r in results)}))


if __name__ == '__main__':
    main()
