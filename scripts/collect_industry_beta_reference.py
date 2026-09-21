"""Archive academic industry beta observations with their original headers."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.request import build_opener, ProxyHandler, Request
from bs4 import BeautifulSoup

ROOT=Path('D:/GPTProject/value-investment')


def main():
    url='https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/Betas.html'
    with build_opener(ProxyHandler({})).open(Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=30) as response:
        raw=response.read(4000001)
        final=response.url
    if len(raw)>4000000:
        raise ValueError('Response too large')
    soup=BeautifulSoup(raw,'html.parser')
    selected=[]
    for table in soup.find_all('table'):
        rows=[[' '.join(c.stripped_strings) for c in row.find_all(['th','td'])] for row in table.find_all('tr')]
        matches=[r for r in rows if r and 'Beverage' in r[0]]
        if matches:
            selected.append({'headers':rows[:2],'rows':matches})
    if not selected:
        raise ValueError('Beverage rows not found; do not substitute unrelated sector')
    links=[{'text':' '.join(a.stripped_strings),'href':a.get('href')} for a in soup.find_all('a') if a.get('href')]
    result={'requested_url':url,'final_url':final,'fetched_at':datetime.now(timezone.utc).isoformat(),
        'original_sha256':hashlib.sha256(raw).hexdigest(),'header_text':' '.join(soup.stripped_strings)[:2800],
        'selected_tables':selected,'links':links,'company_beta_approved':False,
        'limitations':['Academic aggregate is not an independently verified company beta.',
            'Check geography, sample count, cash and debt adjustment, estimation period and benchmark before company application.',
            'Alcoholic beverages include unlike products and channels; retain differences from Chinese premium baijiu.',
            'Levered beta, unlevered beta and cash-adjusted unlevered beta are not interchangeable.',
            'This current snapshot is not a historical point-in-time series.']}
    out=ROOT/'runtime/valuation-research'/('damodaran-industry-beta-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(parents=True)
    (out/'original.html').write_bytes(raw)
    (out/'evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'outputs':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir()}},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'tables':selected,'header':result['header_text'],'links':links[:15]},ensure_ascii=False))


if __name__=='__main__':
    main()
