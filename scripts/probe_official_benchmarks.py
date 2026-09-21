"""Archive official CSI responses before accepting any benchmark series."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import requests

ROOT = Path('D:/GPTProject/value-investment')
OUT = ROOT/'runtime/strategy-validation'/('official-benchmark-probe-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
OUT.mkdir()
session = requests.Session()
session.trust_env = False
records = []
for code in ('H00300', 'H00932'):
    record = {'requested_code': code, 'role': 'broad_total_return_candidate' if code=='H00300' else 'consumer_staples_total_return_candidate', 'accepted': False}
    try:
        response = session.get('https://www.csindex.com.cn/csindex-home/perf/index-perf', params={'indexCode':code,'startDate':'20150101','endDate':'20251231'}, timeout=(10,30))
        path = OUT/(code+'.response')
        path.write_bytes(response.content)
        record.update(url=response.url, status=response.status_code, sha256=hashlib.sha256(response.content).hexdigest(), content_type=response.headers.get('Content-Type'), fetched_at=datetime.now(timezone.utc).isoformat())
        response.raise_for_status()
        body=response.json()
        rows=body.get('data')
        record.update(rows=len(rows) if isinstance(rows,list) else None, first=rows[0] if isinstance(rows,list) and rows else None, last=rows[-1] if isinstance(rows,list) and rows else None)
    except Exception as exc:
        record['error']=type(exc).__name__+': '+str(exc)
    records.append(record)
    print(json.dumps(record,ensure_ascii=False),flush=True)
(OUT/'manifest.json').write_text(json.dumps({'records':records,'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'scope':'Source probe only; total-return identity, coverage, methodology and usability not accepted.'},ensure_ascii=False,indent=2),encoding='utf-8')
print('OUTPUT',OUT)
