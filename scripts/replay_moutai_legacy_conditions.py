"""Run frozen legacy condition scenarios; zero trades do not approve valuation."""
import csv
import json
from datetime import datetime, timezone
from decimal import Decimal as D
from pathlib import Path
import backtrader as bt
import pandas as pd
from replay_moutai_distributions import load_inputs, digest, write_json, EntitlementReplay
from value_investment_agent.share_action_broker import ShareActionResearchBroker
from value_investment_agent.research_commission import DatedResearchCommission

ROOT=Path(__file__).resolve().parents[1]
INPUT=ROOT/'runtime/strategy-validation/moutai-legacy-signal-sensitivity-20260909T112051809228Z/daily-conditions.csv'
EXPECTED='8f92cdda20575deecba6cf63de5e2d83a93ff814cf42421bf4836e9cc342bf50'

class LegacyConditions(EntitlementReplay):
    params=(('conditions',None),('basis',None),('threshold',None))

    def __init__(self):
        super().__init__()
        self.initialized=True
        self.orders=[]; self.decisions=[]

    def next(self):
        day=self.data.datetime.date(0).isoformat()
        row=self.p.conditions[day]
        value=D(row['reference_'+self.p.basis]); price=D(str(self.data.close[0]))
        if price!=D(row['price']):
            raise ValueError('Signal and execution price clocks differ')
        condition='entry_condition' if price<=value*(1-D(self.p.threshold)/100) else (
            'exit_condition_if_held' if price>value else 'neither')
        if condition!=row['condition_'+self.p.basis]:
            raise ValueError('Independent in-engine condition differs')
        action='no_order'
        if condition=='entry_condition' and not self.position:
            self.buy(size=100); action='buy_100_next_bar'
        elif condition=='exit_condition_if_held' and self.position:
            self.close(); action='close_next_bar'
        self.decisions.append({'date':day,'reference':str(value),'price':str(price),
            'condition':condition,'action':action,'annual_source_id':row['annual_source_id'],
            'valuation_approved':False})
        super().next()

    def notify_order(self,order):
        self.orders.append({'date':self.data.datetime.date(0).isoformat(),'status':order.getstatusname(),
            'size':order.executed.size,'price':order.executed.price,'fee':order.executed.comm})

def main():
    if digest(INPUT)!=EXPECTED:
        raise ValueError('Frozen conditions changed')
    bars,events,annual,refs=load_inputs(ROOT)
    with INPUT.open(encoding='utf-8',newline='') as stream:
        conditions=list(csv.DictReader(stream))
    frame=pd.DataFrame(bars).set_index('date');frame.index=pd.to_datetime(frame.index)
    for field in ('open','high','low','close'): frame[field]=frame[field].astype(float)
    out=ROOT/'runtime/strategy-validation'/('moutai-legacy-condition-replay-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir()
    write_json(out/'config.json',{'registered_at':datetime.now(timezone.utc).isoformat(),'thresholds':[20,30,40],
        'bases':['unadjusted','exdate_cash_scenario'],'opening_cash':'1000000','opening_shares':0,
        'entry_size_assumption':100,'cash_interest_assumption':'0','window':['2015-01-01','2025-12-31'],
        'purpose':'Evaluate frozen experimental conditions, preserving zero-transaction results.',
        'nonzero_trade_scope':'Must complete tax/fill constraints before economic acceptance.'})
    results=[]
    for threshold in (20,30,40):
        selected={r['date']:r for r in conditions if int(r['threshold_pct'])==threshold}
        if list(selected)!=[r['date'] for r in bars]: raise ValueError('Incomplete/duplicate date coverage')
        for basis in ('unadjusted','exdate_cash_scenario'):
            engine=bt.Cerebro(stdstats=False);broker=ShareActionResearchBroker();engine.setbroker(broker)
            broker.setcash(1000000);broker.set_coc(False);broker.set_coo(False)
            feed=bt.feeds.PandasData(dataname=frame,volume=None,openinterest=None);engine.adddata(feed,name='600519')
            broker.addcommissioninfo(DatedResearchCommission(feed,'SSE',D('.0003'),D('5'),'legacy-condition-diagnostic',
                legacy_face_value_per_share=D('1'),legacy_broker_rate=D('.0003'),legacy_broker_minimum=D('1'),
                legacy_basis_ref='config.json: analyst fee assumption, not verified invoice'),name='600519')
            engine.addstrategy(LegacyConditions,events=events,annual=annual,opening_shares=0,
                conditions=selected,basis=basis,threshold=threshold)
            strategy=engine.run(runonce=False)[0]
            if len(strategy.rows)!=len(bars) or len(strategy.decisions)!=len(bars):
                raise ValueError('Engine skipped dates')
            # This frozen input has no entries. An unexpected order needs a wider tax/fill audit.
            if strategy.orders or any(r['action']!='no_order' for r in strategy.decisions):
                raise ValueError('Unexpected trades: complete nonzero trade tax/fill audit before publication')
            for row in strategy.rows:
                if row['shares']!=0 or row['cash_gross']!=1000000 or row['marked_equity_gross']!=1000000:
                    raise ValueError('Independent no-trade cash/position ledger mismatch')
            segments=[]
            for start,end in ((2015,2019),(2020,2022),(2023,2025)):
                rows=[r for r in strategy.rows if start<=int(r['date'][:4])<=end]
                segments.append({'segment':f'{start}-{end}','rows':len(rows),'first':rows[0]['date'],
                    'last':rows[-1]['date'],'orders':0,'cash_only_pnl_cny':'0','cash_exposure':'100%'})
            name=f'{threshold}-{basis}'
            with (out/(name+'-daily.csv')).open('w',encoding='utf-8',newline='') as stream:
                writer=csv.DictWriter(stream,fieldnames=list(strategy.rows[0]));writer.writeheader();writer.writerows(strategy.rows)
            write_json(out/(name+'-decisions.json'),strategy.decisions)
            write_json(out/(name+'-orders.json'),strategy.orders)
            results.append({'scenario':name,'rows':len(strategy.rows),'orders':0,'trades':0,
                'ending_cash_cny':'1000000','ending_shares':0,'segments':segments,
                'hypothetical_cash_only_return':'0','strategy_approved':False})
    write_json(out/'result.json',{'results':results,'strategy_backtest_complete':False,
        'interpretation':'Six frozen reference assumptions generated no buy conditions and no orders; engine processed every archived date.',
        'limitations':['These PE/PB reference conventions are unapproved and not v2 DCF.',
            'Zero cash return assumes no cash interest; it is not proof of capital preservation or superiority.',
            'Zero trades cannot validate execution constraints, dividend taxes under turnover or profitability.',
            'Broad-market total-return benchmark, historical treasury shares and dividend recognition remain incomplete.']})
    write_json(out/'input-references.json',refs+[{'path':str(INPUT.relative_to(ROOT)),'sha256':EXPECTED}])
    write_json(out/'manifest.json',{'script_sha256':digest(Path(__file__)),
        'outputs':{p.name:digest(p) for p in out.iterdir() if p.is_file()}})
    print(json.dumps({'output':str(out),'scenarios':len(results),'rows_per_scenario':len(bars),'orders_each':0,
        'segments':results[0]['segments']}))

if __name__=='__main__': main()
