"""Reconcile disclosed cost categories and exact product gross-profit changes."""
from datetime import datetime, timezone
from decimal import Decimal as D
from fractions import Fraction
from pathlib import Path
import json
from check_moutai_ttm_comparability import ROOT, sha, texts


def main():
    annual=ROOT/'runtime/historical-filing-index/20260909T033444358365Z/pdfs/600519-1225114741.pdf'
    interim=ROOT/'runtime/historical-filing-index/20260909T033444358365Z/pdfs/600519-1225475868.pdf'
    for path,expected in [(annual,'474905deeaf0f875fc0a1b097a626c0c7852c427faadc5d7fc7816cbf45ea288'),
                          (interim,'0e10aa26be46b1cf3cd03f06e834c7fb98d5dd0d661b96f8fddd4af7e846a4f6')]:
        if sha(path)!=expected:
            raise ValueError('Original changed')
    rows=[('直接材料','7607858939.76','51.38','6895320421.92'),
          ('直接人工','5499482112.67','37.14','5224448485.08'),
          ('制造费用','902282395.06','6.10','776373890.79'),
          ('燃料动力','469410305.65','3.17','422328634.52'),
          ('运输费','326866386.45','2.21','311524380.58')]
    decoded=texts(annual,11)
    for name,current,weight,prior in rows:
        phrase=name+format(D(current),',.2f')+weight+format(D(prior),',.2f')
        if any(phrase not in text for text in decoded):
            raise ValueError('Cost category mismatch')
    for index,total in [(1,'14805900139.59'),(3,'13629995812.89')]:
        if sum((D(r[index]) for r in rows),D(0))!=D(total) or sum((Fraction(r[index]) for r in rows),Fraction(0))!=Fraction(total):
            raise ValueError('Cost categories do not reconcile')
    statements=[(interim,7,'营业成本变动原因说明：主要是本期销量增加及生产成本增加。'),
                (annual,12,'本期费用化研发支出包括列入生产成本的研发支出及科研人员工资等支出。')]
    for path,page,phrase in statements:
        if any(phrase not in text for text in texts(path,page)):
            raise ValueError('Cost explanation mismatch')
    product_path=ROOT/'runtime/company-research/600519-product-ttm-20260909T100540678699Z/evidence.json'
    manifest=json.loads((product_path.parent/'manifest.json').read_text(encoding='utf-8'))
    if sha(product_path)!=manifest['evidence_sha256']:
        raise ValueError('Product evidence changed')
    products=json.loads(product_path.read_text(encoding='utf-8'))['products']
    bridges={}
    for name,item in products.items():
        r0,r1=D(item['revenue']['H12025']),D(item['revenue']['H12026'])
        c0,c1=D(item['cost']['H12025']),D(item['cost']['H12026'])
        gp0,gp1=r0-c0,r1-c1
        revenue_contribution=r1-r0;cost_drag=c1-c0
        if Fraction(gp1-gp0)!=Fraction(revenue_contribution)-Fraction(cost_drag):
            raise ValueError('Gross profit bridge failed')
        bridges[name]={'prior_gross_profit':str(gp0),'current_gross_profit':str(gp1),
            'revenue_contribution':str(revenue_contribution),'cost_drag':str(cost_drag),
            'gross_profit_change':str(gp1-gp0),'gross_profit_growth':str(gp1/gp0-1),
            'prior_margin':str(gp0/r0),'current_margin':str(gp1/r1),
            'margin_change_percentage_points':str((gp1/r1-gp0/r0)*100)}
    payload={'symbol':'600519','cost_period':'2025FY','product_comparison':'2026H1 versus 2025H1','unit':'CNY',
        'annual_cost_categories':[{'name':r[0],'current':r[1],'prior':r[3]} for r in rows],
        'product_gross_profit_bridges':bridges,'sources':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p)} for p in (annual,interim,product_path)],
        'physical_page_checks':[{'path':str(p.relative_to(ROOT)),'page':n,'phrase':t} for p,n,t in statements],
        'forecast_constraints':['Revenue growth and cost growth must be modelled separately by product.',
            'Total cost growth includes volumes and mix; it is not an observed unit input price change.',
            'Aggregate annual cost categories are not product-specific H1 cost categories.',
            'Do not subtract the total R&D spending disclosure again from profit already net of production costs and R&D expense.',
            'Gross profit is before taxes/surcharges and operating expenses; not EBIT or FCFF.'],
        'forecast_parameters_approved':False}
    out=ROOT/'runtime/company-research'/('600519-cost-drivers-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(exist_ok=False)
    (out/'evidence.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'evidence_sha256':sha(out/'evidence.json'),'script_sha256':sha(Path(__file__))},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'bridges':bridges}))


if __name__=='__main__':
    main()
