"""Integrate existing dated operating, cash, tax and equity claims explicitly."""
from datetime import date,datetime,timezone
from decimal import Decimal as D,localcontext
from pathlib import Path
import json
from check_moutai_ttm_comparability import ROOT,sha

INPUTS={
 'tax':('600519-tax-balance-bridge-20260909T124759649210Z','f9de5d8a27c7aeb80d4d7a3168041359eb59bbfa3ca4078cc3558396b060136f'),
 'cash_dcf':('600519-operating-cash-sensitivity-20260909T133925863982Z','3b5290ce8ed69f79fdfa872807d26a535d6cc0bf7eac9aaa6b08388aa6192b58'),
 'finance':('600519-finance-equity-estimates-20260909T140648431896Z','174a860285f6a770d65a98fdde324404c39028b1115c956d70f69492cdd54c29'),
 'minority':('600519-sales-minority-estimates-20260909T142014571435Z','e49efda92cf9f5486e8ef0993b0e7eff289623ad6f15a9ca5e6ef7ae5bc12a4d'),
 'shares':('600519-current-share-price-review-20260909T135607541717Z','b4d38f775005c34b3367e85dfb279748b70f2596732c68e6822a2482414d4e16'),
 'bridge':('600519-equity-bridge-control-20260909T132548421808Z','1c5137422eeb75ba62ed39d244256c304b7e46bd77a9257a7e1c5929fe6212cd'),
 'operating':('600519-operating-forecast-20260909T104143099320Z','cb52c2b0ac4b7b8474b1afd30a726845a995a14739d8f91ea872256f58b6f2bb')}


def unique(rows, **fields):
    selected=[r for r in rows if all(str(r.get(k))==str(v) for k,v in fields.items())]
    if len(selected)!=1:
        raise ValueError('Nonunique scenario join: '+str(fields))
    return selected[0]


