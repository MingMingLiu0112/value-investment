"""Inspect project-only database activity; cancel only an identified initializer."""
import json
import sys
from value_investment_agent.db import connect
from value_investment_agent.settings import get_settings

with connect(get_settings().database_url) as conn:
    rows=conn.execute("""SELECT pid,state,wait_event_type,query_start,left(query,180) AS query
        FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid()
        AND state<>'idle' ORDER BY query_start""").fetchall()
    print(json.dumps(rows,default=str),flush=True)
    if len(sys.argv)>1:
        pid=int(sys.argv[1])
        match=next((r for r in rows if r['pid']==pid),None)
        if not match or not match['query'].startswith('CREATE TABLE IF NOT EXISTS instruments'):
            raise RuntimeError('Refusing to cancel an unrecognized query')
        print(conn.execute('SELECT pg_cancel_backend(%s) AS cancelled',(pid,)).fetchone(),flush=True)
