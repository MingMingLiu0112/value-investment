"""Test whether official CSI historical values depend on the requested window."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import requests

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'runtime/strategy-validation'
SOURCE=BASE/'official-benchmark-probe-20260909T162408904845Z'
PINS={'H00300':'c8d2aef30a3a421737e8c643f934ba29612626215d7d9d9c73ecb7e78875ef63',
      'H00932':'37c69bbbf9401be987b280dbb21f6ca90ff51d4e9205844c70d245b8b0f831aa'}


def main():
    out=BASE/('benchmark-query-stability-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir()
    session=requests.Session()
    session.trust_env=False
    records=[]
    for code,expected in PINS.items():
        raw=(SOURCE/(code+'.response')).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=expected:
            raise ValueError('Pinned original changed')
        original={r['tradeDate']:r for r in json.loads(raw)['data']}
        for start,end in [('20150101','20150107'),('20150105','20150107'),('20180615','20180620')]:
            record={'code':code,'start':start,'end':end,'original_sha256':expected}
            try:
                response=session.get('https://www.csindex.com.cn/csindex-home/perf/index-perf',params={'indexCode':code,'startDate':start,'endDate':end},timeout=(8,20))
                filename=f'{code}-{start}-{end}.response'
                (out/filename).write_bytes(response.content)
                record.update(url=response.url,status=response.status_code,raw_path=filename,sha256=hashlib.sha256(response.content).hexdigest(),fetched_at=datetime.now(timezone.utc).isoformat())
                response.raise_for_status()
                rows=response.json()['data']
                record['rows']=rows
                record['close_disagreements']=[{'date':r['tradeDate'],'new':r['close'],'original':original.get(r['tradeDate'],{}).get('close')} for r in rows if r['close']!=original.get(r['tradeDate'],{}).get('close')]
                record['missing_original_dates']=[day for day in original if start<=day<=end and day not in {r['tradeDate'] for r in rows}]
                record['duplicate_dates']=len(rows)!=len({r['tradeDate'] for r in rows})
            except Exception as exc:
                record['error']=type(exc).__name__+': '+str(exc)
            records.append(record)
            print(json.dumps({k:v for k,v in record.items() if k!='rows'},ensure_ascii=False),flush=True)
    payload={'records':records,'scope':'Repeated-window consistency is not independent source validation or proof of valid exchange sessions. No source dates corrected or values approved.'}
    (out/'evidence.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'outputs':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir()}},indent=2),encoding='utf-8')
    print('OUTPUT',out)


if __name__=='__main__':
    main()
