"""Integrated operating DCF experiment; no equity valuation or trade approval."""
from datetime import date, datetime, timezone
from decimal import Decimal as D
import json
from pathlib import Path
import sys
ROOT=Path('D:/GPTProject/value-investment')
sys.path.insert(0,str(ROOT/'src'))
from value_investment_agent.scenario_valuation import ForecastYear,Terminal,value_scenario
from check_moutai_ttm_comparability import sha

INPUTS={
 'operating':('600519-dated-operating-20260909T121512582335Z','8d4dc2ae6970fd3f3f71731961fa167e3875045ac1fef15840f5e26a30fd6fec'),
 'capital':('600519-dated-reinvestment-20260909T121930214600Z','5963b633170af73c37cffa7c988795ad53ed8566685e5169b4ccd80e94583b45'),
 'nwc':('600519-nwc-sensitivity-20260909T114536573711Z','1e198cdfd8ba276147ec4eb1c5a6bf77d3ba62f5323619d244c3f13d270a4c42')}


def main():
    packs={}
    refs=[]
    for key,(folder,digest) in INPUTS.items():
        p=ROOT/'runtime/company-research'/folder/'evidence.json'
        if sha(p)!=digest:
            raise ValueError('Pinned component changed: '+key)
        packs[key]=json.loads(p.read_text(encoding='utf-8'))
        refs.append(str(p.relative_to(ROOT)))
    assumptions=[
        'This is a conditional operating calculation, not a complete company valuation.',
        'Charge all shared consolidated overhead to the operating proxy; industrial-financial allocation remains unapproved.',
        '25 percent cash-tax proxy applies to positive operating subtotal; it is not observed cash income tax.',
        'Carry June NWC unchanged to September valuation as an explicit balance approximation, then use forecast ending balance; no daily actual balance claimed.',
        'Existing stub operating and capital allocations retain their stated seasonal and uniform-within-quarter assumptions.',
        'Capitalized lease renewal investment assumed equal to matched ROU amortization, so the two additions cancel in operating cash proxy; not proven actual renewal needs.',
        'All 6/8/10 percent annual-effective discount experiments are shown for every operating case; these are not selected company WACC.',
        'Terminal is zero growth at final-year positive NOPAT, with replacement capital spending equal to depreciation and zero incremental NWC. This is a stable-state assumption, not a proven terminal cash flow.',
        'Terminal ROIC set to 1 only as an inactive engine parameter because growth is zero; no 100 percent company ROIC claim.',
        'Cash flows placed at period ends under ACT/365F; actual intra-period receipt/payment pattern not verified.',
        'No financial assets, debts or minority values are filled as zero. Equity bridge and per-share outputs are deliberately absent until reconciled.']
    asof=date.fromisoformat(packs['operating']['valuation_date'])
    results=[]
    for scenario,operating in packs['operating']['results'].items():
        for anchor in ['recent_ttm','fy2025_spending','fy2024_spending']:
            for nwc_case in packs['nwc']['classification_cases']:
                for rate in map(D,['.06','.08','.10']):
                    forecast=[]
                    dates=[]
                    previous=D(packs['nwc']['classification_cases'][nwc_case]['closing'])
                    for op in operating:
                        end=op['period_end']
                        cap=[r for r in packs['capital']['records'] if r['scenario']==scenario and r['spending_anchor']==anchor and r['period_end']==end]
                        wc=[r for r in packs['nwc']['forecast_sensitivity'] if r['scenario']==scenario and r['case']==nwc_case and r['period_end']==end]
                        if len(cap)!=1 or len(wc)!=1 or cap[0]['period_start']!=op['period_start']:
                            raise ValueError('Component date/scenario join failed')
                        ending=D(wc[0]['illustrative_nwc_balance'])
                        delta=ending-previous
                        previous=ending
                        payment=date.fromisoformat(end)
                        dates.append(payment)
                        forecast.append(ForecastYear(payment.year,D(op['subtotal_with_shared_expenses']),D('.25'),
                            D(cap[0]['da_ex_rou']),D(cap[0]['cash_capex']),delta,rate,tuple(refs)))
                    last=forecast[-1]
                    terminal=Terminal(max(last.ebit,D(0))*(1-last.cash_tax_rate),D(0),D(1),rate,('conditional-zero-growth-replacement-capital',))
                    calc=value_scenario(forecast=forecast,terminal=terminal,bridge=(),
                        operating_exposure_ids=('conditional-industrial-with-shared-expenses',),ordinary_shares=D('1250081601'),
                        share_evidence_refs=('June2026-reported-share-count-unused-no-per-share-output',),currency='CNY',
                        scenario_id=f'{scenario}-{anchor}-{nwc_case}-{rate}',valuation_date=asof,
                        cash_flow_dates=tuple(dates),timing_evidence_refs=('conditional-period-end-payments',))
                    # Recompute directly in binary arithmetic without calling the valuation engine.
                    independent=sum(float(r.ebit-max(r.ebit,D(0))*r.cash_tax_rate+r.depreciation-r.capex-r.working_capital_increase)
                        /(1+float(rate))**((d-asof).days/365) for r,d in zip(forecast,dates))
                    independent+=float(terminal.next_year_nopat/rate)/(1+float(rate))**((dates[-1]-asof).days/365)
                    if abs(independent-float(calc['operating_value']))>0.01:
                        raise ValueError('Independent operating DCF differs by over one cent')
                    results.append({'scenario':scenario,'capital_anchor':anchor,'nwc_case':nwc_case,'discount_rate':str(rate),
                        'conditional_operating_pv':str(calc['operating_value']),
                        'terminal_pv_share':str(calc['terminal_present_value']/calc['operating_value']),
                        'annual_calculations':calc['annual_cash_flows'],
                        'terminal_calculation':{'growth':'0','next_year_nopat':str(terminal.next_year_nopat),'present_value':str(calc['terminal_present_value'])},
                        'independent_pv':independent})
    if len(results)!=54:
        raise ValueError('Incomplete preregistered component grid')
    out=ROOT/'runtime/company-research'/('600519-conditional-operating-dcf-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir()
    payload={'symbol':'600519','valuation_date':asof.isoformat(),'unit':'CNY','assumptions':assumptions,
        'results':results,'equity_bridge':None,'fair_value_per_share':None,'valuation_approved':False,
        'strategy_approved':False,'status':'conditional_operating_integration_only'}
    (out/'evidence.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    lines=['# 茅台经营DCF条件实验','', '54组组合完整报告；不是股权价值、合理价或买卖信号。金额单位：亿元。','',
        '| 经营情景 | 资本开支锚点 | NWC分类 | 折现率 | 条件经营现值 | 终值占比 |','| --- | --- | --- | ---: | ---: | ---: |']
    for r in results:
        lines.append(f"| {r['scenario']} | {r['capital_anchor']} | {r['nwc_case']} | {D(r['discount_rate']):.0%} | {D(r['conditional_operating_pv'])/D('1e8'):.2f} | {D(r['terminal_pv_share']):.1%} |")
    lines+=['','## 假设与未完成范围','']+['- '+a for a in assumptions]
    (out/'review.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'inputs':{str(ROOT/r):sha(ROOT/r) for r in refs},
        'script_sha256':sha(Path(__file__)),'engine_sha256':sha(ROOT/'src/value_investment_agent/scenario_valuation.py'),
        'outputs':{p.name:sha(p) for p in out.iterdir()}},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'runs':len(results),'independent_checks':'passed','fair_value_per_share':None}))


if __name__=='__main__':
    main()
