"""Read original bond line and nearby disclosure text, without inferring zero."""
import hashlib
import json
import argparse
from pathlib import Path
from value_investment_agent.db import connect
from value_investment_agent.settings import get_settings
from value_investment_agent.pdf_text import extract_pages
parser = argparse.ArgumentParser()
parser.add_argument('--symbol', default='000429')
args = parser.parse_args()
if len(args.symbol) != 6 or not args.symbol.isascii() or not args.symbol.isdigit():
    parser.error('symbol must contain six digits')
with connect(get_settings().database_url) as db:
    db.execute('SET TRANSACTION READ ONLY')
    row = db.execute("""SELECT local_path,sha256 FROM official_disclosures
        WHERE symbol=%s AND report_period='2025-12-31' AND report_kind='annual'
        ORDER BY published_at DESC LIMIT 1""",(args.symbol,)).fetchone()
path = Path(row['local_path'])
with path.open('rb') as handle:
    if hashlib.file_digest(handle,'sha256').hexdigest() != row['sha256']:
        raise ValueError('Archive hash mismatch')
for index,page in enumerate(extract_pages(path),1):
    label = '\u5e94\u4ed8\u503a\u5238'
    position = page.find(label)
    if position >= 0:
        print(json.dumps({'page':index,'excerpt':page[max(0,position-180):position+650]},ensure_ascii=False))
