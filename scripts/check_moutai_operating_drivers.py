"""Reconcile issuer operating dimensions before building forecasts."""
from datetime import datetime, timezone
from decimal import Decimal as D
from fractions import Fraction
from pathlib import Path
import json
from check_moutai_ttm_comparability import ROOT, sha, texts


def main():
    source = ROOT/'runtime/historical-filing-index/20260909T033444358365Z/pdfs/600519-1225475868.pdf'
    digest = '0e10aa26be46b1cf3cd03f06e834c7fb98d5dd0d661b96f8fddd4af7e846a4f6'
    if sha(source) != digest:
        raise ValueError('Original changed')
    dimensions = {
        'product': [('茅台酒','77724437925.48','6000884228.70'),
                    ('其他系列酒','12934186511.82','3415795490.58'),
                    ('其他业务','44636527.18','57082846.60')],
        'geography': [('国内','89666168740.29','9388446883.50'),
                      ('国外','1037092224.19','85315682.38')],
        'channel': [('批发代理','38696577376.60','5796572699.06'),
                    ('直销','52006683587.88','3677189866.82')],
    }
    pair = texts(source, 74)
    total_revenue, total_cost = D('90703260964.48'), D('9473762565.88')
    result = {}
    for dimension, rows in dimensions.items():
        values = []
        for name, revenue, cost in rows:
            phrase = name + format(D(revenue), ',.2f') + format(D(cost), ',.2f')
            if any(phrase not in text for text in pair):
                raise ValueError(f'Original row mismatch: {name}')
            margin = (D(revenue)-D(cost))/D(revenue)
            values.append({'name':name,'revenue':revenue,'cost':cost,
                           'revenue_share':str(D(revenue)/total_revenue),
                           'gross_margin':str(margin),'physical_page':74,'verified_row':phrase})
        for index, expected in ((1,total_revenue),(2,total_cost)):
            decimal_total = sum((D(row[index]) for row in rows),D(0))
            exact_total = sum((Fraction(row[index]) for row in rows),Fraction(0))
            if decimal_total != expected or exact_total != Fraction(expected):
                raise ValueError(f'{dimension} does not reconcile')
        result[dimension] = values
    expenses = [('taxes_and_surcharges','合计','14682159453.47','13942384581.48',75),
                ('selling','合计','3206308341.53','3260462949.46',75),
                ('administrative','合计','3635355263.82','3694704172.74',75),
                ('research','合计','114926219.60','73901545.96',75)]
    expense_values = {}
    expense_texts = texts(source,75)
    for key,label,current,prior,page in expenses:
        phrase = label + format(D(current),',.2f') + format(D(prior),',.2f')
        if any(phrase not in text for text in expense_texts):
            raise ValueError(f'Expense row mismatch: {key}')
        expense_values[key] = {'current':current,'prior':prior,'physical_page':page,
                              'verified_row':phrase,'ratio_to_operating_revenue':str(D(current)/total_revenue)}
    residual = total_revenue-total_cost-sum((D(row[2]) for row in expenses),D(0))
    exact = Fraction(total_revenue)-Fraction(total_cost)-sum((Fraction(row[2]) for row in expenses),Fraction(0))
    if Fraction(residual) != exact:
        raise ValueError('Independent residual mismatch')
    evidence = {'symbol':'600519','period':'2026H1','unit':'CNY',
        'source_url':'https://static.cninfo.com.cn/finalpage/2026-08-15/1225475868.PDF',
        'source_sha256':digest,'dimensions':result,'expenses':expense_values,
        'operating_revenue':str(total_revenue),'operating_cost':str(total_cost),
        'revenue_less_cost_and_four_expenses':str(residual),
        'industrial_ebit_approved':False,'forecast_approved':False,
        'interpretation':['Product, geography and channel are alternative partitions; never add their totals.',
            'Operating revenue excludes the separately disclosed financial interest revenue.',
            'The residual still uses consolidated shared expenses; it is not verified industrial EBIT.',
            'Gross margin excludes consumption taxes and other operating expenses.',
            'Channel mix alone cannot identify price or volume growth; do not infer either.',
            'Half-year actuals are not a full-year forecast or normalized margin.']}
    out = ROOT/'runtime/company-research'/('600519-operating-drivers-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(exist_ok=False)
    (out/'evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'source_sha256':digest,
        'evidence_sha256':sha(out/'evidence.json'),'script_sha256':sha(Path(__file__))},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'dimensions_reconciled':list(result),
                     'residual_not_industrial_ebit':str(residual)}))


if __name__ == '__main__':
    main()
