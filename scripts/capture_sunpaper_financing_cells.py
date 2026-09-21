"""Retain mixed financing-table cells without approving a debt roll-forward."""
import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pdfplumber
from pypdf import PdfReader
from value_investment_agent.financing_table import amount_from_fragments

ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / 'runtime/candidate-financing-batch-20260909-01/002078-8ad0fa1bf25e.pdf'
SHA = '8ad0fa1bf25e1aa5a9d8470b759769ef7fa766366c53499c8b9d2a2dd88dd3e2'


def main():
    if hashlib.sha256(PDF.read_bytes()).hexdigest() != SHA:
        raise ValueError('Report hash mismatch')
    with pdfplumber.open(PDF) as document:
        page = document.pages[166]
        selected = [t for t in page.find_tables() if t.extract()[0] ==
                    ['项目', '期初余额', '本期增加', None, '本期减少', None, '期末余额']]
        if len(selected) != 1:
            raise ValueError('Missing or ambiguous reviewed table')
        table = selected[0]
        cells = table.extract()
        bbox = table.bbox
    rows = []
    for raw in cells[2:]:
        if len(raw) != 7 or any(v is None for v in raw):
            raise ValueError('Unexpected merged data cells')
        amounts = []
        for value in raw[1:]:
            number = amount_from_fragments(value.split()) if value.strip() else None
            if value.strip() and number is None:
                raise ValueError('Invalid wrapped amount')
            amounts.append(number)
        rows.append({'label': ''.join(raw[0].split()), 'amounts_cny': amounts,
                     'raw_cells': raw, 'financial_fact_verified': False})
    if rows[-1]['label'] != '合计' or len(rows) != 10:
        raise ValueError('Reviewed table identity differs')
    opening, cash_in, noncash_in, cash_out, noncash_out, closing = map(Decimal, rows[-1]['amounts_cny'])
    difference = opening + cash_in + noncash_in - cash_out - noncash_out - closing
    reader = PdfReader(PDF)
    notes = ''.join((reader.pages[154].extract_text() + reader.pages[155].extract_text()).split())
    note_checks = []
    for label, current, noncurrent in [
        ('长期借款', '2,906,228,660.36', '8,934,114,389.02'),
        ('租赁负债', '1,880,268.42', '21,512,948.83'),
    ]:
        if current not in notes or noncurrent not in notes:
            raise ValueError('Reviewed note evidence changed')
        total = Decimal(current.replace(',', '')) + Decimal(noncurrent.replace(',', ''))
        row = next(r for r in rows if r['label'] == label)
        if total != Decimal(row['amounts_cny'][-1]):
            raise ValueError('Current/noncurrent classification does not reconcile')
        note_checks.append({'label': label, 'current_cny': current.replace(',', ''),
            'noncurrent_cny': noncurrent.replace(',', ''), 'total_cny': str(total),
            'note_pages': [155, 156], 'arithmetic_matched': True,
            'independent_verification': False})
    if '125,175,000.74' not in notes or '应付融资租赁款' not in notes:
        raise ValueError('Financing lease payable note changed')
    lease_payable = next(r for r in rows if r['label'] == '长期应付款')
    if Decimal(lease_payable['amounts_cny'][-1]) != Decimal('125175000.74'):
        raise ValueError('Financing lease payable mismatch')
    result = {'symbol': '002078', 'period': '2025-12-31', 'physical_page': 167,
        'source_url': 'https://static.cninfo.com.cn/finalpage/2026-04-11/1225093922.PDF',
        'source_sha256': SHA, 'table_bbox': bbox, 'raw_headers': cells[:2], 'rows': rows,
        'columns': ['opening', 'cash_increase', 'noncash_increase', 'cash_decrease', 'noncash_decrease', 'closing'],
        'maturity_reconciliations': note_checks,
        'financing_lease_payable_current_cny': '125175000.74',
        'financing_lease_payable_noncurrent_printed_value': None,
        'uniform_liability_formula_residual_cny': str(difference),
        'uniform_liability_formula_applicable': False, 'complete_debt_verified': False,
        'limitations': ['Mixed assets, equity, liabilities and cash-flow-only rows',
            'Blank cells retained as null, not zero',
            'Notes identify all displayed financing lease payables as current; blank noncurrent cell remains null',
            'Table total cannot serve as interest-bearing debt',
            'Capture preserves evidence; no generic parser gate relaxed or production fact promoted']}
    output = ROOT / 'runtime/002078-mixed-financing-cells-20260909.json'
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'rows_captured': len(rows), 'formula_residual_cny': str(difference),
                      'complete_debt_verified': False}))


if __name__ == '__main__':
    main()
