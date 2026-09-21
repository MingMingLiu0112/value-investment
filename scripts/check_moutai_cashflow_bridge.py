"""Explain reported CFO changes; remaining cash flows are not industrial FCFF."""
from datetime import datetime, timezone
from decimal import Decimal as D
from fractions import Fraction
import json
from pathlib import Path

from check_moutai_ttm_comparability import ROOT, sha, texts, compact


ROWS = [
    ('sales', 33, '销售商品、提供劳务收到的现金', '98,421,697,395.39', '95,086,614,960.23', 1, False),
    ('deposits', 33, '客户存款和同业存放款项净增加额', '7,383,004,563.78', '-2,516,653,584.50', 1, True),
    ('interest_in', 33, '收取利息、手续费及佣金的现金', '1,443,093,695.48', '1,473,395,060.41', 1, True),
    ('other_in', 33, '收到其他与经营活动有关的现金59（1）', '1,997,932,646.37', '3,959,173,739.04', 1, False),
    ('purchases', 34, '购买商品、接受劳务支付的现金', '6,118,893,646.05', '6,076,043,334.62', -1, False),
    ('loans', 34, '客户贷款及垫款净增加额', '-1,170,424,843.20', '-254,734,305.26', -1, True),
    ('interbank', 34, '存放中央银行和同业款项净增加额', '-21,895,452,284.18', '25,410,788,169.25', -1, True),
    ('funds_lent', 34, '拆出资金净增加额', '-900,000,000.00', '-2,100,000,000.00', -1, True),
    ('interest_out', 34, '支付利息、手续费及佣金的现金', '71,842,422.65', '43,850,389.39', -1, True),
    ('employees', 34, '支付给职工及为职工支付的现金', '10,296,088,177.23', '9,965,785,368.00', -1, False),
    ('taxes', 34, '支付的各项税费', '42,263,192,495.42', '41,669,889,456.55', -1, False),
    ('other_out', 34, '支付其他与经营活动有关的现金59（1）', '3,770,838,567.99', '4,071,846,731.30', -1, False),
]


def main():
    path = ROOT/'runtime/historical-filing-index/20260909T033444358365Z/pdfs/600519-1225475868.pdf'
    if sha(path) != '0e10aa26be46b1cf3cd03f06e834c7fb98d5dd0d661b96f8fddd4af7e846a4f6':
        raise ValueError('Original hash mismatch')
    pages = {page: texts(path, page) for page in (33,34)}
    rows = []
    for name, page, label, current, prior, sign, financial in ROWS:
        phrase = compact(label + current + prior)
        if any(phrase not in text for text in pages[page]):
            raise ValueError('Cash row mismatch: '+name)
        rows.append({'id':name, 'label':label, 'physical_page':page,
                     'current':current.replace(',',''), 'prior':prior.replace(',',''),
                     'cash_sign':sign, 'explicit_financial_line':financial})
    summary = {}
    for period, total in [('current', D('70690750119.06')), ('prior', D('13119061031.33'))]:
        computed = sum(D(row[period])*row['cash_sign'] for row in rows)
        rational = sum(Fraction(row[period])*row['cash_sign'] for row in rows)
        if computed != total or rational != Fraction(total):
            raise ValueError('Reported CFO does not reconcile')
        finance = sum(D(row[period])*row['cash_sign'] for row in rows if row['explicit_financial_line'])
        summary[period] = {'reported_cfo':str(total), 'explicit_financial_net':str(finance),
                           'other_reported_net':str(total-finance)}
    change = {key:str(D(summary['current'][key])-D(summary['prior'][key])) for key in summary['current']}
    if D(change['reported_cfo']) != D(change['explicit_financial_net'])+D(change['other_reported_net']):
        raise ValueError('Change decomposition mismatch')
    out = ROOT/'runtime/company-research'/('600519-cfo-bridge-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(parents=True, exist_ok=False)
    result = {'symbol':'600519', 'period':'2026H1 versus 2025H1', 'unit':'CNY',
        'source_url':'https://static.cninfo.com.cn/finalpage/2026-08-15/1225475868.PDF',
        'source_sha256':sha(path), 'rows':rows, 'summary':summary, 'change':change,
        'industrial_cfo_approved':False, 'fcff_approved':False,
        'limitations':['Remaining reported lines still include finance staff, taxes and other shared flows',
            'Financial balance runoff is not recurring sales or distributable shareholder earnings',
            'No zero assigned to blank statement lines; nonempty rows reconcile observed total',
            'Operating taxes include multiple tax types, not just income tax']}
    (out/'evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'source_sha256':sha(path),
        'script_sha256':sha(Path(__file__)), 'evidence_sha256':sha(out/'evidence.json')},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'summary':summary,'change':change}))


if __name__ == '__main__':
    main()
