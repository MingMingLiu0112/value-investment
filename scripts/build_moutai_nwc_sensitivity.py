"""Extend the trade subtotal and quantify unresolved classification effects."""
from datetime import datetime, timezone
from decimal import Decimal as D
from fractions import Fraction as F
from pathlib import Path
import json
from check_moutai_ttm_comparability import ROOT, sha, texts

ROWS=[
 ('receivables',1,'570895.04','2609048.49',26,'应收账款3'),
 ('other_receivables',1,'47328677.41','36281302.94',26,'其他应收款6'),
 ('other_current_assets',1,'60066044.49','51027010.56',26,'其他流动资产10'),
 ('prepaid_income_tax_exclusion',-1,'4122884.22','2389005.72',60,'预缴所得税'),
 ('payroll',-1,'375947883.69','5523447166.50',27,'应付职工薪酬29'),
 ('taxes_payable',-1,'6923321600.48','7697169830.69',27,'应交税费30'),
 ('income_tax_exclusion',1,'2909272618.86','3172867724.14',70,'企业所得税'),
 ('pending_output_vat',-1,'384394900.26','994959710.24',71,'待转销项税额'),
 ('materials_guarantees',-1,'178249626.86','199129566.12',71,'材料质量保证金'),
 ('unclassified_other_payables',-1,'3196203100.78','2820157650.85',71,'往来款项'),
]

def load_verified(path):
    manifest=json.loads((path.parent/'manifest.json').read_text(encoding='utf-8'))
    if sha(path)!=manifest['evidence_sha256']:
        raise ValueError('Upstream package changed')
    return json.loads(path.read_text(encoding='utf-8'))

def main():
    source=ROOT/'runtime/historical-filing-index/20260909T033444358365Z/pdfs/600519-1225475868.pdf'
    if sha(source)!='0e10aa26be46b1cf3cd03f06e834c7fb98d5dd0d661b96f8fddd4af7e846a4f6':
        raise ValueError('Original changed')
    pages={p:texts(source,p) for p in {r[4] for r in ROWS}}
    for field,_,closing,opening,page,label in ROWS:
        phrase=label+format(D(closing),',.2f')+format(D(opening),',.2f')
        if any(t.count(phrase)!=1 for t in pages[page]):
            raise ValueError('Source row mismatch '+field)
    prior=ROOT/'runtime/company-research/600519-trade-working-capital-20260909T101654416787Z/evidence.json'
    trade=load_verified(prior)
    cases={}
    for include_unknown in (False,True):
        name='include_all_unclassified_payables' if include_unknown else 'exclude_unclassified_payables'
        totals={}
        for period,index in [('closing',2),('opening',3)]:
            selected=[r for r in ROWS if include_unknown or r[0]!='unclassified_other_payables']
            total=D(trade['subtotal'][period])+sum(D(r[index])*r[1] for r in selected)
            if F(total)!=F(trade['subtotal'][period])+sum(F(r[index])*r[1] for r in selected):
                raise ValueError('Independent subtotal failed')
            totals[period]=str(total)
        totals['balance_change']=str(D(totals['closing'])-D(totals['opening']))
        cases[name]=totals
    op_path=ROOT/'runtime/company-research/600519-operating-forecast-20260909T104143099320Z/evidence.json'
    op=load_verified(op_path)
    forecast=[]
    for case,totals in cases.items():
        for scenario,years in op['results'].items():
            previous=D(totals['closing'])
            for year in years:
                target=D(totals['closing'])*D(year['operating_revenue'])/D(op['ttm_facts']['revenue'])
                change=target-previous
                forecast.append({'case':case,'scenario':scenario,'period_end':year['period_end'],
                    'illustrative_nwc_balance':str(target),'illustrative_nwc_increase':str(change),
                    'approved_nwc_increase':None})
                previous=target
    out=ROOT/'runtime/company-research'/('600519-nwc-sensitivity-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir()
    payload={'symbol':'600519','unit':'CNY','version':'expanded-nwc-classification-research-v2',
        'source_path':str(source.relative_to(ROOT)),'source_sha256':sha(source),'added_original_rows':ROWS,
        'trade_input_path':str(prior.relative_to(ROOT)),'trade_input_sha256':sha(prior),
        'operating_input_path':str(op_path.relative_to(ROOT)),'operating_input_sha256':sha(op_path),
        'classification_cases':cases,'forecast_sensitivity':forecast,'complete_industrial_nwc':False,
        'scope_and_assumptions':[
            'Corporate income-tax payable AND prepaid income tax excluded because cash taxes are modelled separately; other taxes and output VAT retained.',
            'Construction guarantees remain outside operating NWC; construction settlement must be reflected in cash capex consistently.',
            'Other receivables and other current assets excluding prepaid income tax included illustratively pending detailed classification.',
            'Unknown other-payables cases quantify classification impact only; not complete bounds on all unknowns.',
            'Closing NWC / TTM revenue held fixed for forecast. Single-date seasonality and financial-subsidiary payroll/taxes still require review.',
            'Balance changes are not authenticated cash movements: writeoffs, currency and other noncash adjustments still matter.',
            'The June snapshot cannot be treated as the September valuation-date balance without a bridge.',
        ]}
    (out/'evidence.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'script_sha256':sha(Path(__file__)),
        'evidence_sha256':sha(out/'evidence.json')},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'classification_cases':cases,'forecast_rows':len(forecast)}))

if __name__=='__main__':
    main()
