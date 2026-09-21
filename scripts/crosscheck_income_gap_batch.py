"""Bounded, retained-evidence replay for candidate companies missing profit verification."""
import argparse
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path

import requests
from value_investment_agent.adapters import SinaFinancialStatementsAdapter
from value_investment_agent.filing_extract import extract_candidates_from_pages, ANNUAL_BACKFILL_PARSER_VERSION
from value_investment_agent.pdf_text import extract_pages


def retain(path, raw):
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError('Existing evidence differs: ' + str(path))
    else:
        with path.open('xb') as stream:
            stream.write(raw)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit', type=int, default=5)
    parser.add_argument('--offset', type=int, default=0)
    args = parser.parse_args()
    if not 1 <= args.limit <= 10:
        parser.error('limit must be between 1 and 10')
    if args.offset < 0:
        parser.error('offset must be nonnegative')
    gaps = json.loads(Path('runtime/ratio-input-gaps-scoped-20260909.json').read_text(encoding='utf-8'))
    payload_path = Path('runtime/server-export-payload.json')
    if hashlib.sha256(payload_path.read_bytes()).hexdigest() != gaps['payload_sha256']:
        raise ValueError('Gap list no longer matches current export; regenerate it')
    eligible = [r for r in gaps['rows'] if r['reasons'] == ['net_income:not_accepted:pending']]
    selected = eligible[args.offset:args.offset + args.limit]
    if not selected:
        parser.error('No candidates in requested range')
    root = Path('runtime/income-gap-crosschecks') / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    root.mkdir(parents=True)
    session = requests.Session()
    session.trust_env = False
    results = []
    for row in selected:
        symbol = row['symbol']
        result = {'symbol': symbol, 'period': row['period'], 'status': 'unresolved'}
        try:
            official = row['input_records']['operating_cash_flow']
            url, digest = official['source_url'], official['sha256']
            if official['source_name'] != 'CNINFO statutory disclosure' or not url.startswith('https://static.cninfo.com.cn/'):
                raise ValueError('Missing direct pinned statutory PDF')
            response = session.get(url, timeout=(15, 90))
            response.raise_for_status()
            if hashlib.sha256(response.content).hexdigest() != digest:
                raise ValueError('Official document hash mismatch')
            pdf = root / (symbol + '.pdf')
            retain(pdf, response.content)
            candidates = [c for c in extract_candidates_from_pages(extract_pages(pdf)) if c['field_name'] == 'net_income']
            result.update(official_url=url, official_sha256=digest, official_candidates=candidates,
                          official_parser=ANNUAL_BACKFILL_PARSER_VERSION)
            providers = [p for p in SinaFinancialStatementsAdapter().fetch([symbol], report_period=row['period'])
                         if p.field_name == 'net_income']
            if len(providers) != 1:
                raise ValueError('Missing or ambiguous provider attributable profit')
            provider = providers[0]
            provider_hash = hashlib.sha256(provider.raw_payload).hexdigest()
            retain(root / (provider_hash + '.json'), provider.raw_payload)
            result.update(provider_sha256=provider_hash, provider_value=str(provider.value),
                          provider_metadata=provider.point_metadata, provider_url=provider.source_url,
                          fetched_at=provider.fetched_at.isoformat())
            values = {(Decimal(c['value']), c['unit']) for c in candidates}
            matched = (values == {(provider.value, 'CNY')} and provider.unit == 'CNY'
                       and provider.point_metadata.get('statement_scope') == 'consolidated')
            result['status'] = 'matched_research_only' if matched else 'unresolved_scope_or_value'
        except Exception as error:
            result['error'] = str(error)
        results.append(result)
        retain(root / (symbol + '-result.json'), json.dumps(result, ensure_ascii=False, indent=2).encode())
        print(json.dumps({'symbol': symbol, 'status': result['status'], 'error': result.get('error')}, ensure_ascii=False), flush=True)
    retain(root / 'manifest.json', json.dumps({'results': results, 'production_updated': False,
        'selection_offset': args.offset, 'selection_limit': args.limit,
        'payload_sha256': gaps['payload_sha256'],
        'scope': 'Original disclosure versus redistributed provider, not independent audit or strategy validation'},
        ensure_ascii=False, indent=2).encode())
    print(str(root / 'manifest.json'))


if __name__ == '__main__':
    main()
