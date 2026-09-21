"""Read-only comparison on retained annual filings across three industries."""
import hashlib
import json
import logging
from collections import Counter
from decimal import Decimal
from pathlib import Path

from pypdf import PdfReader
from filing_extract import extract_candidates_from_pages as revised
from value_investment_agent.filing_extract import extract_candidates_from_pages as live
from value_investment_agent.pdf_text import extract_pages
from value_investment_agent.candidate_review import AUTOMATIC_FIELD_MAP, values_agree
from value_investment_agent.db import connect
from value_investment_agent.settings import get_settings


def main():
    logging.getLogger('pypdf').setLevel(logging.ERROR)
    with connect(get_settings().database_url) as db:
        db.execute('SET TRANSACTION READ ONLY')
        db.execute("SET statement_timeout='30s'")
        rows = db.execute("""SELECT DISTINCT ON (symbol) symbol,report_period,source_url,sha256,local_path
            FROM official_disclosures WHERE symbol=ANY(%s) AND report_kind='annual'
            ORDER BY symbol,report_period DESC,published_at DESC""", (['600036','600519','000333'],)).fetchall()
        for row in rows:
            path = Path(row['local_path'])
            with path.open('rb') as handle:
                assert hashlib.file_digest(handle,'sha256').hexdigest() == row['sha256']
            secondary = db.execute("""SELECT p.field_name,p.value,p.unit,d.source_url
                FROM data_points p JOIN raw_documents d ON d.document_id=p.source_id
                WHERE p.symbol=%s AND p.period_label=%s AND d.source_name LIKE 'AkShare / Sina%%'
                  AND p.validation_status <> 'failed'
                  AND NOT (COALESCE(p.metadata, '{}'::jsonb) ? 'evidence_quarantine')
                  AND NOT (p.field_name='revenue' AND d.source_name='AkShare / Sina financial abstract')""",
                (row['symbol'],row['report_period'])).fetchall()
            result = dict(row)
            for engine in ('live_pypdf','revised_pdfium'):
                pages = ([p.extract_text() or '' for p in PdfReader(path).pages]
                         if engine == 'live_pypdf' else extract_pages(path))
                candidates = (live if engine == 'live_pypdf' else revised)(pages)
                corroborated = []
                unmatched = []
                for c in candidates:
                    field = AUTOMATIC_FIELD_MAP.get(c['field_name'])
                    if field and any(p['field_name']==field and p['unit']==c['unit']
                        and p['source_url'] != row['source_url']
                        and values_agree(Decimal(c['value']),Decimal(p['value']),c['unit']) for p in secondary):
                        corroborated.append(c)
                    else:
                        comparable = [p for p in secondary if p['field_name']==field and p['unit']==c['unit']]
                        unmatched.append({'field':c['field_name'],'official_value':c['value'],
                            'unit':c['unit'],'page':c['page'],
                            'reason':'value_conflict' if comparable else 'missing_secondary',
                            'secondary_values':sorted({str(p['value']) for p in comparable})})
                result[engine] = {'candidate_count':len(candidates),
                    'fields':dict(Counter(c['field_name'] for c in candidates)),
                    'corroborated_count':len(corroborated),
                    'corroborated_fields':dict(Counter(c['field_name'] for c in corroborated)),
                    'unmatched':unmatched}
                del pages
            print(json.dumps(result,ensure_ascii=False,default=str),flush=True)


if __name__ == '__main__':
    main()
