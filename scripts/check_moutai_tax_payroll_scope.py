"""Separate tax and payroll balance changes from ordinary trade working capital."""
from datetime import datetime, timezone
from decimal import Decimal as D
from pathlib import Path
import json
from check_moutai_ttm_comparability import ROOT, sha, texts

TAXES=[('增值税','1542180362.01','1897379403.43'),('消费税','1809257918.29','2061339912.46'),
 ('企业所得税','2909272618.86','3172867724.14'),('个人所得税','35834702.37','39901988.85'),
 ('城市维护建设税','245594473.48','287381482.22'),('城市教育费附加','93749582.05','111658300.12'),
 ('地方教育费附加','63771179.97','75710325.32'),('印花税','34404704.33','38169483.22'),
 ('房产税','630685.02','866342.50'),('土地使用税','7704.28','10196.71'),
 ('环境保护税','24834.14','40116.41'),('其他','188592835.68','11844555.31')]


def main():
    source=ROOT/'runtime/historical-filing-index/20260909T033444358365Z/pdfs/600519-1225475868.pdf'
    if sha(source)!='0e10aa26be46b1cf3cd03f06e834c7fb98d5dd0d661b96f8fddd4af7e846a4f6':
        raise ValueError('Original changed')
    decoded=texts(source,70)
    for label,current,prior in TAXES:
        phrase=label+format(D(current),',.2f')+format(D(prior),',.2f')
        if any(phrase not in text for text in decoded):
            raise ValueError('Tax original mismatch')
    totals=[sum((D(row[i]) for row in TAXES),D(0)) for i in (1,2)]
    if totals!=[D('6923321600.48'),D('7697169830.69')]:
        raise ValueError('Tax total mismatch')
    payroll=['5523447166.50','5145037970.56','10292537253.37','375947883.69']
    phrase='合计'+''.join(format(D(n),',.2f') for n in payroll)
    if any(phrase not in text for text in texts(source,69)):
        raise ValueError('Payroll original mismatch')
    if D(payroll[0])+D(payroll[1])-D(payroll[2])!=D(payroll[3]):
        raise ValueError('Payroll rollforward mismatch')
    data={'symbol':'600519','period':'2026H1','scope':'consolidated','unit':'CNY',
        'source_sha256':sha(source),'source_path':str(source.relative_to(ROOT)),'physical_pages':[69,70],
        'taxes':[{'name':n,'closing':c,'opening':p,'change':str(D(c)-D(p)),
                  'forecast_bucket':'income_tax_schedule' if n=='企业所得税' else 'requires_operating_and_subsidiary_scope'} for n,c,p in TAXES],
        'tax_totals':list(map(str,totals)),
        'non_corporate_income_tax_balances':[str(totals[i]-D(TAXES[2][i+1])) for i in range(2)],
        'payroll_rollforward':dict(zip(['opening','accrued','settled','closing'],payroll)),
        'payroll_balance_change':str(D(payroll[3])-D(payroll[0])),
        'complete_industrial_NWC':False,
        'limitations':['Tax payable movement is not itself cash tax expense.',
            'If FCFF uses cash income tax, do not also treat the same income-tax payable movement as a separate NWC benefit.',
            'Payroll liabilities and other taxes include consolidated financial subsidiaries; allocation is still required.',
            'Payroll settlement may include timing and seasonal bonuses; do not repeat the half-year reduction every forecast year.',
            'Other taxes are not automatically recurring operating tax funding.']}
    out=ROOT/'runtime/company-research'/('600519-tax-payroll-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(exist_ok=False)
    (out/'evidence.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'evidence_sha256':sha(out/'evidence.json'),'script_sha256':sha(Path(__file__))},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'payroll_balance_change':data['payroll_balance_change'],'tax_categories':len(TAXES)}))


if __name__=='__main__':
    main()
