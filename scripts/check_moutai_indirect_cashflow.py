"""Reconcile all nonblank indirect cash-flow adjustments from the original report."""
from datetime import datetime, timezone
from decimal import Decimal as D
from fractions import Fraction
from pathlib import Path
import json
from check_moutai_ttm_comparability import ROOT, sha, texts

ROWS=[
 ('净利润','46033330566.78','46986681449.24'),
 ('信用减值损失','-32473761.91','-4312358.58'),
 ('产性生物资产折旧','1019596188.09','940703752.88'),
 ('使用权资产摊销','25933200.71','26052929.46'),
 ('无形资产摊销','153074255.31','139668544.83'),
 ('长期待摊费用摊销','8786972.11','10560492.82'),
 ('列）','-139731.04','-511925.45'),
 ('号填列）','2003901.73','1709580.66'),
 ('号填列）','-22082651.62','-1758003.31'),
 ('财务费用（收益以“-”号填列）','21034591.16','4369620.54'),
 ('投资损失（收益以“-”号填列）','-1013870.58','-59165.27'),
 ('“-”号填列）','165578976.91','-133647318.88'),
 ('“-”号填列）','-4558513.32','-37213033.11'),
 ('列）','110213424.88','-628446802.13'),
 ('“-”号填列）','26126578660.96','-20679149330.03'),
 ('“-”号填列）','-2915112091.11','-13505587402.34'),
]


def main():
    source=ROOT/'runtime/historical-filing-index/20260909T033444358365Z/pdfs/600519-1225475868.pdf'
    expected='0e10aa26be46b1cf3cd03f06e834c7fb98d5dd0d661b96f8fddd4af7e846a4f6'
    if sha(source)!=expected:
        raise ValueError('Original changed')
    pair=texts(source,81)
    for label,current,prior in ROWS:
        phrase=label+format(D(current),',.2f')+format(D(prior),',.2f')
        if any(phrase not in text for text in pair):
            raise ValueError('Indirect row mismatch: '+phrase)
    totals={}
    for index,period,expected_total in [(1,'2026H1','70690750119.06'),(2,'2025H1','13119061031.33')]:
        total=sum((D(r[index]) for r in ROWS),D(0))
        independent=sum((Fraction(r[index]) for r in ROWS),Fraction(0))
        if total!=D(expected_total) or independent!=Fraction(expected_total):
            raise ValueError('Indirect cash flow does not reconcile')
        da=sum((D(ROWS[i][index]) for i in [2,4,5]),D(0))
        totals[period]={'CFO':str(total),'DA_excluding_right_of_use':str(da),
            'right_of_use_amortization':ROWS[3][index],
            'DA_including_right_of_use':str(da+D(ROWS[3][index])),
            'inventory_receivable_payable_adjustments':str(sum((D(ROWS[i][index]) for i in [13,14,15]),D(0)))}
    out=ROOT/'runtime/company-research'/('600519-indirect-cashflow-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(exist_ok=False)
    payload={'symbol':'600519','scope':'consolidated','unit':'CNY','physical_page':81,
        'source_path':str(source.relative_to(ROOT)),'source_sha256':sha(source),'original_rows':ROWS,
        'totals':totals,'industrial_FCFF_approved':False,
        'limitations':['All nonblank reported numeric adjustments reconciled; blank entries not imputed as facts.',
            'D&A includes consolidated subsidiaries and is not an authenticated industrial-only allocation.',
            'Lease amortization stays separate until lease debt and reinvestment treatment are matched.',
            'Receivable/payable changes include financial activity and cannot substitute industrial NWC.',
            'No forecast or sustainable cash-conversion assumption follows from this reconciliation.']}
    (out/'evidence.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'evidence_sha256':sha(out/'evidence.json'),'script_sha256':sha(Path(__file__))},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'totals':totals}))


if __name__=='__main__':
    main()
