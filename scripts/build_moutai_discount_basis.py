"""Dated academic/sovereign inputs and explicit cost-of-equity sensitivity."""
from datetime import datetime, timezone
from decimal import Decimal as D
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
from bs4 import BeautifulSoup

ROOT=Path('D:/GPTProject/value-investment')
BASE=ROOT/'runtime/valuation-research'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def percent(value):
    if not value.endswith('%'):
        raise ValueError('Explicit percentage unit required')
    number=D(value[:-1])/100
    if not number.is_finite() or number < 0:
        raise ValueError('Invalid premium')
    return number


def main():
    academic=BASE/'damodaran-country-premium-20260909T115741948194Z'
    original=academic/'original.html'
    if sha(original)!='ea30d57fc0858072c520930e2e5b8a5e5affdce81f7f2e1f9054efab79959dbc':
        raise ValueError('Academic original changed')
    soup=BeautifulSoup(original.read_bytes(),'html.parser')
    text=' '.join(soup.stripped_strings)
    if 'Last updated: January 5, 2026' not in text:
        raise ValueError('Publication date changed')
    countries={}
    for tr in soup.find_all('tr'):
        row=[' '.join(c.stripped_strings) for c in tr.find_all(['th','td'])]
        if row and row[0] in {'China','United States'}:
            if row[0] in countries or len(row)!=8:
                raise ValueError('Ambiguous country row')
            countries[row[0]]=row
    if set(countries)!={'China','United States'}:
        raise ValueError('Required country rows missing')
    china,us=countries['China'],countries['United States']
    default,crp,erp=map(percent,china[2:5])
    mature=erp-crp
    if mature != percent(us[4])-percent(us[3]):
        raise ValueError('Mature-market premium does not reconcile')
    curve_path=BASE/'cfets-normalized-20260909T091701127108Z/evidence.json'
    manifest=json.loads((curve_path.parent/'manifest.json').read_text(encoding='utf-8'))
    if sha(curve_path)!=manifest['evidence_sha256']:
        raise ValueError('Curve package changed')
    curve=json.loads(curve_path.read_text(encoding='utf-8'))
    for ref in curve['sources']:
        p=(BASE/ref['path']).resolve()
        if not p.is_relative_to(BASE.resolve()) or sha(p)!=ref['sha256']:
            raise ValueError('Curve original changed')
    if curve['observation_date']!='2026-09-08' or curve['normalized_unit']!='decimal':
        raise ValueError('Curve date/unit changed')
    ten=[r for r in curve['rows'] if D(r['tenor_years'])==10]
    if len(ten)!=1:
        raise ValueError('Missing or duplicate ten-year point')
    sovereign=D(ten[0]['rates_decimal']['maturityYieldStr'])
    adjusted=sovereign-default
    results=[]
    # Deliberate hypothetical loadings; these are not measured Moutai betas.
    for beta in map(D,['0.8','1.0','1.2']):
        for loading in map(D,['0.5','1.0','1.5']):
            cost=adjusted+beta*mature+loading*crp
            if F(cost)!=F(sovereign)-F(default)+F(beta)*F(mature)+F(loading)*F(crp):
                raise ValueError('Independent cost calculation mismatch')
            results.append({'beta_assumption':str(beta),'country_loading_assumption':str(loading),
                            'illustrative_cost_of_equity':str(cost)})
    unit_load=adjusted+mature+crp
    wrong_double_country=adjusted+erp+crp
    if wrong_double_country-unit_load!=crp:
        raise ValueError('Double-counting diagnostic failed')
    data={'symbol':'600519','valuation_information_date':'2026-09-09',
        'academic_publication_date':'2026-01-05','curve_date':curve['observation_date'],
        'country_source_rows':countries,'unit':'decimal_rates',
        'china_default_spread':str(default),'china_country_risk_premium':str(crp),
        'china_total_equity_risk_premium':str(erp),'mature_market_premium':str(mature),
        'ten_year_sovereign_yield_to_maturity':str(sovereign),
        'illustrative_default_adjusted_sovereign_yield':str(adjusted),
        'formula':'Ke = (CNY sovereign yield - country default spread) + beta * mature ERP + lambda * country ERP',
        'sensitivity':results,'unit_loading_example':str(unit_load),
        'double_country_risk_overstatement':str(wrong_double_country-unit_load),
        'selected_company_cost_of_equity':None,'selected_wacc':None,
        'approved_for_valuation':False,
        'limitations':[
            'January country estimate and September yield are asynchronous; country spread is not a same-day observation.',
            'Subtracting rating-derived country default spread from local sovereign yield is a modelling hypothesis, not an observed default-free CNY rate.',
            'Ten-year yield to maturity is not a zero-coupon annual-effective discount factor; compounding and duration matching remain unapproved.',
            'Beta and lambda grid is hypothetical and symmetric around unit loadings; neither measured beta nor a statistical confidence interval.',
            'Company operating exposure and peer unlevered beta, financial carveout and debt market weights remain necessary.',
            'Do not add country premium again to total country equity premium.',
            'Academic estimates are not company guidance or guaranteed expected returns.',
            'Current references cannot be applied retroactively to 2015-2025 strategy decisions.']}
    out=BASE/('moutai-discount-basis-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir()
    (out/'evidence.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'inputs':{str(p):sha(p) for p in [original,curve_path,Path(__file__)]},
        'evidence_sha256':sha(out/'evidence.json')},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'mature_erp':str(mature),'unit_loading_example':str(unit_load),
        'range':[results[0]['illustrative_cost_of_equity'],results[-1]['illustrative_cost_of_equity']],
        'approved':False}))


if __name__=='__main__':
    main()
