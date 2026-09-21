"""List fact-backed differences across parser versions without losing older flags."""
import argparse
import json
from collections import Counter
from value_investment_agent.db import connect
from value_investment_agent.settings import get_settings
from value_investment_agent.filing_extract import ANNUAL_BACKFILL_PARSER_VERSION

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--parser-version', help='Limit to one exact parser version; default audits all versions.')
args = parser.parse_args()

with connect(get_settings().database_url) as db:
    db.execute('SET TRANSACTION READ ONLY')
    db.execute("SET statement_timeout='30s'")
    rows = db.execute("""WITH flagged AS (
        SELECT DISTINCT jsonb_array_elements_text(details->'supersession_plan'->'fact_backed_requires_audit') AS id
        FROM task_runs WHERE task_name='annual-parser-migration' AND status='succeeded'
          AND (%s::text IS NULL OR details->>'parser_version'=%s)
    ) SELECT c.candidate_id,o.symbol,c.field_name,c.value,c.unit,c.page_number,c.excerpt,
        o.source_url,o.sha256,c.status,
        count(p.data_point_id) AS referencing_points,
        count(p.data_point_id) FILTER (WHERE p.validation_status='verified'
            AND NOT (p.metadata ? 'evidence_quarantine')
            AND NOT (p.metadata ? 'superseded_by_parser')) AS active_verified_points
        FROM flagged f JOIN filing_candidates c ON c.candidate_id::text=f.id
        JOIN official_disclosures o ON o.disclosure_id=c.disclosure_id
        LEFT JOIN data_points p ON p.metadata->>'candidate_id'=f.id
        GROUP BY c.candidate_id,o.symbol,o.source_url,o.sha256
        ORDER BY o.symbol,c.field_name""", (args.parser_version, args.parser_version)).fetchall()
    print(json.dumps({'parser':args.parser_version or 'all_versions',
        'current_parser':ANNUAL_BACKFILL_PARSER_VERSION,'candidate_count':len(rows),
        'active_verified_references':sum(r['active_verified_points'] for r in rows),
        'by_field':dict(Counter(r['field_name'] for r in rows)), 'details':rows},default=str))
