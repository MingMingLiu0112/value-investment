"""Select retained annual reports not yet migrated at their current hash/version."""
import argparse
import json
from collections import defaultdict, deque
from filing_extract import ANNUAL_BACKFILL_PARSER_VERSION
from value_investment_agent.db import connect, current_market_candidate_symbols
from value_investment_agent.market import board_for_symbol
from value_investment_agent.settings import get_settings


def balanced_reports(rows, limit):
    queues = defaultdict(deque)
    for row in sorted(rows, key=lambda row: row['symbol']):
        queues[board_for_symbol(row['symbol'])].append(row)
    selected = []
    while len(selected) < limit and any(queues.values()):
        for board in sorted(queues):
            if queues[board] and len(selected) < limit:
                selected.append(queues[board].popleft())
    return selected

parser = argparse.ArgumentParser()
parser.add_argument('--limit',type=int,default=5)
args = parser.parse_args()
if not 1 <= args.limit <= 20:
    parser.error('limit must be between 1 and 20')
with connect(get_settings().database_url) as db:
    db.execute('SET TRANSACTION READ ONLY')
    db.execute("SET statement_timeout='30s'")
    symbols = current_market_candidate_symbols(db)
    rows = db.execute("""WITH latest AS (
        SELECT DISTINCT ON (symbol) symbol,report_period,sha256,published_at
          FROM official_disclosures WHERE symbol=ANY(%s) AND report_kind='annual'
          ORDER BY symbol,report_period DESC,published_at DESC
        ) SELECT * FROM latest o WHERE NOT EXISTS (
            SELECT 1 FROM task_runs r WHERE r.task_name='annual-parser-migration'
              AND r.status='succeeded' AND r.details->>'symbol'=o.symbol
              AND r.details->>'report_period'=o.report_period
              AND r.details->>'official_sha256'=o.sha256
              AND r.details->>'parser_version'=%s
        ) ORDER BY symbol""",(symbols,ANNUAL_BACKFILL_PARSER_VERSION)).fetchall()
    rows = balanced_reports(rows, args.limit)
    print(json.dumps({'symbols':[r['symbol'] for r in rows],'reports':rows},default=str))
