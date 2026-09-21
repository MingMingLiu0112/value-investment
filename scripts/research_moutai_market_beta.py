"""Historical market co-movement research; not operating beta or WACC approval."""
from datetime import datetime, timezone
from decimal import Decimal as D
from pathlib import Path
import csv
import hashlib
import json
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
from replay_moutai_distributions import load_inputs, digest, write_json

INDEX=ROOT/'runtime/strategy-validation/official-benchmark-probe-20260909T162408904845Z/H00300.response'
INDEX_HASH='c8d2aef30a3a421737e8c643f934ba29612626215d7d9d9c73ecb7e78875ef63'


def estimate_market_slope(rows):
    """Return descriptive OLS slope diagnostics; not a cost-of-capital input."""
    if len(rows) < 3:
        raise ValueError('At least three monthly observations are required')
    x=np.array([float(r['market_return']) for r in rows])
    y=np.array([float(r['stock_return']) for r in rows])
    design=np.column_stack([np.ones(len(x)),x])
    intercept,beta=np.linalg.lstsq(design,y,rcond=None)[0]
    residual=y-(intercept+beta*x)
    sxx=float(np.sum((x-x.mean())**2))
    if sxx <= 0:
        raise ValueError('Market-return variance must be positive')
    residual_variance=float(np.sum(residual**2)/(len(x)-2))
    standard_error=(residual_variance/sxx)**0.5
    r2=1-float(np.sum(residual**2)/np.sum((y-y.mean())**2))
    return {'equity_return_slope':float(beta),'monthly_intercept_not_alpha':float(intercept),
            'r_squared':r2,'ols_slope_standard_error_iid_assumption':standard_error,
            'approximate_95pct_slope_interval_iid_assumption':[float(beta-1.96*standard_error),float(beta+1.96*standard_error)]}


def main():
    if digest(INDEX)!=INDEX_HASH:
        raise ValueError('Market original changed')
    bars,events,annual,refs=load_inputs(ROOT)
    index_rows=json.loads(INDEX.read_text(encoding='utf-8'))['data']
    market={datetime.strptime(r['tradeDate'],'%Y%m%d').date().isoformat():D(str(r['close'])) for r in index_rows}
    if len(market)!=len(index_rows) or any(r['indexCode']!='H00300' for r in index_rows):
        raise ValueError('Market date or identity conflict')
    by_ex={e['ex_date']:e for e in events}
    if len(by_ex)!=len(events):
        raise ValueError('Overlapping entitlement dates require separate accounting')
    level=D(1)
    daily=[]
    event_checks=[]
    for i,bar in enumerate(bars):
        day=bar['date']
        close=D(str(bar['close']))
        if day not in market or close<=0 or market[day]<=0:
            raise ValueError('Missing or invalid same-day observations')
        if i:
            previous=D(str(bars[i-1]['close']))
            event=by_ex.get(day)
            cash=D(event['cash_per_share']) if event else D(0)
            bonus=D(event.get('bonus_shares_per_share') or '0') if event else D(0)
            if event and event['record_date']!=bars[i-1]['date']:
                raise ValueError('Entitlement base not prior observed close')
            gross=(close*(1+bonus)+cash)/previous
            # Independent fractional-share, immediate reinvestment arithmetic.
            independent=(1+float(bonus)+float(cash)/float(close))*float(close)/float(previous)
            if abs(float(gross)-independent)>1e-12:
                raise ValueError('Independent entitlement return mismatch')
            level*=gross
            if event:
                event_checks.append({'date':day,'record_date':event['record_date'],'cash_per_old_share':str(cash),
                                     'bonus_per_old_share':str(bonus),'gross_factor':str(gross)})
        daily.append({'date':day,'stock_gross_reinvestment_level':str(level),'market_tri_level':str(market[day]),'raw_stock_close':str(close)})
    if len(daily)!=2674 or len(event_checks)!=15:
        raise ValueError('Coverage differs from reviewed replay')
    ends={}
    for row in daily:
        ends[row['date'][:7]]=row
    months=list(ends.values())
    monthly=[]
    for prior,current in zip(months,months[1:]):
        monthly.append({'date':current['date'],
                        'stock_return':str(D(current['stock_gross_reinvestment_level'])/D(prior['stock_gross_reinvestment_level'])-1),
                        'market_return':str(D(current['market_tri_level'])/D(prior['market_tri_level'])-1)})
    if len(monthly)!=131:
        raise ValueError('Unexpected complete-month count')
    samples={'full_2015Feb_2025Dec':monthly,
             '2015Feb_2019Dec':[r for r in monthly if r['date']<'2020-01-01'],
             '2020_2022':[r for r in monthly if '2020-01-01'<=r['date']<'2023-01-01'],
             '2023_2025':[r for r in monthly if r['date']>='2023-01-01'],
             'last_60_months_ending_2025Dec':monthly[-60:]}
    estimates={}
    for label,rows in samples.items():
        xd=[D(r['market_return']) for r in rows];yd=[D(r['stock_return']) for r in rows]
        xm=sum(xd)/len(xd);ym=sum(yd)/len(yd)
        numerator=sum((a-xm)*(b-ym) for a,b in zip(xd,yd))
        denominator=sum((a-xm)**2 for a in xd)
        estimate=estimate_market_slope(rows)
        if denominator<=0 or abs(float(numerator/denominator)-estimate['equity_return_slope'])>1e-10:
            raise ValueError('Independent beta covariance mismatch')
        estimates[label]={'observations':len(rows),'first_month_end':rows[0]['date'],'last_month_end':rows[-1]['date'],
                          **estimate}
    limits=[
        'Stock series assumes gross cash entitlements reinvested fractionally at ex-date close, even before cash is paid; bonus shares valued at that close. This is a theoretical return measure, not an executable account.',
        'Uses actual cash entitlement per eligible share, not ex-reference cash over a different share denominator. Taxes, fees and minimum lots are absent.',
        'Regressions use raw monthly returns with an intercept, not risk-free excess returns. The slope is descriptive market co-movement; intercept is not certified alpha.',
        'Excludes partial January 2015 opening month; ends December 2025 and is not a September 2026 current beta.',
        'Observed listed equity includes financial business, cash and leverage. It is not unlevered industrial asset beta and cannot be directly used as company WACC.',
        'Market TRI identity is source-checked but historical methodology and independent values remain unaccepted; the two nonmatching source dates are not used.',
        'Monthly sampling and window sensitivity are research conventions. No parameter chosen to achieve an attractive valuation; no historical decision input is approved.'
        ,'The reported OLS interval uses an IID residual approximation. It is descriptive only and does not address autocorrelation, non-normal returns, benchmark choice or the industrial-asset scope mismatch.'
    ]
    out=ROOT/'runtime/valuation-research'/('moutai-market-beta-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir()
    for name,rows in [('daily',daily),('monthly',monthly)]:
        with (out/(name+'.csv')).open('w',encoding='utf-8',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    write_json(out/'evidence.json',{'symbol':'600519','benchmark':'H00300','estimates':estimates,'events':event_checks,'limits':limits,'company_wacc_approved':False,'historical_valuation_approved':False})
    write_json(out/'manifest.json',{'script_sha256':digest(Path(__file__)),'inputs':refs+[{'path':str(INDEX.relative_to(ROOT)),'sha256':INDEX_HASH}],
                                  'outputs':{p.name:digest(p) for p in out.iterdir()}})
    print(json.dumps({'output':str(out),'estimates':estimates},ensure_ascii=False))


if __name__=='__main__':main()
