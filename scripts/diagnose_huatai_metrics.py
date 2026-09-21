"""Read-only original-page and dual-decoder diagnosis for missing broker metrics."""
import hashlib
import json
from pathlib import Path
from pypdf import PdfReader
from value_investment_agent.db import connect
from value_investment_agent.settings import get_settings
from value_investment_agent.pdf_text import extract_pages
from value_investment_agent.institution_metrics import parse_tables
from value_investment_agent import institution_metrics
from collections import defaultdict
import sys
if '--staged' in sys.argv:
    import institution_scope_ready as institution_metrics
    parse_tables = institution_metrics.parse_tables

with connect(get_settings().database_url) as db:
    db.execute('SET TRANSACTION READ ONLY')
    r = db.execute("""SELECT local_path,sha256,source_url,report_period FROM official_disclosures
        WHERE symbol='601688' AND report_period='2026-06-30'
        ORDER BY published_at DESC LIMIT 1""").fetchone()
path = Path(r['local_path'])
with path.open('rb') as handle:
    assert hashlib.file_digest(handle,'sha256').hexdigest() == r['sha256']
primary = extract_pages(path)
fallback = [p.extract_text() or '' for p in PdfReader(path).pages[:65]]
captured = defaultdict(list)
institution_metrics.defaultdict = lambda factory: captured
result = parse_tables(primary,'broker',str(r['report_period']),fallback_pages=fallback)
print(json.dumps({'report':r, 'hash_verified':True,
    'matched_candidates':{field:[{k:v for k,v in item.items() if k != 'excerpt'} for item in items]
                          for field,items in captured.items()},
    'parsed':result},
    default=str,ensure_ascii=False))
