"""Executed entry and disclosed initial withholding; no final tax/strategy approval."""
import csv
import argparse
from datetime import datetime, timezone
from decimal import Decimal as D
from pathlib import Path
import json
import math
import backtrader as bt
import pandas as pd
from replay_moutai_distributions import load_inputs, EntitlementReplay, verify_accounting, digest, write_json
from value_investment_agent.share_action_broker import ShareActionResearchBroker
from value_investment_agent.research_commission import DatedResearchCommission
from validate_moutai_initial_tax import SOURCE as TAX_SOURCE, EXPECTED as TAX_HASH
from check_moutai_ttm_comparability import texts

ROOT=Path(__file__).resolve().parents[1]
LATER_TAX='runtime/strategy-validation/moutai-later-withholding-20260909T111219421818Z/evidence.json'
LATER_TAX_HASH='71814bb46136de381dd870138023a685efcc7746f02718abec5028cac001d9c8'

class ExecutedEntry(EntitlementReplay):
    params = (('capital_entry', False),)
    def __init__(self):
        super().__init__()
        self.initialized=True  # No assumed opening position; all shares come from fills/actions.
        self.fills=[]
        self.order_states=[]
        self.initial_tax_events=[]
        self.entry_quantity=100
        self.sizing_record=None

    def next(self):
        if len(self)==1:
            if self.p.capital_entry:
                self.entry_quantity=int(D(str(self.broker.getcash()))*D('.99')/D(str(self.data.close[0]))/100)*100
            self.sizing_record={'date':self.data.datetime.date(0).isoformat(),
                'known_close':str(self.data.close[0]),'quantity':self.entry_quantity,
                'cash_before_order':str(self.broker.getcash()),
                'budget_fraction':'.99' if self.p.capital_entry else None,
                'next_open_used_for_sizing':False}
            if self.entry_quantity<=0:
                raise ValueError('Insufficient capital for one board lot')
            self.buy(size=self.entry_quantity)
        super().next()
        day=self.data.datetime.date(0)
        if day.isoformat()=='2015-07-17':
            payments=[p for p in self.cash_events if p['payment_date']==day.isoformat()]
            if len(payments)!=1 or D(payments[0]['cash_per_share'])!=D('4.374'):
                raise ValueError('Disclosed withholding distribution mismatch')
            amount=(D('4.37400')-D('4.15030'))*payments[0]['record_shares']
            self.broker.accrue_tax('2015-initial',amount,day=day,evidence_id=TAX_HASH)
            self.broker.pay_tax('2015-initial-paid','2015-initial',amount,day=day)
            self.initial_tax_events.append({'date':day.isoformat(),'amount':str(amount),
                'record_shares':payments[0]['record_shares'],'source_sha256':TAX_HASH,
                'scope':'disclosed_initial_withholding_only'})
            self.rows[-1]['cash_gross']=self.broker.getcash()
            self.rows[-1]['marked_equity_gross']=self.broker.getvalue()

    def notify_order(self, order):
        self.order_states.append({'date':self.data.datetime.date(0).isoformat(),
                                  'status':order.getstatusname()})
        if order.status==order.Completed:
            self.fills.append({'date':bt.num2date(order.executed.dt).date().isoformat(),
                'quantity':order.executed.size,'price':order.executed.price,
                'commission':order.executed.comm,'order_type':'market_next_bar',
                'fee_breakdown':self.broker.getcommissioninfo(self.data).fee_breakdown(order.executed.size,order.executed.price)})

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--capital-entry',action='store_true')
    args=parser.parse_args()
    prefix='moutai-capital-entry-' if args.capital_entry else 'moutai-executed-entry-'
    out=ROOT/'runtime/strategy-validation'/(prefix+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir()
    configs=[{'id':'retained_003pct_no_min','rate':'0.0003','minimum':'0'},
             {'id':'retained_003pct_min1','rate':'0.0003','minimum':'1'},
             {'id':'retained_01pct_min1','rate':'0.001','minimum':'1'}]
    write_json(out/'config.json',{'registered_at':datetime.now(timezone.utc).isoformat(),
        'window':['2015-01-01','2025-12-31'],'opening_cash':'1000000','opening_shares':0,
        'entry':('First close sizes floor(99% cash / known close / 100) lots; next open market execution may fail for insufficient cash.' if args.capital_entry else 'First archived session close submits 100 shares; next archived open fills.'),
        'capital_entry':args.capital_entry,
        'cash_buffer_basis':'Fixed 1% research execution reserve, not an optimized or guaranteed gap buffer.',
        'commission_rate':'0.0003','minimum_commission':'5','slippage_assumption':'0',
        'legacy_scenarios':configs,'scenario_basis':'Analyst cost experiments, not verified broker schedules or bounds.',
        'face_value_assumption':'1 CNY/share, consistent with 2013 disclosed capital/shares; event continuity not certified.',
        'dividend_tax':'All 15 initial withholding events source-checked for mainland individual unrestricted shares; final tax not approved',
        'strategy_backtest_complete':False})
    try:
        if digest(TAX_SOURCE)!=TAX_HASH:
            raise ValueError('Withholding original changed')
        for page,phrases in {1:['4.37400','4.15030','2015年7月17日'],
                              2:['公司暂按5%的税率','实际每股派发现金红利4.15030元']}.items():
            pair=texts(TAX_SOURCE,page)
            if any(phrase not in text for phrase in phrases for text in pair):
                raise ValueError('Disclosed withholding text mismatch')
        bars,events,annual,references=load_inputs(ROOT)
        if digest(ROOT/LATER_TAX)!=LATER_TAX_HASH:
            raise ValueError('Later withholding evidence changed')
        later=json.loads((ROOT/LATER_TAX).read_text(encoding='utf-8'))
        registry=ROOT/'docs/reviewed-cash-distributions.json'
        if digest(registry)!=later['registry_sha256']:
            raise ValueError('Tax and distribution registry diverged')
        notices={e['record_date']:e for e in later['events']}
        following=[e for e in events if e['record_date']>'2015-09-08']
        if set(notices)!={e['record_date'] for e in following} or len(notices)!=14:
            raise ValueError('Tax coverage incomplete')
        for event in following:
            notice=notices[event['record_date']]
            if (notice['payment_date']!=event['cash_payment_date']
                    or D(notice['cash_per_share'])!=D(event['cash_per_share'])
                    or notice['initial_withholding_per_share_cny']!='0'
                    or digest(ROOT/notice['source_path'])!=notice['source_sha256']):
                raise ValueError('Withholding source/date/amount mismatch')
        references.append({'kind':'later_initial_withholding','path':LATER_TAX,'sha256':LATER_TAX_HASH})
        references.append({'kind':'initial_withholding','path':str(TAX_SOURCE.relative_to(ROOT)),
            'sha256':TAX_HASH,'url':'https://static.cninfo.com.cn/finalpage/2015-07-10/1201268407.PDF'})
        frame=pd.DataFrame(bars).set_index('date')
        frame.index=pd.to_datetime(frame.index)
        for field in ('open','high','low','close'):
            frame[field]=frame[field].astype(float)
        results=[]
        for config in configs:
            engine=bt.Cerebro(stdstats=False)
            broker=ShareActionResearchBroker(); engine.setbroker(broker)
            broker.setcash(1000000); broker.set_coc(False); broker.set_coo(False)
            feed=bt.feeds.PandasData(dataname=frame,volume=None,openinterest=None)
            engine.adddata(feed,name='600519')
            broker.addcommissioninfo(DatedResearchCommission(feed,'SSE',D('.0003'),D('5'),config['id'],
                legacy_face_value_per_share=D('1'),legacy_broker_rate=D(config['rate']),
                legacy_broker_minimum=D(config['minimum']),legacy_basis_ref='config.json: explicit early-SSE assumptions'),name='600519')
            engine.addstrategy(ExecutedEntry,events=events,annual=annual,opening_shares=0,capital_entry=args.capital_entry)
            strategy=engine.run(runonce=False)[0]
            if len(strategy.fills)!=1:
                raise ValueError('Expected exactly one executed acquisition')
            fill=strategy.fills[0]
            quantity=int(D('990000')/D(bars[0]['close'])/100)*100 if args.capital_entry else 100
            if fill['date']!=bars[1]['date'] or fill['quantity']!=quantity or D(str(fill['price']))!=D(bars[1]['open']):
                raise ValueError('Actual acquisition not on next archived open')
            if strategy.rows[0]['shares']!=0 or strategy.rows[0]['cash_gross']!=1000000:
                raise ValueError('Opening inventory or cash fabricated')
            # Independent Decimal entry cost, then reuse the independent daily event ledger.
            turnover=D(bars[1]['open'])*quantity
            fee=max(turnover*D('.0003'),D('5'))+D(quantity)*D('.0003')+max(D(quantity)*D(config['rate']),D(config['minimum']))
            if not math.isclose(float(fee),fill['commission'],rel_tol=0,abs_tol=1e-8):
                raise ValueError('Independent acquisition fee mismatch')
            remaining=D('1000000')-turnover-fee
            known_tax=D('.22370')*quantity
            if len(strategy.initial_tax_events)!=1 or D(strategy.initial_tax_events[0]['amount'])!=known_tax:
                raise ValueError('Independent quantity-scaled disclosed tax mismatch')
            # Independently reverse only the known debit for the existing gross event check.
            restored=[]
            for actual in strategy.rows[1:]:
                record=dict(actual)
                known_debit=known_tax if record['date']>='2015-07-17' else D(0)
                for field in ('cash_gross','marked_equity_gross'):
                    record[field]=float(D(str(record[field]))+known_debit)
                restored.append(record)
            checks=verify_accounting(restored,strategy.cash_events,bars[1:],events,quantity,remaining)
            if self_tax := sum(broker.tax_liabilities.values(),D(0)):
                raise ValueError('Disclosed initial debit did not settle: '+str(self_tax))
            exported=[{({'cash_gross':'cash_after_initial_withholding',
                        'marked_equity_gross':'equity_after_initial_withholding'}.get(k,k)):v
                       for k,v in row.items()} for row in strategy.rows]
            with (out/(config['id']+'-daily.csv')).open('w',encoding='utf-8',newline='') as stream:
                writer=csv.DictWriter(stream,fieldnames=list(exported[0]));writer.writeheader();writer.writerows(exported)
            write_json(out/(config['id']+'-fills.json'),strategy.fills)
            write_json(out/(config['id']+'-distributions.json'),strategy.cash_events)
            write_json(out/(config['id']+'-initial-tax.json'),strategy.initial_tax_events)
            write_json(out/(config['id']+'-sizing.json'),strategy.sizing_record)
            results.append({'scenario':config['id'],'fill':fill,'daily_checks':checks,
                'initial_investment_fraction':str(turnover/D('1000000')),
                'cash_after_acquisition':str(remaining),
                'ending_shares':strategy.rows[-1]['shares'],
                'full_window_rows':len(strategy.rows),'ending_equity_after_initial_withholding':strategy.rows[-1]['marked_equity_gross'],
                'initial_tax_paid_cny':str(known_tax),'initial_withholding_notices_checked':15,
                'final_dividend_tax_approved':False,
                'strategy_backtest_complete':False,'net_benchmark_approved':False})
        write_json(out/'input-references.json',references)
        write_json(out/'result.json',{'results':results,'first_date':bars[0]['date'],'last_date':bars[-1]['date'],
            'purpose':'Executed acquisition, disclosed initial withholding and full-window accounting integration.',
            'limitations':['Not a value-strategy signal ledger; 20/30/40% experiments still pending.',
                'All initial withholding covered only for mainland individual unrestricted account; final liability/bonus tax-lot continuity not approved. No net return or excess return reported.',
                'Limit-up/down, liquidity, official session completeness and slippage have not been certified.',
                ('Capital-sized single-stock buy/hold; dividends retained as cash, not a reinvested total-return index.' if args.capital_entry else 'A fixed 100-share diagnostic position is not a fully invested comparable benchmark.'),
                'No liquidation is assumed at the end; equity is marked with the final archived close.']})
        write_json(out/'manifest.json',{'script_sha256':digest(Path(__file__)),
            'dependencies':{p:digest(ROOT/p) for p in ['scripts/replay_moutai_distributions.py',
                'src/value_investment_agent/research_commission.py','src/value_investment_agent/share_action_broker.py']},
            'outputs':{p.name:digest(p) for p in out.iterdir() if p.is_file()}})
        print(json.dumps({'output':str(out),'scenarios':len(results),'rows_per_scenario':len(bars),
            'first_fill':results[0]['fill'],'strategy_backtest_complete':False},default=str))
    except Exception as exc:
        write_json(out/'failure.json',{'type':type(exc).__name__,'error':str(exc)})
        raise

if __name__=='__main__':
    main()
