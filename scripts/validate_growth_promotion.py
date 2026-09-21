"""Read-only production-data validation of staged growth promotion code."""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from value_investment_agent.db import connect
from value_investment_agent.settings import get_settings

root = Path(__file__).parent
for name in ['growth_evidence','candidate_review']:
    spec = importlib.util.spec_from_file_location('value_investment_agent.'+name,root/(name+'.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
module.AUTOMATIC_FIELD_MAP = {'revenue_yoy':'revenue_yoy','net_income_yoy':'net_income_yoy'}
with connect(get_settings().database_url) as db:
    db.execute('SET TRANSACTION READ ONLY')
    db.execute("SET statement_timeout='60s'")
    found = []
    for candidate,record in module.automatically_verified_candidates(db,20):
        found.append({'symbol':record.symbol,'period':record.period_label,'field':record.field_name,
            'value':str(record.value),'candidate_id':candidate,'sha256':hashlib.sha256(record.raw_payload).hexdigest(),
            'secondary_data_point_id':record.point_metadata['secondary_data_point_id']})
    print(json.dumps({'read_only':True,'eligible':found}))
    expected = {r['field']:r['value'] for r in found if r['symbol']=='000333' and r['period']=='2025-12-31'}
    assert expected == {'revenue_yoy':'12.11','net_income_yoy':'14.03'}, expected
