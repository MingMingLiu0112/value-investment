"""Reconcile disclosed minority profit without substituting book value for value."""
from datetime import datetime, timezone
from decimal import Decimal as D
from fractions import Fraction
import json
from pathlib import Path

from check_moutai_ttm_comparability import ROOT, sha, texts


def main():
    report = ROOT/'runtime/historical-filing-index/20260909T033444358365Z/pdfs/600519-1225475868.pdf'
    finance = ROOT/'runtime/company-research/600519-finance-current-20260909T073502376364Z/600519-1225475863.pdf'
    hashes = ['0e10aa26be46b1cf3cd03f06e834c7fb98d5dd0d661b96f8fddd4af7e846a4f6',
              'cf2d50aa028fcf11ce9eb04746932b7a9be25c3e31d443295f77add844b1121b']
    if [sha(report), sha(finance)] != hashes:
        raise ValueError('Original changed')
    phrases = [(report, 31, '46,033,330,566.78'),
               (report, 31, '44,516,880,421.86'),
               (report, 31, '1,516,450,144.92'),
               (report, 86, '贵州茅台酒销售有限公司10,000,000.00贵州仁怀95投资设立'),
               (report, 87, '51,243,471,447.144,422,563,354.17'),
               (report, 87, '7,648,174.672,486,942.892,486,942.892,119,522.46'),
               (finance, 7, '净利润4.68亿元')]
    refs = []
    for path, page, phrase in phrases:
        if any(phrase not in text for text in texts(path, page)):
            raise ValueError(f'Original phrase mismatch: {page}, {phrase}')
        refs.append({'path': str(path.relative_to(ROOT)), 'page': page, 'excerpt': phrase})
    total, parent, minority = map(D, ['46033330566.78', '44516880421.86', '1516450144.92'])
    if total-parent != minority:
        raise ValueError('Consolidated allocation does not reconcile')
    sales_minority = D('1243471447.14')
    sales_profit = D('2486942.89')*10000
    # Subsidiary table is rounded to 0.01 ten-thousand CNY; allocation is in CNY.
    sales_residual = sales_profit*D('.05')-sales_minority
    if abs(sales_residual) > D('2.505'):
        raise ValueError('Subsidiary allocation exceeds disclosed rounding precision')
    finance_minority = D('4.68')*100000000*D('.49')
    other = minority-sales_minority-finance_minority
    if Fraction(other) != Fraction(minority)-Fraction(sales_minority)-Fraction('4.68')*100000000*Fraction(49,100):
        raise ValueError('Independent arithmetic mismatch')
    uncertainty = D('.005')*100000000*D('.49')
    result = {'symbol': '600519', 'period': '2026H1', 'unit': 'CNY',
        'sources': refs, 'source_method': 'One issuer source per fact; two decoding implementations, not independent sources',
        'consolidated_net_profit': str(total), 'parent_profit': str(parent),
        'minority_profit': str(minority), 'sales_minority_profit_disclosed': str(sales_minority),
        'sales_allocation_rounding_residual': str(sales_residual),
        'finance_minority_profit_estimate': str(finance_minority),
        'unassigned_minority_profit_estimate': str(other),
        'unassigned_minority_profit_rounding_range': [str(other-uncertainty), str(other+uncertainty)],
        'sales_share_of_total_minority_profit': str(sales_minority/minority),
        'valuation_approved': False,
        'model_constraints': [
            'Industrial FCFF includes sales subsidiaries at 100 percent; deduct industrial minority FAIR value, not only finance minority.',
            'Do not multiply all industrial operations by 95 percent: parent production and wholly-owned subsidiaries have different ownership.',
            'If financial subsidiary is separately valued at 51 percent equity, do not deduct its 49 percent minority again.',
            'Standalone finance profit times 49 percent is an allocation estimate, not proof of consolidated eliminations.',
            'Residual includes other subsidiaries and possible consolidation adjustments; it is not verified zero.',
            'Book minority equity and current minority earnings are not minority fair value.',
            'Use sales business forecast or explicitly justified minority claim range; no perpetual half-year doubling.']}
    out = ROOT/'runtime/company-research'/('600519-minority-bridge-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(parents=True)
    (out/'evidence.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'inputs': {str(p): sha(p) for p in [report, finance, Path(__file__)]}, 'evidence_sha256': sha(out/'evidence.json')}, indent=2), encoding='utf-8')
    print(json.dumps({'output':str(out), 'sales_rounding_residual':str(sales_residual), 'remaining_minorities':str(other), 'range':result['unassigned_minority_profit_rounding_range']}))


if __name__ == '__main__':
    main()
