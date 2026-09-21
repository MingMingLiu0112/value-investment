"""Read-only parser comparison with promoted-candidate regression evidence."""
import hashlib
import json
from pathlib import Path
from balance_scope_parser import extract_candidates_from_pages as revised
from value_investment_agent.filing_extract import extract_candidates_from_pages as live
from value_investment_agent.db import connect
from value_investment_agent.settings import get_settings
from value_investment_agent.pdf_text import extract_pages
from candidate_migration import plan_candidate_supersession

symbols = ['000338', '000411', '000581', '000623', '002091', '600036',
           '600519', '000333', '689009', '605098']

def key(row):
    return (row['field_name'], str(row['value']), row.get('page', row.get('page_number')))

with connect(get_settings().database_url) as db:
    db.execute('SET TRANSACTION READ ONLY')
    db.execute("SET statement_timeout='45s'")
    reports = db.execute("""SELECT DISTINCT ON (symbol) disclosure_id,symbol,local_path,sha256
        FROM official_disclosures WHERE symbol=ANY(%s) AND report_kind='annual'
        ORDER BY symbol,report_period DESC,published_at DESC""", (symbols,)).fetchall()
    for report in reports:
        path = Path(report['local_path'])
        with path.open('rb') as handle:
            if hashlib.file_digest(handle, 'sha256').hexdigest() != report['sha256']:
                raise ValueError('Hash mismatch for ' + report['symbol'])
        pages = extract_pages(path)
        before, after = live(pages), revised(pages)
        # Decimal formatting is normalized so 1.00 and 1 are the same value.
        from decimal import Decimal
        def normalized(row):
            field, value, page = key(row)
            return (field, Decimal(value), page)
        after_keys = {normalized(row) for row in after}
        after_values = {(r['field_name'], Decimal(r['value'])) for r in after}
        existing = db.execute('SELECT * FROM filing_candidates WHERE disclosure_id=%s',
                              (report['disclosure_id'],)).fetchall()
        refs = db.execute("""SELECT DISTINCT p.metadata->>'candidate_id' AS candidate_id
            FROM data_points p JOIN filing_candidates c
              ON p.metadata->>'candidate_id'=c.candidate_id::text
            WHERE c.disclosure_id=%s""", (report['disclosure_id'],)).fetchall()
        migration = plan_candidate_supersession(existing, after, [r['candidate_id'] for r in refs])
        promoted = db.execute("""SELECT c.field_name,c.value,c.page_number FROM filing_candidates c
            WHERE c.disclosure_id=%s AND EXISTS (SELECT 1 FROM data_points p
                WHERE p.metadata->>'candidate_id'=c.candidate_id::text
                  AND p.validation_status='verified'
                  AND NOT (p.metadata ? 'evidence_quarantine')
                  AND NOT (p.metadata ? 'superseded_by_parser'))""", (report['disclosure_id'],)).fetchall()
        print(json.dumps({'symbol':report['symbol'], 'hash_verified':True,
            'before':len(before), 'after':len(after),
            'migration_plan': migration,
            'promoted_values_missing': [key(row) for row in promoted
                if (row['field_name'], Decimal(row['value'])) not in after_values],
            'removed':[key(row) for row in before if normalized(row) not in after_keys],
            'promoted_not_reproduced':[key(row) for row in promoted if normalized(row) not in after_keys]},
            default=str), flush=True)
