"""Reconcile every nonblank consolidated balance row before equity bridging."""
from datetime import datetime, timezone
from decimal import Decimal as D
from fractions import Fraction as F
import json
from pathlib import Path
from check_moutai_ttm_comparability import ROOT,sha,texts

# Labels include note numbers only where printed in the original balance sheet.
ASSETS=[
('cash','货币资金1','53518798979.08',25,'financial'),
('interbank','拆出资金2','141084158124.01',26,'financial'),
('receivables','应收账款3','570895.04',26,'working_capital'),
('receivable_financing','应收款项融资4','2475749125.89',26,'working_capital'),
('prepayments','预付款项5','16190168.54',26,'working_capital'),
('other_receivables','其他应收款6','47328677.41',26,'working_capital_scope_pending'),
('reverse_repo','买入返售金融资产7','406491272.08',26,'financial'),
('inventory','存货8','61317208371.30',26,'working_capital'),
('current_debt_investment','一年内到期的非流动资产9','1798106445.56',26,'financial'),
('other_current_assets','其他流动资产10','60066044.49',26,'split_tax_and_working_capital'),
('loans','发放贷款和垫款11','416287173.92',26,'financial'),
('debt_investment','债权投资12','1106707304.24',26,'financial'),
('other_debt_investment','其他债权投资13','2414885261.51',26,'financial'),
('equity_investments','长期股权投资14','147198786.54',26,'strategic_or_nonoperating_pending'),
('other_financial_assets','其他非流动金融资产15','3917510576.37',26,'financial'),
('investment_property','投资性房地产16','2716218.30',26,'operating_or_nonoperating_pending'),
('fixed_assets','固定资产17','22220890242.73',26,'operating_assets_not_added_to_dcf'),
('construction','在建工程18','2481191369.98',26,'operating_assets_not_added_to_dcf'),
('rou_assets','使用权资产19','221878454.33',26,'lease_operating_assets_not_added_to_dcf'),
('intangibles','无形资产20','8578743700.95',26,'operating_assets_not_added_to_dcf'),
('development','开发支出21','137537251.51',26,'operating_assets_not_added_to_dcf'),
('deferred_expenses','长期待摊费用22','127852143.45',26,'operating_assets_not_added_to_dcf'),
('deferred_tax_assets','递延所得税资产23','6436890174.31',26,'tax_timing_pending'),
('other_noncurrent','其他非流动资产24','115827807.77',26,'capital_or_other_scope_pending')]
LIABILITIES=[
('trade_payables','应付账款26','3509015535.31',27,'working_capital'),
('contract_liabilities','合同负债27','3177561597.07',27,'working_capital'),
('external_deposits','吸收存款及同业存放28','25426316668.17',27,'financial_external_claim'),
('payroll','应付职工薪酬29','375947883.69',27,'working_capital_scope_pending'),
('taxes','应交税费30','6923321600.48',27,'split_tax_and_working_capital'),
('other_payables','其他应付款31','6791660124.62',27,'split_operating_capital_and_pending'),
('current_lease','一年内到期的非流动负债32','56855365.72',27,'lease_debt'),
('output_vat','其他流动负债33','384394900.26',27,'working_capital'),
('noncurrent_lease','租赁负债34','186829502.34',27,'lease_debt'),
('deferred_income','递延收益35','51479378.82',27,'grant_timing_pending'),
('deferred_tax_liability','递延所得税负债23','71049838.47',27,'tax_timing_pending')]


def main():
    pdf=ROOT/'runtime/historical-filing-index/20260909T033444358365Z/pdfs/600519-1225475868.pdf'
    if sha(pdf)!='0e10aa26be46b1cf3cd03f06e834c7fb98d5dd0d661b96f8fddd4af7e846a4f6':
        raise ValueError('Original changed')
    pages={p:texts(pdf,p) for p in [25,26,27,28]}
    for key,label,value,page,_ in ASSETS+LIABILITIES:
        phrase=label+format(D(value),',.2f')
        if any(t.count(phrase)!=1 for t in pages[page]):
            raise ValueError('Unique balance row mismatch: '+key)
    totals={'assets':D('309050784569.31'),'liabilities':D('46954432394.95'),
        'equity':D('262096352174.36'),'parent_equity':D('251253594419.50'),'minority_equity':D('10842757754.86')}
    for value,page in [(totals['assets'],26),(totals['liabilities'],27),(totals['equity'],28),(totals['parent_equity'],28),(totals['minority_equity'],28)]:
        if any(format(value,',.2f') not in t for t in pages[page]):
            raise ValueError('Reported control total absent')
    for name,rows in [('assets',ASSETS),('liabilities',LIABILITIES)]:
        if sum(F(r[2]) for r in rows)!=F(totals[name]):
            raise ValueError('Nonblank balance rows incomplete or duplicated: '+name)
    if totals['assets']-totals['liabilities']!=totals['equity'] or totals['parent_equity']+totals['minority_equity']!=totals['equity']:
        raise ValueError('Balance ownership identity failed')
    groups={}
    rows=[]
    for side,items in [('asset',ASSETS),('liability',LIABILITIES)]:
        for key,label,amount,page,group in items:
            groups.setdefault(side+':'+group,D(0))
            groups[side+':'+group]+=D(amount)
            rows.append({'side':side,'id':key,'source_label':label,'amount':amount,'physical_page':page,'research_classification':group,
                         'approved_valuation_adjustment':None})
    out=ROOT/'runtime/company-research'/('600519-balance-scope-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir()
    payload={'symbol':'600519','date':'2026-06-30','unit':'CNY','rows':rows,'book_control_totals':{k:str(v) for k,v in totals.items()},
        'group_subtotals':{k:str(v) for k,v in groups.items()},'balance_and_equity_reconciled':True,'equity_bridge_approved':False,
        'limitations':['Classifications are research routing, not financial/industrial entity attribution or fair values.',
            'Working-capital liabilities already included in cashflow must not also be deducted wholesale as debt.',
            'Tax rows and other payables require their existing note-level splits before downstream use.',
            'Fixed assets, inventories and other operating assets cannot be added to DCF merely because they have book values.',
            'Reconciliation covers nonblank reported rows, not undisclosed obligations or an explicit zero debt assertion.',
            'Deferred tax assets of CNY 6.4369 billion cannot be added at face value without matching tax forecasts and recoverability.',
            'Minority book equity must not substitute for a fair-value claim; financial and industrial components must remain separate.']}
    (out/'evidence.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# 茅台合并资产负债表范围图','', '账面归类，不是股权估值。金额单位：亿元。','',
        '| 项目 | 资产/负债 | 金额 | 模型处理状态 | 原文页 |','| --- | --- | ---: | --- | ---: |']
    for row in rows:
        lines.append(f"| {row['source_label']} | {row['side']} | {D(row['amount'])/D('1e8'):.4f} | {row['research_classification']} | {row['physical_page']} |")
    (out/'review.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'inputs':{str(p):sha(p) for p in [pdf,Path(__file__)]},
        'outputs':{p.name:sha(p) for p in out.iterdir()}},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'asset_rows':len(ASSETS),'liability_rows':len(LIABILITIES),'all_balances_reconciled':True}))


if __name__=='__main__':
    main()
