"""Match existing capital-spending sensitivities to the forecast stub."""
from datetime import date, datetime, timezone
from decimal import Decimal as D
from fractions import Fraction as F
import json
from pathlib import Path
from check_moutai_ttm_comparability import ROOT, sha, texts


def main():
    base=ROOT/'runtime/company-research'
    inputs=[(base/'600519-reinvestment-basis-20260909T104614530208Z/evidence.json','00fe8a450a5cd1e60d9ad1da181886df4bf88e4bd3e88fd196f198c3c1fad370'),
        (base/'600519-dated-operating-20260909T121512582335Z/evidence.json','8d4dc2ae6970fd3f3f71731961fa167e3875045ac1fef15840f5e26a30fd6fec')]
    packs=[]
    for p,h in inputs:
        if sha(p)!=h:
            raise ValueError('Input changed')
        packs.append(json.loads(p.read_text(encoding='utf-8')))
    capital,dated=packs
    for _,p,h,_ in capital['source_bindings']:
        if sha(ROOT/p)!=h:
            raise ValueError('Capital original changed')
    quarter=base/'600519-quarter-timing-20260909T121136927272Z/600519-1224764517.pdf'
    if sha(quarter)!='622935d03b23310dcde1ba3c3d398b130c3fbf73b753fb79fab934999524307a':
        raise ValueError('Quarter original changed')
    phrase='购建固定资产、无形资产和其他长期资产支付的现金2,282,862,269.892,874,366,279.39'
    if any(phrase not in t for t in texts(quarter,11)):
        raise ValueError('Quarter capital cash row mismatch')
    fy,h1=map(D,capital['original_rows']['cash_capex'][1][:2])
    q3=D('2282862269.89')-h1
    q4=fy-D('2282862269.89')
    if F(h1)+F(q3)+F(q4)!=F(fy):
        raise ValueError('Independent annual capital reconciliation failed')
    share=D(dated['remaining_q3_days'])/D(dated['full_q3_days'])
    capex_weight=(h1+q4+q3*share)/fy
    start=date.fromisoformat(dated['valuation_date'])
    first_end=date.fromisoformat(dated['results']['base'][0]['period_end'])
    da_weight=D((first_end-start).days)/D(365)
    records=[]
    for row in capital['connected_forecast_sensitivity']:
        target=[r for r in dated['results'][row['scenario']] if r['period_end']==row['period_end']]
        if len(target)!=1:
            raise ValueError('Date join is not unique')
        first=row['period_end']==first_end.isoformat()
        capex=D(row['cash_capex'])*(capex_weight if first else 1)
        da=D(row['da_ex_rou'])*(da_weight if first else 1)
        net=capex-da
        if abs(F(net)-(F(capex)-F(da)))>F(1,10**15):
            raise ValueError('Independent dated capital subtotal mismatch')
        records.append({'scenario':row['scenario'],'spending_anchor':row['spending_anchor'],
            'period_start':target[0]['period_start'],'period_end':row['period_end'],
            'cash_capex':str(capex),'da_ex_rou':str(da),'net_reinvestment_before_nwc':str(net),
            'lease_adjustment':None,'industrial_fcff':None})
    if len(records)!=45:
        raise ValueError('Incomplete scenario join')
    out=base/('600519-dated-reinvestment-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir()
    result={'symbol':'600519','unit':'CNY','capital_seasonality_2025':{k:str(v) for k,v in [('FY',fy),('H1',h1),('Q3',q3),('Q4',q4)]},
        'stub_capex_fraction':str(capex_weight),'stub_da_fraction':str(da_weight),'records':records,
        'industrial_reinvestment_approved':False,
        'assumptions':['Use 2025 capital cash seasonality for all three spending-anchor experiments; not verified future project timing.',
            'Within-Q3 cash capex uses the explicit uniform-day assumption of the dated operating forecast.',
            'D&A accrues uniformly over time in the stub as an assumption; asset commissioning and disposals can change this.',
            'Lease amortization excluded; lease debt/cash and industrial-financial allocation remain unresolved.',
            'First-period NWC must be measured from valuation-date balance, not simply prorated from annual change.',
            'Other financing cash includes potential repurchases and other items; not assumed equal to lease payment.',
            'Historical cash spending is not verified maintenance capex; negative net spending remains unchanged.']}
    (out/'evidence.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'inputs':{str(p):sha(p) for p in [p for p,_ in inputs]+[quarter,Path(__file__)]},
        'evidence_sha256':sha(out/'evidence.json')},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'capex_weight':str(capex_weight),'da_weight':str(da_weight),'records':len(records)}))


if __name__=='__main__':
    main()
