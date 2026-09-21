"""Authenticate lease and minority claims; book balances are not fair values."""
from datetime import datetime, timezone
from decimal import Decimal as D
from pathlib import Path
import json
from check_moutai_ttm_comparability import ROOT, sha, texts


def main():
    source=ROOT/'runtime/historical-filing-index/20260909T033444358365Z/pdfs/600519-1225475868.pdf'
    digest='0e10aa26be46b1cf3cd03f06e834c7fb98d5dd0d661b96f8fddd4af7e846a4f6'
    if sha(source)!=digest:
        raise ValueError('Original changed')
    checks={28:['少数股东权益10,842,757,754.869,321,442,876.89'],
            71:['一年内到期的租赁负债56,855,365.7244,206,237.05',
                '长期租赁负债186,829,502.34189,504,942.77'],
            87:['贵州茅台酒销售有限公司51,243,471,447.144,422,563,354.17',
                '单位：万元','7,648,174.672,486,942.892,486,942.892,119,522.46',
                '公司持有贵州赖茅酒业有限公司43%的股权比例']}
    for page,phrases in checks.items():
        pair=texts(source,page)
        for phrase in phrases:
            if any(phrase not in text for text in pair):
                raise ValueError(f'Original mismatch p{page}: {phrase}')
    lease=D('56855365.72')+D('186829502.34')
    minority_profit=D('1243471447.14')
    rounded_profit=D('2486942.89')*10000
    rounding_residual=rounded_profit*D('.05')-minority_profit
    # Subsidiary profit is reported to 0.01 ten-thousand CNY (100 CNY).
    if abs(rounding_residual)>D('50')*D('.05')+D('.005'):
        raise ValueError('Subsidiary minority profit does not reconcile within source precision')
    total_minority=D('10842757754.86'); sales_minority=D('4422563354.17')
    result={'symbol':'600519','period_end':'2026-06-30','unit':'CNY',
        'source_url':'https://static.cninfo.com.cn/finalpage/2026-08-15/1225475868.PDF',
        'source_sha256':digest,'physical_page_checks':checks,
        'consolidated_current_and_noncurrent_lease_liability':str(lease),
        'consolidated_minority_book_equity':str(total_minority),
        'sales_subsidiary_minority_book_equity':str(sales_minority),
        'other_subsidiaries_minority_book_equity_residual':str(total_minority-sales_minority),
        'sales_subsidiary_minority_profit_H1':str(minority_profit),
        'sales_subsidiary_minority_fraction':'.05',
        'profit_reconciliation_rounding_residual':str(rounding_residual),
        'bridge_fair_values_approved':False,
        'required_model_treatment':[
            'Consolidated operating value requires valuation of operating minority claims, not automatic book-value subtraction.',
            'If operating cash flows already exclude minority participation, do not subtract the same minority claim again.',
            'Financial subsidiary minority is excluded when only the parent-owned financial equity is added; do not subtract it twice.',
            'Sales subsidiary profit and assets contain internal transactions; do not add standalone value on top of consolidated operations.',
            'Lease debt subtraction must match the treatment of lease expense, depreciation and future lease investment in FCFF.',
            'Lease balance is not proof of complete industrial debt or a market value of debt.',
            'The remaining minority book equity is not automatically attributable entirely to the financial subsidiary.']}
    out=ROOT/'runtime/company-research'/('600519-equity-claims-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(exist_ok=False)
    (out/'evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'source_sha256':digest,'script_sha256':sha(Path(__file__)),
        'evidence_sha256':sha(out/'evidence.json')},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'leases':str(lease),'minority_profit_rounding_residual':str(rounding_residual)}))


if __name__=='__main__':
    main()
