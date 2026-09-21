"""Inspect historical ordinary ROE provenance without mutating facts."""
import json
from value_investment_agent.db import connect
from value_investment_agent.settings import get_settings

with connect(get_settings().database_url) as db:
    db.execute('SET TRANSACTION READ ONLY')
    db.execute("SET statement_timeout='30s'")
    groups = db.execute("""SELECT d.source_name,d.parser_version,p.validation_status,
        count(*) AS records,count(DISTINCT p.symbol) AS companies,
        count(*) FILTER (WHERE p.metadata ? 'candidate_id') AS candidate_linked,
        count(*) FILTER (WHERE p.human_reviewed) AS human_reviewed,
        count(*) FILTER (WHERE d.local_path IS NOT NULL) AS archived
        FROM data_points p JOIN raw_documents d ON d.document_id=p.source_id
        WHERE p.field_name='roe' AND d.source_name='AkShare / Sina financial indicators'
          AND NOT (p.metadata ? 'superseded_by_parser')
        GROUP BY d.source_name,d.parser_version,p.validation_status""").fetchall()
    samples = db.execute("""SELECT p.symbol,p.period_label,p.value,p.unit,p.metadata,
        d.source_url,d.parser_version,d.sha256,d.local_path,
        d.metadata->>'field_name' AS document_metric
        FROM data_points p JOIN raw_documents d ON d.document_id=p.source_id
        WHERE p.field_name='roe' AND d.source_name='AkShare / Sina financial indicators'
          AND NOT (p.metadata ? 'superseded_by_parser')
        ORDER BY p.created_at DESC,p.data_point_id DESC LIMIT 5""").fetchall()
    print(json.dumps({'groups':groups,'samples':samples}, default=str))
