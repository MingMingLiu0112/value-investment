"""Authenticate cash capex and D&A; preserve consolidation and lease scope."""
from datetime import datetime, timezone
from decimal import Decimal as D
from fractions import Fraction as F
from pathlib import Path
import json
from check_moutai_ttm_comparability import ROOT, sha, texts
from build_moutai_product_ttm import SOURCES

ROWS = {
 'cash_capex': ('购建固定资产、无形资产和其他长期资产支付的现金',
                ['3127594916.41','1595995809.23','832142752.28'], [13,32,34]),
 'fixed_asset_depreciation': ('固定资产折旧、油气资产折耗、生产性生物资产折旧',
                ['1893338311.91','940703752.88','1019596188.09'], [115,77,81]),
 'rou_amortization': ('使用权资产摊销', ['55797324.89','26052929.46','25933200.71'], [115,77,81]),
 'intangible_amortization': ('无形资产摊销', ['289613682.99','139668544.83','153074255.31'], [115,77,81]),
 'deferred_expense_amortization': ('长期待摊费用摊销', ['20637734.49','10560492.82','8786972.11'], [115,77,81]),
}

def main():
    for _, path, digest, _ in SOURCES:
        if sha(ROOT/path) != digest:
            raise ValueError('Original hash changed')
    cache, values = {}, {}
    for field, (label, periods, pages) in ROWS.items():
        for i, page in enumerate(pages):
            key = (i,page)
            if key not in cache:
                cache[key] = texts(ROOT/SOURCES[i][1],page)
            phrase = label+format(D(periods[i]),',.2f')
            if any(t.count(phrase) != 1 for t in cache[key]):
                raise ValueError('Original row mismatch: '+field+' '+str(i))
        ttm = D(periods[0])-D(periods[1])+D(periods[2])
        if F(ttm) != F(periods[0])-F(periods[1])+F(periods[2]):
            raise ValueError('Independent TTM check failed')
        values[field] = str(ttm)
    da = sum(D(values[f]) for f in ('fixed_asset_depreciation','intangible_amortization','deferred_expense_amortization'))
    net = D(values['cash_capex'])-da
    # Explicit historically anchored cash-spending experiments, not maintenance estimates.
    sensitivity = {
        'recent_ttm': values['cash_capex'],
        'fy2025_spending': ROWS['cash_capex'][1][0],
        'fy2024_spending': '4678712053.56',
    }
    annual = cache[(0,13)]
    phrase = ROWS['cash_capex'][0]+'3,127,594,916.41'+'4,678,712,053.56'
    if any(t.count(phrase) != 1 for t in annual):
        raise ValueError('FY2024 capex comparative not matched')
    outputs = {k: {'cash_capex':v,'less_ttm_da_ex_rou':str(D(v)-da)} for k,v in sensitivity.items()}
    operating_path = ROOT/'runtime/company-research/600519-operating-forecast-20260909T104143099320Z/evidence.json'
    operating_manifest = json.loads((operating_path.parent/'manifest.json').read_text(encoding='utf-8'))
    if sha(operating_path) != operating_manifest['evidence_sha256']:
        raise ValueError('Operating forecast changed')
    operating = json.loads(operating_path.read_text(encoding='utf-8'))
    connected = []
    for scenario, years in operating['results'].items():
        for year in years:
            scale = D(year['operating_revenue'])/D(operating['ttm_facts']['revenue'])
            for anchor, capex in sensitivity.items():
                projected_capex, projected_da = D(capex)*scale, da*scale
                deduction = projected_capex-projected_da
                exact = (F(capex)-F(da))*F(year['operating_revenue'])/F(operating['ttm_facts']['revenue'])
                if abs(F(deduction)-exact) > F(1,1000000):
                    raise ValueError('Connected sensitivity recomputation failed')
                connected.append({'scenario':scenario,'period_end':year['period_end'],'spending_anchor':anchor,
                    'cash_capex':str(projected_capex),'da_ex_rou':str(projected_da),
                    'net_cash_reinvestment_before_nwc':str(deduction),
                    'cash_tax':None,'working_capital_change':None,'fcff':None,
                    'status':'pending_industrial_allocation_cash_tax_nwc_and_lease_treatment'})
    out = ROOT/'runtime/company-research'/('600519-reinvestment-basis-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir()
    payload = {'symbol':'600519','unit':'CNY','scope':'consolidated',
        'source_bindings':SOURCES,'original_rows':ROWS,'ttm_to':'2026-06-30','ttm':values,
        'ttm_da_ex_rou':str(da),'cash_capex_less_da_ex_rou':str(net),
        'spending_sensitivity':outputs,'industrial_reinvestment_approved':False,
        'operating_forecast_path':str(operating_path.relative_to(ROOT)),
        'operating_forecast_sha256':sha(operating_path), 'connected_forecast_sensitivity':connected,
        'scaling_assumption':'Scale D&A and each spending anchor with forecast operating revenue / baseline TTM revenue; illustrative capital intensity, not validated capacity economics.',
        'independent_fraction_checks':'passed',
        'limitations':[
            'Cash capex is not accrued asset additions or proven maintenance capex.',
            'D&A includes financial subsidiaries and other consolidated activities; no industrial allocation inferred.',
            'ROU amortization is separate. Lease debt, lease cash and capex must be matched before FCFF.',
            'Negative cash capex less D&A is preserved; payment timing is not perpetual asset harvesting.',
            'Three historical cash-spending levels are sensitivity anchors, not guaranteed lower/upper future bounds.',
            'Working capital, cash taxes and financial scope remain required. This is not FCFF.',
        ]}
    (out/'evidence.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'script_sha256':sha(Path(__file__)),
        'evidence_sha256':sha(out/'evidence.json')},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'ttm':values,'da_ex_rou':str(da),'net':str(net),'sensitivity':outputs}))

if __name__ == '__main__':
    main()
