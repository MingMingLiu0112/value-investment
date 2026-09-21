"""Archive the previously indexed Q3 filing for forecast seasonality research."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.request import build_opener, ProxyHandler
from pypdf import PdfReader

ROOT=Path('D:/GPTProject/value-investment')


def main():
    index=ROOT/'runtime/historical-filing-index/20260908T123913013985Z/600519-1-fda76dbd4cb8430d5616d2473b1b3ce9e5f26bb68f0ca38e33aeaa5aa47187a8.json'
    data=json.loads(index.read_text(encoding='utf-8'))
    rows=[r for r in data['response']['announcements'] if str(r['announcementId'])=='1224764517']
    if len(rows)!=1 or rows[0]['secCode']!='600519' or rows[0]['adjunctUrl']!='finalpage/2025-10-30/1224764517.PDF':
        raise ValueError('Indexed filing identity mismatch')
    url='https://static.cninfo.com.cn/'+rows[0]['adjunctUrl']
    with build_opener(ProxyHandler({})).open(url,timeout=30) as r:
        raw=r.read(12000001)
    if len(raw)>12000000 or not raw.startswith(b'%PDF'):
        raise ValueError('Invalid bounded PDF')
    out=ROOT/'runtime/company-research'/('600519-quarter-timing-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(parents=True)
    pdf=out/'600519-1224764517.pdf'
    pdf.write_bytes(raw)
    reader=PdfReader(pdf)
    pages=[{'physical_page':i+1,'text':p.extract_text()} for i,p in enumerate(reader.pages)]
    if '2025' not in pages[0]['text'] or '第三季度' not in pages[0]['text']:
        raise ValueError('PDF report identity mismatch')
    result={'source_url':url,'source_sha256':hashlib.sha256(raw).hexdigest(),'index':str(index.relative_to(ROOT)),
        'index_sha256':hashlib.sha256(index.read_bytes()).hexdigest(),'announcement':rows[0],
        'fetched_at':datetime.now(timezone.utc).isoformat(),'pages':pages,'forecast_timing_approved':False}
    (out/'evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'outputs':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir()}},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'pages':[p for p in pages if p['physical_page']==1 or '营业收入' in p['text']]},ensure_ascii=False))


if __name__=='__main__':
    main()
