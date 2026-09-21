"""Reconcile H1/Q3/Q4 operating seasonality without assuming daily uniformity."""
from datetime import datetime, timezone
from decimal import Decimal as D
from fractions import Fraction as F
import json
from pathlib import Path
from build_moutai_operating_forecast import FIELDS
from build_moutai_product_ttm import SOURCES
from check_moutai_ttm_comparability import ROOT, sha, texts

Q3={'revenue':'128453707655.86','cost':'11183972073.77','surcharges':'20645707926.55',
    'selling':'4478672252.48','admin':'5503383668.62','research':'113086640.98'}


def main():
    directory=ROOT/'runtime/company-research/600519-quarter-timing-20260909T121136927272Z'
    reference=json.loads((directory/'evidence.json').read_text(encoding='utf-8'))
    pdf=directory/'600519-1224764517.pdf'
    if sha(pdf)!=reference['source_sha256']:
        raise ValueError('Quarter original changed')
    for _,p,h,_ in SOURCES[:2]:
        if sha(ROOT/p)!=h:
            raise ValueError('Annual/interim original changed')
    qtext=texts(pdf,8)
    fytext=texts(ROOT/SOURCES[0][1],61)
    htext=texts(ROOT/SOURCES[1][1],28)
    results={}
    for field,(label,values,notes) in FIELDS.items():
        for decoded,phrase in [(qtext,label+format(D(Q3[field]),',.2f')),
            (fytext,label+notes[0]+format(D(values[0]),',.2f')),
            (htext,label+notes[1]+format(D(values[1]),',.2f'))]:
            if any(t.count(phrase)!=1 for t in decoded):
                raise ValueError('Unique source row mismatch '+field)
        annual,half,nine=D(values[0]),D(values[1]),D(Q3[field])
        quarters={'H1':half,'Q3':nine-half,'Q4':annual-nine}
        if sum(map(F,quarters.values()))!=F(annual):
            raise ValueError('Independent period sum mismatch')
        results[field]={'FY':str(annual),'amounts':{k:str(v) for k,v in quarters.items()},
            'fractions_of_FY':{k:str(v/annual) for k,v in quarters.items()}}
    direct='营业收入39,064,353,239.020.56128,453,707,655.866.36'
    if any(direct not in t for t in texts(pdf,1)) or D(results['revenue']['amounts']['Q3'])!=D('39064353239.02'):
        raise ValueError('Independent disclosed Q3 revenue mismatch')
    out=ROOT/'runtime/company-research'/('600519-seasonality-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir()
    payload={'symbol':'600519','year':2025,'unit':'CNY','results':results,'forecast_timing_approved':False,
        'limitations':['One historical year is not a stable seasonal forecasting law.',
            'Operating expense ratios vary by period; do not allocate every line by revenue fractions.',
            'Quarter revenue is not quarterly cash receipts or FCFF.',
            'September 9 remaining Q3 cannot be inferred from quarterly totals; daily proration would be an explicit assumption.',
            'No 2026Q3 actuals are inferred. Cash taxes, financial scope and capex timing remain separate.',
            'H1/Q3/Q4 total operating figures do not establish individual product seasonality.']}
    (out/'evidence.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'inputs':{str(p):sha(p) for p in [pdf,ROOT/SOURCES[0][1],ROOT/SOURCES[1][1],Path(__file__)]},
        'evidence_sha256':sha(out/'evidence.json')},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'revenue':results['revenue'],'cost':results['cost']}))


if __name__=='__main__':
    main()
