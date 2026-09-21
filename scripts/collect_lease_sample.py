"""Retain only noncurrent lease evidence without changing the debt formula."""
import hashlib
import json
from pathlib import Path
import uuid
import argparse

from value_investment_agent.filing_extract import extract_candidates_from_pages, ANNUAL_BACKFILL_PARSER_VERSION
from value_investment_agent.adapters import SinaFinancialStatementsAdapter
from value_investment_agent.db import connect, begin_run, end_run, store_record
from value_investment_agent.pdf_text import extract_pages
from value_investment_agent.settings import get_settings

parser = argparse.ArgumentParser()
parser.add_argument('--symbol', default='000729')
args = parser.parse_args()
if len(args.symbol) != 6 or not args.symbol.isascii() or not args.symbol.isdigit():
    parser.error('symbol must contain six digits')
symbol = args.symbol
settings = get_settings()
with connect(settings.database_url) as db:
    report = db.execute("""SELECT * FROM official_disclosures WHERE symbol=%s
        AND report_kind='annual' ORDER BY report_period DESC,published_at DESC LIMIT 1""", (symbol,)).fetchone()
if report is None:
    raise ValueError('No retained annual report for ' + symbol)
path = Path(report['local_path'])
with path.open('rb') as handle:
    if hashlib.file_digest(handle, 'sha256').hexdigest() != report['sha256']:
        raise ValueError('Official file hash mismatch')
field = 'lease_liabilities_noncurrent'
candidates = [c for c in extract_candidates_from_pages(extract_pages(path)) if c['field_name'] == field]
records = [r for r in SinaFinancialStatementsAdapter().fetch([symbol], report_period=report['report_period'])
           if r.field_name == field and r.symbol == symbol and r.period_label == report['report_period']
           and r.unit == 'CNY' and r.source_name == 'AkShare / Sina detailed financial statements']
if not records or len({r.value for r in records}) != 1:
    raise ValueError('Missing or conflicting same-period lease evidence for ' + symbol)
with connect(settings.database_url) as db:
    run = begin_run(db, 'collect-lease-sample')
    for record in records:
        store_record(db, record, 'pending')
    for c in candidates:
        db.execute("""INSERT INTO filing_candidates(candidate_id,disclosure_id,field_name,value,unit,
            page_number,source_label,excerpt,parser_version,status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (disclosure_id,field_name,page_number,source_label) DO NOTHING""",
            (uuid.uuid4(),report['disclosure_id'],field,c['value'],c['unit'],c['page'],
             c['source_label'],c['excerpt'],ANNUAL_BACKFILL_PARSER_VERSION,c['status']))
    result = {'symbol': symbol, 'period': report['report_period'],
              'official_candidates': candidates, 'secondary_values': [str(r.value) for r in records],
              'sha256': report['sha256'], 'debt_formula_unchanged': True}
    end_run(db, run, 'succeeded', result)
print(json.dumps(result, ensure_ascii=False))
