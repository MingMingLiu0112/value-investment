"""Bounded issuer originals for the latest disclosed capital-event review."""
from pathlib import Path
from datetime import datetime,timezone
from urllib.request import build_opener,ProxyHandler
import json,hashlib
from pypdf import PdfReader

ROOT=Path('D:/GPTProject/value-investment')


def main():
    index=next((ROOT/'runtime/historical-filing-index/20260909T134257473871Z').glob('*.json'))
    package=json.loads(index.read_text(encoding='utf-8'))
    items=package['response']['announcements']
    if package['response'].get('hasMore') or len(items)!=package['response']['totalAnnouncement'] or len({r['announcementId'] for r in items})!=len(items):
        raise ValueError('Incomplete capital event query')
    out=ROOT/'runtime/company-research'/('600519-current-capital-events-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir()
    selected=['1225431263','1225379934','1225347653','1225475862','1225366264']
    records=[]
    for identifier in selected:
        matches=[r for r in items if str(r['announcementId'])==identifier and r['secCode']=='600519']
        if len(matches)!=1:
            raise ValueError('Issuer or event mismatch')
        item=matches[0]
        url='https://static.cninfo.com.cn/'+item['adjunctUrl']
        with build_opener(ProxyHandler({})).open(url,timeout=30) as response:
            raw=response.read(15000001)
        if not raw.startswith(b'%PDF') or len(raw)>15000000:
            raise ValueError('Unexpected PDF response')
        path=out/(identifier+'.pdf')
        path.write_bytes(raw)
        pages=[{'page':i+1,'text':p.extract_text()} for i,p in enumerate(PdfReader(path).pages)]
        records.append({'announcement':item,'url':url,'sha256':hashlib.sha256(raw).hexdigest(),'pages':pages})
        print(json.dumps({'id':identifier,'title':item['announcementTitle'],'pages':pages[:3]},ensure_ascii=False),flush=True)
    payload={'symbol':'600519','query':package['query'],'official_index':str(index),
        'official_index_sha256':hashlib.sha256(index.read_bytes()).hexdigest(),'records':records,
        'available_evidence_only':True,'absence_of_announcements_is_not_registry_confirmation':True}
    (out/'evidence.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'outputs':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir()}},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out)},ensure_ascii=False))


if __name__=='__main__':main()