def main():
    packs={};paths=[]
    for key,(directory,digest) in INPUTS.items():
        p=ROOT/'runtime/company-research'/directory/'evidence.json'
        if sha(p)!=digest:
            raise ValueError('Pinned component changed: '+key)
        packs[key]=json.loads(p.read_text(encoding='utf-8'));paths.append(p)
    shares=D(packs['shares']['disclosure_supported_ordinary_share_assumption'])
    if shares<=0 or shares!=shares.to_integral_value() or packs['shares']['valuation_approved']:
        raise ValueError('Unexpected share/approval scope')
    valuation=date.fromisoformat(packs['cash_dcf']['valuation_date'])
    tax_cases={'intercompany_tax_asset_only':D(packs['tax']['internal_profit_deferred_asset']),
               'all_consolidated_net_deferred_tax':D(packs['tax']['net_deferred_tax_asset_closing'])}
    ttm_revenue=D(packs['operating']['ttm_facts']['revenue'])
    output=[]
    with localcontext() as context:
        context.prec=45
        for op in packs['cash_dcf']['results']:
            rate=D(op['discount_rate'])
            bridge=unique(packs['bridge']['book_scope_cases'],nwc_case=op['nwc_case'])
            finance=unique(packs['finance']['results'],earnings_anchor='ttm_net_profit',equity_discount_rate=str(rate))
            sales=unique(packs['minority']['results'],scenario=op['scenario'],capital_intensity_multiplier='1',equity_discount_rate=str(rate))
            other=unique(packs['minority']['other_minority_scope']['estimates'],profit_anchor='midpoint',equity_rate=str(rate))
            for tax_case,initial_tax in tax_cases.items():
                last_tax=initial_tax;tax_pv=D(0);schedule=[]
                for year in packs['operating']['results'][op['scenario']]:
                    ending=initial_tax*D(year['operating_revenue'])/ttm_revenue
                    movement=ending-last_tax
                    payment=date.fromisoformat(year['period_end'])
                    discounted=-movement/(1+rate)**(D((payment-valuation).days)/D(365))
                    tax_pv+=discounted
                    schedule.append({'period_end':payment.isoformat(),'tax_asset_beginning':str(last_tax),
                        'tax_asset_ending':str(ending),'additional_cash_tax_assumption':str(movement),
                        'operating_pv_change':str(discounted)})
                    last_tax=ending
                adjustments={
                    'operating_value_after_required_cash_changes':D(op['adjusted_conditional_operating_pv']),
                    'tax_working_capital_pv_change':tax_pv,
                    'retained_net_book_after_book_minorities':D(bridge['retained_net_book_after_all_book_minority']),
                    'initial_operating_cash_exclusion':-D(op['initial_reserved_cash']),
                    'initial_operating_tax_asset_exclusion':-initial_tax,
                    'finance_parent_fair_minus_book':D(finance['parent_bridge_fair_minus_book_adjustment']),
                    'sales_minority_additional_deduction':-D(sales['additional_deduction_if_book_already_deducted']),
                    'other_minority_additional_deduction':-D(other['additional_deduction_if_book_already_deducted'])}
                total=sum(adjustments.values())
                independent_tax=-sum(float(r['additional_cash_tax_assumption'])/(1+float(rate))**((date.fromisoformat(r['period_end'])-valuation).days/365) for r in schedule)
                independent_total=sum(float(v) for k,v in adjustments.items() if k!='tax_working_capital_pv_change')+independent_tax
                if abs(float(total)-independent_total)>.01 or abs(float(tax_pv)-independent_tax)>.01:
                    raise ValueError('Independent integrated equity calculation mismatch')
                output.append({'scenario':op['scenario'],'discount_rate':str(rate),'capital_anchor':op['capital_anchor'],
                    'nwc_case':op['nwc_case'],'reserve_days':op['reserve_days'],'payment_basis':op['payment_basis'],
                    'tax_case':tax_case,'tax_schedule':schedule,'bridge':{k:str(v) for k,v in adjustments.items()},
                    'conditional_equity_value':str(total),'disclosed_share_assumption':str(shares),
                    'conditional_value_per_disclosed_share':str(total/shares),
                    'formal_fair_value':None,'trade_approved':False})
    if len(output)!=648:
        raise ValueError('Incomplete integration grid')
    representatives=[unique(output,scenario=s,discount_rate='0.08',capital_anchor='fy2025_spending',
        nwc_case='exclude_unclassified_payables',reserve_days=60,payment_basis='latest_half_year_average',
        tax_case='intercompany_tax_asset_only') for s in ['bear','base','bull']]
    if not all(D(a['conditional_value_per_disclosed_share'])<=D(b['conditional_value_per_disclosed_share']) for a,b in zip(representatives,representatives[1:])):
        raise ValueError('Representative scenarios not ordered')
    limitations=[
        'This is an integrated conditional research estimate, not an accepted intrinsic value, current target price or trading threshold.',
        'All shared consolidated overhead remains charged to operating proxy even though financial equity is separately estimated. This conservative loading can double-charge financial overhead; industrial/finance separation remains unverified, so complete company FCFF is not approved.',
        'June balances and latest disclosed ordinary shares are carried to September as explicit approximations; no current registry or full post-balance roll-forward is claimed.',
        'Retained assets/claims use reported net book as a research proxy. Financial instrument approximation has issuer support; strategic/tax/other retained items are not individually fair-valued.',
        '25 percent operating tax is interpreted before changes in the selected deferred tax capital. Existing selected tax assets are removed from nonoperating bridge and their later changes affect cash tax once.',
        'Deferred tax balances scale with revenue, approximating continuing inventory-related tax capital. Detailed reversal/new-origin cohorts are unknown; the all-net case can include financial tax exposures.',
        'Existing net current income-tax liability CNY 2,905,149,734.64 remains deducted once in retained book; no second opening-liability settlement is inserted into forecast cashflow.',
        'Stable terminal retains operating cash and tax capital with no growth or liquidation release. Tax capital is not a perpetual extra tax saving.',
        'Finance uses TTM earnings, sales uses ordinary incremental capital intensity, and other minority uses midpoint residual profit. Their broader sensitivities remain in component packages rather than being silently claimed fully crossed here.',
        'Common 6/8/10 percent hurdles are comparative experiments; industrial WACC and subsidiary equity costs are not empirically shown equal.',
        'Representative 8 percent, prior-FY capex, 60-day latest-half cash buffer and excluded unclassified payables are transparent comparison choices, not probability-calibrated best estimates.',
        'All price/volume, constant-margin, capital-retention and dividend-availability caveats from input packages remain binding. No observed stock price or desired buy threshold was used.'
    ]
    out=ROOT/'runtime/company-research'/('600519-integrated-conditional-equity-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir()
    payload={'symbol':'600519','valuation_date':valuation.isoformat(),'currency':'CNY',
        'results':output,'representative_scenarios':representatives,'limitations':limitations,
        'valuation_approved':False,'industrial_financial_scope_approved':False,'strategy_approved':False}
    (out/'evidence.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# 茅台条件股权估值整合','',
        '首次将经营DCF、现金留存、税资本、金融公司、销售及其他少数权益、披露股数放入同一计算。研究条件未全部验收，不是交易合理价。','',
        '| 经营情景 | 条件每股值（元） | 条件普通股权益（亿元） |','| --- | ---: | ---: |']
    for r in representatives:
        lines.append(f"| {r['scenario']} | {D(r['conditional_value_per_disclosed_share']):.2f} | {D(r['conditional_equity_value'])/D('1e8'):.2f} |")
    lines+=['','代表组固定8%回报、2025资本开支锚点、60天最新半年支付缓冲、不把往来款计作经营NWC、仅内部未实现利润税资产计为经营税资本。全部648组及逐项桥接见evidence.json。','',
        '## 代表组桥接（亿元）','', '| 项目 | 悲观 | 基准 | 乐观 |','| --- | ---: | ---: | ---: |']
    for key in representatives[0]['bridge']:
        lines.append('| '+key+' | '+' | '.join(f"{D(r['bridge'][key])/D('1e8'):.4f}" for r in representatives)+' |')
    lines+=['','## 必须保留的限制','']+['- '+x for x in limitations]
    (out/'review.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'inputs':{str(p):sha(p) for p in paths},
        'script_sha256':sha(Path(__file__)),'outputs':{p.name:sha(p) for p in out.iterdir()}},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'runs':len(output),'representatives':[{k:r[k] for k in ['scenario','conditional_equity_value','conditional_value_per_disclosed_share']} for r in representatives]},ensure_ascii=False))


if __name__=='__main__':main()
