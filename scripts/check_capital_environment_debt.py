"""Reviewed note reconciliation, not approval of complete interest-bearing debt."""
import hashlib
import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from pypdf import PdfReader
from value_investment_agent.pdf_text import extract_pages

ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / 'runtime/candidate-financing-batch-20260909-01/600008-1540fcaf4ae3.pdf'
SHA = '1540fcaf4ae3cb08a63b9f2d2245956361b6ce20b4c2e5c891f040d23e9697a4'


def main():
    if hashlib.sha256(PDF.read_bytes()).hexdigest() != SHA:
        raise ValueError('Original report hash mismatch')
    required = {
        209: ['租赁负债', '单位：元', '195,160,440.30', '41,695,830.89', '153,464,609.41',
              '保理融资款', '300,000,000.00', '1,079,907,706.18', '439,659,832.89', '640,247,873.29'],
        210: ['专项应付款', '政府相关部门拨款', '104,475,910.28', '北京农投商业保理有限公司'],
        225: ['单位：万元', '107,990.78', '10,447.60', '19,516.04', '1年内到期列报调整前金额'],
    }
    pdfium = extract_pages(PDF)
    reader = PdfReader(PDF)
    for page, tokens in required.items():
        for text in (pdfium[page - 1], reader.pages[page - 1].extract_text() or ''):
            compact = ''.join(text.split())
            if any(token not in compact for token in tokens):
                raise ValueError(f'Reviewed page anchors differ: {page}')
    rows = []
    for field, total, current, noncurrent, rounded in [
        ('lease_liabilities', '195160440.30', '41695830.89', '153464609.41', '19516.04'),
        ('long_term_payables_before_current_reclassification', '1079907706.18', '439659832.89', '640247873.29', '107990.78'),
    ]:
        total, current, noncurrent, rounded = map(Decimal, (total, current, noncurrent, rounded))
        if total - current != noncurrent:
            raise ValueError('Maturity classification mismatch')
        unit_match = (total / 10000).quantize(Decimal('.01'), rounding=ROUND_HALF_UP) == rounded
        rows.append({'field': field, 'total_cny': str(total), 'current_cny': str(current),
            'noncurrent_cny': str(noncurrent), 'financing_table_cny_10k': str(rounded),
            'note_page': 209, 'financing_page': 225, 'maturity_arithmetic_matched': True,
            'rounded_table_matched': unit_match,
            'financing_minus_note_cny': str(rounded * 10000 - total),
            'table_status': 'matched_at_display_precision' if unit_match else 'unresolved_difference',
            'independent_cross_source_verified': False})
    result = {'symbol': '600008', 'period': '2025-12-31',
        'source_url': 'https://static.cninfo.com.cn/finalpage/2026-04-11/1225095393.PDF',
        'source_path': str(PDF.relative_to(ROOT)), 'source_sha256': SHA,
        'review_method': 'Manually reviewed note amounts; two-decoder anchor replay and Decimal reconciliation',
        'components': rows, 'factoring_financing_cny': '300000000.00',
        'special_payables_cny': '104475910.28',
        'special_payables_description': 'Government departmental appropriations; not automatically financing debt',
        'complete_debt_verified': False, 'backtest_ready': False,
        'limitations': ['Long-term payables total is not wholly classified as interest-bearing',
            'Local fiscal/national debt funds, government debt-swap bonds and other balances need scope review',
            'Factoring is included in long-term payables; do not add it twice',
            'Current maturities are already included in financing-table totals',
            'Two decoders and same-report reconciliation are not independent financial verification']}
    path = ROOT / 'runtime/600008-debt-note-reconciliation-20260909.json'
    path.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
