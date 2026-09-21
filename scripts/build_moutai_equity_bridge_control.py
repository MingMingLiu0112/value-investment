"""Reconcile book scopes before replacing operations and minority claims by value."""
from datetime import datetime, timezone
from decimal import Decimal as D
from fractions import Fraction as F
from pathlib import Path
import json
from check_moutai_ttm_comparability import ROOT, sha, texts

BASE = ROOT/'runtime/company-research'
BALANCE = BASE/'600519-balance-scope-20260909T124526091284Z/evidence.json'
NWC = BASE/'600519-nwc-sensitivity-20260909T114536573711Z/evidence.json'
REPORT = ROOT/'runtime/historical-filing-index/20260909T033444358365Z/pdfs/600519-1225475868.pdf'
FINANCE = BASE/'600519-finance-current-20260909T073502376364Z/600519-1225475863.pdf'
PINS = {BALANCE:'42aeeabedb74c3d89e579b804d41ebf8060171b01b20cc91146133a9a7ad10f8',
        NWC:'1e198cdfd8ba276147ec4eb1c5a6bf77d3ba62f5323619d244c3f13d270a4c42',
        REPORT:'0e10aa26be46b1cf3cd03f06e834c7fb98d5dd0d661b96f8fddd4af7e846a4f6',
        FINANCE:'cf2d50aa028fcf11ce9eb04746932b7a9be25c3e31d443295f77add844b1121b'}


