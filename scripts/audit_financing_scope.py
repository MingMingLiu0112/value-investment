"""Read-only note screening; mentions are audit leads, never numeric facts."""
import hashlib
import json
import argparse
from pathlib import Path

from value_investment_agent.db import connect
from value_investment_agent.pdf_text import extract_pages
from value_investment_agent.settings import get_settings


TERMS = (
    '\u552e\u540e\u79df\u56de',
    '\u878d\u8d44\u79df\u8d41',
    '\u503a\u6743\u878d\u8d44',
    '\u957f\u671f\u5e94\u4ed8\u6b3e',
    '\u79df\u8d41\u8d1f\u503a',
)


parser = argparse.ArgumentParser()
parser.add_argument('--limit',type=int,default=5)
args = parser.parse_args()
if not 1 <= args.limit <= 10:
    parser.error('limit must be between 1 and 10')

with connect(get_settings().database_url) as db:
    db.execute('SET TRANSACTION READ ONLY')
    db.execute("SET statement_timeout='45s'")
    reports = db.execute("""SELECT DISTINCT ON (o.symbol) o.symbol,o.report_period,
            o.local_path,o.sha256,o.source_url
        FROM official_disclosures o JOIN financial_quality_results q USING (symbol)
        WHERE q.model_type='general_enterprise' AND q.coverage_ratio>=0.8
          AND NOT (COALESCE(q.calculation_details->'accepted_fields','[]'::jsonb) ? 'interest_bearing_debt')
          AND o.report_kind='annual'
          AND EXISTS (SELECT 1 FROM market_screen_results m WHERE m.symbol=o.symbol
              AND m.screen_date=(SELECT max(screen_date) FROM market_screen_results))
        ORDER BY o.symbol,o.report_period DESC,o.published_at DESC LIMIT %s""",(args.limit,)).fetchall()

for report in reports:
    try:
        path = Path(report['local_path'])
        with path.open('rb') as handle:
            if hashlib.file_digest(handle, 'sha256').hexdigest() != report['sha256']:
                raise ValueError('Retained PDF hash mismatch')
        hits = []
        for page_number, page in enumerate(extract_pages(path), 1):
            for line_index, line in enumerate(page.splitlines()):
                terms = [term for term in TERMS if term in line.replace(' ', '')]
                if not terms:
                    continue
                lines = page.splitlines()
                hits.append({'page': page_number, 'terms': terms,
                             'excerpt': '\n'.join(lines[max(0, line_index-1):line_index+4])[:1000]})
        print(json.dumps({**report, 'hash_verified': True, 'hits': hits,
                          'interpretation': 'screening_leads_only_not_verified_balances'},
                         ensure_ascii=True, default=str), flush=True)
    except Exception as error:
        print(json.dumps({'symbol': report['symbol'], 'error': str(error)}), flush=True)
