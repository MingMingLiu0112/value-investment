"""Retain provider snapshot and compare exact attributable-profit scope."""
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path

from value_investment_agent.adapters import SinaFinancialStatementsAdapter
from value_investment_agent.filing_extract import extract_candidates_from_pages, ANNUAL_BACKFILL_PARSER_VERSION
from value_investment_agent.pdf_text import extract_pages


def main():
    root = Path('runtime/shenzhen-energy-income-20260909')
    pdf = root / '000027-2026H1.pdf'
    expected = '181663cbf6a61cd35a5d3b87d3eaa2d2ee7810db0d76bb051eae3d4a2206f29e'
    if hashlib.sha256(pdf.read_bytes()).hexdigest() != expected:
        raise ValueError('Official evidence changed')
    official = [r for r in extract_candidates_from_pages(extract_pages(pdf)) if r['field_name'] == 'net_income']
    if len(official) != 1 or official[0]['unit'] != 'CNY':
        raise ValueError('Ambiguous official profit candidates')
    records = [r for r in SinaFinancialStatementsAdapter().fetch(['000027'], report_period='2026-06-30')
               if r.field_name == 'net_income']
    if len(records) != 1:
        raise ValueError('Missing or ambiguous supplemental profit')
    record = records[0]
    if record.point_metadata.get('statement_scope') != 'consolidated' or record.unit != 'CNY':
        raise ValueError('Supplemental profit scope is not consolidated CNY')
    digest = hashlib.sha256(record.raw_payload).hexdigest()
    snapshot = root / (digest + '.json')
    if snapshot.exists():
        if hashlib.sha256(snapshot.read_bytes()).hexdigest() != digest:
            raise ValueError('Existing snapshot corrupted')
    else:
        with snapshot.open('xb') as stream:
            stream.write(record.raw_payload)
    matched = record.value == Decimal(official[0]['value'])
    result = {'symbol': '000027', 'period': record.period_label,
              'official_sha256': expected, 'official_candidate': official[0],
              'official_parser': ANNUAL_BACKFILL_PARSER_VERSION,
              'provider_value': str(record.value), 'provider_sha256': digest,
              'provider_snapshot': str(snapshot), 'provider_url': record.source_url,
              'provider_parser': record.parser_version, 'provider_metadata': record.point_metadata,
              'fetched_at': record.fetched_at.isoformat(), 'exact_value_match': matched,
              'production_updated': False,
              'scope': 'Official disclosure and redistributed provider data agree; not an independent audit.'}
    target = root / ('crosscheck-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json')
    with target.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps({'report': str(target), 'exact_value_match': matched,
                      'provider_sha256': digest, 'production_updated': False}))
    if not matched:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
