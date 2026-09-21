"""Matched-factor comparisons of the existing complete conditional DCF grid."""
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal as D
from itertools import product
import json
from pathlib import Path
from check_moutai_ttm_comparability import ROOT,sha


def main():
    folder=ROOT/'runtime/company-research/600519-conditional-operating-dcf-20260909T123857151905Z'
    source=folder/'evidence.json'
    if sha(source)!='931d9234f3e473b50ec30f4c65fb4e08deb263f9a34fd9babc780d9f5037372b':
        raise ValueError('DCF package changed')
    data=json.loads(source.read_text(encoding='utf-8'))
    if data['valuation_approved'] or data['fair_value_per_share'] is not None:
        raise ValueError('Unexpected valuation approval')
    factors={'scenario':['bear','base','bull'],
        'capital_anchor':['recent_ttm','fy2025_spending','fy2024_spending'],
        'nwc_case':['exclude_unclassified_payables','include_all_unclassified_payables'],
        'discount_rate':['0.06','0.08','0.10']}
    dimensions=list(factors)
    rows=data['results']
    keys=[tuple(r[k] for k in dimensions) for r in rows]
    if len(keys)!=len(set(keys)) or set(keys)!=set(product(*factors.values())):
        raise ValueError('Not the complete balanced factor grid')
    comparisons={}
    for varied,levels in factors.items():
        held=[k for k in dimensions if k!=varied]
        groups=defaultdict(list)
        for r in rows:
            groups[tuple(r[k] for k in held)].append(r)
        output=[]
        for key,subset in groups.items():
            if {r[varied] for r in subset}!=set(levels):
                raise ValueError('Unmatched factor levels')
            values=[D(r['conditional_operating_pv']) for r in subset]
            output.append({'held_fixed':dict(zip(held,key)),
                'conditional_operating_pv_span':str(max(values)-min(values)),
                'level_values':{r[varied]:r['conditional_operating_pv'] for r in subset}})
        spans=[D(r['conditional_operating_pv_span']) for r in output]
        comparisons[varied]={'matched_comparisons':output,'min_span':str(min(spans)),
            'max_span':str(max(spans)),'mean_span':str(sum(spans)/len(spans))}
    terminal=[D(r['terminal_pv_share']) for r in rows]
    result={'symbol':'600519','unit':'CNY','source_sha256':sha(source),'grid_size':len(rows),
        'comparisons':comparisons,'terminal_share_range':[str(min(terminal)),str(max(terminal))],
        'valuation_approved':False,
        'interpretation':['Each span holds every other grid dimension fixed; not a probability or statistical confidence interval.',
            'Ranks depend on chosen experimental ranges and do not prove universally dominant economic risks.',
            'Terminal amount is not varied independently here; its high contribution cannot prove terminal assumptions are sound.',
            'Unmodelled financial scope, tax timing and minority claims are absent from this attribution, not insignificant.',
            'Use the matched grid to prioritize full company-model assumptions, not tune parameters to reach a buy price.']}
    out=ROOT/'runtime/company-research'/('600519-dcf-sensitivity-review-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir()
    (out/'evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    labels={'scenario':'经营情景','capital_anchor':'资本开支锚点','nwc_case':'往来款分类','discount_rate':'折现率'}
    lines=['# 条件DCF敏感性复核','', '保持其他条件一致，逐项改变一个因素。结果为经营现值变化，单位亿元；不是股权估值。','',
        '| 因素 | 最小影响 | 最大影响 | 平均影响 |','| --- | ---: | ---: | ---: |']
    for k,v in comparisons.items():
        lines.append(f"| {labels[k]} | {D(v['min_span'])/D('1e8'):.2f} | {D(v['max_span'])/D('1e8'):.2f} | {D(v['mean_span'])/D('1e8'):.2f} |")
    lines+=['',f'终值占经营现值比例：{min(terminal):.1%}至{max(terminal):.1%}。','',
        '这些范围仅反映当前实验。优先检验长期经营假设及资本成本，不能以微小分类差异已查清替代它们；未纳入实验的股权桥接、税务和少数股东仍须完成。']
    (out/'review.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'inputs':{str(p):sha(p) for p in [source,Path(__file__)]},
        'outputs':{p.name:sha(p) for p in out.iterdir()}},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'mean_spans':{k:v['mean_span'] for k,v in comparisons.items()},'terminal_share_range':result['terminal_share_range']}))


if __name__=='__main__':
    main()
