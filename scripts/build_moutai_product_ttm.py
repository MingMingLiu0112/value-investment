"""Original product revenue/cost TTM bridge; no forward assumptions."""
from datetime import datetime, timezone
from decimal import Decimal as D
from fractions import Fraction
from pathlib import Path
import json
from check_moutai_ttm_comparability import ROOT, sha, texts

SOURCES=[
 ('FY2025','runtime/historical-filing-index/20260909T033444358365Z/pdfs/600519-1225114741.pdf','474905deeaf0f875fc0a1b097a626c0c7852c427faadc5d7fc7816cbf45ea288',10),
 ('H12025','runtime/historical-filing-index/20260909T033820132471Z/pdfs/600519-1224462930.pdf','c80fb7180169469053c396e65315414368bcfa9f1f1d4e3bf793c8fb327e6b0c',70),
 ('H12026','runtime/historical-filing-index/20260909T033444358365Z/pdfs/600519-1225475868.pdf','0e10aa26be46b1cf3cd03f06e834c7fb98d5dd0d661b96f8fddd4af7e846a4f6',74),
]
DATA={
 'moutai': [('茅台酒','146499906480.49','9484757825.54'),('茅台酒','75589948903.79','4649298661.23'),('茅台酒','77724437925.48','6000884228.70')],
 'series': [('其他系列酒','22274678707.16','5321142314.05'),('系列酒','13762529352.77','3083996598.51'),('其他系列酒','12934186511.82','3415795490.58')],
}


def main():
    for i,(period,path,digest,page) in enumerate(SOURCES):
        pdf=ROOT/path
        if sha(pdf)!=digest:
            raise ValueError('Original changed')
        pair=texts(pdf,page)
        for rows in DATA.values():
            label,revenue,cost=rows[i]
            phrase=label+format(D(revenue),',.2f')+format(D(cost),',.2f')
            if any(phrase not in text for text in pair):
                raise ValueError(f'Product row mismatch: {period} {label}')
    result={}
    for product,rows in DATA.items():
        calculated={}
        for index,field in [(1,'revenue'),(2,'cost')]:
            annual,prior,current=[D(r[index]) for r in rows]
            ttm=annual-prior+current
            if Fraction(ttm)!=Fraction(annual)-Fraction(prior)+Fraction(current):
                raise ValueError('Independent TTM mismatch')
            calculated[field]={'FY2025':str(annual),'H12025':str(prior),'H12026':str(current),
                'H22025':str(annual-prior),'TTM_to_2026_06_30':str(ttm),
                'H1_yoy':str(current/prior-1)}
        revenue=D(calculated['revenue']['TTM_to_2026_06_30']);cost=D(calculated['cost']['TTM_to_2026_06_30'])
        calculated['TTM_gross_margin']=str(1-cost/revenue)
        result[product]=calculated
    out=ROOT/'runtime/company-research'/('600519-product-ttm-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(exist_ok=False)
    payload={'symbol':'600519','unit':'CNY','ttm_start':'2025-07-01','ttm_end':'2026-06-30',
        'source_bindings':SOURCES,'original_rows':DATA,'products':result,
        'formula':'FY2025 - H12025 + H12026','forecast_approved':False,
        'limitations':['Reported product classification, not a claim of identical SKU mix.',
            'Excludes other business and separately reported financial interest income.',
            'Gross margins exclude consumption taxes, selling, administration, financing and income taxes.',
            'TTM is a historical flow; no H2 forecast or automatic annualization.',
            'Same issuer originals and dual decoders are not independent industry corroboration.']}
    (out/'evidence.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'script_sha256':sha(Path(__file__)),
        'evidence_sha256':sha(out/'evidence.json')},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'products':result}))


if __name__=='__main__':
    main()
