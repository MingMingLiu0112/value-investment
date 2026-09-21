"""Read-only verification of the latest official Wuliangye facts."""
import hashlib
import json
from pathlib import Path
from value_investment_agent.db import connect
from value_investment_agent.settings import get_settings

with connect(get_settings().database_url) as db:
    db.execute('SET TRANSACTION READ ONLY')
    rows = db.execute("""SELECT p.field_name,p.value,p.unit,p.period_label,p.created_at,
        p.metadata->>'page_number' AS page,p.metadata->>'candidate_id' AS candidate_id,
        p.metadata->>'secondary_data_point_id' AS secondary_id,
        d.source_url,d.sha256,d.local_path
        FROM data_points p JOIN raw_documents d ON d.document_id=p.source_id
        WHERE p.symbol='000858' AND p.validation_status='verified'
          AND NOT (p.metadata ? 'superseded_by_parser')
          AND NOT (p.metadata ? 'evidence_quarantine')
        ORDER BY p.created_at DESC,p.data_point_id DESC LIMIT 3""").fetchall()
    for row in rows:
        with Path(row['local_path']).open('rb') as stream:
            row['official_hash_matches'] = hashlib.file_digest(stream,'sha256').hexdigest()==row['sha256']
        secondary = db.execute("""SELECT p.symbol,p.field_name,p.period_label,p.value,p.unit,
            p.validation_status,d.source_url,p.metadata->>'statement_scope' AS scope
            FROM data_points p JOIN raw_documents d ON d.document_id=p.source_id
            WHERE p.data_point_id=%s""", (row['secondary_id'],)).fetchone()
        row['secondary'] = secondary
    print(json.dumps(rows,default=str))
