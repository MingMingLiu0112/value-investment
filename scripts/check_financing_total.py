"""Exercise staged total extraction against an archived official PDF."""
import hashlib
import importlib.util
import json
import sys
import argparse
from pathlib import Path
from pypdf import PdfReader
from value_investment_agent.db import connect
from value_investment_agent.settings import get_settings
from value_investment_agent.pdf_text import extract_pages

parser = argparse.ArgumentParser()
parser.add_argument('--symbols',nargs='+',default=['000411'])
args = parser.parse_args()
if len(args.symbols)>10 or any(len(s)!=6 or not s.isascii() or not s.isdigit() for s in args.symbols):
    parser.error('Provide at most ten six-digit symbols')

for name in ('financing_rollforward','financing_table'):
    full = 'value_investment_agent.'+name
    spec = importlib.util.spec_from_file_location(full,Path(__file__).with_name(name+'.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[full] = module
    spec.loader.exec_module(module)
with connect(get_settings().database_url) as db:
    db.execute('SET TRANSACTION READ ONLY')
    reports = db.execute("""SELECT DISTINCT ON(symbol) symbol,report_period,local_path,source_url,sha256
        FROM official_disclosures WHERE symbol=ANY(%s) AND report_kind='annual'
        ORDER BY symbol,report_period DESC,published_at DESC""",(args.symbols,)).fetchall()
for missing in sorted(set(args.symbols)-{r['symbol'] for r in reports}):
    print(json.dumps({'symbol':missing,'status':'official_report_missing'}),flush=True)
for report in reports:
    path = Path(report['local_path'])
    with path.open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest()!=report['sha256']:
            raise ValueError('Official file hash mismatch')
    pages = [i for i,text in enumerate(extract_pages(path)) if module.TITLE in ''.join(text.split())]
    reader = PdfReader(path)
    results = []
    for index in pages:
        layout = reader.pages[index].extract_text(extraction_mode='layout')
        result = module.extract_financing_components(layout)
        results.append({'page':index+1,'applicability':module.financing_applicability(layout),
                        'extraction':result})
    print(json.dumps({'symbol':report['symbol'],'period':report['report_period'],
        'source_url':report['source_url'],'sha256':report['sha256'],
        'status':'inspected' if pages else 'section_not_found','results':results},ensure_ascii=False),flush=True)
