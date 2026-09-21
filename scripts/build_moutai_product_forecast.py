"""Company-specific operating scenarios, separate from approved equity value."""
from datetime import datetime, timezone
from decimal import Decimal as D, localcontext
from fractions import Fraction as F
from pathlib import Path
import hashlib
import json

ROOT = Path('D:/GPTProject/value-investment')
INPUT = ROOT/'runtime/company-research/600519-product-ttm-20260909T100540678699Z/evidence.json'
INPUT_SHA = 'a33a1be115ecf49f67c1e181e68f33e38e2dde5657342f6945067274560de1c8'
# Analyst stress assumptions, not observed facts or calibrated optimal parameters.
SCENARIOS = {
    'bear': {'moutai': ('-.05', '.02'), 'series': ('-.10', '.03')},
    'base': {'moutai': ('.02', '.01'), 'series': ('-.02', '.01')},
    'bull': {'moutai': ('.05', '0'), 'series': ('.03', '0')},
}

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    if sha(INPUT) != INPUT_SHA:
        raise ValueError('Pinned historical operating input changed')
    baseline = json.loads(INPUT.read_text(encoding='utf-8'))
    for _, path, digest, _ in baseline['source_bindings']:
        if sha(ROOT/path) != digest:
            raise ValueError('Original filing changed')
    results = {}
    with localcontext() as context:
        context.prec = 50
        for scenario, assumptions in SCENARIOS.items():
            products = {}
            for product, (growth, cost_shift) in assumptions.items():
                start = baseline['products'][product]
                revenue = D(start['revenue']['TTM_to_2026_06_30'])
                cost = D(start['cost']['TTM_to_2026_06_30'])
                initial_revenue, initial_cost = revenue, cost
                rows = []
                for step in range(1, 6):
                    revenue *= 1+D(growth)
                    # Permanent level stress in year one; no automatic margin recovery.
                    cost = initial_cost*(revenue/initial_revenue)+revenue*D(cost_shift)
                    independent_revenue = F(initial_revenue)*(1+F(growth))**step
                    independent_cost = F(initial_cost)*(1+F(growth))**step+independent_revenue*F(cost_shift)
                    for actual, expected in ((revenue, independent_revenue), (cost, independent_cost)):
                        if abs(F(actual)-expected) > F(1, 1000000):
                            raise ValueError('Independent rational recomputation failed')
                    rows.append({'period_start': f'{2025+step}-07-01',
                                 'period_end': f'{2026+step}-06-30',
                                 'revenue': str(revenue), 'cost': str(cost),
                                 'gross_profit': str(revenue-cost),
                                 'gross_margin': str(1-cost/revenue)})
                products[product] = rows
            results[scenario] = {'products': products, 'combined': [
                {'period_end': products['moutai'][i]['period_end'],
                 **{field: str(sum(D(products[p][i][field]) for p in products))
                    for field in ('revenue', 'cost', 'gross_profit')}} for i in range(5)]}
        for step in range(5):
            for field in ('revenue', 'gross_profit'):
                ordered = [D(results[s]['combined'][step][field]) for s in ('bear', 'base', 'bull')]
                if ordered != sorted(ordered):
                    raise ValueError('Scenario ordering failed')
    payload = {
        'symbol': '600519', 'version': 'product-operating-scenarios-research-v1',
        'unit': 'CNY', 'historical_input_sha256': INPUT_SHA,
        'historical_input_path': str(INPUT.relative_to(ROOT)),
        'as_of_information_date': '2026-09-09',
        'forecast_clock': 'Five rolling July-June years after the June 2026 TTM; not calendar FY forecasts.',
        'assumptions': SCENARIOS, 'assumption_units': ['annual_revenue_growth', 'cost_ratio_level_increase'],
        'assumption_basis': {
            'growth': 'FY2025 liquor revenue -1.08%, volume +2.13%, implied mix/price -3.1431%; H12026 Moutai +2.8238%, series -6.0188%. Base deliberately assumes moderation and partial series recovery, not a fact.',
            'cost': 'H12026 gross margins declined approximately 1.5700pp and 4.0004pp for Moutai and series. Bear stresses the TTM cost ratios by a further 2pp/3pp; base by 1pp each; bull assumes no further deterioration, not reversal.',
            'horizon': 'Constant growth isolates persistent franchise stress. It is an analyst experiment, not a demand forecast validated for five years.',
        },
        'counterevidence_and_falsifiers': [
            'Positive Moutai H1 revenue did not translate into matching gross profit growth; mix and costs can overwhelm nominal growth.',
            'Series revenue contraction with increasing cost contradicts an automatic recovery assumption.',
            'Base and bull require subsequent same-period revenue and margin evidence; further deterioration invalidates them.',
            'Production of base liquor cannot substantiate contemporaneous sales volume or revenue.',
        ],
        'results': results, 'independent_recomputation': 'Fraction closed-form values vs iterative Decimal, tolerance < CNY 0.000001',
        'forecast_approved': False, 'equity_valuation_approved': False,
        'remaining_dependencies': [
            'Independent industry/peer counterevidence and explicit forecast assumption review',
            'Other-business revenue, consumption taxes, selling/admin/R&D and financial/shared expense allocation',
            'Cash taxes, reinvestment and full working capital',
            'Financial subsidiary, cash, debt, minority interests and current ordinary-share bridge',
            'Discount-rate and terminal economics; historical strategy ledger and aligned benchmark',
        ],
    }
    out = ROOT/'runtime/company-research'/('600519-product-forecast-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir()
    (out/'evidence.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# 茅台三情景经营预测初稿', '',
             '这是产品收入与毛利压力实验，不是公司合理价或交易批准。全部金额单位为亿元。', '',
             '| 情景 | 滚动年度结束 | 收入 | 毛利 |', '| --- | --- | ---: | ---: |']
    for scenario, result in results.items():
        for row in result['combined']:
            lines.append(f"| {scenario} | {row['period_end']} | {D(row['revenue'])/D('1e8'):.2f} | {D(row['gross_profit'])/D('1e8'):.2f} |")
    lines += ['', '增长和成本参数是单列的研究假设，具体依据、反证和待完成范围见同目录 evidence.json。',
              '滚动年度不冒充会计年度；毛利不冒充EBIT、FCFF或归母利润。未解决范围不得以零填充。']
    (out/'research.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'script_sha256': sha(Path(__file__)),
        'evidence_sha256': sha(out/'evidence.json'), 'report_sha256': sha(out/'research.md')}, indent=2), encoding='utf-8')
    print(json.dumps({'output': str(out), 'independent_recomputation': 'passed',
                      'first_year': {s: r['combined'][0] for s, r in results.items()}}))

if __name__ == '__main__':
    main()
