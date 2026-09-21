"""Capital and liquidity constraints for scenario inputs; no assumed maintenance split."""
from datetime import datetime, timezone
from decimal import Decimal as D
import json
from pathlib import Path
from check_moutai_ttm_comparability import ROOT, sha, texts


def main():
    source = ROOT/'runtime/historical-filing-index/20260909T033444358365Z/pdfs/600519-1225475868.pdf'
    if sha(source) != '0e10aa26be46b1cf3cd03f06e834c7fb98d5dd0d661b96f8fddd4af7e846a4f6':
        raise ValueError('Original changed')
    checks = {
        34:['购建固定资产、无形资产和其他长期资产支付的现金832,142,752.281,595,995,809.23'],
        65:['合计42,785,000,000.002,145,323,030.74565,917,450.93582,281,953.062,128,958,528.61',
            '在建工程2,481,191,369.982,471,886,030.58'],
        69:['合计8,358,830,124.378,358,830,124.37//30,570,381,314.2930,564,429,120.66//',
            '存放中央银行法定存款准备金',
            '应付货款及服务费3,509,015,535.314,007,309,049.87',
            '预收货款3,177,561,597.078,006,739,780.94'],
    }
    for page, phrases in checks.items():
        pair = texts(source, page)
        for phrase in phrases:
            if any(phrase not in text for text in pair):
                raise ValueError(f'Capital evidence mismatch p{page}: {phrase}')
    start, additions, transfers, end = map(D, ['2145323030.74','565917450.93','582281953.06','2128958528.61'])
    if start+additions-transfers != end:
        raise ValueError('Important construction rollforward mismatch')
    out = ROOT/'runtime/company-research'/('600519-capital-inputs-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(parents=True,exist_ok=False)
    result = {'symbol':'600519','period_end':'2026-06-30','unit':'CNY','scope':'consolidated disclosed constraints',
        'source_url':'https://static.cninfo.com.cn/finalpage/2026-08-15/1225475868.PDF',
        'physical_page_checks':checks,'capex_h1':'832142752.28','capex_prior_h1':'1595995809.23',
        'important_construction':{'opening':str(start),'additions':str(additions),'transfers_to_fixed_assets':str(transfers),'closing':str(end),
            'total_project_budgets':'42785000000.00','rollforward_reconciled':True},
        'restricted_carrying_value':'8358830124.37','prior_restricted_carrying_value':'30564429120.66',
        'contract_liability_change':str(D('3177561597.07')-D('8006739780.94')),
        'trade_payable_change':str(D('3509015535.31')-D('4007309049.87')),
        'maintenance_capex_approved':False,'remaining_project_cash_commitment_approved':False,
        'industrial_nwc_approved':False,'distributable_cash_approved':False,
        'interpretation':['Project budget minus closing construction balance is not remaining cash commitment',
            'Cash capital expenditure and accrued project additions/transfers are different measures',
            'Statutory financial reserve is restricted; do not deduct twice from an already adjusted cash base',
            'Contract liability and payable movements are components, not complete industrial NWC',
            'Half-year spending does not establish sustainable annual maintenance spending']}
    (out/'evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'source_sha256':sha(source),'script_sha256':sha(Path(__file__)),
        'evidence_sha256':sha(out/'evidence.json')},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'restricted_cash':result['restricted_carrying_value'],
                      'contract_liability_change':result['contract_liability_change'],'construction_reconciled':True}))


if __name__ == '__main__':
    main()
