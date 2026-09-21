"""Full-window legacy signal sensitivity, not approved valuation or fills."""
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal as D
from fractions import Fraction as F
from pathlib import Path
from replay_moutai_distributions import load_inputs, digest, write_json, ANNUAL_DIR
from build_moutai_annual_inputs import select_original_vintage

ROOT=Path(__file__).resolve().parents[1]

def main():
    bars,events,annual,refs=load_inputs(ROOT)
    pre=ROOT/ANNUAL_DIR/'prehistory-distribution.json'
    if digest(pre)!='05db89733bfd8b048b24e08ebfb7ce1fee7ca07ecdc5d75803fd63fa33aa2ca3':
        raise ValueError('Prehistory changed')
    old=json.loads(pre.read_text(encoding='utf-8'))
    if digest(ROOT/old['source_path'])!=old['raw_file_hash']:
        raise ValueError('Prehistory original changed')
    ap=ROOT/'runtime/strategy-validation/moutai-distribution-availability-20260909T093331444948Z/evidence.json'
    am=json.loads((ap.parent/'manifest.json').read_text(encoding='utf-8'))
    if digest(ap)!=am['evidence_sha256']:
        raise ValueError('Event availability changed')
    known={e['record_date']:e['available_at'] for e in json.loads(ap.read_text(encoding='utf-8'))['events']}
    actions=[{**old,'cash_per_share':old['cash_per_old_share_gross']}]+[
        {**e,'available_at':known[e['record_date']]} for e in events]
    rows=[]; counts={str(t):Counter() for t in (20,30,40)}
    for bar in bars:
        day=bar['date']; decision=day+'T15:00:00+08:00'
        vintage=select_original_vintage(annual,decision)[0]
        shares=D(vintage['inputs']['ending_issued_shares'])
        profit=D(vintage['inputs']['parent_profit_cny']); equity=D(vintage['inputs']['parent_equity_cny'])
        distribution=D(0); applied=[]
        for event in sorted(actions,key=lambda a:a['ex_date']):
            if vintage['period_label']<event['ex_date']<=day:
                if datetime.fromisoformat(event['available_at'])>datetime.fromisoformat(decision):
                    raise ValueError('Future distribution information')
                distribution+=shares*D(event['cash_per_share'])
                shares*=1+D(event.get('bonus_shares_per_share','0'))
                applied.append(event['record_date'])
        # Historical annual-profit/ending-share PE component, not rounded accounting EPS.
        unadjusted=(profit*18+equity*4)/(shares*2)
        adjusted=(profit*18+(equity-distribution)*4)/(shares*2)
        for value,book in ((unadjusted,equity),(adjusted,equity-distribution)):
            if abs(F(value)-(F(profit)*18+F(book)*4)/(F(shares)*2))>F(1,1000000):
                raise ValueError('Independent reference arithmetic failed')
        for threshold in (20,30,40):
            margin=D(threshold)/100; price=D(bar['close'])
            def state(value):
                if value<=0: return 'invalid_reference'
                if price<=value*(1-margin): return 'entry_condition'
                if price>value: return 'exit_condition_if_held'
                return 'neither'
            before,after=state(unadjusted),state(adjusted)
            counts[str(threshold)][before+' -> '+after]+=1
            rows.append({'date':day,'threshold_pct':threshold,'price':str(price),
                'annual_source_id':vintage['source_id'],'annual_available_at':vintage['available_at'],
                'reference_unadjusted':str(unadjusted),'reference_exdate_cash_scenario':str(adjusted),
                'condition_unadjusted':before,'condition_exdate_cash_scenario':after,
                'events':';'.join(applied),'post_2025_repurchase_scope_unresolved':day>='2025-01-02',
                'trade_approved':False})
    out=ROOT/'runtime/strategy-validation'/('moutai-legacy-signal-sensitivity-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir()
    with (out/'daily-conditions.csv').open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    result={'window':[bars[0]['date'],bars[-1]['date']],'bars':len(bars),'condition_rows':len(rows),
        'threshold_transitions':{k:dict(v) for k,v in counts.items()},
        'changed_days_by_threshold':{k:sum(n for transition,n in v.items() if len(set(transition.split(' -> ')))>1) for k,v in counts.items()},
        'rule':'Equal blend of annual profit / bonus-rebased shares * PE18 and annual equity / bonus-rebased shares * PB4.',
        'purpose':'Quantify consequences of unresolved distribution bridge, not endorse either convention.',
        'strategy_backtest_complete':False,'orders_executed':False,
        'limitations':['Ex-date subtraction is an explicit economic sensitivity, not verified dividend liability recognition timing.',
            'Reported equity may already recognise some declared distributions; this scenario can double subtract. Resolve before trading.',
            'Gross cash computed on bonus-only shares; 2025 treasury exclusions/cancellation and share counts remain unresolved.',
            'Conditional exit requires actual holdings; condition counts are not trade counts or returns.',
            'Both references exclude intra-year retained earnings and business changes; neither is v2 company DCF.',
            'No current company research or 2026 facts enter historical reference inputs.']}
    write_json(out/'result.json',result)
    write_json(out/'input-references.json',refs+[{'path':str(pre.relative_to(ROOT)),'sha256':digest(pre)},
        {'path':str(ap.relative_to(ROOT)),'sha256':digest(ap)}])
    write_json(out/'manifest.json',{'script_sha256':digest(Path(__file__)),
        'outputs':{p.name:digest(p) for p in out.iterdir() if p.is_file()}})
    print(json.dumps({'output':str(out),'bars':len(bars),'changed_days':result['changed_days_by_threshold'],
        'transitions':result['threshold_transitions']}))

if __name__=='__main__':
    main()
