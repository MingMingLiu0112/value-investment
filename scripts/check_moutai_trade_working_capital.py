"""Selected disclosed trading balances, not complete industrial NWC."""
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
    rows=[('bank_acceptance',1,'2475749125.89','4457064160.16',54,'银行承兑票据2,475,749,125.894,457,064,160.16'),
          ('prepayments',1,'16190168.54','6637314.31',55,'合计16,190,168.54100.006,637,314.31100.00'),
          ('trade_payables',-1,'3509015535.31','4007309049.87',69,'应付货款及服务费3,509,015,535.314,007,309,049.87'),
          ('customer_advances',-1,'3177561597.07','8006739780.94',69,'预收货款3,177,561,597.078,006,739,780.94'),
          ('dealer_deposits',-1,'3200597532.27','2056169120.41',71,'经销商保证金3,200,597,532.272,056,169,120.41')]
    cache={page:texts(source,page) for page in {r[4] for r in rows}}
    for _,_,_,_,page,phrase in rows:
        if any(phrase not in text for text in cache[page]):
            raise ValueError('Trading-balance original mismatch')
    inventory=ROOT/'runtime/company-research/600519-inventory-bridge-20260909T101454111336Z/evidence.json'
    expected=json.loads((inventory.parent/'manifest.json').read_text(encoding='utf-8'))['evidence_sha256']
    if sha(inventory)!=expected:
        raise ValueError('Inventory evidence changed')
    inv=json.loads(inventory.read_text(encoding='utf-8'))
    opening=sum((D(r['opening_carrying_value']) for r in inv['categories']),D(0))
    closing=sum((D(r['closing_carrying_value']) for r in inv['categories']),D(0))
    normalized=[{'field':'inventory','sign':1,'closing':str(closing),'opening':str(opening),'source':str(inventory.relative_to(ROOT))}]
    normalized.extend({'field':key,'sign':sign,'closing':current,'opening':prior,'page':page,'original_row':phrase}
                      for key,sign,current,prior,page,phrase in rows)
    totals={}
    for period in ('closing','opening'):
        total=sum((D(r[period])*r['sign'] for r in normalized),D(0))
        if Fraction(total)!=sum((Fraction(r[period])*r['sign'] for r in normalized),Fraction(0)):
            raise ValueError('Independent subtotal mismatch')
        totals[period]=str(total)
    change=D(totals['closing'])-D(totals['opening'])
    for row in normalized:
        row['signed_change']=str((D(row['closing'])-D(row['opening']))*row['sign'])
    out=ROOT/'runtime/company-research'/('600519-trade-working-capital-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(exist_ok=False)
    payload={'symbol':'600519','period':'2026H1','unit':'CNY','scope':'selected consolidated trading-balance subtotal',
        'source_path':str(source.relative_to(ROOT)),'source_sha256':sha(source),'inventory_input_sha256':sha(inventory),
        'components':normalized,'subtotal':totals,'subtotal_increase':str(change),
        'complete_industrial_NWC':False,'FCFF_input_approved':False,
        'remaining_scope':['Trade receivables and other receivables, payroll, operating taxes, other trading balances and subsidiary allocation.',
            'Separate construction-related guarantees/payables from ordinary operating reinvestment.',
            'Cash-flow effects need noncash/foreign-exchange and finance-company reconciliation.'],
        'limitations':['This subtotal is not the consolidated cash-flow receivable/payable adjustment.',
            'Dealer deposits are refundable funding, not sales revenue.',
            'Do not re-add derecognized endorsed/discounted bills to on-balance-sheet receivables.',
            'Reported balance changes do not alone establish a sustainable forecast ratio.']}
    (out/'evidence.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'evidence_sha256':sha(out/'evidence.json'),'script_sha256':sha(Path(__file__))},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'selected_subtotal_increase':str(change),'complete_industrial_NWC':False}))


if __name__=='__main__':
    main()
