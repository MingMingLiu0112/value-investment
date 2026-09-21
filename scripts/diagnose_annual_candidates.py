"""Read-only annual candidate and evidence diagnostics for retained samples."""
import json
from value_investment_agent.db import connect
from value_investment_agent.settings import get_settings

with connect(get_settings().database_url) as db:
    db.execute('SET TRANSACTION READ ONLY')
    db.execute("SET statement_timeout='45s'")
    for symbol in ['000333','600036','600519']:
        candidates = db.execute("""SELECT c.candidate_id,c.field_name,c.value,c.unit,c.status,
            c.page_number,c.parser_version,o.extraction_status,o.extraction_parser_version,
            (SELECT jsonb_agg(jsonb_build_object('status',p.validation_status,'metadata',p.metadata))
               FROM data_points p WHERE p.metadata->>'candidate_id'=c.candidate_id::text) AS promoted
            FROM official_disclosures o LEFT JOIN filing_candidates c ON c.disclosure_id=o.disclosure_id
            WHERE o.symbol=%s AND o.report_period='2025-12-31' AND o.report_kind='annual'
              AND (c.field_name IN ('revenue','net_income') OR c.field_name IS NULL)""",(symbol,)).fetchall()
        evidence = db.execute("""SELECT DISTINCT ON (p.field_name,d.source_name)
            p.field_name,p.value,p.unit,p.validation_status,d.source_name,
            p.metadata ? 'evidence_quarantine' AS quarantined
            FROM data_points p JOIN raw_documents d ON d.document_id=p.source_id
            WHERE p.symbol=%s AND p.period_label='2025-12-31' AND p.field_name IN ('revenue','net_income')
            ORDER BY p.field_name,d.source_name,p.created_at DESC""",(symbol,)).fetchall()
        print(json.dumps({'symbol':symbol,'candidates':candidates,'evidence':evidence},default=str),flush=True)
