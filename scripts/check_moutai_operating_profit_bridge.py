"""Bridge reported trading subtotal to consolidated profit, preserving scope."""
from datetime import datetime, timezone
from decimal import Decimal as D
from fractions import Fraction
from pathlib import Path
import json
from check_moutai_ttm_comparability import ROOT, sha, texts


def main():
    source=ROOT/'runtime/historical-filing-index/20260909T033444358365Z/pdfs/600519-1225475868.pdf'
    if sha(source)!='0e10aa26be46b1cf3cd03f06e834c7fb98d5dd0d661b96f8fddd4af7e846a4f6':
        raise ValueError('Original changed')
    data=[('financial_interest_income',1,'1574811118.73',30),
          ('financial_interest_expense',-1,'76587662.57',30),
          ('financial_commission_expense',-1,'183088.17',30),
          ('finance_expense',-1,'-243237716.96',30),
          ('other_income',1,'23554465.99',30),('investment_income',1,'1013870.58',30),
          ('fair_value_gain',1,'22082651.62',30),('credit_impairment_gain',1,'32473761.91',31),
          ('asset_disposal_gain',1,'139731.04',31)]
    decoded={p:texts(source,p) for p in (30,31)}
    labels={
        'financial_interest_income':('利息收入44','1704408137.13'),
        'financial_interest_expense':('利息支出44','91606314.10'),
        'financial_commission_expense':('手续费及佣金支出44','42669.36'),
        'finance_expense':('财务费用49','-486644673.87'),
        'other_income':('加：其他收益50','22518010.95'),
        'investment_income':('投资收益（损失以“-”号填列）51','59165.27'),
        'fair_value_gain':('公允价值变动收益（损失以“-”号填列）52','1758003.31'),
        'credit_impairment_gain':('信用减值损失（损失以“-”号填列）53','4312358.58'),
        'asset_disposal_gain':('资产处置收益（损失以“-”号填列）54','511925.45'),
    }
    original_rows={}
    for name,_,value,page in data:
        label,comparative=labels[name]
        phrase=label+format(D(value),',.2f')+format(D(comparative),',.2f')
        if any(t.count(phrase)!=1 for t in decoded[page]):
            raise ValueError('Profit adjustment row not uniquely matched: '+name)
        original_rows[name]=phrase
    total_row='三、营业利润（亏损以“-”号填列）61,411,291,686.2762,768,973,374.37'
    if any(t.count(total_row)!=1 for t in decoded[31]):
        raise ValueError('Operating profit target row not uniquely matched')
    prior=ROOT/'runtime/company-research/600519-operating-drivers-20260909T091956535440Z/evidence.json'
    manifest=json.loads((prior.parent/'manifest.json').read_text(encoding='utf-8'))
    if sha(prior)!=manifest['evidence_sha256']:
        raise ValueError('Operating input changed')
    subtotal=D(json.loads(prior.read_text(encoding='utf-8'))['revenue_less_cost_and_four_expenses'])
    adjustment=sum((sign*D(value) for _,sign,value,_ in data),D(0))
    total=subtotal+adjustment
    if total!=D('61411291686.27') or Fraction(total)!=Fraction(subtotal)+sum((sign*Fraction(value) for _,sign,value,_ in data),Fraction(0)):
        raise ValueError('Operating profit bridge failed')
    out=ROOT/'runtime/company-research'/('600519-operating-profit-bridge-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(exist_ok=False)
    payload={'symbol':'600519','period':'2026H1','unit':'CNY','source_sha256':sha(source),
        'source_path':str(source.relative_to(ROOT)),'subtotal_input_sha256':sha(prior),
        'trading_subtotal_with_consolidated_expenses':str(subtotal),
        'adjustments':[{'field':name,'sign':sign,'reported_value':value,'page':page} for name,sign,value,page in data],
        'adjustments_total':str(adjustment),'reported_consolidated_operating_profit':str(total),
        'original_adjustment_rows':original_rows,'original_total_row':total_row,
        'verification_version':'label-note-two-period-unique-row-v2',
        'industrial_EBIT_approved':False,
        'limitations':['The starting subtotal still bears consolidated shared/financial subsidiary operating expenses.',
            'Financial interest and finance-expense interest are separate statement lines; neither may be omitted or counted twice.',
            'Positive credit impairment is a gain/reversal here, not a cash operating expense.',
            'Subtracting standalone finance-company profit may miss intercompany interest eliminations.',
            'Numerical decomposition is not a recurring industrial earnings forecast.']}
    (out/'evidence.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'evidence_sha256':sha(out/'evidence.json'),'script_sha256':sha(Path(__file__))},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'adjustments_total':str(adjustment),'operating_profit':str(total)}))


if __name__=='__main__':
    main()
