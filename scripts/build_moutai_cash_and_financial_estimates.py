"""Source-supported balance-date estimates and explicit liquidity stress assumptions."""
from datetime import datetime, timezone
from decimal import Decimal as D
from fractions import Fraction as F
from pathlib import Path
import json
from build_moutai_product_ttm import SOURCES
from check_moutai_ttm_comparability import ROOT,sha,texts

INVENTORY = ROOT/'runtime/company-research/600519-financial-asset-inventory-20260909T114226391473Z/evidence.json'
PAYMENTS = [
    ('purchases','购买商品、接受劳务支付的现金',['11450143940.22','6076043334.62','6118893646.05']),
    ('employees','支付给职工及为职工支付的现金',['15473458699.70','9965785368.00','10296088177.23']),
    ('taxes','支付的各项税费',['77430597986.28','41669889456.55','42263192495.42']),
    ('other_operating','支付其他与经营活动有关的现金',['9012158197.61','4071846731.30','3770838567.99']),
]


def main():
    for _,path,digest,_ in SOURCES:
        if sha(ROOT/path)!=digest:
            raise ValueError('Original report changed')
    report=ROOT/SOURCES[2][1]
    inventory=json.loads(INVENTORY.read_text(encoding='utf-8'))
    if inventory['source_sha256']!=sha(report):
        raise ValueError('Inventory source mismatch')
    notes={p:texts(report,p) for p in [26,53,59,90,91]}
    approximation='其账面价值与公允价值差异较小'
    if any(approximation not in t for t in notes[91]):
        raise ValueError('Issuer book approximation not found')
    for phrase in ['以净资产法计算截至资产负债表日的公允价值','按照中央国债登记结算有限责任公司、银行间市场清算所股份有限公司的估值结果确定公允价值']:
        if any(phrase not in t for t in notes[90]):
            raise ValueError('Valuation method disclosure missing')
    rows=[]
    for r in inventory['rows']:
        amount=D(r['closing'])
        if any(format(amount,',.2f') not in t for t in notes[r['page']]):
            raise ValueError('Inventory amount does not match original')
        measured=r['id'] in {'other_debt_investments','other_financial_assets'}
        if measured and any(format(amount,',.2f') not in t for t in notes[90]):
            raise ValueError('Measured fair value row mismatch')
        rows.append({'exposure':r['id'],'book_amount':str(amount),
            'balance_date_research_estimate':str(amount),'fair_minus_book_assumption':'0',
            'basis':'reported_fair_value' if measured else 'issuer_disclosed_book_fair_difference_small',
            'source_page':90 if measured else 91,
            'estimate_scope':'2026-06-30 only; not current fair value or free cash',
            'zero_is_explicit_estimate_not_missing_data':True})
    estimated=sum(D(r['balance_date_research_estimate']) for r in rows)
    if estimated!=D(inventory['totals']['closing']['selected_financial_assets']):
        raise ValueError('Financial estimate coverage mismatch')
    # Decode each cashflow source once; all four fields stay in the same scope.
    decoded=[texts(ROOT/item[1],page) for item,page in zip(SOURCES,[65,32,34])]
    cash=[]
    for key,label,values in PAYMENTS:
        for pair,value in zip(decoded,values):
            if any(label not in t or format(D(value),',.2f') not in t for t in pair):
                raise ValueError('Cash payment field missing: '+key)
        if any(format(D(values[1]),',.2f') not in t for t in decoded[2]):
            raise ValueError('Current comparative differs from original')
        value=D(values[0])-D(values[1])+D(values[2])
        if F(value)!=F(values[0])-F(values[1])+F(values[2]):
            raise ValueError('Independent TTM cash arithmetic failed')
        cash.append({'field':key,'label':label,'original_values_fy_prior_current':values,'ttm':str(value)})
    total=sum(D(r['ttm']) for r in cash)
    h1total=sum(D(r['original_values_fy_prior_current'][2]) for r in cash)
    days=(datetime(2026,7,1)-datetime(2025,7,1)).days
    half_days=(datetime(2026,7,1)-datetime(2026,1,1)).days
    runs=[]
    for duration in [30,60,90]:
        for basis,daily in [('trailing_365_day_average',total/D(days)),('latest_half_year_average',h1total/D(half_days))]:
            reserve=daily*duration
            runs.append({'cash_interruption_days':duration,'payment_basis':basis,
                'daily_selected_cash_payments':str(daily),'illustrative_reserve':str(reserve),
                'assumption':'Zero operating receipts during the stated interruption, selected payments continue at historical average; not a probability estimate or proven required cash.'})
    limitations=[
        'Issuer interim disclosure is not independent external verification or assurance against bank default.',
        'Reported fair values are as of June 30; no September repricing or liquidity premium inferred.',
        'Third-level private-fund NAV is not a quoted executable price or a guaranteed redemption amount.',
        'Restricted reserve remains included in financial assets; distributability and finance capital are handled separately.',
        'Selected payment rows exclude bank deposit/loan/interbank principal flows but still include financial-subsidiary payroll, tax and overhead.',
        'Cash taxes include multiple taxes and seasonal settlement; not industrial income tax or EBIT cash-tax rate.',
        'The 30/60/90-day horizons are explicit research stress durations, not issuer policy or empirically optimized reserve targets.',
        'Historical averages do not capture intra-month payment peaks. No receipt offset assumed during stress.',
        'Capex, debt refinancing and legal contingencies are outside these selected payments; liquidity stress is not complete solvency stress.',
        'A selected reserve must be included consistently in initial operating capital and future changes, not deducted twice from enterprise value.',
        'Finance equity, industrial minority values, tax matching and post-balance movements remain required for total equity valuation.'
    ]
    out=ROOT/'runtime/company-research'/('600519-cash-financial-estimates-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir()
    result={'symbol':'600519','balance_date':'2026-06-30','unit':'CNY','financial_estimates':rows,
        'financial_estimate_total':str(estimated),'cash_payment_ttm':cash,'cash_payment_total':str(total),
        'liquidity_stress_cases':runs,'selected_required_cash':None,'research_book_proxy_supported':True,
        'current_fair_value_approved':False,'equity_valuation_approved':False,'limitations':limitations}
    (out/'evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# 金融资产估计与必要现金压力基准','',
        '金融资产六月末研究估计沿用已披露账面数，合计2046.6295亿元。非公允计量项依据中报第91页的差异较小说明；其他债权投资、私募基金依据第90页已报告公允价值。不是九月估值，不是全部可分配现金。','',
        f'四类支付TTM合计{total/D("1e8"):.4f}亿元，排除财务公司的存贷款及同业本金流。四类仍含金融子公司薪酬、税费和共有费用，不能称精确工业现金支出。','',
        '| 停收情景天数 | 支付基准 | 所需支付缓冲（亿元） |', '| ---: | --- | ---: |']
    for r in runs:
        lines.append(f"| {r['cash_interruption_days']} | {r['payment_basis']} | {D(r['illustrative_reserve'])/D('1e8'):.4f} |")
    lines+=['','30/60/90天为研究压力时长，未选择为公司必要现金。零回款假设用于展示现金需求的经济含义，非发生概率、保守下界或已验收流动性模型。','',
        '正式接线：金融资产零公允减账面调整已有六月末来源依据；必要现金仍需选择有明确用途的假设，并纳入未来现金需求变化。税、金融权益、少数权益及后续余额仍单独处理。','']+['- '+x for x in limitations]
    (out/'review.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'inputs':{str(ROOT/p):h for _,p,h,_ in SOURCES},
        'inventory_sha256':sha(INVENTORY),'script_sha256':sha(Path(__file__)),
        'source_pages':{'FY2025':65,'H12025':32,'H12026_cash':34,'H12026_fair_value':[90,91]},
        'outputs':{p.name:sha(p) for p in out.iterdir()}},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'financial_estimate_total':str(estimated),'ttm_selected_payments':str(total),'stress_cases':runs},ensure_ascii=False))


if __name__=='__main__':
    main()
