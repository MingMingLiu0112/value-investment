"""Integrate explicit cash-reserve scenarios with the existing dated DCF engine."""
from datetime import date,datetime,timezone
from decimal import Decimal as D
from pathlib import Path
import json
import sys
ROOT=Path('D:/GPTProject/value-investment')
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from value_investment_agent.scenario_valuation import ForecastYear,Terminal,value_scenario
from check_moutai_ttm_comparability import sha

INPUTS={
 'cash':('600519-cash-financial-estimates-20260909T133421689700Z','e85ec5461f2b13ebd14632455011c166976c6e2bbd56cd20d8bfa117009b468c'),
 'dcf':('600519-conditional-operating-dcf-20260909T123857151905Z','931d9234f3e473b50ec30f4c65fb4e08deb263f9a34fd9babc780d9f5037372b'),
 'operating':('600519-operating-forecast-20260909T104143099320Z','cb52c2b0ac4b7b8474b1afd30a726845a995a14739d8f91ea872256f58b6f2bb')}


def main():
    packs={}
    paths=[]
    for key,(folder,digest) in INPUTS.items():
        p=ROOT/'runtime/company-research'/folder/'evidence.json'
        if sha(p)!=digest:
            raise ValueError('Pinned input changed: '+key)
        packs[key]=json.loads(p.read_text(encoding='utf-8'))
        paths.append(p)
    # Recover the reported TTM revenue from the source-defined operating package.
    operating=packs['operating']
    ttm_revenue=D(operating['ttm_facts']['revenue'])
    if ttm_revenue<=0:
        raise ValueError('Positive reported TTM revenue required')
    output=[]
    valuation=date.fromisoformat(packs['dcf']['valuation_date'])
    for base in packs['dcf']['results']:
        full=operating['results'][base['scenario']]
        if len(full)!=len(base['annual_calculations']):
            raise ValueError('Forecast lengths differ')
        for cash in packs['cash']['liquidity_stress_cases']:
            initial=D(cash['illustrative_reserve'])
            previous=initial
            changes=[]
            forecast=[]
            dates=[]
            for year,annual in zip(full,base['annual_calculations']):
                if year['period_end']!=annual['cash_flow_date']:
                    raise ValueError('Cash reserve forecast date mismatch')
                # Ending required stock uses full-year activity, never stub revenue.
                ending=initial*D(year['operating_revenue'])/ttm_revenue
                delta=ending-previous
                previous=ending
                payment=date.fromisoformat(annual['cash_flow_date'])
                dates.append(payment)
                changes.append({'period_end':payment.isoformat(),'required_cash_end':str(ending),'increase':str(delta)})
                forecast.append(ForecastYear(annual['year'],D(annual['ebit']),D(annual['cash_tax_rate']),
                    D(annual['depreciation']),D(annual['capex']),D(annual['working_capital_increase'])+delta,
                    D(annual['wacc']),(str(paths[0]),str(paths[1]),str(paths[2]))))
            rate=D(base['discount_rate'])
            terminal=Terminal(D(base['terminal_calculation']['next_year_nopat']),D(0),D(1),rate,('same-zero-growth-terminal-no-reserve-liquidation',))
            calculated=value_scenario(forecast=forecast,terminal=terminal,bridge=(),
                operating_exposure_ids=('same-conditional-operations-plus-operating-cash',),ordinary_shares=D('1250081601'),
                share_evidence_refs=('unused-june-share-count-no-equity-output',),currency='CNY',
                scenario_id=f"{base['scenario']}-{base['capital_anchor']}-{base['nwc_case']}-{rate}-{cash['cash_interruption_days']}-{cash['payment_basis']}",
                valuation_date=valuation,cash_flow_dates=tuple(dates),timing_evidence_refs=('same-ACT365F-period-end-assumption',))
            operating_change=calculated['operating_value']-D(base['conditional_operating_pv'])
            independent=-sum(float(r['increase'])/(1+float(rate))**((d-valuation).days/365) for r,d in zip(changes,dates))
            if abs(float(operating_change)-independent)>0.01:
                raise ValueError('Independent reserve PV change differs')
            net_change=operating_change-initial
            output.append({'scenario':base['scenario'],'capital_anchor':base['capital_anchor'],'nwc_case':base['nwc_case'],
                'discount_rate':str(rate),'reserve_days':cash['cash_interruption_days'],'payment_basis':cash['payment_basis'],
                'initial_reserved_cash':str(initial),'reserve_forecast':changes,
                'operating_pv_change':str(operating_change),'bridge_change':str(-initial),
                'combined_value_change_before_other_unresolved_adjustments':str(net_change),
                'adjusted_conditional_operating_pv':str(calculated['operating_value'])})
    if len(output)!=324:
        raise ValueError('Incomplete cash-reserve grid')
    out=ROOT/'runtime/company-research'/('600519-operating-cash-sensitivity-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir()
    result={'symbol':'600519','valuation_date':valuation.isoformat(),'unit':'CNY','results':output,
        'equity_value':None,'fair_value_per_share':None,'valuation_approved':False,
        'assumptions':['Carry June required cash to September unchanged, not observed balance.',
            'Required cash scales with full forecast revenue at fixed historical payment/revenue relationship; costs and taxes can diverge.',
            'Initial reserve reduces excess assets once; future changes reduce/increase operating cashflow once.',
            'Zero terminal growth means constant required cash, no further annual investment and no terminal liquidation release.',
            'No interest income is assigned to operating cash; not an observed deposit yield.',
            'All six stress reserves are retained; no empirically optimal cash level or complete equity valuation claimed.']}
    (out/'evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    grouped=[]
    for days in [30,60,90]:
        values=[D(r['combined_value_change_before_other_unresolved_adjustments']) for r in output if r['reserve_days']==days]
        grouped.append({'days':days,'minimum_change':str(min(values)),'maximum_change':str(max(values))})
    (out/'summary.json').write_text(json.dumps(grouped,indent=2),encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'inputs':{str(p):sha(p) for p in paths},
        'script_sha256':sha(Path(__file__)),'engine_sha256':sha(ROOT/'src/value_investment_agent/scenario_valuation.py'),
        'outputs':{p.name:sha(p) for p in out.iterdir()}},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'runs':len(output),'summaries':grouped},ensure_ascii=False))


if __name__=='__main__':main()
