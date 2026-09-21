"""Read retained annual summary layouts to diagnose unsupported growth rows."""
import json
import hashlib
import argparse
from pathlib import Path
from value_investment_agent.db import connect
from value_investment_agent.settings import get_settings
from value_investment_agent.pdf_text import extract_pages
parser = argparse.ArgumentParser()
parser.add_argument('--symbols', nargs='+', default=['000027', '000030'])
args = parser.parse_args()
if len(args.symbols) > 20 or any(len(s) != 6 or not s.isascii() or not s.isdigit() for s in args.symbols):
    parser.error('Provide at most 20 six-digit symbols')
with connect(get_settings().database_url) as db:
    db.execute('SET TRANSACTION READ ONLY')
    rows = db.execute("""SELECT DISTINCT ON (symbol) symbol,local_path,sha256
        FROM official_disclosures WHERE symbol=ANY(%s) AND report_kind='annual'
        ORDER BY symbol,report_period DESC,published_at DESC""",(args.symbols,)).fetchall()
for row in rows:
    path = Path(row['local_path'])
    with path.open('rb') as handle:
        assert hashlib.file_digest(handle,'sha256').hexdigest() == row['sha256']
    for index,page in enumerate(extract_pages(path),1):
        if '\u4e3b\u8981\u4f1a\u8ba1\u6570\u636e\u548c\u8d22\u52a1\u6307\u6807' in page:
            print(json.dumps({'symbol':row['symbol'],'page':index,'text':page},ensure_ascii=False),flush=True)