def main():
    for path, digest in PINS.items():
        if sha(path) != digest:
            raise ValueError('Pinned input changed: '+str(path))
    balance = json.loads(BALANCE.read_text(encoding='utf-8'))
    nwc = json.loads(NWC.read_text(encoding='utf-8'))
    rows = balance['rows']
    amounts = {r['id']:D(r['amount']) for r in rows}
    if len(amounts) != len(rows):
        raise ValueError('Duplicate balance exposure')
    equity = balance['book_control_totals']
    signed = lambda r: D(r['amount']) * (1 if r['side']=='asset' else -1)
    if sum(map(signed,rows)) != D(equity['equity']):
        raise ValueError('Full book scope does not reconcile')
    sales_book = D('4422563354.17')
    page = texts(REPORT,87)
    for token in ['4,422,563,354.17','10,331,087.77','1,485,961.06','单位：万元币种：人民币']:
        if any(token not in t for t in page):
            raise ValueError('Sales subsidiary balance original mismatch')
    sales_net = (D('10331087.77')-D('1485961.06'))*10000
    sales_rounded_claim = sales_net*D('.05')
    # Each subsidiary total is rounded to CNY 100; two totals yield CNY 5 NCI tolerance.
    if abs(sales_rounded_claim-sales_book) > D('5.005'):
        raise ValueError('Sales minority ownership does not reconcile at disclosed precision')
    finance_text = texts(FINANCE,7)
    if any('所有者权益合计119.41亿元' not in t for t in finance_text):
        raise ValueError('Finance book equity source mismatch')
    finance_book = D('119.41')*D('1e8')
    finance_rounding = D('.005')*D('1e8')
    finance_nci = finance_book*D('.49')
    residual = D(equity['minority_equity'])-sales_book-finance_nci
    minority = {'total_reported':equity['minority_equity'], 'sales_reported':str(sales_book),
        'sales_net_assets_at_rounded_precision':str(sales_net),
        'sales_five_percent_reconciliation_residual':str(sales_rounded_claim-sales_book),
        'finance_49_percent_rounded_book':str(finance_nci),
        'other_and_consolidation_residual_midpoint':str(residual),
        'other_and_consolidation_residual_low':str(residual-finance_rounding*D('.49')),
        'other_and_consolidation_residual_high':str(residual+finance_rounding*D('.49')),
        'precision_limit':'Range reflects finance report rounding only, not valuation uncertainty or assured exact entity allocation.'}
    # Inventory and trade balances are already in NWC; do not add them again here.
    fixed_ids = ('fixed_assets','construction','rou_assets','intangibles','development','deferred_expenses','other_noncurrent')
    fixed = sum(amounts[k] for k in fixed_ids)
    cases = []
    for name, values in nwc['classification_cases'].items():
        operating_book = D(values['closing'])+fixed
        retained_before_nci = D(equity['equity'])-operating_book
        retained_after_nci = D(equity['parent_equity'])-operating_book
        if F(operating_book)+F(retained_before_nci)-F(equity['minority_equity']) != F(equity['parent_equity']):
            raise ValueError('Independent book equity bridge failed')
        cases.append({'nwc_case':name,'nwc_book':values['closing'], 'fixed_and_capital_book':str(fixed),
            'operating_book_to_replace':str(operating_book),
            'retained_net_book_before_minority':str(retained_before_nci),
            'retained_net_book_after_all_book_minority':str(retained_after_nci),
            'book_reconciliation_residual':'0',
            'retained_amount_is_not_distributable_cash':True})
    controls = [
        'Start with consolidated operating value for exactly the operating scope replaced.',
        'Add retained net book after all book minority, then explicit fair-minus-book adjustments; never deduct full minority fair value again.',
        'Sales adjustment is minus (sales full-claim fair value minus reported sales NCI book).',
        'Other industrial adjustment is minus (other industrial NCI full-claim fair value minus matching book). Residual is not zero.',
        'Finance adjustment is plus 51 percent times (finance fair equity minus matching book equity) only after finance operating assets/expenses are completely separated.',
        'Do not additionally add internal deposits or gross finance equity to retained consolidated assets.',
        'Working cash retained for operations must be deducted from excess assets, or included consistently in forecast invested capital, not both.',
        'Deferred/current tax retained at book requires matching forecast cash tax; if tax reversals are already in DCF, remove the duplicated asset/claim.',
        'Unclassified payables move between operating and retained scopes with the NWC case. Never ignore them in both.',
        'Book reserve cash is not worthless. Liquidity restrictions belong in finance/cash valuation, without a second arbitrary reserve deduction.',
        'Retained loan/fund/strategic investment book values are not asserted equal to fair value.',
        'Fixed scope is a consolidated research partition; financial-company assets embedded in it still require scope adjustment.',
        'June book values cannot be called September balances; post-balance movements and actual ordinary shares remain required.'
    ]
    out = BASE/('600519-equity-bridge-control-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir()
    result = {'symbol':'600519','balance_date':'2026-06-30','unit':'CNY',
        'minority_book_control':minority,'book_scope_cases':cases,'fixed_scope_ids':fixed_ids,
        'controls':controls,'equity_value':None,'fair_value_per_share':None,'valuation_approved':False,
        'pending_value_adjustments':{key:None for key in ['working_cash','financial_asset_fair_minus_book',
            'finance_equity_fair_minus_book','sales_nci_fair_minus_book','other_nci_fair_minus_book',
            'tax_matching','industrial_financial_scope','post_balance_movements','actual_ordinary_shares']}}
    (out/'evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# 茅台股权桥接控制表','', '此表完成账面范围勾稽，不是公允价值或可分配现金。金额单位：亿元。','',
        '| NWC分类 | 待替换经营账面净资产 | 留存净账面（扣全部账面少数权益后） | 勾稽差额 |',
        '| --- | ---: | ---: | ---: |']
    for row in cases:
        lines.append(f"| {row['nwc_case']} | {D(row['operating_book_to_replace'])/D('1e8'):.4f} | {D(row['retained_net_book_after_all_book_minority'])/D('1e8'):.4f} | 0 |")
    lines += ['',f"销售子公司账面少数权益{sales_book/D('1e8'):.4f}亿元；财务公司49%账面估算{finance_nci/D('1e8'):.4f}亿元；其他与合并调整残余约{residual/D('1e8'):.4f}亿元。残余没有被当成零。",'',
        '## 下一步实际桥接', '',
        '经营现值 + 留存净账面 + 各项公允减账面调整 = 普通股权益估计。该式只有在经营/金融范围、税、现金及少数权益完全匹配后才可代入估值，不把数学恒等式当成经济估计。', '',
        '少数权益已经按账面扣除，因此追加扣的是公允价值减账面价值；若换用直接资产负债法，应扣完整公允少数权益，两种方法不得混用。财务公司整体股权价值不能在保留金融资产后重复加回。','',
        '两种营运资本分类对应不同桥接留存项，不能选择较有利的经营DCF和另一分类较大的留存值拼接。','',
        '## 未完成调整', ''] + ['- '+c for c in controls]
    (out/'review.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'inputs':{str(p):h for p,h in PINS.items()},
        'script_sha256':sha(Path(__file__)),'outputs':{p.name:sha(p) for p in out.iterdir()}},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'minority':minority,'book_cases':cases},ensure_ascii=False))


if __name__ == '__main__':
    main()
