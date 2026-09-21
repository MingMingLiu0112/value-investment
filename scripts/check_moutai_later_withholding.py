"""Authenticate later notices' initial withholding, not final investor tax."""
from datetime import datetime, timezone
from pathlib import Path
import json
from pypdf import PdfReader
from check_moutai_ttm_comparability import ROOT, sha, texts, compact

def main():
    registry=ROOT/'docs/reviewed-cash-distributions.json'
    events=sorted([e for e in json.loads(registry.read_text(encoding='utf-8'))['events']
                   if e['symbol']=='600519' and e['record_date']>'2015-09-08'],key=lambda e:e['record_date'])
    if len(events)!=14:
        raise ValueError('Later distribution inventory changed')
    evidence=[]
    for event in events:
        source=event['evidence'][0]; path=(ROOT/source['path']).resolve()
        if not path.is_relative_to(ROOT) or sha(path)!=source['sha256']:
            raise ValueError('Notice changed')
        pages=[]
        for number,page in enumerate(PdfReader(path).pages,1):
            text=compact(page.extract_text())
            if '暂不扣缴个人所得税' in text:
                pages.append(number)
        if not pages:
            raise ValueError('Initial withholding statement absent')
        selected=None
        for page in pages:
            pair=texts(path,page)
            if all('暂不扣缴个人所得税' in t and '股息红利所得暂免征收个人所得税' in t for t in pair):
                selected=(page,pair)
                break
        if selected is None:
            raise ValueError('Both holding-period treatments not found on one page')
        page,pair=selected
        text=pair[0]; index=text.index('暂不扣缴个人所得税')
        excerpt=text[max(0,index-180):index+220]
        evidence.append({'record_date':event['record_date'],'payment_date':event['cash_payment_date'],
            'cash_per_share':event['cash_per_share'],'initial_withholding_per_share_cny':'0',
            'account_scope':'mainland_individual_unrestricted_sse_szse',
            'source_path':source['path'],'source_url':source['url'],'source_sha256':source['sha256'],
            'physical_page':page,'excerpt':excerpt,
            'method':'issuer original SHA and two decoders; initial nonwithholding and long-holding exemption clauses',
            'final_tax_approved':False})
    out=ROOT/'runtime/strategy-validation'/('moutai-later-withholding-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir()
    result={'symbol':'600519','events':evidence,'registry_sha256':sha(registry),
        'scope':'initial cash withholding for stated individual unrestricted account only',
        'limitations':['Zero initial debit does not mean zero final tax on disposal.',
            'Corporate-action tax-lot acquisition dates and FIFO disposal still require operational evidence.',
            'Do not apply this scope to QFII, Stock Connect, restricted shares or unknown account types.']}
    (out/'evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'script_sha256':sha(Path(__file__)),
        'evidence_sha256':sha(out/'evidence.json')},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'verified_notices':len(evidence),'evidence_sha256':sha(out/'evidence.json')}))

if __name__=='__main__':
    main()
