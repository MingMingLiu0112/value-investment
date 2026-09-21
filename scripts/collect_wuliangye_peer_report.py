"""Archive an officially indexed peer report for operating counterevidence."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.request import build_opener,ProxyHandler
from pypdf import PdfReader

ROOT=Path('D:/GPTProject/value-investment')


def main():
    indexes=list((ROOT/'runtime/historical-filing-index/20260909T125142961645Z').glob('*.json'))
    if len(indexes)!=1:
        raise ValueError('Unexpected index pages')
    index=indexes[0]
    data=json.loads(index.read_text(encoding='utf-8'))
    rows=[r for r in data['response']['announcements'] if str(r['announcementId'])=='1225531252']
    if len(rows)!=1 or rows[0]['secCode']!='000858' or rows[0]['announcementTitle']!='2026年半年度报告':
        raise ValueError('Peer report identity mismatch')
    url='https://static.cninfo.com.cn/'+rows[0]['adjunctUrl']
    with build_opener(ProxyHandler({})).open(url,timeout=30) as response:
        raw=response.read(20000001)
    if len(raw)>20000000 or not raw.startswith(b'%PDF'):
        raise ValueError('Invalid bounded PDF')
    out=ROOT/'runtime/company-research'/('000858-peer-interim-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(parents=True)
    pdf=out/'000858-1225531252.pdf'
    pdf.write_bytes(raw)
    pages=[{'page':i+1,'text':page.extract_text()} for i,page in enumerate(PdfReader(pdf).pages)]
    if '五粮液' not in pages[0]['text'] or '2026' not in pages[0]['text']:
        raise ValueError('Wrong downloaded issuer/date')
    selected=[p for p in pages if ('主要会计数据和财务指标' in p['text'] or '营业收入构成' in p['text'] or '主营业务分析' in p['text']) and p['page']>3]
    result={'symbol':'000858','source_url':url,'source_sha256':hashlib.sha256(raw).hexdigest(),
        'official_index':str(index.relative_to(ROOT)),'official_index_sha256':hashlib.sha256(index.read_bytes()).hexdigest(),
        'announcement':rows[0],'fetched_at':datetime.now(timezone.utc).isoformat(),'pages':pages,
        'peer_support_approved':False,'limitations':['Independent issuer, not independent confirmation of Moutai facts.',
            'Different liquor categories, channels and consolidation scope; no automatic ratio transfer.',
            'One interim observation does not establish terminal demand or long-run growth.']}
    (out/'evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'outputs':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir()}},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'selected_pages':selected[:3]},ensure_ascii=False))


if __name__=='__main__':
    main()
