"""Print selected pages from a hash-checked retained annual report."""
import argparse
import hashlib
import json
from pathlib import Path
from value_investment_agent.db import connect
from value_investment_agent.pdf_text import extract_pages
from value_investment_agent.settings import get_settings

parser = argparse.ArgumentParser()
parser.add_argument('--symbol',required=True)
parser.add_argument('--pages',nargs='+',type=int,required=True)
parser.add_argument('--layout',action='store_true')
args = parser.parse_args()
if len(args.symbol)!=6 or not args.symbol.isascii() or not args.symbol.isdigit() or len(args.pages)>5 or min(args.pages)<1:
    parser.error('Use one six-digit symbol and at most five positive page numbers')
with connect(get_settings().database_url) as db:
    db.execute('SET TRANSACTION READ ONLY')
    report = db.execute("""SELECT symbol,report_period,source_url,local_path,sha256
        FROM official_disclosures WHERE symbol=%s AND report_kind='annual'
        ORDER BY report_period DESC,published_at DESC LIMIT 1""",(args.symbol,)).fetchone()
if not report:
    raise ValueError('No annual report')
path = Path(report['local_path'])
with path.open('rb') as stream:
    if hashlib.file_digest(stream,'sha256').hexdigest()!=report['sha256']:
        raise ValueError('Official PDF hash mismatch')
if args.layout:
    from pypdf import PdfReader
    reader = PdfReader(path)
    selected = {page:reader.pages[page-1].extract_text(extraction_mode='layout') for page in args.pages}
else:
    pages = extract_pages(path)
    selected = {page:pages[page-1] for page in args.pages}
print(json.dumps({**report,'pages':selected},ensure_ascii=False,default=str))
