"""Align experimental account ledgers; not a certified net-return benchmark."""
import csv
import json
from datetime import datetime, timezone
from decimal import Decimal as D
from pathlib import Path
import math
import numpy as np
from value_investment_agent.account_path_metrics import account_path_metrics
from replay_moutai_distributions import digest, write_json

ROOT=Path(__file__).resolve().parents[1]
RUNS={
 'hold':('moutai-capital-entry-20260909T145011356660Z','73b0d1092caead794fa5374fbc41b1a1e7265e69cd96d72f0232769ef95eca13'),
 'legacy':('moutai-legacy-condition-replay-20260909T112345869780Z','dc63cbe96d0b889ce0c12e28a850c269e35e133f2297fa08559b8a493bc40fa7')}

def read_csv(path):
    with path.open(encoding='utf-8',newline='') as stream: return list(csv.DictReader(stream))


def path_report(ledger, *, equity_field, cash_field):
    rows=[dict(date=r['date'],equity=r[equity_field],cash=r[cash_field],shares=r['shares'],close=r['close']) for r in ledger]
    reports={}
    for label,lo,hi in [('full','2015-01-01','2025-12-31'),('2015-2019','2015-01-01','2019-12-31'),('2020-2022','2020-01-01','2022-12-31'),('2023-2025','2023-01-01','2025-12-31')]:
        indices=[i for i,r in enumerate(rows) if lo<=r['date']<=hi]
        if not indices:
            raise ValueError('Missing registered segment')
        first=indices[0]
        anchor=rows[first-1] if first else dict(date=rows[0]['date'],equity='1000000')
        segment=[rows[i] for i in indices]
        report=account_path_metrics(segment,opening_equity=anchor['equity'],opening_date=anchor['date'])
        # Independent vector peak and compounded daily returns, not the Decimal loop.
        values=np.array([float(anchor['equity'])]+[float(r['equity']) for r in segment])
        independently_compounded=float(np.prod(values[1:]/values[:-1])-1)
        independently_drawdown=float(np.max(1-values/np.maximum.accumulate(values)))
        if not math.isclose(float(report['marked_return']),independently_compounded,abs_tol=1e-10) or not math.isclose(float(report['max_drawdown']),independently_drawdown,abs_tol=1e-10):
            raise ValueError('Independent path statistics mismatch')
        reports[label]=report
    chained=np.prod([1+float(reports[k]['marked_return']) for k in ('2015-2019','2020-2022','2023-2025')])-1
    if not math.isclose(chained,float(reports['full']['marked_return']),abs_tol=1e-10):
        raise ValueError('Segment boundary capital discontinuity')
    return reports

