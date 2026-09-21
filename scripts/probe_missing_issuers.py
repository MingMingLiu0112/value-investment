"""Read-only official issuer identity diagnostics for missing annual reports."""
import json
import argparse
from value_investment_agent.db import connect
from value_investment_agent.settings import get_settings
from value_investment_agent.disclosures import _request_json, _cninfo_security_id

parser = argparse.ArgumentParser()
parser.add_argument('--symbols', nargs='+', default=['001237','920079','920138','920174'])
parser.add_argument('--search-key')
args = parser.parse_args()
if len(args.symbols) > 10 or any(len(s) != 6 or not s.isascii() or not s.isdigit() for s in args.symbols):
    parser.error('Provide at most ten six-digit symbols')
with connect(get_settings().database_url) as db:
    db.execute('SET TRANSACTION READ ONLY')
    issuers = db.execute('SELECT symbol,name FROM instruments WHERE symbol=ANY(%s)',
        (args.symbols,)).fetchall()
for issuer in issuers:
    column, fallback = _cninfo_security_id(issuer['symbol'])
    payload = _request_json({'pageNum':'1','pageSize':'30','tabName':'fulltext','column':'',
        'stock':'','searchkey':args.search_key or issuer['name'],'secid':'','plate':'','category':'',
        'trade':'','seDate':'','sortName':'','sortType':'','isHLtitle':'false'})
    print(json.dumps({'issuer':issuer,'column':column,'fallback':fallback,
        'results':[{k:r.get(k) for k in ('secCode','secName','orgId','announcementTitle','adjunctUrl')}
                   for r in (payload.get('announcements') or [])[:8]]},ensure_ascii=False),flush=True)
