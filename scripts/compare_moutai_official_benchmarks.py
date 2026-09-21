"""Compare existing account marks to official gross TRI levels, with limits."""
from datetime import date, datetime, timezone
from decimal import Decimal as D
from pathlib import Path
import csv
import hashlib
import json

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'runtime/strategy-validation'
SOURCE=BASE/'official-benchmark-probe-20260909T162408904845Z'
ACCOUNT=BASE/'moutai-account-comparison-20260909T145827486266Z/aligned-daily.csv'
PINS={ACCOUNT:'c71ab0c4693421bd2a0942b31e72466093873e6d933c3a2bcfb8e6339d7ee73e',
      SOURCE/'H00300.response':'c8d2aef30a3a421737e8c643f934ba29612626215d7d9d9c73ecb7e78875ef63',
      SOURCE/'H00932.response':'37c69bbbf9401be987b280dbb21f6ca90ff51d4e9205844c70d245b8b0f831aa'}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    for path, expected in PINS.items():
        if digest(path)!=expected:
            raise ValueError('Source hash changed: '+str(path))
    with ACCOUNT.open(encoding='utf-8',newline='') as stream:
        accounts=[r for r in csv.DictReader(stream) if r['scenario']=='20-unadjusted']
    dates=[r['date'] for r in accounts]
    if len(dates)!=2674 or dates!=sorted(set(dates)):
        raise ValueError('Account date coverage changed')
    curves={'moutai_hold_account':[D(r['hold_account_equity_after_initial_withholding']) for r in accounts],
            'legacy_zero_trade_account':[D(r['legacy_account_equity']) for r in accounts]}
    excluded={}
    for code, name in [('H00300','沪深300全收益指数'),('H00932','中证主要消费全收益指数')]:
        rows=json.loads((SOURCE/(code+'.response')).read_text(encoding='utf-8'))['data']
        values={}
        for row in rows:
            day=datetime.strptime(row['tradeDate'],'%Y%m%d').date().isoformat()
            if day in values or row['indexCode']!=code or row['indexNameCnAll']!=name:
                raise ValueError('Duplicate date or wrong index identity')
            value=D(str(row['close']))
            if not value.is_finite() or value<=0:
                raise ValueError('Invalid index level')
            values[day]=value
        if set(dates)-set(values):
            raise ValueError('Benchmark missing account dates')
        excluded[code]=[r for r in rows if datetime.strptime(r['tradeDate'],'%Y%m%d').date().isoformat() not in dates]
        curves[code]=[values[day] for day in dates]
    results={}
    segments={'full':('2015-01-05','2025-12-31'),'2015-2019':('2015-01-05','2019-12-31'),
              '2020-2022':('2020-01-01','2022-12-31'),'2023-2025':('2023-01-01','2025-12-31')}
    for label,(start,end) in segments.items():
        indices=[i for i,day in enumerate(dates) if start<=day<=end]
        first=max(0,indices[0]-1)
        last=indices[-1]
        metric={}
        for name,curve in curves.items():
            peak=curve[first]
            drawdown=D(0)
            for value in curve[first:last+1]:
                peak=max(peak,value)
                drawdown=max(drawdown,(peak-value)/peak)
            ret=curve[last]/curve[first]-1
            independent=float(curve[last])/float(curve[first])-1
            if abs(float(ret)-independent)>1e-12:
                raise ValueError('Return arithmetic mismatch')
            metric[name]={'return':str(ret),'max_drawdown':str(drawdown),
                          'opening_date':dates[first],'ending_date':dates[last]}
        results[label]=metric
    out=BASE/('moutai-official-benchmark-comparison-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir()
    limits=[
        'Official API identifies total-return series; detailed methodology and independent series cross-check remain unverified.',
        'Two extra source dates per index are quarantined rather than relabelled or silently filled; index source calendar anomalies require explanation.',
        'TRI is a gross theoretical dividend-reinvestment level, not a tradable ETF or after-fee account. Hold account retains cash dividends; it is not an identical reinvestment convention.',
        'Both indices normalized at 2015-01-05 close; stock account begins cash and fills on 2015-01-06 open. Initial execution timing differs.',
        'Legacy account is the previously verified zero-trade case, not evidence of a functioning historical valuation strategy.',
        'Historical names and composition may change. Consumer-staples industry suitability is a research comparison, not a claim of identical stock risk exposure.',
        'Performance differences are descriptive, not certified net alpha, causal strategy benefit, or live admission.'
    ]
    payload={'metrics':results,'excluded_source_rows':excluded,'rows':len(dates),'limits':limits,'net_alpha_approved':False,'strategy_approved':False}
    (out/'evidence.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    with (out/'aligned-levels.csv').open('w',encoding='utf-8',newline='') as stream:
        writer=csv.writer(stream)
        writer.writerow(['date',*curves])
        for i,day in enumerate(dates):
            writer.writerow([day,*(str(curve[i]/curve[0]) for curve in curves.values())])
    lines=['# 茅台账户与官方全收益指数：研究诊断','',
           '账户收益与税费前、分红再投资的指数口径不同；不能据此宣称净超额收益。','',
           '| 区间 | 茅台持有账户 | 旧规则零交易 | 沪深300全收益 | 主要消费全收益 |','| --- | ---: | ---: | ---: | ---: |']
    for segment,metrics in results.items():
        lines.append('| '+segment+' | '+' | '.join(f"{D(m['return'])*100:.2f}%" for m in metrics.values())+' |')
    lines+=['','## 限制','']+['- '+item for item in limits]
    (out/'comparison.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps({'inputs':{str(p.relative_to(ROOT)):h for p,h in PINS.items()},'script_sha256':digest(Path(__file__)),'outputs':{p.name:digest(p) for p in out.iterdir()}},indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'metrics':results},ensure_ascii=False))


if __name__=='__main__':
    main()
