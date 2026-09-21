"""Execute the local queue function against temporary PostgreSQL tables only."""
import ast
import json
from pathlib import Path
import sys

from value_investment_agent.db import connect
from value_investment_agent.settings import get_settings


def main():
    tree = ast.parse(Path(sys.argv[1]).read_text(encoding='utf-8'))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == 'claim_financial_enrichment_batch')
    namespace = {}
    exec('from __future__ import annotations\n' + ast.unparse(function), namespace)
    claim = namespace['claim_financial_enrichment_batch']
    with connect(get_settings().database_url) as db:
        db.execute("SET statement_timeout='15s'")
        db.execute('CREATE TEMP TABLE financial_enrichment_queue '
                   '(symbol text, status text, updated_at timestamptz, '
                   'priority_score numeric, attempts integer DEFAULT 0, last_error text)')
        db.execute('CREATE TEMP TABLE market_screen_results (symbol text, screen_date date)')
        db.execute('CREATE TEMP TABLE instruments (symbol text, name text)')
        db.execute("INSERT INTO market_screen_results VALUES ('old',CURRENT_DATE),"
                   "('recent',CURRENT_DATE),('pending',CURRENT_DATE),('stale',CURRENT_DATE-1)")
        db.execute("INSERT INTO financial_enrichment_queue(symbol,status,updated_at,priority_score) VALUES "
                   "('old','official_filings_archived',now()-interval '2 days',10),"
                   "('recent','official_filings_archived',now()-interval '2 hours',100),"
                   "('stale','official_filings_archived',now()-interval '3 days',100),"
                   "('pending','pending_official_filings',now()-interval '1 hour',90)")
        first = claim(db, 1)
        assert [r['symbol'] for r in first] == ['old'], first
        second = claim(db, 40)
        assert [r['symbol'] for r in second] == ['pending'], second
        assert claim(db, 40) == []
        state = db.execute('SELECT symbol,status,attempts FROM financial_enrichment_queue '
                           'ORDER BY symbol').fetchall()
        assert all(row['attempts'] == (1 if row['symbol'] in ('old', 'pending') else 0)
                   for row in state)
        print(json.dumps({'temporary_tables_only': True, 'checks_passed': True,
                          'state': state}))


if __name__ == '__main__':
    main()
