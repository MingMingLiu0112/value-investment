"""Validate production growth selection without writes, locks, or fetching."""
import json
import importlib.util
from pathlib import Path
from value_investment_agent.db import connect
from value_investment_agent.settings import get_settings

spec = importlib.util.spec_from_file_location('value_investment_agent.growth_queue_probe',
                                              Path(__file__).with_name('growth_collection.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

with connect(get_settings().database_url) as db:
    db.execute('SET TRANSACTION READ ONLY')
    db.execute("SET statement_timeout='45s'")
    rows = module.select_reports(db, 5)
    print(json.dumps({'read_only': True, 'selected': [
        {'symbol': r['symbol'], 'period': r['report_period'], 'fields': sorted(r['fields'])}
        for r in rows]}))
