"""Inspect raw official annual titles for issuers with outdated archives."""
import json
from value_investment_agent.db import connect
from value_investment_agent.settings import get_settings
from value_investment_agent.disclosures import _request_json, _cninfo_security_id, _discover_security_id

with connect(get_settings().database_url) as db:
    db.execute('SET TRANSACTION READ ONLY')
    issuers = db.execute("SELECT symbol,name FROM instruments WHERE symbol=ANY(%s)",
                        (['600050','600958','601107'],)).fetchall()
for issuer in issuers:
    symbol = issuer['symbol']
    column, fallback = _cninfo_security_id(symbol)
    org = _discover_security_id(symbol, column, fallback, issuer['name'])
    payload = _request_json({'pageNum':'1','pageSize':'30','tabName':'fulltext','column':column,
        'stock':f'{symbol},{org}','searchkey':'年度报告','secid':'','plate':'','category':'',
        'trade':'','seDate':'','sortName':'','sortType':'','isHLtitle':'false'})
    print(json.dumps({'issuer':issuer,'org':org,'first_results':[
        {k:r.get(k) for k in ('secCode','announcementTitle','adjunctUrl')}
        for r in (payload.get('announcements') or [])]},ensure_ascii=False),flush=True)
