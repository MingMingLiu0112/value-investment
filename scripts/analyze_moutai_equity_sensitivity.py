"""Matched-factor attribution of the integrated conditional equity grid."""
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal as D
from itertools import product
from pathlib import Path
import hashlib
import json

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'runtime/company-research/600519-integrated-conditional-equity-20260909T142721122559Z/evidence.json'
EXPECTED='67e908b43a33700442267796e71a75e91b93430cd749de9fe1392e3d01eff6bc'
FACTORS=['scenario','discount_rate','capital_anchor','nwc_case','reserve_days','payment_basis','tax_case']


def main():
    raw=SOURCE.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=EXPECTED:
        raise ValueError('Integrated source changed')
    data=json.loads(raw)
    if data['valuation_approved'] or data['strategy_approved']:
        raise ValueError('Unexpected approval scope')
    rows=data['results']
    levels={key:sorted({str(row[key]) for row in rows}) for key in FACTORS}
    keys=[tuple(str(row[key]) for key in FACTORS) for row in rows]
    if len(rows)!=648 or len(set(keys))!=648 or set(keys)!=set(product(*levels.values())):
        raise ValueError('Incomplete integrated factor grid')
    summaries={}
    for factor in FACTORS:
        held=[key for key in FACTORS if key!=factor]
        groups=defaultdict(list)
        for row in rows:
            groups[tuple(str(row[key]) for key in held)].append(row)
        comparisons=[]
        for key,group in groups.items():
            if sorted(str(row[factor]) for row in group)!=levels[factor]:
                raise ValueError('Unmatched factor group')
            values={str(row[factor]):D(row['conditional_value_per_disclosed_share']) for row in group}
            span=max(values.values())-min(values.values())
            if abs(float(span)-(max(map(float,values.values()))-min(map(float,values.values()))))>1e-9:
                raise ValueError('Independent span arithmetic failed')
            comparisons.append({'held_fixed':dict(zip(held,key)),'per_share_span':str(span),'level_values':{k:str(v) for k,v in values.items()}})
        spans=[D(r['per_share_span']) for r in comparisons]
        summaries[factor]={'minimum_span':str(min(spans)),'maximum_span':str(max(spans)),'mean_span':str(sum(spans)/len(spans)),'comparisons':comparisons}
    ranking=sorted(FACTORS,key=lambda key:D(summaries[key]['mean_span']),reverse=True)
    limits=[
        'All values are conditional CNY per disclosed share, not approved fair prices or trade limits.',
        'One factor varies at a time while all other grid dimensions stay fixed; means are unweighted descriptive summaries, not expectations.',
        'Ranking depends on experimental ranges; 6/8/10 percent common hurdle is not independently validated company WACC.',
        'Industrial and finance overhead separation, post-balance movements, historical forecasts and other unmodelled uncertainties remain outside this grid. They cannot be declared immaterial.',
        'Tax comparisons cover two deferred-tax-capital treatments only, not all cash tax or tax-rate uncertainty.',
        'Discount-rate comparisons also change financial/minority equity rates in this existing integrated design; the factor is a joint hurdle change, not isolated industrial WACC.',
        'No current stock price is used. Do not select parameters to generate a desired buy threshold.'
    ]
    out=ROOT/'runtime/company-research'/('600519-equity-sensitivity-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir()
    result={'symbol':'600519','grid_rows':648,'source_sha256':EXPECTED,'ranking':ranking,'factors':summaries,'limits':limits,'valuation_approved':False,'strategy_approved':False}
    (out/'evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    labels={'scenario':'经营情景','discount_rate':'联合回报率','capital_anchor':'资本开支锚点','nwc_case':'往来款分类','reserve_days':'现金缓冲天数','payment_basis':'现金支付基数','tax_case':'递延税资本分类'}
    lines=['# 茅台完整条件股权模型敏感性','', '单位：元/披露股。未批准为合理价，排序不代表因素发生概率。','', '| 因素 | 最小变化幅度 | 最大变化幅度 | 平均变化幅度 |','| --- | ---: | ---: | ---: |']
    for key in ranking:
        r=summaries[key]
        lines.append(f"| {labels[key]} | {D(r['minimum_span']):.2f} | {D(r['maximum_span']):.2f} | {D(r['mean_span']):.2f} |")
    lines+=['','## 解释限制','']+['- '+item for item in limits]
    (out/'review.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'source_path':str(SOURCE.relative_to(ROOT)),'source_sha256':EXPECTED,'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'outputs':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir()}},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'ranking':[{k:summaries[key][k] for k in ('mean_span','maximum_span')}|{'factor':key} for key in ranking]},ensure_ascii=False))


if __name__=='__main__':main()
