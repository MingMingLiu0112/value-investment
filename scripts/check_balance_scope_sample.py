"""Compare staged and live parsers on retained official evidence, read-only."""
import hashlib
import json
from pathlib import Path
from balance_scope_parser import extract_candidates_from_pages as revised
from value_investment_agent.filing_extract import extract_candidates_from_pages as live
from value_investment_agent.db import connect
from value_investment_agent.settings import get_settings
from value_investment_agent.pdf_text import extract_pages

with connect(get_settings().database_url) as db:
    db.execute('SET TRANSACTION READ ONLY')
    report = db.execute("""SELECT local_path,sha256 FROM official_disclosures
        WHERE symbol='000338' AND report_kind='annual'
        ORDER BY report_period DESC,published_at DESC LIMIT 1""").fetchone()
path = Path(report['local_path'])
with path.open('rb') as handle:
    assert hashlib.file_digest(handle, 'sha256').hexdigest() == report['sha256']
pages = extract_pages(path)
result = {'hash_verified': True}
result['boundary_samples'] = [
    {'page': i, 'lines': [line for line in page.splitlines() if any(term in line for term in
        ('\u8d44\u4ea7\u8d1f\u503a\u8868', '\u6743\u76ca\u603b', '\u6743\u76ca\u5408', '\u8d1f\u503a\u548c', '\u8d1f\u503a\u53ca'))]}
    for i, page in enumerate(pages, 1) if i >= 78 and any(term in page for term in
        ('\u8d44\u4ea7\u8d1f\u503a\u8868', '\u8d1f\u503a\u548c', '\u8d1f\u503a\u53ca'))]
for name, parser in [('live', live), ('revised', revised)]:
    rows = parser(pages)
    result[name] = {'total_candidates': len(rows), 'leases': [
        {'page': r['page'], 'value': r['value']} for r in rows
        if r['field_name'] == 'lease_liabilities_noncurrent']}
print(json.dumps(result))
