"""Reconcile visually reviewed audited deposit rows with the annual report."""
from datetime import datetime, timezone
from decimal import Decimal as D
import hashlib
import json
from pathlib import Path

from pypdf import PdfReader
from build_moutai_business_evidence import ROOT, RELATIVE, EXPECTED, compact


def main():
    folder = 'runtime/historical-filing-index/20260909T030826765130Z/pdfs/'
    sources = [
        (RELATIVE, EXPECTED),
        (folder + '600519-1222993904.pdf', '875129da0837f9a6819945e3b9ee0befc5ba3dbbac09121dbc4417926a042973'),
        (folder + '600519-1222993922.pdf', '22a0338b2613e98450300c533e9e017dcd789a873e501434820e5a4bb9d7613d'),
    ]
    for relative, expected in sources:
        if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != expected:
            raise ValueError('Original changed: ' + relative)
    annual = PdfReader(ROOT / RELATIVE)
    risk = PdfReader(ROOT / sources[1][0])
    snippets = [
        (annual, 121, '贵州茅台集团财务有限公司2,500,000,000.00贵州仁怀51投资设立'),
        (risk, 1, '贵州茅台酒股份有限公司12.7551'),
        (risk, 5, '资产总额为人民币1481.34亿元、负债总额为人民币1374.88亿元、所有者权益合计人民币106.46亿元'),
        (risk, 5, '净利润人民币11.75亿元'),
        (risk, 6, '公司在财务公司存款余额为人民币579.79亿元'),
        (annual, 13, '23,102,858,820.97'),
        (annual, 13, '12,034,492,909.95'),
    ]
    for document, page, snippet in snippets:
        if compact(snippet) not in compact(document.pages[page - 1].extract_text()):
            raise ValueError('Reviewed scope snippet absent: ' + snippet)
    # The scanned accountant table is visually transcribed, not OCR-approved.
    rows = [
        ('group_principal', '347180.60', '1447827.77'),
        ('group_interest', '32.90', '183.71'),
        ('group_subsidiaries_principal', '853779.87', '859153.28'),
        ('group_subsidiaries_interest', '2455.92', '3121.12'),
    ]
    checks = {}
    for name, column, annual_amount in [('opening', 1, '12034492909.95'), ('closing', 2, '23102858820.97')]:
        reconstructed = sum(D(row[column]) for row in rows) * D('10000')
        difference = D(annual_amount) - reconstructed
        # Four table cells round to 0.01 ten-thousand CNY; annual value to cents.
        bound = D(len(rows)) * D('50') + D('0.005')
        if abs(difference) > bound:
            raise ValueError('External deposits do not reconcile within published precision')
        checks[name] = {'reconstructed_CNY': str(reconstructed), 'annual_CNY': annual_amount,
                        'difference_CNY': str(difference), 'rounding_bound_CNY': str(bound),
                        'within_rounding': True}
    if D('1481.34') - D('1374.88') != D('106.46'):
        raise ValueError('Financial company balance sheet identity failed')
    result = {
        'symbol': '600519', 'period_end': '2024-12-31',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'sources': [{'path': path, 'sha256': digest} for path, digest in sources],
        'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'table_physical_page': 4, 'table_unit': 'CNY ten_thousand',
        'transcription_method': 'Agent visual inspection of rendered scanned original; no trustworthy text layer',
        'rows': [{'scope': name, 'opening': opening, 'closing': closing} for name, opening, closing in rows],
        'deposit_reconciliation': checks,
        'finance_company_ownership': '0.51',
        'finance_company_book_equity_CNY_100million': '106.46',
        'proportionate_book_equity_not_fair_value_CNY_100million': str(D('106.46') * D('0.51')),
        'proportionate_reported_profit_before_consolidation_adjustments_CNY_100million': str(D('11.75') * D('0.51')),
        'company_deposit_distinct_scope_CNY_100million': '579.79',
        'limitations': ['Auditor table and issuer risk report have different scopes',
                        'Rounded book equity is not fair value or distributable cash',
                        'No finance/industrial consolidation elimination bridge yet',
                        'No automated extraction verification of scanned numeric cells',
                        'Audit opinion is limited to the disclosed schedule, not valuation'],
        'production_approved': False, 'valuation_approved': False,
    }
    target = ROOT / 'runtime/company-research' / ('600519-finance-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    target.mkdir(parents=True, exist_ok=False)
    (target / 'evidence.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'output': str(target / 'evidence.json'), 'deposit_reconciliation': checks}))


if __name__ == '__main__':
    main()
