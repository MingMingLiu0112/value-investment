"""Add authenticated TTM overheads and other business to product scenarios."""
from datetime import datetime, timezone
from decimal import Decimal as D, localcontext
from fractions import Fraction as F
from pathlib import Path
import json
from check_moutai_ttm_comparability import ROOT, sha, texts
from build_moutai_product_ttm import SOURCES, DATA

# Same-scope operating revenue, cost, surcharges, selling, admin and R&D.
FIELDS = {
 'revenue': ('营业收入', ['168838102514.79','89389354416.84','90703260964.48'], ['44','41','43']),
 'cost': ('营业成本', ['14892277570.91','7777491083.93','9473762565.88'], ['44','41','43']),
 'surcharges': ('税金及附加', ['27354227684.88','13942384581.48','14682159453.47'], ['46','43','45']),
 'selling': ('销售费用', ['7253499600.68','3260462949.46','3206308341.53'], ['47','44','46']),
 'admin': ('管理费用', ['8320061659.66','3694704172.74','3635355263.82'], ['48','45','47']),
 'research': ('研发费用', ['190112246.58','73901545.96','114926219.60'], ['49','46','48']),
}

def main():
    decoded = []
    for (_,path,digest,_), page in zip(SOURCES, (61,28,30)):
        if sha(ROOT/path) != digest:
            raise ValueError('Original changed')
        decoded.append(texts(ROOT/path,page))
    facts = {}
    for field, (label, values, notes) in FIELDS.items():
        for i in range(3):
            phrase = label+notes[i]+format(D(values[i]),',.2f')
            if any(t.count(phrase) != 1 for t in decoded[i]):
                raise ValueError('Unique source row mismatch: '+field+' '+str(i))
        value = D(values[0])-D(values[1])+D(values[2])
        if F(value) != F(values[0])-F(values[1])+F(values[2]):
            raise ValueError('TTM recomputation failed')
        facts[field] = str(value)
    product = {}
    for index, field in ((1,'revenue'),(2,'cost')):
        product[field] = sum(D(rows[0][index])-D(rows[1][index])+D(rows[2][index]) for rows in DATA.values())
    other = {field: str(D(facts[field])-product[field]) for field in product}
    path = ROOT/'runtime/company-research/600519-product-forecast-20260909T103718221562Z/evidence.json'
    manifest = json.loads((path.parent/'manifest.json').read_text(encoding='utf-8'))
    if sha(path) != manifest['evidence_sha256']:
        raise ValueError('Product forecast changed')
    forecast = json.loads(path.read_text(encoding='utf-8'))
    results = {}
    with localcontext() as ctx:
        ctx.prec = 50
        for scenario, input_result in forecast['results'].items():
            rows = []
            for original in input_result['combined']:
                revenue = D(original['revenue'])+D(other['revenue'])
                cost = D(original['cost'])+D(other['cost'])
                expenses = {f: revenue*D(facts[f])/D(facts['revenue']) for f in ('surcharges','selling','admin','research')}
                residual = revenue-cost-sum(expenses.values())
                independent = F(revenue)-F(cost)-sum(F(revenue)*F(facts[f])/F(facts['revenue']) for f in expenses)
                if abs(F(residual)-independent) > F(1,1000000):
                    raise ValueError('Independent overhead forecast recomputation failed')
                rows.append({'period_end': original['period_end'], 'operating_revenue': str(revenue),
                    'operating_cost': str(cost), 'expenses': {k:str(v) for k,v in expenses.items()},
                    'subtotal_with_shared_consolidated_expenses': str(residual)})
            results[scenario] = rows
    out = ROOT/'runtime/company-research'/('600519-operating-forecast-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir()
    payload = {'symbol':'600519','version':'operating-forecast-research-v1','unit':'CNY',
        'source_bindings': [{'path':p,'sha256':h,'page':page} for (_,p,h,_),page in zip(SOURCES,(61,28,30))],
        'original_values':FIELDS,'ttm_facts':facts,'other_business_ttm':other,
        'product_forecast_path':str(path.relative_to(ROOT)),'product_forecast_sha256':sha(path),
        'assumptions': [
            'Other-business revenue and cost held at verified TTM amounts, explicitly not missing=zero.',
            'Surcharges and overheads scale at their TTM ratios to same-scope operating revenue. This is an analyst baseline, not a statutory tax rate or verified cost elasticity.',
            'Constant expense ratios do not capture channel/consumption-tax changes or operating leverage; sensitivity and external review remain required.',
            'The rolling full periods include elapsed time at the September information date and are not dated remaining cash flows.',
        ],'results':results,'independent_fraction_checks':'passed',
        'industrial_ebit_approved':False,'fcff_approved':False,'equity_value_approved':False,
        'scope_blockers':['Consolidated overheads include finance-company/shared expenses; allocation still needed.',
            'No financial interest profit, industrial interest, cash taxes, D&A, capex or working capital has been silently set to zero.',
            'Do not discount this subtotal or publish it as EBIT/FCFF/fair value.']}
    (out/'evidence.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'script_sha256':sha(Path(__file__)),
        'evidence_sha256':sha(out/'evidence.json')},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'ttm':facts,'other_business':other,
        'first_year_subtotal':{s:r[0]['subtotal_with_shared_consolidated_expenses'] for s,r in results.items()}}))

if __name__ == '__main__':
    main()
