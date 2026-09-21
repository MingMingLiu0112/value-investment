"""Replay an explicitly reviewed two-page financing table; no debt approval."""
import hashlib
import json
from pathlib import Path

import pdfplumber
from value_investment_agent.financing_cells import extract_financing_cells

ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / 'runtime/candidate-financing-batch-20260909-02/600141-9235c74ba25a.pdf'
SHA = '9235c74ba25a6a628ca6f79dca1939317263970eaa5e9d0cde713f37622eef7e'


def main():
    if hashlib.sha256(PDF.read_bytes()).hexdigest() != SHA:
        raise ValueError('Reviewed PDF hash mismatch')
    with pdfplumber.open(PDF) as document:
        left_page, right_page = document.pages[169:171]
        left_tables, right_tables = left_page.find_tables(), right_page.find_tables()
        left, right = left_tables[-1], right_tables[0]
        a, b = left.extract(), right.extract()
        if a[-1][0] != '专项应付款' or len(b) != 2 or b[0][0] != '' or b[1][0] != '合计':
            raise ValueError('Reviewed continuation identity changed')
        left_cells, right_cells = left.rows[-1].cells, right.rows[0].cells
        if len(left_cells) != 7 or len(right_cells) != 7:
            raise ValueError('Unexpected column count')
        for column, (lcell, rcell) in enumerate(zip(left_cells, right_cells)):
            tolerance = 1.0 if not a[-1][column] and not b[0][column] else .5
            if lcell is None or rcell is None or any(abs(lcell[i] - rcell[i]) > tolerance for i in (0, 2)):
                raise ValueError('Cross-page column alignment differs')
        context = left_page.crop((0, left_tables[-2].bbox[3], left_page.width, left.bbox[1])).extract_text()
        combined = a[:-1] + [[x + ('\n' + y if y else '') for x, y in zip(a[-1], b[0])]] + b[1:]
        result = extract_financing_cells(combined, context or '')
        if result is None or not result['balances_reconcile']:
            raise ValueError('Stitched table failed original component reconciliation')
        output = {'symbol': '600141', 'period': '2025-12-31',
            'source_url': 'https://static.cninfo.com.cn/finalpage/2026-04-04/1225080143.PDF',
            'source_sha256': SHA, 'physical_pages': [170, 171],
            'source_tables': [a, b], 'source_bboxes': [left.bbox, right.bbox],
            'context': context, 'extraction': result, 'complete_debt_verified': False,
            'limitations': ['Only this hash-pinned original and reviewed adjacent-page boundary',
                'Includes dividends and special payables; total is not interest-bearing debt',
                'Blank movement cells remain null', 'Same-document arithmetic is not independent verification']}
    path = ROOT / 'runtime/600141-financing-continuation-20260909.json'
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'rows': len(result['rows']), 'balances_reconcile': result['balances_reconcile'],
        'total_closing_cny': result['total']['amounts']['closing'], 'complete_debt_verified': False}))


if __name__ == '__main__':
    main()
