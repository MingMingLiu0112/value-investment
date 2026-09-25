"""Read recent supplemental collection outcomes without exposing connection settings."""
import json
from value_investment_agent.db import connect
from value_investment_agent.settings import get_settings
with connect(get_settings().database_url) as db:
    db.execute('SET TRANSACTION READ ONLY')
    rows = db.execute("""SELECT started_at,finished_at,status,details FROM task_runs
        WHERE task_name='collect-secondary-financials' ORDER BY started_at DESC LIMIT 3""").fetchall()
    print(json.dumps(rows,default=str))
