"""Inspect why retained cashflow evidence does not enter shadow reverification."""
import json
from value_investment_agent.db import connect
from value_investment_agent.settings import get_settings

with connect(get_settings().database_url) as db:
    db.execute('SET TRANSACTION READ ONLY')
    db.execute("SET statement_timeout='30s'")
    for symbol in ('000709','000830','000858','000887','000928'):
        points = db.execute("""SELECT p.data_point_id,p.value,p.unit,p.validation_status,p.created_at,
            d.source_name,p.metadata->>'statement_scope' AS scope,
            p.metadata->>'candidate_id' AS candidate_id,d.local_path,
            c.status AS candidate_status,c.value AS candidate_value
            FROM data_points p JOIN raw_documents d ON d.document_id=p.source_id
            LEFT JOIN filing_candidates c ON c.candidate_id::text=p.metadata->>'candidate_id'
            WHERE p.symbol=%s AND p.field_name='operating_cash_flow' AND p.period_label='2025-12-31'
              AND NOT (p.metadata ? 'superseded_by_parser')
            ORDER BY p.created_at DESC,p.data_point_id DESC LIMIT 8""",(symbol,)).fetchall()
        print(json.dumps({'symbol':symbol,'points':points},default=str),flush=True)
