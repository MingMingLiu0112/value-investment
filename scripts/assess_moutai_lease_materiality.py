"""Quantify an explicit lease overcharge stress, not a fair-value estimate."""
from datetime import datetime, timezone
from decimal import Decimal as D
from fractions import Fraction as F
import json
from pathlib import Path
from check_moutai_ttm_comparability import ROOT,sha,texts


def main():
    base=ROOT/'runtime/company-research'
    path=base/'600519-lease-model-20260909T122451598326Z/evidence.json'
    manifest=json.loads((path.parent/'manifest.json').read_text(encoding='utf-8'))
    if sha(path)!=manifest['evidence_sha256']:
        raise ValueError('Lease input changed')
    lease=json.loads(path.read_text(encoding='utf-8'))
    source=ROOT/'runtime/historical-filing-index/20260909T033444358365Z/pdfs/600519-1225475868.pdf'
    if sha(source)!=lease['source_sha256']:
        raise ValueError('Original changed')
    if any('股份总数1,252,270,215.00-2,188,614.00-2,188,614.001,250,081,601.00' not in t for t in texts(source,72)):
        raise ValueError('Period-end reported shares mismatch')
    shares=D('1250081601')
    annual_shock=D(lease['total_lease_cash_outflow'])*2
    debt=D(lease['liability_rollforward']['closing'])
    rows=[]
    for rate in map(D,['0.04','0.06','0.08','0.10','0.12']):
        pv=annual_shock/rate+debt
        per_share=pv/shares
        exact=(F(annual_shock)/F(rate)+F(debt))/F(shares)
        if abs(F(per_share)-exact)>F(1,10**20):
            raise ValueError('Independent stress calculation failed')
        rows.append({'stress_discount_rate':str(rate),'additional_annual_expense':str(annual_shock),
            'additional_debt_deduction':str(debt),'capitalized_stress':str(pv),'period_end_per_share_effect':str(per_share)})
    result={'symbol':'600519','unit':'CNY','reported_share_date':'2026-06-30','reported_shares':str(shares),
        'experiment':'Additional perpetual zero-growth expense equal to twice H1 total lease cash, plus one-time deduction of all disclosed lease debt.',
        'results':rows,'fair_value_approved':False,'maximum_loss_bound_proven':False,
        'decision':'Deprioritize further small lease classification appendices; retain explicit lease sensitivity and prioritize material financial-asset and industrial-minority scope.',
        'limitations':['This deliberately overcharges existing lease costs and debt to measure scale; never insert both charges into the production model.',
            'Doubling H1 is a stress assumption, not a verified full-year lease forecast or renewal obligation.',
            'The selected rates are illustrative stress denominators, not approved company WACC.',
            'Future lease expansion or off-balance obligations may exceed this experiment; it is not a rigorous upper bound.',
            'Reported June shares do not prove September shares or a valid current per-share valuation.',
            'No fairness/approval threshold is inferred solely from a small numerical effect.']}
    out=base/('600519-lease-materiality-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir()
    (out/'evidence.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'inputs':{str(p):sha(p) for p in [path,source,Path(__file__)]},
        'evidence_sha256':sha(out/'evidence.json')},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'per_share_stress':[(r['stress_discount_rate'],r['period_end_per_share_effect']) for r in rows]}))


if __name__=='__main__':
    main()
