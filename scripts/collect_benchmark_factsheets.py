"""Archive CSI's published index factsheets for benchmark identity review."""
from datetime import datetime, timezone
from pathlib import Path
from io import BytesIO
import hashlib
import json
import requests
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[1]
out=ROOT/'runtime/strategy-validation'/('benchmark-factsheets-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
out.mkdir()
session=requests.Session()
session.trust_env=False
records=[]
for code in ('000300','000932'):
    url=f'https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/{code}factsheet.pdf'
    record={'code':code,'requested_url':url}
    try:
        response=session.get(url,timeout=(8,20))
        path=out/(code+'.response')
        path.write_bytes(response.content)
        record.update(status=response.status_code,url=response.url,sha256=hashlib.sha256(response.content).hexdigest(),fetched_at=datetime.now(timezone.utc).isoformat())
        response.raise_for_status()
        if not response.content.startswith(b'%PDF'):
            raise ValueError('Response is not a PDF')
        reader=PdfReader(BytesIO(response.content))
        text='\n'.join(f'PAGE {i+1}\n'+p.extract_text() for i,p in enumerate(reader.pages))
        (out/(code+'.txt')).write_text(text,encoding='utf-8')
        record['pages']=len(reader.pages)
        print(text,flush=True)
    except Exception as exc:
        record['error']=type(exc).__name__+': '+str(exc)
    records.append(record)
(out/'manifest.json').write_text(json.dumps({'records':records,'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'scope':'Current factsheet only; not proof of historical methodology versions.'},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'output':str(out),'records':records},ensure_ascii=False))
