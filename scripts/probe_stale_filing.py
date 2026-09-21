"""Inspect official search results for a stale issuer without storing facts."""
import json
from value_investment_agent.db import connect
from value_investment_agent.settings import get_settings
from value_investment_agent.disclosures import search_latest_reports, _request_json

with connect(get_settings().database_url) as db:
    db.execute('SET TRANSACTION READ ONLY')
    issuer = db.execute("SELECT symbol,name FROM instruments WHERE symbol='600754'").fetchone()
reports = search_latest_reports(issuer['symbol'], issuer['name'])
print(json.dumps({'issuer': issuer, 'reports': [
    {key: r.get(key) for key in ('secCode', 'orgId', 'announcementTitle', 'announcementTime', 'adjunctUrl')}
    for r in reports]}, ensure_ascii=False), flush=True)
payload = _request_json({
    'pageNum': '1', 'pageSize': '30', 'tabName': 'fulltext', 'column': 'sse',
    'stock': '600754,gssh0600754', 'searchkey': '', 'secid': '', 'plate': '',
    'category': 'category_ndbg_szsh', 'trade': '', 'seDate': '', 'sortName': '',
    'sortType': '', 'isHLtitle': 'true',
})
print(json.dumps({'total': payload.get('totalAnnouncement'), 'raw_annual_results': [
    {key: r.get(key) for key in ('secCode', 'announcementTitle', 'adjunctUrl')}
    for r in payload.get('announcements') or []]}, ensure_ascii=False), flush=True)
