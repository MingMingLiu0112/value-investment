"""Read-only annual debt and growth evidence for the next near-complete issuer."""
import json
import argparse
from value_investment_agent.db import connect,latest_points
from value_investment_agent.settings import get_settings
fields = ['short_term_borrowings','current_portion_long_term_debt','long_term_borrowings',
          'bonds_payable','interest_bearing_debt','revenue_yoy','net_income_yoy']
parser = argparse.ArgumentParser()
parser.add_argument('--symbol', default='000429')
parser.add_argument('--lease-only', action='store_true')
args = parser.parse_args()
if args.lease_only:
    fields = ['lease_liabilities_noncurrent']
if len(args.symbol) != 6 or not args.symbol.isascii() or not args.symbol.isdigit():
    parser.error('symbol must contain six digits')
with connect(get_settings().database_url) as db:
    db.execute('SET TRANSACTION READ ONLY')
    db.execute("SET statement_timeout='45s'")
    points = [{key:p.get(key) for key in ('symbol','field_name','value','unit','period_label',
               'validation_status','source_name','source_id','metadata')}
              for p in latest_points(db,annual_only=True) if p['symbol']==args.symbol and p['field_name'] in fields]
    candidates = db.execute("""SELECT c.field_name,c.value,c.unit,c.page_number,c.source_label,c.status,
        o.source_url,o.local_path,o.sha256 FROM filing_candidates c
        JOIN official_disclosures o ON o.disclosure_id=c.disclosure_id
        WHERE o.symbol=%s AND o.report_period='2025-12-31' AND c.field_name=ANY(%s)
        ORDER BY c.field_name,c.page_number""",(args.symbol,fields)).fetchall()
    print(json.dumps({'points':points,'candidates':candidates},default=str))
