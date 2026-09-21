"""Same legal-entity TTM and explicit earnings-capitalization diagnostics."""
from datetime import datetime, timezone
from decimal import Decimal as D
from fractions import Fraction as F
import json
from pathlib import Path
from build_moutai_product_ttm import SOURCES
from check_moutai_ttm_comparability import ROOT,sha,texts

DATA=[['14161293.55','4722835.76','4053877.47'],
      ['7263658.54','2443050.48','2526758.69'],
      ['7648174.67','2486942.89','2119522.46']]


def main():
    for (_,path,digest,_),page,values in zip(SOURCES,[120,82,87],DATA):
        if sha(ROOT/path)!=digest:
            raise ValueError('Original changed')
        sequence=''.join(format(D(v),',.2f') for v in [values[0],values[1],values[1],values[2]])
        decoded=texts(ROOT/path,page)
        if any(sequence not in t or '单位：万元币种：人民币' not in t for t in decoded):
            raise ValueError('Same-scope original row mismatch')
    latest=texts(ROOT/SOURCES[2][1],87)
    if any('7,263,658.542,443,050.482,443,050.482,526,758.69' not in t for t in latest):
        raise ValueError('Prior interim comparable changed')
    metrics={}
    for col,name in enumerate(['revenue','net_profit','operating_cash_flow']):
        value=(D(DATA[0][col])-D(DATA[1][col])+D(DATA[2][col]))*10000
        if F(value)!=(F(DATA[0][col])-F(DATA[1][col])+F(DATA[2][col]))*10000:
            raise ValueError('Independent TTM failed')
        metrics[name]=value
    minority_profit=metrics['net_profit']*D('.05')
    minority_cfo=metrics['operating_cash_flow']*D('.05')
    # This is a deliberately strong assumption, retained as a diagnostic only.
    experiments=[{'capitalization_rate':str(r),'zero_growth_full_profit_payout_value':str(minority_profit/r)}
                 for r in map(D,['.06','.08','.10','.12'])]
    out=ROOT/'runtime/company-research'/('600519-sales-minority-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir()
    result={'symbol':'600519','entity':'贵州茅台酒销售有限公司','period_end':'2026-06-30',
        'source_unit':'CNY_10000','output_unit':'CNY','source_rows':DATA,
        'source_bindings':[{'path':p,'sha256':h,'physical_page':pg} for (_,p,h,_),pg in zip(SOURCES,[120,82,87])],
        'ttm':{k:str(v) for k,v in metrics.items()},'ttm_cfo_to_profit':str(metrics['operating_cash_flow']/metrics['net_profit']),
        'minority_fraction':'.05','minority_profit_at_rounded_subsidiary_precision':str(minority_profit),
        'minority_cfo_not_fcfe':str(minority_cfo),'earnings_capitalization_experiments':experiments,
        'approved_minority_fair_value':None,
        'limitations':['Sales subsidiary is not the entire industrial group; do not apply its 5 percent to all company operating value.',
            'TTM source rows use rounded ten-thousand CNY; profit allocation is not exact minority consolidated profit.',
            'Operating cash includes internal working-capital flows; not distributable FCFE or an independent whole-group cash flow.',
            'Capitalization assumes flat earnings and full sustainable payout, before validating capex, required capital, taxes and internal pricing.',
            'Diagnostic rates are not approved equity costs and values are not a verified fair-value interval.',
            'Do not add minority book cash separately if capitalization already includes its interest or eventual distribution value.',
            'Other industrial minorities and financial minorities remain separate exposures.']}
    (out/'evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'inputs':{str(p):sha(p) for p in [ROOT/x[1] for x in SOURCES]+[Path(__file__)]},
        'evidence_sha256':sha(out/'evidence.json')},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'ttm':result['ttm'],'cfo_profit':result['ttm_cfo_to_profit'],'minority_profit':str(minority_profit)}))


if __name__=='__main__':
    main()
