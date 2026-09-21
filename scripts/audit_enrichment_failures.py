"""Inspect bounded official-archive retry diagnostics without modifying queues."""
import json
import argparse
import hashlib
from pathlib import Path
from value_investment_agent.db import connect
from value_investment_agent.settings import get_settings

parser = argparse.ArgumentParser()
parser.add_argument('--verify-symbols', nargs='*', default=[])
args = parser.parse_args()
if len(args.verify_symbols) > 10 or any(len(s) != 6 or not s.isascii() or not s.isdigit() for s in args.verify_symbols):
    parser.error('Provide at most ten six-digit symbols')
with connect(get_settings().database_url) as db:
    db.execute('SET TRANSACTION READ ONLY')
    db.execute("SET statement_timeout='15s'")
    rows = db.execute("""SELECT q.symbol,i.name,q.status,q.attempts,q.last_error,q.updated_at,
        (SELECT count(*) FROM official_disclosures o WHERE o.symbol=q.symbol) AS archived_reports
        FROM financial_enrichment_queue q JOIN instruments i USING (symbol)
        WHERE q.status IN ('retry','manual_review_required')
        ORDER BY q.attempts DESC,q.symbol LIMIT 25""").fetchall()
    reports = db.execute('SELECT symbol,report_period,report_kind,source_url,sha256,local_path '
                         'FROM official_disclosures WHERE symbol=ANY(%s)', (args.verify_symbols,)).fetchall() if args.verify_symbols else []
for report in reports:
    with Path(report['local_path']).open('rb') as handle:
        report['hash_matches'] = hashlib.file_digest(handle, 'sha256').hexdigest() == report['sha256']
    if not report['hash_matches']:
        raise ValueError('Retained official file hash mismatch: '+report['symbol'])
print(json.dumps({'read_only': True, 'retry_samples': rows, 'retained_reports': reports}, ensure_ascii=False, default=str))
