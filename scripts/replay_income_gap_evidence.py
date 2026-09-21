"""Re-evaluate retained batch evidence without network or promotion."""
import argparse
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path

from value_investment_agent.filing_extract import extract_candidates_from_pages, ANNUAL_BACKFILL_PARSER_VERSION
from value_investment_agent.pdf_text import extract_pages


def replay(manifest):
    packet = json.loads(manifest.read_text(encoding='utf-8'))
    results = []
    for previous in packet['results']:
        symbol = previous['symbol']
        result = {'symbol': symbol, 'period': previous['period'],
                  'previous_status': previous['status'], 'status': 'unresolved'}
        try:
            pdf = manifest.parent / (symbol + '.pdf')
            if hashlib.sha256(pdf.read_bytes()).hexdigest() != previous['official_sha256']:
                raise ValueError('Official evidence hash mismatch')
            digest = previous['provider_sha256']
            raw = (manifest.parent / (digest + '.json')).read_bytes()
            if hashlib.sha256(raw).hexdigest() != digest:
                raise ValueError('Provider evidence hash mismatch')
            provider = json.loads(raw)
            if provider['code'] != symbol or provider['report_date'] != previous['period']:
                raise ValueError('Provider symbol or report period mismatch')
            income = provider['income']
            if '合并' not in str(income.get('类型', '')):
                raise ValueError('Missing consolidated income scope')
            value = Decimal(str(income['归属于母公司所有者的净利润']))
            if not value.is_finite():
                raise ValueError('Nonfinite provider profit')
            candidates = [c for c in extract_candidates_from_pages(extract_pages(pdf))
                          if c['field_name'] == 'net_income']
            matched = {(Decimal(c['value']), c['unit']) for c in candidates} == {(value, 'CNY')}
            result.update(status='matched_research_only' if matched else 'unresolved_scope_or_value',
                          official_candidates=candidates, provider_value=str(value),
                          official_sha256=previous['official_sha256'], provider_sha256=digest)
        except (KeyError, ValueError, OSError, TypeError) as error:
            result['error'] = str(error)
        results.append(result)
    return {'manifest': str(manifest), 'parser': ANNUAL_BACKFILL_PARSER_VERSION,
            'results': results, 'production_updated': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifests', type=Path, nargs='+')
    args = parser.parse_args()
    reports = [replay(path) for path in args.manifests]
    target = Path('runtime/income-gap-crosschecks') / ('replay-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json')
    with target.open('x', encoding='utf-8') as stream:
        json.dump(reports, stream, ensure_ascii=False, indent=2)
    rows = [row for report in reports for row in report['results']]
    print(json.dumps({'report': str(target), 'examined': len(rows),
                      'matched': sum(r['status'] == 'matched_research_only' for r in rows),
                      'unresolved': [r['symbol'] for r in rows if r['status'] != 'matched_research_only']}))
