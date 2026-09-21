"""Join forecast and line-specific seasonality with an explicit remaining stub."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal as D, localcontext
from fractions import Fraction as F
import json
from pathlib import Path
from check_moutai_ttm_comparability import ROOT, sha

INPUTS={
    'operating':('600519-operating-forecast-20260909T104143099320Z','cb52c2b0ac4b7b8474b1afd30a726845a995a14739d8f91ea872256f58b6f2bb'),
    'seasonality':('600519-seasonality-20260909T121302838806Z','afa19c3fff00099da926596f4f2f47edb3bb7ec82ebbc447c4853223d09f3411')}


def main():
    packs={}
    paths=[]
    for key,(folder,digest) in INPUTS.items():
        path=ROOT/'runtime/company-research'/folder/'evidence.json'
        if sha(path)!=digest:
            raise ValueError('Pinned input changed: '+key)
        packs[key]=json.loads(path.read_text(encoding='utf-8'))
        paths.append(path)
    if packs['operating']['equity_value_approved'] or packs['seasonality']['forecast_timing_approved']:
        raise ValueError('Research scope changed')
    valuation=date(2026,9,9)
    quarter_start,quarter_end=date(2026,7,1),date(2026,9,30)
    remaining=(quarter_end-valuation).days
    duration=(quarter_end-quarter_start).days+1
    assert (remaining,duration)==(21,92)
    results={}
    with localcontext() as ctx:
        ctx.prec=45
        weights={}
        for field,season in packs['seasonality']['results'].items():
            annual=D(season['FY'])
            amounts=season['amounts']
            future=(D(amounts['H1'])+D(amounts['Q4'])+D(amounts['Q3'])*D(remaining)/duration)/annual
            exact=(F(amounts['H1'])+F(amounts['Q4'])+F(amounts['Q3'])*F(remaining,duration))/F(annual)
            if abs(F(future)-exact)>F(1,10**35) or not 0<future<1:
                raise ValueError('Independent future-weight mismatch')
            weights[field]=future
        for scenario,years in packs['operating']['results'].items():
            rows=[]
            for i,year in enumerate(years):
                values={'revenue':D(year['operating_revenue']),'cost':D(year['operating_cost']),
                    **{k:D(v) for k,v in year['expenses'].items()}}
                allocated={k:v*(weights[k] if i==0 else 1) for k,v in values.items()}
                removed={k:values[k]-allocated[k] for k in values}
                residual=allocated['revenue']-allocated['cost']-sum(allocated[k] for k in year['expenses'])
                independent=F(allocated['revenue'])-F(allocated['cost'])-sum(F(allocated[k]) for k in year['expenses'])
                if abs(F(residual)-independent)>F(1,10**25):
                    raise ValueError('Independent subtotal mismatch')
                end=date.fromisoformat(year['period_end'])
                start=valuation+timedelta(days=1) if i==0 else date(end.year-1,7,1)
                if start<=valuation or start>end:
                    raise ValueError('Elapsed forecast period')
                rows.append({'period_start':start.isoformat(),'period_end':end.isoformat(),
                    'period_days_inclusive':(end-start).days+1,
                    'future_operating_amounts':{k:str(v) for k,v in allocated.items()},
                    'removed_elapsed_forecast_amounts':{k:str(v) for k,v in removed.items()},
                    'subtotal_with_shared_expenses':str(residual),
                    'industrial_ebit':None,'cash_flow_date':None,'fcff':None})
            results[scenario]=rows
    result={'symbol':'600519','valuation_date':valuation.isoformat(),'unit':'CNY',
        'remaining_q3_days':remaining,'full_q3_days':duration,
        'first_period_future_fractions':{k:str(v) for k,v in weights.items()},'results':results,
        'timing_approved':False,'equity_value_approved':False,
        'assumptions':[
            'Apply 2025 aggregate H1/Q3/Q4 seasonal proportions to each corresponding forecast revenue/cost/expense line.',
            'Apply historical H1 proportions to following-year H1 within each July-June forecast; no observed 2027 outcomes.',
            'Within Q3, each line accrues uniformly by calendar day as an explicit research approximation.',
            'Removed amounts are elapsed portions of a forecast, not measured 2026 July-September actuals.',
            'Operating accrual dates are not receipt/payment dates. No cash-flow-date or FCFF approval follows.',
            'Industrial scope, cash tax, capex, D&A, working capital, leases and valuation-date asset bridge remain required.',
            'One-year historical seasonal pattern may not persist; product mix, holidays and channel changes can invalidate it.']}
    out=ROOT/'runtime/company-research'/('600519-dated-operating-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir()
    (out/'evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'inputs':{str(p):sha(p) for p in paths+[Path(__file__)]},
        'evidence_sha256':sha(out/'evidence.json')},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'first_period':[results['base'][0]['period_start'],results['base'][0]['period_end']],
        'first_year_subtotal':{s:r[0]['subtotal_with_shared_expenses'] for s,r in results.items()},'rows':sum(map(len,results.values()))}))


if __name__=='__main__':
    main()
