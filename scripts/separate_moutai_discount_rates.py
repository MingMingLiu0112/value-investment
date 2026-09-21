"""Separate operating, finance and minority experimental rates using pinned components."""
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal as D, localcontext
from pathlib import Path
import json
from integrate_moutai_conditional_equity import INPUTS, unique
from replay_moutai_distributions import digest, write_json

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'runtime/company-research'
SOURCE=BASE/'600519-integrated-conditional-equity-20260909T142721122559Z/evidence.json'
SOURCE_HASH='67e908b43a33700442267796e71a75e91b93430cd749de9fe1392e3d01eff6bc'
RATES=('0.06','0.08','0.10')
NONRATE=('scenario','capital_anchor','nwc_case','reserve_days','payment_basis','tax_case')


def main():
    if digest(SOURCE)!=SOURCE_HASH:
        raise ValueError('Integrated source changed')
    original=json.loads(SOURCE.read_text(encoding='utf-8'))
    if original['valuation_approved'] or original['strategy_approved'] or len(original['results'])!=648:
        raise ValueError('Unexpected original scope')
    packs={};pins={str(SOURCE.relative_to(ROOT)):SOURCE_HASH}
    for name in ('finance','minority'):
        folder,expected=INPUTS[name]
        path=BASE/folder/'evidence.json'
        if digest(path)!=expected:
            raise ValueError('Component changed: '+name)
        packs[name]=json.loads(path.read_text(encoding='utf-8'))
        pins[str(path.relative_to(ROOT))]=expected
    results=[];diagonal=0
    with localcontext() as context:
        context.prec=45
        for index,row in enumerate(original['results']):
            shares=D(row['disclosed_share_assumption'])
            if shares<=0:
                raise ValueError('Invalid disclosed shares')
            old=row['bridge']
            replace=('finance_parent_fair_minus_book','sales_minority_additional_deduction','other_minority_additional_deduction')
            fixed=sum(D(value) for key,value in old.items() if key not in replace)
            for finance_rate in RATES:
                finance=unique(packs['finance']['results'],earnings_anchor='ttm_net_profit',equity_discount_rate=finance_rate)
                for minority_rate in RATES:
                    sales=unique(packs['minority']['results'],scenario=row['scenario'],capital_intensity_multiplier='1',equity_discount_rate=minority_rate)
                    other=unique(packs['minority']['other_minority_scope']['estimates'],profit_anchor='midpoint',equity_rate=minority_rate)
                    adjustments={
                        'finance_parent_fair_minus_book':D(finance['parent_bridge_fair_minus_book_adjustment']),
                        'sales_minority_additional_deduction':-D(sales['additional_deduction_if_book_already_deducted']),
                        'other_minority_additional_deduction':-D(other['additional_deduction_if_book_already_deducted'])}
                    value=fixed+sum(adjustments.values())
                    # Independent change-to-old-value path, not the fixed-scope sum.
                    independent=float(row['conditional_equity_value'])+sum(float(v)-float(old[k]) for k,v in adjustments.items())
                    if abs(float(value)-independent)>.01:
                        raise ValueError('Independent equity replacement mismatch')
                    if finance_rate==minority_rate==row['discount_rate']:
                        if abs(value-D(row['conditional_equity_value']))>D('.000001'):
                            raise ValueError('Original equal-rate diagonal not preserved')
                        diagonal+=1
                    results.append({**{key:row[key] for key in NONRATE},'original_row_index':index,
                                    'operating_rate':row['discount_rate'],'finance_equity_rate':finance_rate,
                                    'minority_equity_rate':minority_rate,'replaced_bridge_items':{k:str(v) for k,v in adjustments.items()},
                                    'fixed_bridge_subtotal':str(fixed),'conditional_equity_value':str(value),
                                    'conditional_value_per_disclosed_share':str(value/shares),
                                    'formal_fair_value':None,'trade_approved':False})
    dimensions=(*NONRATE,'operating_rate','finance_equity_rate','minority_equity_rate')
    keys=[tuple(str(r[k]) for k in dimensions) for r in results]
    if len(results)!=5832 or len(set(keys))!=5832 or diagonal!=648:
        raise ValueError('Incomplete independent-rate grid')
    comparisons={}
    for rate in ('operating_rate','finance_equity_rate','minority_equity_rate'):
        held=[k for k in dimensions if k!=rate]
        groups=defaultdict(list)
        for row in results:
            groups[tuple(str(row[k]) for k in held)].append(row)
        spans=[]
        for group in groups.values():
            if {r[rate] for r in group}!=set(RATES):
                raise ValueError('Unmatched rate comparison')
            values={r[rate]:D(r['conditional_value_per_disclosed_share']) for r in group}
            if rate=='finance_equity_rate' and not values['0.06']>=values['0.08']>=values['0.10']:
                raise ValueError('Finance value does not decline with rate')
            if rate=='minority_equity_rate' and not values['0.06']<=values['0.08']<=values['0.10']:
                raise ValueError('Minority deduction does not decline with rate')
            spans.append(max(values.values())-min(values.values()))
        comparisons[rate]={'matched_groups':len(groups),'minimum_span':str(min(spans)),
                           'maximum_span':str(max(spans)),'mean_span':str(sum(spans)/len(spans))}
    limits=[
        'Rates are independently varied 6/8/10 percent experiments, not approved industrial WACC or subsidiary equity costs.',
        'Finance retains TTM earnings and minority retains the original capital/profit anchors. New grid separates discount-rate dimensions, not unverified overhead or cashflow boundaries.',
        'Sales and other minority use a shared minority experiment rate; their company-specific costs remain unapproved.',
        'Higher minority discount rate lowers the deducted claim and raises conditional parent value. This arithmetic is not evidence that worsening subsidiary risk benefits shareholders.',
        '648 equal-rate cases reproduce the old grid. All inherited assumptions and original limitations remain binding.',
        'No historical values, current market price, probability distribution or trade threshold is introduced.'
    ]
    out=BASE/('600519-separated-rates-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir()
    write_json(out/'evidence.json',{'symbol':'600519','results':results,'rate_comparisons':comparisons,
                                   'equal_rate_cases_reproduced':diagonal,'limits':limits,
                                   'inherited_limitations':original['limitations'],'valuation_approved':False,'strategy_approved':False})
    labels={'operating_rate':'经营折现率','finance_equity_rate':'金融权益回报率','minority_equity_rate':'少数权益回报率'}
    lines=['# 茅台独立回报率实验','', '5832组条件试算；原648组同回报率结果全部复现。不是批准估值。','',
           '| 独立变化因素 | 平均每股影响幅度 | 最大每股影响幅度 |','| --- | ---: | ---: |']
    for key,row in comparisons.items():
        lines.append(f"| {labels[key]} | {D(row['mean_span']):.2f}元 | {D(row['maximum_span']):.2f}元 |")
    lines+=['','## 适用限制','']+['- '+x for x in limits]
    (out/'review.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    write_json(out/'manifest.json',{'inputs':pins,'script_sha256':digest(Path(__file__)),
                                   'join_helper_script_sha256':digest(ROOT/'scripts/integrate_moutai_conditional_equity.py'),
                                   'outputs':{p.name:digest(p) for p in out.iterdir()}})
    print(json.dumps({'output':str(out),'rows':len(results),'diagonal':diagonal,'comparisons':comparisons},ensure_ascii=False))


if __name__=='__main__':main()
