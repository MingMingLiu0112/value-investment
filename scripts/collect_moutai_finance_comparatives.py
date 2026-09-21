"""Archive exact issuer finance-company annual and interim comparatives."""
from pathlib import Path
from datetime import datetime,timezone
from urllib.request import build_opener,ProxyHandler
import json,hashlib
from pypdf import PdfReader

ROOT=Path('D:/GPTProject/value-investment')


def main():
    index=next((ROOT/'runtime/historical-filing-index/20260909T135800048472Z').glob('*.json'))
    rows=json.loads(index.read_text(encoding='utf-8'))['response']['announcements']
    out=ROOT/'runtime/company-research'/('600519-finance-comparatives-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir()
    records=[]
    for identifier in ['1225114745','1224462928']:
        matches=[r for r in rows if str(r['announcementId'])==identifier and r['secCode']=='600519']
        if len(matches)!=1:
            raise ValueError('Finance source identity mismatch')
        item=matches[0]
        url='https://static.cninfo.com.cn/'+item['adjunctUrl']
        with build_opener(ProxyHandler({})).open(url,timeout=30) as response:
            raw=response.read(10000001)
        if not raw.startswith(b'%PDF') or len(raw)>10000000:
            raise ValueError('Invalid PDF')
        pdf=out/(identifier+'.pdf');pdf.write_bytes(raw)
        pages=[{'page':i+1,'text':p.extract_text()} for i,p in enumerate(PdfReader(pdf).pages)]
        records.append({'announcement':item,'url':url,'sha256':hashlib.sha256(raw).hexdigest(),'pages':pages})
        print(json.dumps({'id':identifier,'pages':[p for p in pages if '净利润' in p['text']]},ensure_ascii=False),flush=True)
    (out/'evidence.json').write_text(json.dumps({'official_index':str(index),'index_sha256':hashlib.sha256(index.read_bytes()).hexdigest(),'records':records},ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'outputs':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir()}},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out)}))


if __name__=='__main__':main()
