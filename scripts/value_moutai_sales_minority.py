"""Scenario-linked minority dividends after explicit net-capital retention."""
from datetime import date,datetime,timezone
from decimal import Decimal as D,localcontext
from pathlib import Path
import json
from check_moutai_ttm_comparability import ROOT,sha,texts
from value_moutai_finance_equity import SOURCES as FINANCE_SOURCES

INPUTS={
 'sales':('600519-sales-minority-20260909T123034927493Z','149b847ba84a332a57dac5bce76e95417ce74bc64ebf7cb5f1f454f09aa92c9b'),
 'products':('600519-product-forecast-20260909T103718221562Z','9488a8c0fb97bf0c62ec6bc24ca202910b95c15577fb1ca9595f3038836dcadc'),
 'bridge':('600519-equity-bridge-control-20260909T132548421808Z','1c5137422eeb75ba62ed39d244256c304b7e46bd77a9257a7e1c5929fe6212cd')}


def main():
    packs={};paths=[]
    for key,(directory,digest) in INPUTS.items():
        path=ROOT/'runtime/company-research'/directory/'evidence.json'
        if sha(path)!=digest:
            raise ValueError('Minority input changed: '+key)
        packs[key]=json.loads(path.read_text(encoding='utf-8'));paths.append(path)
    sales=packs['sales']
    for binding in sales['source_bindings']:
        if sha(ROOT/binding['path'])!=binding['sha256']:
            raise ValueError('Sales original changed')
    book_control=packs['bridge']['minority_book_control']
    book=D(book_control['sales_net_assets_at_rounded_precision'])
    minority_book=D(book_control['sales_reported'])
    base_profit=D(sales['ttm']['net_profit'])
    fraction=D(sales['minority_fraction'])
    valuation=date(2026,9,9)
    results=[]
    with localcontext() as ctx:
        ctx.prec=45
        for scenario,product in packs['products']['results'].items():
            growth=D(packs['products']['assumptions'][scenario]['moutai'][0])
            forecast_years=product['products']['moutai']
            for retention in map(D,['1','1.5','2']):
                for rate in map(D,['.06','.08','.10']):
                    previous_date=valuation;previous_book=book;factor=D(1)
                    dividend_pv=D(0);excess_pv=D(0);rows=[]
                    for n,year in enumerate(forecast_years,1):
                        payment=date.fromisoformat(year['period_end'])
                        span=D((payment-previous_date).days)/D(365)
                        step_factor=(1+rate)**span
                        factor*=step_factor
                        activity=(1+growth)**n
                        # A capital-intensity stress on additional assets; no contraction release.
                        required=book+retention*book*max(activity-1,D(0))
                        ending=max(previous_book,required)
                        increase=ending-previous_book
                        full_profit=base_profit*activity
                        profit=full_profit*span if n==1 else full_profit
                        dividend=profit-increase
                        excess=profit-previous_book*(step_factor-1)
                        dividend_pv+=dividend/factor
                        excess_pv+=excess/factor
                        rows.append({'payment_date':payment.isoformat(),'activity_factor':str(activity),
                            'net_profit_assumption':str(profit),'equity_beginning':str(previous_book),
                            'equity_ending':str(ending),'capital_retained':str(increase),
                            'distributable_cash_assumption':str(dividend),'discount_factor':str(1/factor)})
                        previous_book=ending;previous_date=payment
                    terminal=full_profit/rate
                    equity=dividend_pv+terminal/factor
                    excess_value=book+excess_pv+(terminal-previous_book)/factor
                    independent=sum(float(r['distributable_cash_assumption'])/(1+float(rate))**((date.fromisoformat(r['payment_date'])-valuation).days/365) for r in rows)
                    independent+=float(terminal)/(1+float(rate))**((payment-valuation).days/365)
                    if abs(equity-excess_value)>D('.000001') or abs(float(equity)-independent)>.01:
                        raise ValueError('Minority DDM/RI/float reconciliation failed')
                    claim=equity*fraction
                    results.append({'scenario':scenario,'capital_intensity_multiplier':str(retention),
                        'equity_discount_rate':str(rate),'annual_rows':rows,
                        'sales_entity_equity_estimate':str(equity),'sales_minority_full_claim':str(claim),
                        'sales_minority_book':str(minority_book),
                        'additional_deduction_if_book_already_deducted':str(claim-minority_book),
                        'terminal_equity_value':str(terminal),'crosscheck_equity':str(excess_value)})
    representative=[r for r in results if D(r['equity_discount_rate'])==D('.08') and D(r['capital_intensity_multiplier'])==1]
    if len(results)!=27 or len(representative)!=3:
        raise ValueError('Incomplete minority scenarios')
    # Complete the remaining minority scope without treating the residual as zero.
    disclosed_nci=['2990257731.99','1583719151.14','1516450144.92']
    for source,page,value in zip(sales['source_bindings'],[62,29,31],disclosed_nci):
        if any(format(D(value),',.2f') not in t for t in texts(ROOT/source['path'],page)):
            raise ValueError('Consolidated minority profit source mismatch')
    for path,digest,page,values in FINANCE_SOURCES:
        if sha(path)!=digest or any(values[2]+'亿元' not in t for t in texts(path,page)):
            raise ValueError('Finance minority profit original mismatch')
    all_nci=D(disclosed_nci[0])-D(disclosed_nci[1])+D(disclosed_nci[2])
    finance_ttm=(D(FINANCE_SOURCES[0][3][2])-D(FINANCE_SOURCES[1][3][2])+D(FINANCE_SOURCES[2][3][2]))*D('1e8')
    sales_ttm=base_profit*fraction
    residual_profit=all_nci-sales_ttm-finance_ttm*D('.49')
    residual_book=D(book_control['other_and_consolidation_residual_midpoint'])
    uncertainty=D('.015')+D('7.5')+D('735000')
    other=[]
    interval=D((date(2027,6,30)-valuation).days)/365
    for anchor,profit in [('rounding_low',residual_profit-uncertainty),('midpoint',residual_profit),('rounding_high',residual_profit+uncertainty)]:
        for rate in map(D,['.06','.08','.10']):
            factor=(1+rate)**interval
            value=(profit*interval+profit/rate)/factor
            independently=(float(profit)*float(interval)+float(profit)/float(rate))/(1+float(rate))**float(interval)
            if abs(float(value)-independently)>.01:
                raise ValueError('Residual minority independent value mismatch')
            other.append({'profit_anchor':anchor,'net_profit_assumption':str(profit),'equity_rate':str(rate),
                'full_claim_estimate':str(value),'book_claim_midpoint':str(residual_book),
                'additional_deduction_if_book_already_deducted':str(value-residual_book)})
    other_scope={'all_minority_ttm':str(all_nci),'sales_minority_ttm':str(sales_ttm),
        'finance_minority_ttm_rounded':str(finance_ttm*D('.49')),'residual_net_profit_ttm':str(residual_profit),
        'source_rounding_uncertainty':str(uncertainty),'book_midpoint':str(residual_book),'estimates':other,
        'scope':'Other industrial subsidiaries plus consolidation attribution residual; not verified standalone entity FCFE.',
        'assumptions':'Constant current capital, no incremental capital need, flat residual earnings fully distributable, same hypothetical first dividend; stress estimates not approved fair claims.',
        'no_double_fraction':'Residual is already the outside shareholders profit; do not multiply by 5% or 49% again.'}
    out=ROOT/'runtime/company-research'/('600519-sales-minority-estimates-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir()
    limits=[
        'Sales company is a separate legal entity; 5 percent does not apply to total industrial group value.',
        'Growth follows existing Moutai net-revenue stress paths as an explicit proxy for subsidiary activity. Internal transfer prices, channel changes and July pricing can change its margin.',
        'Profit grows at the activity rate with fixed net margin; not an observed future profit forecast.',
        'Net book capital requirements scale with positive activity growth at 1/1.5/2 times current intensity; existing capital is not released on contraction.',
        'Future equity retention is a proxy for total net-capital needs, not observed capex/working-capital/financing or legal dividend permission.',
        'TTM CFO/profit about 76.5 percent is counterevidence to assuming full earnings available; persistent cash-conversion shortfalls can invalidate these proxy retention assumptions.',
        'First stub income assumes uniform accrual; full-year subsequent profits and hypothetical June year-end dividends are not actual payout timing.',
        'At the terminal, net profit is flat, no further capital investment or liquidation release; held idle capital earns no separately added income.',
        'Profit includes whole-entity income; the resulting claim includes retained assets. Do not also deduct another minority cash or book-equity claim.',
        'Rates are equity-return sensitivities, not approved subsidiary equity cost. Arithmetic equivalence is not economic approval.',
        'Other industrial minority and financial minority remain separate. These scenarios do not finish the total group equity bridge.'
    ]
    payload={'symbol':'600519','entity':sales['entity'],'valuation_date':valuation.isoformat(),
        'unit':'CNY','source_book_date':'2026-06-30','minority_fraction':str(fraction),
        'ttm_cfo_to_profit':sales['ttm_cfo_to_profit'],'results':results,
        'representative_selection':'Same three operating cases, middle tested return and unamplified incremental capital intensity; research comparison, not empirical approval.',
        'other_minority_scope':other_scope,'valuation_approved':False,'limitations':limits}
    (out/'evidence.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# 销售子公司少数权益条件估计','',
        '五年经营情景映射至子公司净利润；先留存新增资本再估未来股利。资本保留不等于现金可分配事实。','',
        '| 情景 | 新增资本强度倍数 | 权益回报 | 5%完整索偿（亿元） | 已扣账面后追加扣项（亿元） |',
        '| --- | ---: | ---: | ---: | ---: |']
    for r in results:
        lines.append(f"| {r['scenario']} | {r['capital_intensity_multiplier']} | {D(r['equity_discount_rate']):.0%} | {D(r['sales_minority_full_claim'])/D('1e8'):.4f} | {D(r['additional_deduction_if_book_already_deducted'])/D('1e8'):.4f} |")
    lines+=['','## 剩余少数权益','',
        f'合并TTM少数损益减销售5%及财务49%后，残余{residual_profit/10000:.4f}万元。该量已是外部股东份额，不再乘一次持股比例。',
        '固定资本及零增长全分派条件下的九种折现/披露舍入结果见JSON；残余包括合并调整，尚非精确其他子公司独立FCFE。','',
        '## 条件和反证','']+['- '+x for x in limits]
    (out/'review.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'inputs':{str(p):sha(p) for p in paths},
        'finance_originals':{str(p):h for p,h,_,_ in FINANCE_SOURCES},
        'script_sha256':sha(Path(__file__)),'outputs':{p.name:sha(p) for p in out.iterdir()}},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'runs':len(results),'other_minority':other_scope,'representative':[{
        k:r[k] for k in ['scenario','sales_minority_full_claim','additional_deduction_if_book_already_deducted']} for r in representative]},ensure_ascii=False))


if __name__=='__main__':main()
