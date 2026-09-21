"""Reconcile operating proxy to reported PBT without inventing segment costs."""
from datetime import datetime,timezone
from decimal import Decimal as D
from fractions import Fraction as F
from pathlib import Path
import json
from check_moutai_ttm_comparability import ROOT,sha,texts

ROWS=[
 ('operating_revenue',1,'90703260964.48',30,'included_operating'),
 ('operating_cost',-1,'9473762565.88',30,'included_operating'),
 ('surcharges',-1,'14682159453.47',30,'included_shared_scope'),
 ('selling',-1,'3206308341.53',30,'included_shared_scope'),
 ('admin',-1,'3635355263.82',30,'included_shared_scope'),
 ('research',-1,'114926219.60',30,'included_shared_scope'),
 ('finance_interest_revenue',1,'1574811118.73',30,'excluded_separate_finance'),
 ('finance_interest_expense',-1,'76587662.57',30,'excluded_separate_finance'),
 ('finance_commission_expense',-1,'183088.17',30,'excluded_separate_finance'),
 ('financial_expense',-1,'-243237716.96',30,'excluded_financing_and_cash_income'),
 ('other_income',1,'23554465.99',30,'excluded_other'),
 ('investment_income',1,'1013870.58',30,'excluded_other'),
 ('fair_value_gain',1,'22082651.62',30,'excluded_other'),
 ('credit_impairment_gain',1,'32473761.91',31,'excluded_other'),
 ('asset_disposal_gain',1,'139731.04',31,'excluded_other'),
 ('nonoperating_income',1,'35315234.56',31,'excluded_other'),
 ('nonoperating_expense',-1,'8187743.54',31,'excluded_other')]


def main():
    original=ROOT/'runtime/historical-filing-index/20260909T033444358365Z/pdfs/600519-1225475868.pdf'
    if sha(original)!='0e10aa26be46b1cf3cd03f06e834c7fb98d5dd0d661b96f8fddd4af7e846a4f6':
        raise ValueError('Report changed')
    decoded={p:texts(original,p) for p in [30,31,76]}
    for name,sign,value,page,scope in ROWS:
        if any(format(D(value),',.2f') not in t for t in decoded[page]):
            raise ValueError('Original PBT row mismatch: '+name)
    pbt=D('61438419177.29')
    if any(format(pbt,',.2f') not in t for t in decoded[31]):
        raise ValueError('PBT total missing')
    total=sum(sign*D(value) for _,sign,value,_,_ in ROWS)
    exact=sum(sign*F(value) for _,sign,value,_,_ in ROWS)
    if total!=pbt or exact!=F(pbt):
        raise ValueError('Operating-to-PBT reconciliation failed')
    proxy=sum(sign*D(value) for _,sign,value,_,scope in ROWS if scope.startswith('included'))
    financial_components=[('interest_expense','21034591.16'),('interest_income','-266574096.14'),('other','2301788.02')]
    for _,value in financial_components:
        if any(format(D(value),',.2f') not in t for t in decoded[76]):
            raise ValueError('Finance-expense note mismatch')
    if sum(D(v) for _,v in financial_components)!=D('-243237716.96'):
        raise ValueError('Finance-expense detail does not reconcile')
    out=ROOT/'runtime/company-research'/('600519-operating-profit-scope-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir()
    result={'symbol':'600519','period':'2026H1','unit':'CNY',
        'source_url':'https://static.cninfo.com.cn/finalpage/2026-08-15/1225475868.PDF',
        'source_sha256':sha(original),'operating_proxy':str(proxy),'reported_pbt':str(pbt),
        'excluded_net_items':str(pbt-proxy),'reconciliation_residual':'0',
        'ledger':[{'field':name,'sign':sign,'reported_value':value,'page':page,'scope':scope} for name,sign,value,page,scope in ROWS],
        'known_excluded_finance_costs':{'interest_and_commission_expenses':str(D('76587662.57')+D('183088.17')),'net_financial_expense':'-243237716.96'},
        'scope_conclusion':'Explicit finance interest/commission and financial-expense rows already excluded. Only financial amounts embedded in included operating/shared rows may require correction.',
        'unknown_industrial_finance_shared_expense_adjustment':None,
        'prohibited_corrections':['Do not add excluded finance interest/commission expense back again.',
            'Do not subtract all finance standalone PBT from an operating proxy already excluding financial revenue.',
            'Finance standalone revenue minus PBT includes internal deposit interest, gains/losses and other items; not a verified consolidated shared-overhead amount.',
            'Excluded deposit interest cannot be added to industrial DCF if corresponding financial assets or finance equity already capture its value.'],
        'industrial_financial_scope_approved':False}
    (out/'evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'source_sha256':sha(original),'script_sha256':sha(Path(__file__)),
        'evidence_sha256':sha(out/'evidence.json')},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'operating_proxy':str(proxy),'pbt':str(pbt),'excluded_net':str(pbt-proxy)},ensure_ascii=False))


if __name__=='__main__':main()
