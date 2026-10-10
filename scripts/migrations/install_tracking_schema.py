"""Install only the additive tracking audit table with bounded DDL waits."""
import json
from pathlib import Path
from value_investment_agent.db import connect
from value_investment_agent.settings import get_settings

with connect(get_settings().database_url) as db:
    db.execute("SET lock_timeout='3s'")
    db.execute("SET statement_timeout='20s'")
    db.execute(Path('/staged/tracking_schema.sql').read_text())
    db.execute('CREATE INDEX IF NOT EXISTS candidate_tracking_latest ON candidate_tracking_observations(symbol, quote_as_of DESC, created_at DESC)')
    columns = db.execute("""SELECT column_name FROM information_schema.columns
        WHERE table_schema='public' AND table_name='candidate_tracking_observations'""").fetchall()
    assert {r['column_name'] for r in columns} == {
        'run_id','symbol','source_id','quote_as_of','quote_status','signal_blocked','observation','created_at'}
    db.commit()
print(json.dumps({'tracking_schema_installed': True, 'existing_business_rows_modified': False}))
