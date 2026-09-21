"""Attach independently dated archived-index availability to reviewed events."""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
from replay_moutai_distributions import digest, write_json
from value_investment_agent.historical_asof import publication_date_upper_bound


def main():
    root=Path(__file__).resolve().parents[1]
    index=root/'runtime/historical-filing-index/20260908T062537893160Z/600519-1-b576a76a0e0ef5352bdb7c1a0e6bb007a86dbd06f20862044b940ee8be1f0b4c.json'
    packet=json.loads(index.read_text(encoding='utf-8'))
    # The index wrapper stores the raw provider response separately from request metadata.
    candidates=[v for v in packet.values() if isinstance(v,dict) and 'announcements' in v]
    if len(candidates)!=1:
        raise ValueError('Ambiguous archived response')
    response=candidates[0]
    if response['hasMore'] or response['totalpages']!=1 or len(response['announcements'])!=response['totalAnnouncement']:
        raise ValueError('Index pagination incomplete')
    events=[e for e in json.loads((root/'docs/reviewed-cash-distributions.json').read_text(encoding='utf-8'))['events'] if e['symbol']=='600519']
    rows=[]
    for event in sorted(events,key=lambda e:e['record_date']):
        refs=[]
        for source in event['evidence']:
            if digest(root/source['path'])!=source['sha256']:
                raise ValueError('Reviewed PDF changed')
            matches=[a for a in response['announcements'] if 'https://static.cninfo.com.cn/'+a['adjunctUrl']==source['url'] and a['secCode']=='600519']
            if len(matches)!=1:
                raise ValueError('Missing or duplicate identity match')
            row=matches[0]
            published=datetime.fromtimestamp(row['announcementTime']/1000,timezone(timedelta(hours=8))).date().isoformat()
            if row['adjunctUrl'].split('/')[1]!=published:
                raise ValueError('Index date and URL date disagree')
            if '实施' not in row['announcementTitle']:
                raise ValueError('Source is not implementation announcement')
            upper=publication_date_upper_bound(published)
            if upper>=datetime.fromisoformat(event['ex_date']+'T00:00:00+08:00'):
                raise ValueError('Implementation not established before ex-date')
            refs.append({'announcement_id':row['announcementId'],'title':row['announcementTitle'],
                'published_date':published,'available_at':upper.isoformat(),'source':source,
                'timestamp_precision':'date','availability_method':'china_publication_date_upper_bound'})
        rows.append({'record_date':event['record_date'],'ex_date':event['ex_date'],
            'available_at':max(r['available_at'] for r in refs),'evidence':refs,
            'historical_event_availability_verified':True})
    if len(rows)!=15:
        raise ValueError('Event inventory changed')
    out=root/'runtime/strategy-validation'/('moutai-distribution-availability-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(exist_ok=False)
    write_json(out/'evidence.json',{'events':rows,'index_path':str(index.relative_to(root)),
        'index_sha256':digest(index),'registry_sha256':digest(root/'docs/reviewed-cash-distributions.json'),
        'limitations':['Verified dates are conservative availability bounds, not intraday timestamps.',
            'Reviewed implementation events do not prove absence of other share actions or corrections.',
            'Dividend declaration recognition in book equity may precede ex-date; needs separate accounting treatment.',
            'No tax, valuation or strategy approval is implied.']})
    write_json(out/'manifest.json',{'script_sha256':digest(Path(__file__)),
        'evidence_sha256':digest(out/'evidence.json')})
    print(json.dumps({'output':str(out),'events_with_pre_ex_date_availability':len(rows)}))


if __name__=='__main__':
    main()
