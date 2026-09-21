"""Read a bounded sample of archived institution report tables, without downloads."""
import json
import logging
from pathlib import Path

from pypdf import PdfReader
from value_investment_agent.settings import get_settings
from value_investment_agent.db import connect

logging.getLogger('pypdf').setLevel(logging.ERROR)
with connect(get_settings().database_url) as conn:
    reports = conn.execute("""SELECT DISTINCT ON(symbol) symbol, report_period, local_path
        FROM official_disclosures WHERE symbol = ANY(%s)
        ORDER BY symbol, report_period DESC""", (['600036','000001','600030','601628','601398'],)).fetchall()
    for report in reports:
        reader = PdfReader(Path(report['local_path']))
        hits = []
        for i, page in enumerate(reader.pages[:65], 1):
            text = page.extract_text() or ''
            lines = text.splitlines()
            for j, line in enumerate(lines):
                if any(word in line for word in ['不良贷款率','拨备覆盖率','核心一级资本充足率','净息差','风险覆盖率','流动性覆盖率','偿付能力充足率']):
                    hits.append({'page':i,'text':'\n'.join(lines[max(0,j-4):j+3])})
        print(json.dumps({'symbol':report['symbol'],'period':str(report['report_period']),'hits':hits},ensure_ascii=False), flush=True)
