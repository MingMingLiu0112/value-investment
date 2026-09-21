"""Preserve both issuer revisions; current comparison is not historical availability."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.request import build_opener,ProxyHandler
from pypdf import PdfReader

ROOT=Path('D:/GPTProject/value-investment')


def main():
    indexes=list((ROOT/'runtime/historical-filing-index/20260909T125407022966Z').glob('*.json'))
    if len(indexes)!=1:
        raise ValueError('Unexpected index')
    data=json.loads(indexes[0].read_text(encoding='utf-8'))
    out=ROOT/'runtime/company-research'/('000858-comparative-versions-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(parents=True)
    results=[]
    for identifier in ['1224596951','1225273126']:
        matches=[r for r in data['response']['announcements'] if str(r['announcementId'])==identifier]
        if len(matches)!=1 or matches[0]['secCode']!='000858':
            raise ValueError('Issuer/version mismatch')
        item=matches[0]
        url='https://static.cninfo.com.cn/'+item['adjunctUrl']
        with build_opener(ProxyHandler({})).open(url,timeout=30) as response:
            raw=response.read(20000001)
        if len(raw)>20000000 or not raw.startswith(b'%PDF'):
            raise ValueError('Invalid PDF')
        path=out/(identifier+'.pdf')
        path.write_bytes(raw)
        pages=[{'page':i+1,'text':p.extract_text()} for i,p in enumerate(PdfReader(path).pages)]
        result={'announcement':item,'source_url':url,'source_sha256':hashlib.sha256(raw).hexdigest(),'pages':pages}
        results.append(result)
        (out/(identifier+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        selected=[p for p in pages if p['page']>3 and '主要会计数据和财务指标' in p['text']]
        print(json.dumps({'version':item['announcementTitle'],'selected':selected[:1]},ensure_ascii=False),flush=True)
    (out/'manifest.json').write_text(json.dumps({'official_index':str(indexes[0]),'index_sha256':hashlib.sha256(indexes[0].read_bytes()).hexdigest(),
        'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'outputs':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir()},
        'historical_rule':'The April 2026 revised filing is unavailable for 2025 decisions; preserve original and revision separately.'},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out)}))


if __name__=='__main__':
    main()
