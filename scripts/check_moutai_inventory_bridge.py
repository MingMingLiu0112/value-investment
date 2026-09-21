"""Inventory carrying values and cash-flow reconciliation, without assumed turnover."""
from datetime import datetime, timezone
from decimal import Decimal as D
from fractions import Fraction
from pathlib import Path
import json
from check_moutai_ttm_comparability import ROOT, sha, texts


def main():
    source=ROOT/'runtime/historical-filing-index/20260909T033444358365Z/pdfs/600519-1225475868.pdf'
    if sha(source)!='0e10aa26be46b1cf3cd03f06e834c7fb98d5dd0d661b96f8fddd4af7e846a4f6':
        raise ValueError('Original changed')
    rows=[('原材料','2480473410.45','3738451309.98'),
          ('在产品','19295520769.07','25663368216.66'),
          ('库存商品','4618161161.62','4506771668.40'),
          ('自制半成品','34923053030.16','27518830601.14')]
    pair=texts(source,58)
    checks=['原材料2,480,473,410.452,480,473,410.453,738,451,309.983,738,451,309.98',
            '在产品19,296,804,753.901,283,984.8319,295,520,769.0725,664,652,201.491,283,984.8325,663,368,216.66',
            '库存商品4,618,161,161.624,618,161,161.624,506,771,668.404,506,771,668.40',
            '自制半成品34,923,053,030.1634,923,053,030.1627,518,830,601.1427,518,830,601.14',
            '合计61,318,492,356.131,283,984.8361,317,208,371.3061,428,705,781.011,283,984.8361,427,421,796.18']
    for phrase in checks:
        if any(phrase not in text for text in pair):
            raise ValueError('Inventory original row mismatch')
    totals=[]
    for index,expected in [(1,'61317208371.30'),(2,'61427421796.18')]:
        total=sum((D(row[index]) for row in rows),D(0))
        if total!=D(expected) or Fraction(total)!=sum((Fraction(row[index]) for row in rows),Fraction(0)):
            raise ValueError('Inventory total mismatch')
        totals.append(total)
    delta=totals[0]-totals[1]
    if -delta!=D('110213424.88'):
        raise ValueError('Cash-flow movement mismatch')
    if any('列）110,213,424.88-628,446,802.13' not in text for text in texts(source,81)):
        raise ValueError('Cash flow original mismatch')
    values=[{'category':name,'closing_carrying_value':current,'opening_carrying_value':prior,
             'change':str(D(current)-D(prior)),'closing_share':str(D(current)/totals[0])} for name,current,prior in rows]
    out=ROOT/'runtime/company-research'/('600519-inventory-bridge-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(exist_ok=False)
    result={'symbol':'600519','period':'2026H1','scope':'consolidated disclosed inventory','unit':'CNY',
        'source_path':str(source.relative_to(ROOT)),'source_sha256':sha(source),'physical_pages':[58,81],
        'original_rows':checks,'categories':values,'total_change':str(delta),
        'cashflow_inventory_release':str(-delta),'industrial_NWC_approved':False,
        'limitations':['Carrying value is net of disclosed impairment; gross balances cannot substitute it.',
            'Category changes do not identify internal transfers, purchases or consumption separately.',
            'Semi-finished inventory cannot automatically be classified as sale-ready aged liquor.',
            'Inventory cash-flow reconciliation does not complete industrial working capital or establish sustainable release.',
            'Do not extrapolate one half-year inventory reduction as recurring future cash generation.']}
    (out/'evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'evidence_sha256':sha(out/'evidence.json'),'script_sha256':sha(Path(__file__))},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'total_change':str(delta),'categories':values}))


if __name__=='__main__':
    main()
