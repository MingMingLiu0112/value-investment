"""Read-only first-party PDF versus structured payables comparison."""
import hashlib
import importlib.util
import json
from pathlib import Path
from value_investment_agent.db import connect
from value_investment_agent.settings import get_settings
from value_investment_agent.pdf_text import extract_pages

root = Path(__file__).parent
def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, root / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

parser = load('payables_parser', 'payables_parser.py')
adapters = load('value_investment_agent.payables_adapters', 'payables_adapters.py')
field = 'long_term_payables_noncurrent'
with connect(get_settings().database_url) as db:
    db.execute('SET TRANSACTION READ ONLY')
    reports = db.execute("""SELECT DISTINCT ON(symbol) symbol,report_period,source_url,local_path,sha256
        FROM official_disclosures WHERE symbol=ANY(%s) AND report_kind='annual'
        ORDER BY symbol,report_period DESC,published_at DESC""", (['000683','000338'],)).fetchall()
for r in reports:
    path = Path(r['local_path'])
    with path.open('rb') as handle:
        assert hashlib.file_digest(handle,'sha256').hexdigest() == r['sha256']
    pages = extract_pages(path)
    official = [c for c in parser.extract_candidates_from_pages(pages) if c['field_name']==field]
    note_hits = []
    for index, text in enumerate(pages, 1):
        for term in ('\u4e13\u9879\u5e94\u4ed8\u6b3e',):
            position = text.find(term)
            if position >= 0:
                note_hits.append({'page':index,'excerpt':text[max(0,position-200):position+650]})
    secondary = [p for p in adapters.SinaFinancialStatementsAdapter().fetch([r['symbol']],report_period=r['report_period'])
                 if p.field_name in ('long_term_payables_excluding_special', 'special_payables_noncurrent', 'long_term_payables_noncurrent')
                 and p.symbol==r['symbol'] and p.period_label==r['report_period']]
    print(json.dumps({'symbol':r['symbol'],'report_period':r['report_period'],'official_url':r['source_url'],
        'sha256':r['sha256'],'note_hits':note_hits,'official':official,'secondary':[
            {'field':p.field_name,'value':str(p.value),'unit':p.unit,'source_url':p.source_url,
             'metadata':p.point_metadata} for p in secondary]},default=str),flush=True)
