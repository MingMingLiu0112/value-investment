"""Latest-disclosed share basis plus a material post-interim pricing event."""
from datetime import datetime,timezone
from decimal import Decimal as D,ROUND_HALF_UP
from fractions import Fraction as F
from pathlib import Path
import json
from check_moutai_ttm_comparability import ROOT,sha,texts

BASE=ROOT/'runtime/company-research/600519-current-capital-events-20260909T134419983339Z'


def main():
    evidence=BASE/'evidence.json'
    if sha(evidence)!='c2cb3a0f82727af3203c6ba82f042cb64a7d1520a96f853b4d8d224c07827fe8':
        raise ValueError('Capital events package changed')
    pack=json.loads(evidence.read_text(encoding='utf-8'))
    index=Path(pack['official_index'])
    if sha(index)!=pack['official_index_sha256']:
        raise ValueError('Official index changed')
    for r in pack['records']:
        if sha(BASE/(str(r['announcement']['announcementId'])+'.pdf'))!=r['sha256']:
            raise ValueError('Capital event original changed')
    share_pages=texts(BASE/'1225347653.pdf',1)
    for phrase in ['公司总股本为1,250,081,601股','回购专用证券账户内股份数为0股']:
        if any(phrase not in t for t in share_pages):
            raise ValueError('Share/treasury scope mismatch')
    distribution=texts(BASE/'1225379934.pdf',2)
    for phrase in ['1,250,081,601股','28.02423元','35,032,574,305.19元','2026/6/26']:
        if any(phrase not in t for t in distribution):
            raise ValueError('Dividend basis mismatch')
    shares=1250081601
    gross=D(shares)*D('28.02423')
    if F(gross)!=F(shares)*F('28.02423') or gross.quantize(D('.01'),rounding=ROUND_HALF_UP)!=D('35032574305.19'):
        raise ValueError('Dividend arithmetic mismatch')
    interim=ROOT/'runtime/historical-filing-index/20260909T033444358365Z/pdfs/600519-1225475868.pdf'
    if sha(interim)!='0e10aa26be46b1cf3cd03f06e834c7fb98d5dd0d661b96f8fddd4af7e846a4f6':
        raise ValueError('Interim changed')
    for t in texts(interim,22):
        if '三、股份总数1,252,270,215100-2,188,614-2,188,6141,250,081,601100' not in t:
            raise ValueError('Interim share confirmation mismatch')
    pricing=texts(BASE/'1225431263.pdf',1)
    for phrase in ['2026年7月18日零时起','1539元/瓶调整为1639元/瓶','1269元/瓶调整为1369元/瓶','飞天53%vol500ml贵州茅台酒（2026）']:
        if any(phrase not in t for t in pricing):
            raise ValueError('Price-event identity/scope mismatch')
    changes=[]
    for name,old,new in [('platform_retail','1539','1639'),('sales_contract','1269','1369')]:
        ratio=D(new)/D(old)-1
        if abs(F(ratio)-(F(new)/F(old)-1))>F(1,10**25):
            raise ValueError('Price ratio recomputation mismatch')
        breakeven=D(old)/D(new)-1
        if abs((1+ratio)*(1+breakeven)-1)>D('1e-25'):
            raise ValueError('Price-volume revenue break-even failed')
        sensitivity=[]
        for volume in map(D,['-.10','-.05','0','.05']):
            change=(1+ratio)*(1+volume)-1
            exact=(F(new)/F(old))*(1+F(volume))-1
            if abs(F(change)-exact)>F(1,10**25):
                raise ValueError('Independent price-volume calculation failed')
            sensitivity.append({'volume_change':str(volume),'affected_sales_revenue_change':str(change)})
        changes.append({'channel_price':name,'old':old,'new':new,'change':'100','proportional_change':str(ratio),
            'volume_change_at_revenue_break_even':str(breakeven),'volume_sensitivity':sensitivity})
    channel=texts(interim,8)
    for phrase in ['不含税收入4,026,356.42万元','5,196,204.70','3,869,657.74']:
        if any(phrase not in t for t in channel):
            raise ValueError('Original channel disclosure missing')
    platform=D('4026356.42')*10000
    liquor_revenue=D('77724437925.48')+D('12934186511.82')
    channel_scope={'period':'2026H1','unit':'CNY','platform_alcohol_revenue_ex_vat':str(platform),
        'all_alcohol_revenue':str(liquor_revenue),
        'historical_platform_share_of_alcohol':str(platform/liquor_revenue),
        'target_sku_revenue':None,'target_sku_units':None,
        'future_platform_share':None,
        'scope':'Platform total includes multiple products. Published product/channel marginals do not identify target SKU by channel.',
        'model_formula':'Total affected-plus-unaffected revenue factor = 1 + retail_weight*((new_retail/old_retail)*(1+retail_volume_change)-1) + contract_weight*((new_contract/old_contract)*(1+contract_volume_change)-1)',
        'weight_contract':'Weights are disjoint baseline recognized-revenue exposures, nonnegative and sum <= 1. Do not count the same bottle at retail and upstream contract prices.',
        'assumptions':'Same VAT basis and revenue recognition within each comparison; unchanged unexposed sales; no mix/cost/tax/commission or channel substitution effects.',
        'limits':'One-off price level change, not a recurring annual price growth rate. No incremental profit or company revenue forecast inferred.'}
    result={'symbol':'600519','research_as_of':'2026-09-09','disclosure_supported_ordinary_share_assumption':shares,
        'last_reported_share_date':'2026-06-30','prior_disclosed_treasury_shares':0,
        'current_registry_verified':False,'capital_query_window':pack['query']['seDate'],
        'current_share_basis':'Latest disclosed shares carried forward; no later capital-change announcement identified in the complete query, not an as-of registry extract.',
        'distribution':{'gross_per_share':'28.02423','gross_announced':'35032574305.19','payment_date':'2026-06-26',
            'exact_product_before_cent_rounding':str(gross),'deduct_again_from_june_book_equity':False,
            'one_cent_difference_vs_interim_equity_note':'0.01; retain reported precision, do not rewrite one source'},
        'pricing_event':{'effective_at':'2026-07-18T00:00:00+08:00','publication_date':'2026-07-18',
            'conservative_historical_available_at':'2026-07-19T00:00:00+08:00','intraday_publication_verified':False,
            'product':'飞天53%vol 500ml贵州茅台酒（2026）','changes':changes,
            'forecast_treatment':'Reassess existing aggregate-growth assumptions; do not add both price increases to all company sales.',
            'affected_volume_and_channel_mix':None,'realized_incremental_revenue':None},
        'channel_scope':channel_scope,
        'affected_research':['product growth assumptions','industrial margin/channel mix','sales-subsidiary minority forecast'],
        'historical_facts_changed':False,'existing_condition_experiments_retained':True,
        'current_forecast_event_review_complete':True,
        'event_review_scope':'Aggregate stress assumptions reviewed, not realized uplift or approved company forecast.',
        'assumption_decision':'Retain existing -5/+2/+5 percent Moutai net-revenue growth stress cases. They represent combined price, volume and mix outcomes, not a no-price-change quantity forecast. Do not stack an extra price uplift or repeat this one-off price change each year. Target SKU quantities remain unknown without blocking other explicitly conditional bridge estimates.',
        'valuation_approved':False}
    out=ROOT/'runtime/company-research'/('600519-current-share-price-review-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir()
    (out/'evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'inputs':{str(evidence):sha(evidence),str(index):sha(index),str(interim):sha(interim)},
        'script_sha256':sha(Path(__file__)),'evidence_sha256':sha(out/'evidence.json')},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'shares_assumption':shares,'price_changes':changes,'distribution_already_before_balance':True},ensure_ascii=False))


if __name__=='__main__':main()
