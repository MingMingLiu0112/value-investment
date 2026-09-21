"""Archive issuer trademark agreements discovered in the official index."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import shutil
import requests
import argparse
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--index',default='runtime/historical-filing-index/20260909T170051469712Z')
parser.add_argument('--title-contains',default='')
args=parser.parse_args()
INDEX=(ROOT/args.index).resolve()
if not INDEX.is_relative_to(ROOT):raise ValueError('Index escapes project')
out=ROOT/'runtime/company-research'/('600519-trademark-contracts-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
out.mkdir()
session=requests.Session();session.trust_env=False
records=[]
for index in INDEX.glob('*.json'):
    package=json.loads(index.read_text(encoding='utf-8'))
    for row in package['response']['announcements']:
        if args.title_contains not in row['announcementTitle']:continue
        if row['secCode']!='600519':raise ValueError('Wrong issuer')
        url='https://static.cninfo.com.cn/'+row['adjunctUrl']
        if shutil.disk_usage(out).free<2*1024**3:raise OSError('Preserve 2 GiB free')
        response=session.get(url,timeout=(8,30));response.raise_for_status()
        if not response.content.startswith(b'%PDF'):raise ValueError('Not a PDF')
        path=out/(row['announcementId']+'.pdf');path.write_bytes(response.content)
        reader=PdfReader(path)
        pages=[p.extract_text() for p in reader.pages]
        (out/(row['announcementId']+'.txt')).write_text('\n'.join(pages),encoding='utf-8')
        record={'source_id':row['announcementId'],'url':url,'path':str(path.relative_to(ROOT)),
                'sha256':hashlib.sha256(response.content).hexdigest(),'index_path':str(index.relative_to(ROOT)),
                'index_sha256':hashlib.sha256(index.read_bytes()).hexdigest(),'announcement_time_raw':row['announcementTime'],
                'fetched_at':datetime.now(timezone.utc).isoformat(),'pages':len(pages)}
        records.append(record)
        for i,text in enumerate(pages):
            if any(token in text for token in ('1.5','许可费','使用费','有效期','商标')):
                print(json.dumps({'source':row['announcementId'],'page':i+1,'text':text},ensure_ascii=False),flush=True)
(out/'manifest.json').write_text(json.dumps({'records':records,'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},ensure_ascii=False,indent=2),encoding='utf-8')
print('OUTPUT',out)
