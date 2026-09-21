"""Source-backed tax reconciliation and explicit, unapproved forecast sensitivities."""
from datetime import datetime, timezone
from decimal import Decimal as D
from fractions import Fraction as F
from pathlib import Path
import json
from check_moutai_ttm_comparability import ROOT, sha, texts

def main():
    source=ROOT/'runtime/historical-filing-index/20260909T033444358365Z/pdfs/600519-1225475868.pdf'
    expected='0e10aa26be46b1cf3cd03f06e834c7fb98d5dd0d661b96f8fddd4af7e846a4f6'
    if sha(source)!=expected:
        raise ValueError('Original changed')
    pair=texts(source,78)
    rows=[('当期所得税费用','15255249283.39','15962179669.57'),
          ('递延所得税费用','149839327.12','-170860351.99'),
          ('合计','15405088610.51','15791319317.58')]
    bridge=[('按法定/适用税率计算的所得税费用','15359604794.32'),
            ('子公司适用不同税率的影响','-653592.63'),
            ('调整以前期间所得税的影响','-137159711.51'),
            ('非应税收入的影响','-6750063.57'),
            ('不可抵扣的成本、费用和损失的影响','190047183.89')]
    for label,*values in rows+bridge+[('利润总额','61438419177.29')]:
        phrase=label+''.join(format(D(v),',.2f') for v in values)
        if any(t.count(phrase)!=1 for t in pair):
            raise ValueError('Unique tax row mismatch: '+label)
    expense=D(rows[2][1])
    bridge_difference=F(expense)-sum(F(v) for _,v in bridge)
    # Published component rounding can leave a one-cent reconciliation residual.
    if D(rows[0][1])+D(rows[1][1])!=expense or abs(bridge_difference)>F(1,100):
        raise ValueError('Tax expense reconciliation failed')
    pbt=D('61438419177.29')
    if abs(pbt*D('.25')-D(bridge[0][1]))>D('.01'):
        raise ValueError('25 percent statutory basis failed')
    operating_path=ROOT/'runtime/company-research/600519-operating-forecast-20260909T104143099320Z/evidence.json'
    manifest=json.loads((operating_path.parent/'manifest.json').read_text(encoding='utf-8'))
    if sha(operating_path)!=manifest['evidence_sha256']:
        raise ValueError('Operating input changed')
    operating=json.loads(operating_path.read_text(encoding='utf-8'))
    sensitivity=[]
    for scenario, years in operating['results'].items():
        for year in years:
            subtotal=D(year['subtotal_with_shared_consolidated_expenses'])
            for rate in (D('.24'),D('.25'),D('.26')):
                estimate=max(subtotal,D(0))*rate
                if abs(F(estimate)-max(F(subtotal),F(0))*F(rate))>F(1,1000000):
                    raise ValueError('Independent tax sensitivity failed')
                sensitivity.append({'scenario':scenario,'period_end':year['period_end'],
                    'assumed_rate':str(rate),'tax_on_unapproved_operating_subtotal':str(estimate),
                    'approved_cash_tax':None,'approved_nopat':None})
    out=ROOT/'runtime/company-research'/('600519-tax-forecast-basis-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir()
    payload={'symbol':'600519','period':'2026H1','unit':'CNY','source_path':str(source.relative_to(ROOT)),
        'source_sha256':expected,'physical_page':78,'expense_rows':rows,'statutory_bridge':bridge,
        'reported_effective_tax_rate':str(expense/pbt),'current_expense_to_pbt':str(D(rows[0][1])/pbt),
        'statutory_starting_rate':'0.25','statutory_check_tolerance_cny':'0.01',
        'reported_bridge_residual_cny':str(D(bridge_difference.numerator)/D(bridge_difference.denominator)),
        'bridge_residual_treatment':'Preserved one-cent difference; rounding is plausible, not proven. No source values changed.',
        'operating_input_path':str(operating_path.relative_to(ROOT)), 'operating_input_sha256':sha(operating_path),
        'forecast_sensitivity':sensitivity,'checks':'expense sum, independent statutory bridge, statutory rate and 45 forecast cells passed',
        'cash_tax_approved':False,
        'assumptions_and_limits':[
            '25% anchored to the issuer statutory/appropriate rate reconciliation; 24%/26% are analyst sensitivities, not legal rates or confidence intervals.',
            'Current tax expense is not cash paid. The cash-flow statement total taxes includes VAT and consumption taxes.',
            'Deferred tax expense is noncash and not simply the balance change where other comprehensive income or other movements apply.',
            'Tax on the current shared-expense subtotal is provisional; industrial scope and permanent differences must be resolved before approved NOPAT.',
            'No immediate tax refund for forecast losses; deferred loss utilisation is not modelled.',
        ]}
    (out/'evidence.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'script_sha256':sha(Path(__file__)),
        'evidence_sha256':sha(out/'evidence.json')},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'statutory_rate':'25%','effective_rate':payload['reported_effective_tax_rate'],
        'sensitivity_rows':len(sensitivity),'cash_tax_approved':False}))

if __name__=='__main__':
    main()
