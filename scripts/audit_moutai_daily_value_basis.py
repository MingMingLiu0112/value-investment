"""Locate real daily valuation-basis gaps before strategy order generation."""
from datetime import datetime, timezone
from pathlib import Path
import csv
import json
from replay_moutai_distributions import load_inputs, digest, write_json
from build_moutai_annual_inputs import select_original_vintage


def main():
    root=Path(__file__).resolve().parents[1]
    bars,events,annual,references=load_inputs(root)
    rows=[]
    for bar in bars:
        day=bar['date']
        selected=select_original_vintage(annual,day+'T15:00:00+08:00')
        if len(selected)!=1:
            raise ValueError(f'Expected one historical annual original: {day}')
        vintage=selected[0]
        period=vintage['period_label']
        applied=[event for event in events if period < event['ex_date'] <= day]
        bonus=[event for event in applied if event.get('bonus_shares_per_share')]
        rows.append({'date':day,'close':bar['close'],'source_id':vintage['source_id'],
            'report_period':period,'available_at':vintage['available_at'],
            'post_report_distributions':len(applied),'post_report_bonus_events':len(bonus),
            'events':';'.join(event['record_date'] for event in applied),
            'basis_state':'requires_distribution_bridge' if applied else 'no_reviewed_distribution_since_report',
            'trade_value_approved':False})
        if datetime.fromisoformat(vintage['available_at'])>datetime.fromisoformat(day+'T15:00:00+08:00'):
            raise ValueError('Future annual input selected')
    intervals=[]
    for row in rows:
        identity=(row['source_id'],row['events'],row['basis_state'])
        if intervals and intervals[-1]['identity']==identity:
            intervals[-1]['last_date']=row['date']; intervals[-1]['bars']+=1
        else:
            intervals.append({'identity':identity,'first_date':row['date'],'last_date':row['date'],'bars':1})
    result={'scope':'real archived daily annual-reference basis audit; no strategy or performance',
        'bars':len(rows),'first_date':rows[0]['date'],'last_date':rows[-1]['date'],
        'bars_after_distribution_since_report':sum(r['post_report_distributions']>0 for r in rows),
        'bars_after_bonus_since_report':sum(r['post_report_bonus_events']>0 for r in rows),
        'intervals':intervals,'strategy_backtest_complete':False,
        'next_implementation':'Bridge original earnings, equity and actual share count to each decision date using known corporate actions before applying legacy PE/PB thresholds.',
        'limitations':['No-distribution status does not prove all share actions are complete.',
            'Do not subtract the cash distribution from an arbitrary blended target price: reconcile equity and earnings components separately.',
            'Announcements available after the decision must not enter the bridge; effective event timing and historical information timing differ.',
            'Legacy fixed PE/PB research is separate from v2 company FCFF valuation.',
            'This audit does not execute trades, model taxes or certify official price/calendar completeness.']}
    out=root/'runtime/strategy-validation'/('moutai-daily-value-basis-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(exist_ok=False)
    with (out/'daily-basis.csv').open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    write_json(out/'result.json',result)
    write_json(out/'input-references.json',references)
    write_json(out/'manifest.json',{'script_sha256':digest(Path(__file__)),
        'outputs':{p.name:digest(p) for p in out.iterdir() if p.is_file()}})
    print(json.dumps({'output':str(out),**{k:v for k,v in result.items() if k not in ('intervals','limitations')}}))


if __name__=='__main__':
    main()
