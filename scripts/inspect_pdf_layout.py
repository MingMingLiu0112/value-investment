"""Inspect bounded text-layer evidence for missing financial-institution facts."""
import hashlib
import json
import logging
from pathlib import Path
import re
import sys
import unicodedata

from pypdf import PdfReader
from value_investment_agent.db import connect
from value_investment_agent.settings import get_settings

logging.getLogger('pypdf').setLevel(logging.ERROR)
symbols = sys.argv[1:] or ['600036','601398','601628','000001']
with connect(get_settings().database_url) as connection:
    reports = connection.execute('''SELECT DISTINCT ON(symbol) symbol, title, report_period,
        local_path, source_url, sha256 FROM official_disclosures WHERE symbol = ANY(%s)
        ORDER BY symbol,report_period DESC,published_at DESC''',(symbols,)).fetchall()
    for report in reports:
        path = Path(report['local_path'])
        assert hashlib.sha256(path.read_bytes()).hexdigest() == report['sha256']
        reader = PdfReader(path)
        hits = []
        samples = []
        first = ''
        for i,page in enumerate(reader.pages[:80],1):
            text = unicodedata.normalize('NFKC',page.extract_text() or '')
            if i == 1:
                first = text[:850]
            if i in {3,5,10,15}:
                samples.append({'page':i,'text':text[:1800]})
            lines = text.splitlines()
            for j,line in enumerate(lines):
                if any(word in re.sub(r'\s+','',line) for word in ['不良贷款率','拨备覆盖率','核心一级资本充足率','净息差','偿付能力充足率',
                                                               '不良貸款率','撥備覆蓋率','核心一級資本充足率','淨息差']):
                    hits.append({'page':i,'text':'\n'.join(lines[max(0,j-10):j+3])})
            if len(hits) >= 12:
                break
        print(json.dumps({**report,'page_count':len(reader.pages),'first_page_text':first,'samples':samples,'hits':hits[:12]},
                         ensure_ascii=False,default=str),flush=True)
