"""Current financial-subsidiary scope, rounded facts; no fair-value inference."""
from datetime import datetime, timezone
from decimal import Decimal as D
from fractions import Fraction
import json
from pathlib import Path

from check_moutai_ttm_comparability import ROOT, sha, texts


def main():
    original = ROOT/'runtime/company-research/600519-finance-current-20260909T073502376364Z/600519-1225475863.pdf'
    expected = 'cf2d50aa028fcf11ce9eb04746932b7a9be25c3e31d443295f77add844b1121b'
    interim = ROOT/'runtime/historical-filing-index/20260909T033444358365Z/pdfs/600519-1225475868.pdf'
    if sha(original) != expected or sha(interim) != '0e10aa26be46b1cf3cd03f06e834c7fb98d5dd0d661b96f8fddd4af7e846a4f6':
        raise ValueError('Original changed')
    snippets = [(original, 1, '贵州茅台酒股份有限公司12.7551'),
        (original, 7, '资产总额为1571.36亿元、负债总额为1451.96亿元、所有者权益合计119.41亿元'),
        (original, 7, '2026年1-6月，财务公司实现营业收入15.76亿元，实现利润总额8.02亿元，净利润4.68亿元'),
        (original, 7, '资本充足率≥10.5%20.94%'),
        (original, 8, '公司在财务公司存款余额为301.45亿元，无贷款'),
        (interim, 86, '贵州茅台集团财务有限公司2,500,000,000.00贵州仁怀51投资设立')]
    evidence = []
    for path, page, phrase in snippets:
        if any(phrase not in value for value in texts(path, page)):
            raise ValueError(f'Reviewed original phrase mismatch: {page}')
        evidence.append({'path': str(path.relative_to(ROOT)), 'physical_page': page, 'excerpt': phrase})
    values = {'assets': '1571.36', 'liabilities': '1451.96', 'equity': '119.41',
              'revenue_h1': '15.76', 'pretax_profit_h1': '8.02', 'net_profit_h1': '4.68',
              'issuer_deposit': '301.45'}
    residual = D(values['assets'])-D(values['liabilities'])-D(values['equity'])
    bound = D('0.005')*3
    if abs(residual) > bound:
        raise ValueError('Balance-sheet rounding reconciliation failed')
    equity_share = D(values['equity'])*D('0.51')
    profit_share = D(values['net_profit_h1'])*D('0.51')
    if Fraction(equity_share) != Fraction('119.41')*Fraction(51,100):
        raise ValueError('Independent equity-share calculation failed')
    out = ROOT/'runtime/company-research'/('600519-finance-scope-current-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(parents=True, exist_ok=False)
    result = {'symbol': '600519', 'period_end': '2026-06-30', 'source_unit': 'CNY_100million',
        'ownership': '0.51', 'rounded_disclosed_values': values, 'evidence': evidence,
        'balance_residual': str(residual), 'rounding_bound': str(bound),
        'proportionate_book_equity': str(equity_share), 'proportionate_h1_profit': str(profit_share),
        'pretax_minus_net_profit': str(D('8.02')-D('4.68')),
        'pretax_minus_net_ratio': str((D('8.02')-D('4.68'))/D('8.02')),
        'fair_value_approved': False, 'industrial_financial_eliminations_approved': False,
        'cash_tax_rate_approved': False, 'financial_capital_release_approved': False,
        'interpretation': ['Ownership-weighted book figures are not fair value or distributable dividends',
            'Issuer deposits at controlled subsidiary are intra-consolidation balances; do not add twice',
            'Pretax-minus-net gap is not verified cash income tax; investigate before forecasting',
            'Reported capital ratio above minimum does not measure freely releasable equity',
            'Rounded issuer risk report is not an independent audit; retain rounding bounds']}
    (out/'evidence.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    inputs = [original, interim, Path(__file__), ROOT/'scripts/check_moutai_ttm_comparability.py']
    (out/'manifest.json').write_text(json.dumps({'inputs':{str(p):sha(p) for p in inputs},
        'evidence_sha256':sha(out/'evidence.json')},indent=2),encoding='utf-8')
    print(json.dumps({'output': str(out), 'proportionate_book_equity_CNY_100million':str(equity_share),
        'proportionate_h1_profit_CNY_100million':str(profit_share), 'rounding_reconciled':True}))


if __name__ == '__main__':
    main()