def main():
    dirs={}
    for name,(directory,expected) in RUNS.items():
        folder=ROOT/'runtime/strategy-validation'/directory;dirs[name]=folder
        manifest=folder/'manifest.json'
        if digest(manifest)!=expected: raise ValueError('Pinned manifest changed')
        for file,checksum in json.loads(manifest.read_text(encoding='utf-8'))['outputs'].items():
            path=(folder/file).resolve()
            if not path.is_relative_to(folder) or digest(path)!=checksum: raise ValueError('Ledger output changed')
    hold=read_csv(dirs['hold']/'retained_003pct_min1-daily.csv')
    fill=json.loads((dirs['hold']/'retained_003pct_min1-fills.json').read_text(encoding='utf-8'))[0]
    if D(str(fill['commission']))!=D('290.88'): raise ValueError('Fee scenario differs')
    hold_config=json.loads((dirs['hold']/'config.json').read_text(encoding='utf-8'))
    legacy_config=json.loads((dirs['legacy']/'config.json').read_text(encoding='utf-8'))
    if hold_config['opening_cash']!=legacy_config['opening_cash'] or hold_config['window']!=legacy_config['window']:
        raise ValueError('Incompatible capital or window')
    cases=json.loads((dirs['legacy']/'result.json').read_text(encoding='utf-8'))['results']
    rows=[];summary=[]
    metrics={'hold':path_report(hold,equity_field='equity_after_initial_withholding',cash_field='cash_after_initial_withholding'),'legacy':{}}
    for case in cases:
        ledger=read_csv(dirs['legacy']/(case['scenario']+'-daily.csv'))
        metrics['legacy'][case['scenario']]=path_report(ledger,equity_field='marked_equity_gross',cash_field='cash_gross')
        if [r['date'] for r in ledger]!=[r['date'] for r in hold] or len(ledger)!=2674:
            raise ValueError('Date alignment failed')
        for a,b in zip(ledger,hold):
            if D(a['close'])!=D(b['close']): raise ValueError('Different valuation price')
            av=D(a['marked_equity_gross']);bv=D(b['equity_after_initial_withholding'])
            rows.append({'scenario':case['scenario'],'date':a['date'],'legacy_account_equity':str(av),
                'hold_account_equity_after_initial_withholding':str(bv),'legacy_minus_hold_cny':str(av-bv)})
        summary.append({'scenario':case['scenario'],'legacy_orders':case['orders'],
            'ending_legacy_equity':rows[-1]['legacy_account_equity'],
            'ending_hold_equity':rows[-1]['hold_account_equity_after_initial_withholding'],
            'ending_difference_cny':rows[-1]['legacy_minus_hold_cny']})
    final=hold[-1]
    # Independent final marked-account equation from acquisition, cash notices and last close.
    payments=json.loads((dirs['hold']/'retained_003pct_min1-distributions.json').read_text(encoding='utf-8'))
    gross=sum(D(p['gross_cash']) for p in payments)
    taxes=json.loads((dirs['hold']/'retained_003pct_min1-initial-tax.json').read_text(encoding='utf-8'))
    tax=sum(D(t['amount']) for t in taxes)
    invested=D(str(fill['price']))*fill['quantity']
    expected=D('1000000')-invested-D(str(fill['commission']))+gross-tax+D(final['close'])*D(final['shares'])
    if abs(expected-D(final['equity_after_initial_withholding']))>D('.000001'):
        raise ValueError('Independent final-account equation failed')
    out=ROOT/'runtime/strategy-validation'/('moutai-account-comparison-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir()
    write_json(out/'path-metrics.json',metrics)
    with (out/'aligned-daily.csv').open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    write_json(out/'result.json',{'runs':RUNS,'summary':summary,'aligned_rows':len(rows),
        'independent_ending_hold_equity_cny':str(expected),'certified_excess_return':None,
        'strategy_approved':False,'initial_hold_investment_fraction':str(invested/D('1000000')),
        'limitations':['Same initial capital, daily dates and marks; first known close sizes 99% budget in board lots, actual entry investment 96%. Dividends remain cash.',
            'Buy-hold includes observed initial withholding only; final tax/fill/slippage scope remains unapproved.',
            'Legacy zero-order result depends on unapproved PE/PB reference conventions.',
            'Differences are experimental account amounts, not proven net alpha or a broad-market benchmark.',
            'Six cases are correlated parameter variants, not six independent validation samples.']})
    text=['# 茅台历史账户对照初稿','',
        '2015-01-05至2025-12-31，2674个归档行情日。六组旧PE/PB实验均未触发买入；没有为产生交易而修改阈值。','',
        '| 项目 | 结果 |','| --- | ---: |','| 各账户初始资金 | 1,000,000元 |',
        '| 六组旧规则期末账户金额 | 1,000,000元 |',f'| 买入持有对照期末账户金额 | {expected:,.2f}元 |',
        f'| 旧规则减买入持有的期末金额差 | {D("1000000")-expected:,.2f}元 |','',
        '对照按首个已知收盘价和99%资金预算计算整手股数，2015-01-06按归档开盘价200元模拟买入4800股，实际股票投入96%，送股后5280股。费用290.88元为显式研究假设，15次分红及初始扣税入账；分红留作现金，期末未卖出。不是分红再投资全收益指数。','',
        '上述金额不是已认证税后收益或超额收益。完整成交约束、最终税务、净资产确认与2025回购口径仍未验收；宽基全收益基准尚缺。六组结果相同并不增加独立样本量。','',
        '对当前项目的含义：旧固定PE/PB规则在这个预选案例中长期不参与，不能据此证明能实现长期正收益。继续建设公司专属估值和其他固定案例，不按这一个已知样本调参。']
    text += ['', '## 买入持有路径风险（研究口径）', '',
             '| 区间 | 账面变动 | 年化账面变动 | 最大回撤 | 平均股票占比 |',
             '| --- | ---: | ---: | ---: | ---: |']
    for label,m in metrics['hold'].items():
        text.append(f"| {label} | {D(m['marked_return']):.2%} | {m['annualized_marked_return_act36525']:.2%} | {D(m['max_drawdown']):.2%} | {D(m['mean_session_stock_fraction']):.2%} |")
    text += ['', '分段继承前一交易日的账户净值与持仓，不在边界重新买入；三个阶段复利勾稽全期。回撤为各区间内含期初锚点的收盘账面回撤。平均股票占比按归档会话等权，未假设分红再投资或现金利息。以上非最终税后可执行业绩，亦不证明选股有效。']
    (out/'comparison.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
    write_json(out/'manifest.json',{'script_sha256':digest(Path(__file__)),
        'metrics_code_sha256':digest(ROOT/'src/value_investment_agent/account_path_metrics.py'),
        'outputs':{p.name:digest(p) for p in out.iterdir() if p.is_file()}})
    print(json.dumps({'output':str(out),'aligned_rows':len(rows),'ending_hold_equity':str(expected),
        'difference':str(D('1000000')-expected),'strategy_approved':False}))

if __name__=='__main__': main()
