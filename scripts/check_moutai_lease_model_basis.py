"""Authenticate lease asset rollforward and keep cash/accrual claims distinct."""
from datetime import datetime, timezone
from decimal import Decimal as D
from fractions import Fraction as F
import json
from pathlib import Path
from check_moutai_ttm_comparability import ROOT,sha,texts


def main():
    pdf=ROOT/'runtime/historical-filing-index/20260909T033444358365Z/pdfs/600519-1225475868.pdf'
    if sha(pdf)!='0e10aa26be46b1cf3cd03f06e834c7fb98d5dd0d661b96f8fddd4af7e846a4f6':
        raise ValueError('Original changed')
    checks={66:['406,638,003.71','（1）租入27,656,398.1527,656,398.15','22,523,264.11','411,771,137.75',
        '184,899,776.20','25,933,200.71','20,940,293.49','189,892,683.42','221,878,454.33','221,738,227.51'],
        83:['16,481,907.68(单位：元币种：人民币)','与租赁相关的现金流出总额35,735,006.11'],
        51:['本公司后续采用直线法对使用权资产计提折旧'],
        80:['偿还租赁负债支付的金额18,590,812.0018,208,426.74',
            '233,711,179.8233,064,621.8117,111,073.385,979,860.19243,684,868.06'],
        71:['一年内到期的租赁负债56,855,365.7244,206,237.05',
            '长期租赁负债186,829,502.34189,504,942.77']}
    for page,phrases in checks.items():
        for phrase in phrases:
            if any(phrase not in t for t in texts(pdf,page)):
                raise ValueError(f'Original mismatch {page}: {phrase}')
    gross_start,gross_add,gross_disposal,gross_end=map(D,['406638003.71','27656398.15','22523264.11','411771137.75'])
    dep_start,dep_add,dep_disposal,dep_end=map(D,['184899776.20','25933200.71','20940293.49','189892683.42'])
    net_start,net_end=D('221738227.51'),D('221878454.33')
    checks_arithmetic=[gross_start+gross_add-gross_disposal==gross_end,
        dep_start+dep_add-dep_disposal==dep_end,gross_start-dep_start==net_start,
        gross_end-dep_end==net_end,net_start+gross_add-dep_add-(gross_disposal-dep_disposal)==net_end]
    if not all(checks_arithmetic):
        raise ValueError('Lease asset rollforward failed')
    net_reinvestment=gross_add-dep_add
    if F(net_reinvestment)!=F('27656398.15')-F('25933200.71'):
        raise ValueError('Independent net reinvestment calculation failed')
    debt_start,noncash_add,cash_reduction,noncash_reduction,debt_end=map(D,
        ['233711179.82','33064621.81','17111073.38','5979860.19','243684868.06'])
    if F(debt_start)+F(noncash_add)-F(cash_reduction)-F(noncash_reduction)!=F(debt_end):
        raise ValueError('Independent liability rollforward failed')
    if D('56855365.72')+D('186829502.34')!=debt_end:
        raise ValueError('Current/noncurrent debt mismatch')
    out=ROOT/'runtime/company-research'/('600519-lease-model-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir()
    result={'symbol':'600519','version':'lease-model-basis-v2','period':'2026H1','unit':'CNY','source_url':'https://static.cninfo.com.cn/finalpage/2026-08-15/1225475868.PDF',
        'source_sha256':sha(pdf),'page_checks':checks,'five_rollforward_checks':checks_arithmetic,
        'lease_asset_additions':str(gross_add),'rou_depreciation':str(dep_add),
        'disposed_net_book_value':str(gross_disposal-dep_disposal),
        'additions_less_depreciation':str(net_reinvestment),
        'total_lease_cash_outflow':'35735006.11','short_low_value_lease_expense':'16481907.68',
        'liability_rollforward':{'opening':str(debt_start),'noncash_additions':str(noncash_add),
            'cash_reduction':str(cash_reduction),'noncash_reduction':str(noncash_reduction),'closing':str(debt_end),
            'cash_increase':None,'blank_cash_increase_note':'Blank in original; zero net residual follows full rollforward, not an explicit reported zero.'},
        'financing_lease_payment':'18590812.00',
        'payment_less_liability_cash_reduction':str(D('18590812.00')-cash_reduction),
        'noncash_liability_additions_less_rou_additions':str(noncash_add-gross_add),
        'column_verification':'Agent inspected rendered physical page 80: increases/decreases each split cash and noncash; paired PDF text decoders verify values.',
        'approved_fcff_lease_adjustment':None,
        'model_route':'Financing treatment candidate: add back matched ROU amortization, include new lease investment and subtract matched lease liabilities in equity bridge.',
        'constraints':[
            'Retaining ROU amortization as an operating deduction and also subtracting lease debt can double count lease economics.',
            'Do not subtract total lease cash as an additional FCFF expense after adopting the financing route.',
            'Short/low-value lease expense remains operating; no corresponding debt assumed.',
            'ROU additions can include advance payments/direct costs; cash capex overlap must be checked, not assumed absent.',
            'ROU depreciation may be capitalized in inventory rather than fully in current EBIT; cash-flow addback matching still required.',
            'Total lease cash less short lease expense is not verified lease principal: expense differs from payment and interest exists.',
            'Disposed net book value is not a cash disposal receipt.',
            'Half-year additions are not a sustainable forecast; three-source TTM and renewal assumptions remain needed.',
            'Payment minus liability cash reduction is not automatically lease interest; differences require cash-flow classification reconciliation.',
            'Noncash liability additions include unidentified changes; do not use as newly leased investment or treat the difference from ROU additions as capex overlap.',
            'Consolidated lease assets are not automatically industrial-only.']}
    (out/'evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    import pypdfium2 as pdfium
    document=pdfium.PdfDocument(str(pdf))
    document[79].render(scale=1.7).to_pil().save(out/'page80.png')
    (out/'manifest.json').write_text(json.dumps({'inputs':{str(p):sha(p) for p in [pdf,Path(__file__)]},
        'evidence_sha256':sha(out/'evidence.json')},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'five_checks':all(checks_arithmetic),'net_lease_reinvestment':str(net_reinvestment)}))


if __name__=='__main__':
    main()
