"""Rebase original annual profit to reviewed bonus-share dates; research only."""
import csv
import json
from datetime import datetime, timezone
from decimal import Decimal as D
from fractions import Fraction
from pathlib import Path
from replay_moutai_distributions import load_inputs, digest, write_json, ANNUAL_DIR
from build_moutai_annual_inputs import select_original_vintage


def main():
    root=Path(__file__).resolve().parents[1]
    bars,events,annual,refs=load_inputs(root)
    pre=root/ANNUAL_DIR/'prehistory-distribution.json'
    if digest(pre)!='05db89733bfd8b048b24e08ebfb7ce1fee7ca07ecdc5d75803fd63fa33aa2ca3':
        raise ValueError('Prehistory changed')
    old=json.loads(pre.read_text(encoding='utf-8'))
    if digest(root/old['source_path'])!=old['raw_file_hash']:
        raise ValueError('Prehistory original changed')
    availability=root/'runtime/strategy-validation/moutai-distribution-availability-20260909T093331444948Z'
    manifest=json.loads((availability/'manifest.json').read_text(encoding='utf-8'))
    if digest(availability/'evidence.json')!=manifest['evidence_sha256']:
        raise ValueError('Event availability changed')
    known={r['record_date']:r for r in json.loads((availability/'evidence.json').read_text(encoding='utf-8'))['events']}
    actions=[old]+[{**e,'available_at':known[e['record_date']]['available_at']} for e in events if e.get('bonus_shares_per_share')]
    for action in actions:
        if datetime.fromisoformat(action['available_at'])>=datetime.fromisoformat(action['ex_date']+'T00:00:00+08:00'):
            raise ValueError('Action not available before effective date')
    def shares_at(vintage,day):
        shares=D(vintage['inputs']['ending_issued_shares'])
        exact=Fraction(shares)
        applied=[]
        for action in sorted(actions,key=lambda a:a['ex_date']):
            if vintage['period_label']<action['ex_date']<=day:
                ratio=D(action['bonus_shares_per_share'])
                shares*=1+ratio; exact*=1+Fraction(ratio)
                applied.append(action['ex_date'])
        if shares!=shares.to_integral_value() or Fraction(shares)!=exact:
            raise ValueError('Noninteger or inconsistent share basis')
        return shares,applied
    crosschecks=[]
    for previous,current in zip(annual,annual[1:]):
        shares,_=shares_at(previous,current['period_label'])
        if shares!=D(current['inputs']['ending_issued_shares']):
            raise ValueError('Reviewed bonus events do not reconcile next original annual share count')
        crosschecks.append({'from':previous['source_id'],'to':current['source_id'],'shares':str(shares)})
    rows=[]
    for bar in bars:
        day=bar['date']; vintage=select_original_vintage(annual,day+'T15:00:00+08:00')[0]
        shares,applied=shares_at(vintage,day)
        profit=D(vintage['inputs']['parent_profit_cny'])
        rows.append({'date':day,'source_id':vintage['source_id'],'period':vintage['period_label'],
            'shares_on_reviewed_bonus_basis':str(shares),'original_annual_profit':str(profit),
            'annual_profit_per_rebased_share':str(profit/shares),'applied_bonus_dates':';'.join(applied),
            'complete_current_share_basis_verified':False,'trade_value_approved':False})
    out=root/'runtime/strategy-validation'/('moutai-daily-share-basis-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(exist_ok=False)
    with (out/'daily-share-basis.csv').open('w',encoding='utf-8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    write_json(out/'result.json',{'bars':len(rows),'rebased_bars':sum(bool(r['applied_bonus_dates']) for r in rows),
        'annual_share_crosschecks':crosschecks,'strategy_backtest_complete':False,
        'limitations':['Uses original annual profit, not quarterly TTM or accounting weighted EPS.',
            'Annual ending-share agreement does not prove absence of intervening buybacks or other share changes.',
            '2025 post-report repurchases/cancellations still require event coverage; share count is only the reviewed bonus basis.',
            'Equity distribution recognition and debt/asset changes are separate; no complete reference price produced.']})
    write_json(out/'input-references.json',refs+[{'path':str(pre.relative_to(root)),'sha256':digest(pre)},
        {'path':str((availability/'evidence.json').relative_to(root)),'sha256':digest(availability/'evidence.json')}])
    write_json(out/'manifest.json',{'script_sha256':digest(Path(__file__)),
        'outputs':{p.name:digest(p) for p in out.iterdir() if p.is_file()}})
    print(json.dumps({'output':str(out),'bars':len(rows),'rebased_bars':sum(bool(r['applied_bonus_dates']) for r in rows),'crosschecks':len(crosschecks)}))


if __name__=='__main__':
    main()
