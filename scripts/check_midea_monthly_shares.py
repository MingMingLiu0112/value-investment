"""Reconcile the reviewed monthly-return share table; no accounting EPS approval."""
import hashlib
import json
import re
from pathlib import Path

from pypdf import PdfReader

from value_investment_agent.pdf_text import extract_pages
from value_investment_agent.historical_asof import publication_date_upper_bound


ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / 'runtime/midea-monthly-shares/20260908T155205603488Z/midea-202509-monthly.pdf'
SHA = '11bd651623c597214119f3df719caaf0622f1728ce48909e294735af0c88b85d'
INDEX_SHA = '4189e602aee9a62a3c0c83ebf8d2a1c7594d7661cb5b455790524c4bccf7699d'


def reviewed_availability(index):
    rows = [r for r in index['News'] if r.get('ID') == 7812944]
    if (len(rows) != 1 or rows[0].get('formatedDate') != '03 October 2025'
            or rows[0].get('title') != 'Monthly Return of Equity Issuer on Movements in Securities for the month ended 30 September 2025'):
        raise ValueError('Monthly index date or identity mismatch')
    attachments = [a for a in index['Attachments'] if a.get('prID') == 7812944]
    if (len(attachments) != 1 or attachments[0].get('atID') != 3926930
            or attachments[0].get('filename') != 'HKEX-EPS_20251003_11869418_0.PDF'):
        raise ValueError('Monthly index attachment mismatch')
    return {'published_date_candidate': '2025-10-03',
            'available_at_candidate': publication_date_upper_bound('2025-10-03').isoformat(),
            'availability_method': 'china_publication_date_upper_bound',
            'timestamp_precision': 'date', 'index_pdf_date_agreement': True,
            'availability_bound_verified': False,
            'limitation': 'Date agreement is research evidence, not independently verified historical availability'}


def parse_reviewed_table(pages):
    first = ' '.join(pages[0].split())
    if not all(s in first for s in ('Midea Group Co., Ltd.',
            'For the month ended: 30 September 2025', 'Date Submitted: 03 October 2025')):
        raise ValueError('Wrong issuer or monthly period')
    table = ' '.join(pages[1].split())
    if 'II. Movements in Issued Shares and/or Treasury Shares' not in table:
        raise ValueError('Not the issued-share table')
    result = {}
    sections = re.split(r'(?=Class of shares )', table)
    for kind, code in (('H', '00300'), ('A', '000333')):
        blocks = [s for s in sections if s.startswith(f'Class of shares Ordinary shares Type of shares {kind} ')]
        if len(blocks) != 1:
            raise ValueError('Missing or duplicate share-class section: ' + kind)
        pattern = (rf'Class of shares Ordinary shares Type of shares {kind} '
                   rf'Listed on the Exchange \(Note 1\) (?:Yes|No) '
                   rf'Stock code \(if listed\) {code} Description .*?'
                   r'Number of issued shares \(excluding treasury shares\) '
                   r'Number of treasury shares Total number of issued shares '
                   r'Balance at close of preceding month [\d,]+ [\d,]+ [\d,]+ '
                   r'Increase / decrease \(-\) [-\d,]+ [-\d,]+ '
                   r'Balance at close of the month ([\d,]+) ([\d,]+) ([\d,]+)')
        matches = re.findall(pattern, blocks[0])
        if len(matches) != 1:
            raise ValueError('Missing or ambiguous share-class row: ' + kind)
        outstanding, treasury, issued = [int(n.replace(',', '')) for n in matches[0]]
        if outstanding <= 0 or treasury < 0 or outstanding + treasury != issued:
            raise ValueError('Share class does not reconcile: ' + kind)
        result[kind] = {'issued_excluding_treasury': outstanding,
                        'treasury': treasury, 'issued_total': issued}
    return result


def main():
    if hashlib.sha256(PDF.read_bytes()).hexdigest() != SHA:
        raise ValueError('Monthly original hash mismatch')
    index_raw = PDF.with_name('index.json').read_bytes()
    if hashlib.sha256(index_raw).hexdigest() != INDEX_SHA:
        raise ValueError('Monthly index hash mismatch')
    availability = reviewed_availability(json.loads(index_raw))
    pdfium = extract_pages(PDF)
    pypdf = [p.extract_text() or '' for p in PdfReader(PDF).pages]
    shares = parse_reviewed_table(pdfium)
    if shares != parse_reviewed_table(pypdf):
        raise ValueError('Monthly table decoder disagreement')
    issued = sum(r['issued_total'] for r in shares.values())
    treasury = sum(r['treasury'] for r in shares.values())
    outstanding = sum(r['issued_excluding_treasury'] for r in shares.values())
    if issued != 7682861544 or treasury != 98588844 or outstanding != 7584272700:
        raise ValueError('Reviewed total differs')
    if shares['A']['treasury'] != 97345744:
        raise ValueError('Does not match reviewed quarterly A-share account')
    result = {'symbol': '000333', 'period': '2025-09-30', 'monthly_submitted_date': '2025-10-03',
        'source_path': str(PDF.relative_to(ROOT)), 'source_sha256': SHA,
        'index_sha256': INDEX_SHA, 'availability_research': availability,
        'source_tier': 'issuer-embedded IR vendor copy; direct HKEX original not matched',
        'source_pages': [1, 2], 'share_classes': shares,
        'issued_total': issued, 'treasury_total': treasury,
        'issued_excluding_treasury_total': outstanding,
        'two_decoders_agree': True, 'quarterly_a_treasury_matches': True,
        'financial_facts_verified': False, 'backtest_ready': False,
        'limitations': ['Month-end outstanding shares are not period-weighted EPS shares',
            'A/H economic-rights and other equity adjustments require separate review',
            'Monthly submitted date is not a verified intraday publication timestamp',
            'Do not forward-fill across subsequent issuance or repurchase events',
            'Issuer reports and issuer-embedded copy are not independent financial sources']}
    output = ROOT / 'runtime/midea-monthly-share-reconciliation-20260908.json'
    output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
