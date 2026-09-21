"""Finance-subsidiary equity scenarios, no release of existing capital."""
from datetime import date,datetime,timezone
from decimal import Decimal as D,localcontext
from fractions import Fraction as F
from pathlib import Path
import json
from check_moutai_ttm_comparability import ROOT,sha,texts

BASE=ROOT/'runtime/company-research'
SOURCES=[
 (BASE/'600519-finance-comparatives-20260909T135909985886Z/1225114745.pdf','0225fe2f8dc67e8cdf751bcbb69239e831a0ceeb3c2c5c3ab9f5d74a3ba5dd09',7,['32.17','15.32','11.56','114.39']),
 (BASE/'600519-finance-comparatives-20260909T135909985886Z/1224462928.pdf','5d32e0aa02a47f2178cc973b278177d337f472eaacd46ae2807ed5b6b44ef297',5,['17.04','8.45','6.34','112.76']),
 (BASE/'600519-finance-current-20260909T073502376364Z/600519-1225475863.pdf','cf2d50aa028fcf11ce9eb04746932b7a9be25c3e31d443295f77add844b1121b',7,['15.76','8.02','4.68','119.41'])]


def main():
    for path,digest,page,values in SOURCES:
        if sha(path)!=digest:
            raise ValueError('Finance original changed')
        pair=texts(path,page)
        for value in values:
            if any(value+'亿元' not in t for t in pair):
                raise ValueError('Finance original numeric unit mismatch: '+value)
    facts={}
    for i,name in enumerate(['revenue','pretax_profit','net_profit']):
        v=(D(SOURCES[0][3][i])-D(SOURCES[1][3][i])+D(SOURCES[2][3][i]))*D('1e8')
        if F(v)!=(F(SOURCES[0][3][i])-F(SOURCES[1][3][i])+F(SOURCES[2][3][i]))*10**8:
            raise ValueError('Independent finance TTM failed')
        facts[name]=str(v)
    capital=D('119.41')*D('1e8')
    valuation=date(2026,9,9)
    first=date(2027,6,30)
    period=D((first-valuation).days)/D(365)
    earnings=[('latest_half_annualized',D('4.68')*2*D('1e8')),
              ('ttm_net_profit',D(facts['net_profit'])),
              ('prior_full_year',D('11.56')*D('1e8'))]
    results=[]
    with localcontext() as ctx:
        ctx.prec=45
        for anchor,earn in earnings:
            for rate in map(D,['.06','.08','.10']):
                factor=(1+rate)**period
                dividend=earn*period
                terminal=earn/rate
                value=(dividend+terminal)/factor
                first_capital_charge=capital*(factor-1)
                first_excess=dividend-first_capital_charge
                annual_excess=earn-rate*capital
                residual_income_value=capital+(first_excess+annual_excess/rate)/factor
                independent=(float(earn)*float(period)+float(earn)/float(rate))/(1+float(rate))**float(period)
                if abs(value-residual_income_value)>D('.000001') or abs(float(value)-independent)>.01:
                    raise ValueError('Independent dividend/residual-income reconciliation failed')
                results.append({'earnings_anchor':anchor,'annual_net_profit_assumption':str(earn),
                    'equity_discount_rate':str(rate),'first_distribution':str(dividend),
                    'capital_retained':str(capital),'new_capital_required_assumption':'0',
                    'finance_equity_estimate':str(value),'residual_income_crosscheck':str(residual_income_value),
                    'parent_51pct_finance_value':str(value*D('.51')),
                    'parent_bridge_fair_minus_book_adjustment':str((value-capital)*D('.51'))})
    representative=next(r for r in results if r['earnings_anchor']=='ttm_net_profit' and D(r['equity_discount_rate'])==D('.08'))
    out=BASE/('600519-finance-equity-estimates-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir()
    limitations=[
        'Annualized interim, observed TTM and prior-year earnings are alternative persistence hypotheses, not confidence bounds.',
        'Rounded source values imply TTM rounding tolerance up to CNY 1.5 million; no claim of cent-accurate forecasts.',
        'Hold June book capital and required business scale unchanged to valuation date and thereafter; actual September capital and balance movements are not verified.',
        'Full future net-profit payout assumes no additional required capital, liquidity retention or distribution restrictions beyond current retained capital. It is not evidence of approved dividends.',
        'Capital adequacy above the regulatory minimum does not authorize releasing existing capital; the model releases none.',
        '6/8/10 percent are equity required-return sensitivities, not an empirically approved finance-company cost of equity or industrial WACC.',
        'First dividend is hypothetical June 2027 using uniform earnings accrual over the stub; future full-year payments are annual. Actual payout dates unknown.',
        'The pretax/net gap is retained in observed net profit, not recast as an observed cash tax rate.',
        'Residual-income agreement tests arithmetic under identical assumptions, not independent market valuation evidence.',
        'Consolidated asset retention requires adding only 51 percent of fair-minus-book finance equity, not gross finance equity again.',
        'Finance assets/expenses present in the operating DCF must still be removed consistently. Minority, tax and share scopes remain separate.'
    ]
    payload={'symbol':'600519','entity':'贵州茅台集团财务有限公司','valuation_date':valuation.isoformat(),
        'balance_date':'2026-06-30','currency':'CNY','ownership':'.51','ttm_facts_at_rounded_precision':facts,
        'first_distribution_date':first.isoformat(),'stub_act365f':str(period),'results':results,
        'representative_conditional_case':representative,'representative_case_selection':'TTM earnings and middle tested required return, for research comparison only; not an optimized or approved estimate.',
        'estimate_type':'conditional_constant_capital_dividend_equity','company_equity_valuation_approved':False,
        'finance_fair_value_approved':False,'limitations':limitations}
    (out/'evidence.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# 财务公司条件股权估计','',
        '使用同口径2025全年减2025半年加2026半年，TTM收入30.89亿元、税前利润14.89亿元、净利润9.90亿元。不是半年翻倍。', '',
        '现有119.41亿元资本持续留存；在业务规模、资本需求不增加且未来净利润可全额分派的明确条件下，计算未来股利现值。不释放监管资本。','',
        '| 盈利锚点 | 股权折现率 | 财务公司股权（亿元） | 归属51%公允减账面调整（亿元） |',
        '| --- | ---: | ---: | ---: |']
    for r in results:
        lines.append(f"| {r['earnings_anchor']} | {D(r['equity_discount_rate']):.0%} | {D(r['finance_equity_estimate'])/D('1e8'):.4f} | {D(r['parent_bridge_fair_minus_book_adjustment'])/D('1e8'):.4f} |")
    lines+=['','## 条件与边界','']+['- '+x for x in limitations]
    (out/'review.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'inputs':{str(p):h for p,h,_,_ in SOURCES},'script_sha256':sha(Path(__file__)),
        'outputs':{p.name:sha(p) for p in out.iterdir()}},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'ttm':facts,'representative':representative,'checks':'nine dividend/residual-income and independent float comparisons passed'},ensure_ascii=False))


if __name__=='__main__':main()
