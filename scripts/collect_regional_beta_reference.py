"""Archive author-linked China/global beta workbooks and exact sector rows."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.request import build_opener, ProxyHandler
import xlrd

ROOT=Path('D:/GPTProject/value-investment')


def main():
    out=ROOT/'runtime/valuation-research'/('damodaran-regional-beta-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(parents=True)
    opener=build_opener(ProxyHandler({}))
    results=[]
    for region,name in [('China','betaChina.xls'),('Global','betaGlobal.xls')]:
        url='https://pages.stern.nyu.edu/~adamodar/pc/datasets/'+name
        with opener.open(url,timeout=30) as r:
            raw=r.read(5000001)
            final=r.url
        if len(raw)>5000000:
            raise ValueError('Response too large')
        (out/name).write_bytes(raw)
        book=xlrd.open_workbook(file_contents=raw)
        sheets=[]
        for sheet in book.sheets():
            rows=[sheet.row_values(i) for i in range(sheet.nrows)]
            selected=[{'excel_row':i+1,'values':row} for i,row in enumerate(rows)
                      if any(isinstance(v,str) and 'Beverage' in v for v in row)]
            if selected:
                sheets.append({'sheet':sheet.name,'header_rows':rows[:12],'selected_rows':selected})
        if not sheets:
            raise ValueError('No beverage industry found: '+region)
        result={'region':region,'url':url,'final_url':final,'original_sha256':hashlib.sha256(raw).hexdigest(),
            'sheets':sheets,'downloaded_at':datetime.now(timezone.utc).isoformat()}
        results.append(result)
        (out/(region+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'region':region,'data':sheets},ensure_ascii=False),flush=True)
    result={'sources':results,'company_beta_approved':False,
        'limitations':['Published regional aggregates, not verified Moutai beta or independently verified issuer data.',
            'Regional samples overlap with global; these are not independent estimators.',
            'Excel dates can be numeric serials; original datemode and cell types must be checked before interpreting date.',
            'Column units and methodology require verification before input promotion.']}
    (out/'evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'outputs':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir()}},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out)}),flush=True)


if __name__=='__main__':
    main()
