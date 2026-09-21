"""Read-only official prospectus discovery for companies missing annual reports."""
import json
from value_investment_agent.disclosures import _request_json

for symbol, org in [('001237','9900063097'), ('920079','gfbj0874075'), ('920138','9900034944')]:
    for keyword in ['招股说明书', '上市公告书']:
        payload = _request_json({'pageNum':'1','pageSize':'30','tabName':'fulltext','column':'',
            'stock':f'{symbol},{org}','searchkey':keyword,'secid':'','plate':'','category':'',
            'trade':'','seDate':'','sortName':'','sortType':'','isHLtitle':'false'})
        print(json.dumps({'symbol':symbol,'keyword':keyword,'total':payload.get('totalAnnouncement'),
            'results':[{k:r.get(k) for k in ('secCode','announcementTitle','announcementTime','adjunctUrl')}
                       for r in (payload.get('announcements') or [])[:3]]},ensure_ascii=False),flush=True)
