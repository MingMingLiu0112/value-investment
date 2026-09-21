"""Archive a bounded public academic reference, not a company WACC approval."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.request import build_opener, ProxyHandler, Request
from bs4 import BeautifulSoup

ROOT = Path('D:/GPTProject/value-investment')


def main():
    url = 'https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/ctryprem.html'
    opener = build_opener(ProxyHandler({}))
    request = Request(url, headers={'User-Agent':'Mozilla/5.0 research reference retrieval'})
    with opener.open(request, timeout=30) as response:
        raw = response.read(4000001)
        final_url = response.url
        content_type = response.headers.get('Content-Type')
    if len(raw) > 4000000:
        raise ValueError('Response exceeds bounded reference size')
    soup = BeautifulSoup(raw, 'html.parser')
    rows = []
    for table in soup.find_all('table'):
        parsed = [[' '.join(c.stripped_strings) for c in r.find_all(['th','td'])] for r in table.find_all('tr')]
        matches = [r for r in parsed if r and r[0].strip().casefold() in {'china','united states'}]
        if matches:
            rows.append({'header_context':parsed[:3], 'selected_rows':matches})
    plain = soup.get_text(' ', strip=True)
    out = ROOT/'runtime/valuation-research'/('damodaran-country-premium-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(parents=True)
    (out/'original.html').write_bytes(raw)
    result = {'requested_url':url, 'final_url':final_url,'fetched_at':datetime.now(timezone.utc).isoformat(),
        'content_type':content_type,'original_sha256':hashlib.sha256(raw).hexdigest(),
        'header_text':plain[:9000], 'selected_tables':rows,
        'company_wacc_approved':False,
        'limitations':['Academic estimates, not an exchange/company disclosure or observed future return.',
            'Verify publication date, rating method, base market premium and country risk loading before use.',
            'Chinese sovereign yield is not automatically default-free; avoid adding country risk twice.',
            'Country equity premium is not company WACC; business exposure, beta and debt weighting remain necessary.',
            'Current web page is not a point-in-time historical backtest source.']}
    (out/'evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'outputs':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir()}},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'tables':rows,'header':plain[:2600]},ensure_ascii=False))


if __name__=='__main__':
    main()
