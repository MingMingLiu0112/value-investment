"""Read-only count of latest pending facts shadowing same-period verified values."""
import json
from collections import Counter
from value_investment_agent.db import connect
from value_investment_agent.settings import get_settings
with connect(get_settings().database_url) as db:
    db.execute('SET TRANSACTION READ ONLY')
    db.execute("SET statement_timeout='60s'")
    rows = db.execute("""WITH latest AS (
        SELECT DISTINCT ON (symbol,field_name,period_label) * FROM data_points
        WHERE NOT (metadata ? 'superseded_by_parser')
        ORDER BY symbol,field_name,period_label,created_at DESC,data_point_id DESC
    ) SELECT p.symbol,p.field_name,p.period_label,p.value,p.unit,
         d.source_name,p.metadata->>'statement_scope' AS statement_scope,
         count(*) FILTER (WHERE v.value=p.value AND v.unit=p.unit) AS identical_verified,
         count(*) FILTER (WHERE v.value<>p.value OR v.unit<>p.unit) AS different_verified
      FROM latest p JOIN raw_documents d ON d.document_id=p.source_id
      JOIN data_points v ON v.symbol=p.symbol AND v.field_name=p.field_name
        AND v.period_label=p.period_label AND v.validation_status='verified'
        AND NOT (v.metadata ? 'evidence_quarantine')
        AND NOT (v.metadata ? 'superseded_by_parser')
      WHERE p.validation_status='pending' AND p.period_label ~ '^[0-9]{4}-12-31$'
      GROUP BY p.symbol,p.field_name,p.period_label,p.value,p.unit,d.source_name,p.metadata
      ORDER BY p.symbol,p.field_name,p.period_label""").fetchall()
    print(json.dumps({'shadowed_annual_keys':len(rows),
        'identical_only':sum(r['identical_verified']>0 and r['different_verified']==0 for r in rows),
        'by_source_scope':dict(Counter((r['source_name']+' / '+str(r['statement_scope'])) for r in rows)),
        'by_field':dict(Counter(r['field_name'] for r in rows)),
        'samples':rows[:12]},default=str))
