"""Read-only verification of growth integration and remaining annual score inputs."""
import json
from value_investment_agent.db import connect,latest_points,current_market_candidate_symbols
from value_investment_agent.settings import get_settings
from value_investment_agent.financial_quality import GENERAL_FIELDS,evaluate_financial_quality
with connect(get_settings().database_url) as db:
    db.execute('SET TRANSACTION READ ONLY')
    db.execute("SET statement_timeout='45s'")
    quality = db.execute("SELECT * FROM financial_quality_results WHERE symbol='000333'").fetchone()
    points = [{k:p.get(k) for k in ['field_name','period_label','value','unit','validation_status','source_name','source_id','created_at','metadata']}
              for p in latest_points(db,annual_only=True) if p['symbol']=='000333'
              and p['field_name'] in GENERAL_FIELDS + ('revenue','net_income','operating_cost')]
    fresh = evaluate_financial_quality('000333',None,None,points).database_row()
    print(json.dumps({'in_current_candidate_pool':'000333' in current_market_candidate_symbols(db),
                     'fresh_quality':fresh,'quality':quality,'annual_inputs':points},default=str))
