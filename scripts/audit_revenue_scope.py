"""Read-only inventory of legacy total-revenue rows and direct verification dependents."""
import json
from evidence_dependencies import affected_point_ids
from value_investment_agent.db import connect
from value_investment_agent.settings import get_settings

with connect(get_settings().database_url) as db:
    db.execute('SET TRANSACTION READ ONLY')
    db.execute("SET statement_timeout='45s'")
    rows = db.execute("""SELECT p.data_point_id,p.symbol,p.period_label,p.value,p.validation_status
        FROM data_points p JOIN raw_documents d ON d.document_id=p.source_id
        WHERE p.field_name='revenue' AND d.source_name='AkShare / Sina financial abstract'
        ORDER BY p.symbol,p.period_label""").fetchall()
    ids = [str(r['data_point_id']) for r in rows]
    dependents = db.execute("""SELECT data_point_id,symbol,field_name,period_label,value,validation_status,
            metadata->>'secondary_data_point_id' AS secondary_data_point_id
        FROM data_points WHERE metadata->>'secondary_data_point_id'=ANY(%s)""", (ids,)).fetchall()
    linked = db.execute("""SELECT p.data_point_id,p.symbol,p.field_name,p.period_label,p.source_id,
            p.validation_status,p.metadata
        FROM data_points p WHERE p.metadata ? 'secondary_data_point_id'
            OR p.metadata ? 'input_source_ids' OR p.metadata ? 'input_facts'
            OR p.metadata ? 'input_data_point_ids'
            OR p.data_point_id::text=ANY(%s)""", (ids,)).fetchall()
    affected = affected_point_ids(linked, ids)
    impacted = [p for p in linked if str(p['data_point_id']) in affected]
    print(json.dumps({'legacy_rows':len(rows),'direct_dependents':len(dependents),
                      'total_affected':len(affected),
                      'affected_verified':sum(p['validation_status']=='verified' for p in impacted),
                      'affected':impacted,'legacy':rows,'dependents':dependents},ensure_ascii=False,default=str))
