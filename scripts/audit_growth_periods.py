"""Read-only audit of the official period basis for promoted growth facts."""
import json

from value_investment_agent.db import connect
from value_investment_agent.growth_evidence import official_growth_period_matches
from value_investment_agent.settings import get_settings


with connect(get_settings().database_url) as db:
    db.execute('SET TRANSACTION READ ONLY')
    db.execute("SET statement_timeout='30s'")
    rows = db.execute("""SELECT p.data_point_id,p.symbol,p.field_name,p.period_label,p.value,
        o.report_period,c.excerpt FROM data_points p
        LEFT JOIN filing_candidates c ON c.candidate_id::text=p.metadata->>'candidate_id'
        LEFT JOIN official_disclosures o ON o.disclosure_id=c.disclosure_id
        WHERE p.field_name IN ('revenue_yoy','net_income_yoy')
          AND p.validation_status='verified'
          AND p.metadata->>'automatic_cross_source_verification'='true'
          AND NOT (COALESCE(p.metadata,'{}'::jsonb) ? 'evidence_quarantine')
        ORDER BY p.symbol,p.field_name""").fetchall()
    failures = [r for r in rows if r['period_label'] != r['report_period']
                or not official_growth_period_matches(r['excerpt'], r['report_period'])]
    print(json.dumps({'checked': len(rows), 'failures': failures,
        'verified_growth': [{key: row[key] for key in ('symbol','field_name','period_label','value')}
                            for row in rows]}, default=str))
    if failures:
        raise SystemExit(1)
