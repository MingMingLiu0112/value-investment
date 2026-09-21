"""Read-only lineage of the nine newly blocked annual cash fields."""
import json
from value_investment_agent.db import connect
from value_investment_agent.settings import get_settings

symbols = ['001233', '001386', '002011', '002043', '002444', '301376',
           '300815', '002727', '000425']
with connect(get_settings().database_url) as db:
    db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
    db.execute("SET LOCAL statement_timeout='30s'")
    rows = db.execute('''SELECT symbol, data_point_id, source_id, value, unit,
        validation_status, created_at, metadata FROM data_points
        WHERE symbol=ANY(%s) AND field_name='cash' AND period_label='2025-12-31'
        ORDER BY symbol,created_at DESC''', (symbols,)).fetchall()
    print(json.dumps(rows, default=str, ensure_ascii=False))
