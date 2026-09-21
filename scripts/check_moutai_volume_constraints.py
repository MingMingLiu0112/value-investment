"""Archive actual volume/mix evidence and constraints on scenario forecasts."""
from datetime import datetime, timezone
from decimal import Decimal as D
from pathlib import Path
import json
from check_moutai_ttm_comparability import ROOT, sha, texts


def main():
    source=ROOT/'runtime/historical-filing-index/20260909T033444358365Z/pdfs/600519-1225114741.pdf'
    digest='474905deeaf0f875fc0a1b097a626c0c7852c427faadc5d7fc7816cbf45ea288'
    if sha(source)!=digest:
        raise ValueError('Original changed')
    checks={10:['酒类168,774,585,187.6514,805,900,139.5991.23-1.088.63',
                '酒类吨116,123.7385,104.14339,977.8611.252.139.67'],
            15:['茅台酒制酒车间46,395.0058,473.16','系列酒制酒车间59,400.0057,650.57',
                '实际产能按报告期实际基酒产量计算'],
            22:['贮足陈酿、不卖新酒','零售价格动态调整机制']}
    for page,phrases in checks.items():
        decoded=texts(source,page)
        for phrase in phrases:
            if any(phrase not in text for text in decoded):
                raise ValueError(f'Original mismatch p{page}: {phrase}')
    revenue=D('168774585187.65'); volume=D('85104.14')
    # Published growth rates are rounded; this is a mix proxy, not a price series.
    mix_change=(1+D('-1.08')/100)/(1+D('2.13')/100)-1
    result={'symbol':'600519','period':'2025FY','source_path':str(source.relative_to(ROOT)),
        'source_sha256':digest,'physical_page_checks':checks,
        'liquor_revenue_CNY':str(revenue),'sales_tonnes':str(volume),
        'production_base_liquor_tonnes':'116123.73','inventory_tonnes':'339977.86',
        'realized_revenue_per_sales_tonne_CNY':str(revenue/volume),
        'reported_revenue_growth_pct':'-1.08','reported_sales_volume_growth_pct':'2.13',
        'approximate_revenue_per_tonne_change':str(mix_change),
        'scenario_constraints':[
            'Revenue fell while sales volume rose: a constant rising price assumption lacks support.',
            'Revenue per tonne combines product/channel mix and realized pricing; not retail or wholesale price.',
            'Production capacity is base liquor production, not same-year finished-goods sales.',
            'Issuer commits to aged products: capacity release does not prove immediate sellable inventory.',
            'Dynamic retail pricing is a management plan, not a guaranteed revenue increase.',
            'Inventory tonnes cannot be treated as immediately distributable cash or added on top of operating value.'],
        'forecast_parameters_approved':False,'independent_external_corroboration':False}
    out=ROOT/'runtime/company-research'/('600519-volume-constraints-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(exist_ok=False)
    (out/'evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'source_sha256':digest,'script_sha256':sha(Path(__file__)),
        'evidence_sha256':sha(out/'evidence.json')},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'approximate_mix_change':str(mix_change)}))


if __name__=='__main__':
    main()
