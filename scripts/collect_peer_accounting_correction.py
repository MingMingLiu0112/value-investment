"""Archive and inspect the issuer's accounting-correction explanation."""
from datetime import datetime,timezone
import hashlib,json
from pathlib import Path
from urllib.request import build_opener,ProxyHandler
from pypdf import PdfReader

ROOT=Path('D:/GPTProject/value-investment')


def main():
    index=next((ROOT/'runtime/historical-filing-index/20260909T125708144490Z').glob('*.json'))
    rows=json.loads(index.read_text(encoding='utf-8'))['response']['announcements']
    if len(rows)!=1 or str(rows[0]['announcementId'])!='1225273122' or rows[0]['secCode']!='000858':
        raise ValueError('Correction identity mismatch')
    url='https://static.cninfo.com.cn/'+rows[0]['adjunctUrl']
    with build_opener(ProxyHandler({})).open(url,timeout=30) as r:
        raw=r.read(10000001)
    if len(raw)>10000000 or not raw.startswith(b'%PDF'):
        raise ValueError('Invalid bounded PDF')
    out=ROOT/'runtime/company-research'/('000858-accounting-correction-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(parents=True)
    pdf=out/'1225273122.pdf';pdf.write_bytes(raw)
    pages=[{'page':i+1,'text':p.extract_text()} for i,p in enumerate(PdfReader(pdf).pages)]
    result={'source_url':url,'source_sha256':hashlib.sha256(raw).hexdigest(),'announcement':rows[0],
        'index_sha256':hashlib.sha256(index.read_bytes()).hexdigest(),'pages':pages,
        'historical_use':'Unavailable before actual announcement; do not rewrite prior decisions.'}
    (out/'evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'outputs':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir()}},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'pages':pages[:3]},ensure_ascii=False))


if __name__=='__main__':main()
