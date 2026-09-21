"""Hypothetical disposal tax sensitivity; never posts a fictional market sale."""
from datetime import date, datetime, timezone
from decimal import Decimal as D
from pathlib import Path
import json
from replay_moutai_distributions import load_inputs, digest, write_json
from value_investment_agent.dividend_tax import calculate_dividend_tax

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'runtime/strategy-validation/moutai-executed-entry-20260909T111336220381Z'

def main():
    manifest=json.loads((RUN/'manifest.json').read_text(encoding='utf-8'))
    for name,expected in manifest['outputs'].items():
        path=(RUN/name).resolve()
        if not path.is_relative_to(RUN) or digest(path)!=expected:
            raise ValueError('Actual entry ledger changed')
    bars,events,annual,refs=load_inputs(ROOT)
    fills=json.loads((RUN/'retained_003pct_no_min-fills.json').read_text(encoding='utf-8'))
    if len(fills)!=1 or fills[0]['quantity']!=100 or fills[0]['date']!='2015-01-06':
        raise ValueError('Sensitivity requires the fixed no-sale 100-share acquisition')
    bonus=[e for e in events if e.get('bonus_shares_per_share')]
    if len(bonus)!=1 or D(bonus[0]['bonus_shares_per_share'])!=D('.1'):
        raise ValueError('Corporate action inventory changed')
    initial=json.loads((RUN/'retained_003pct_no_min-initial-tax.json').read_text(encoding='utf-8'))
    if len(initial)!=1 or D(initial[0]['amount'])!=D('22.37'):
        raise ValueError('Initial withholding changed')
    scenarios=[]
    for mode in ('inherit_original_date','new_listing_date'):
        acquired=date.fromisoformat(fills[0]['date'])
        bonus_acquired=acquired if mode=='inherit_original_date' else date.fromisoformat(bonus[0]['bonus_listing_date'])
        rows=[]
        for event in events:
            record=date.fromisoformat(event['record_date'])
            if event is bonus[0]:
                # Explicit scenario inference from issuer's 5% initial withholding.
                incomes=[(acquired,D('22.37')/D('.05'),'initial_withholding_divided_by_disclosed_rate')]
            else:
                incomes=[(acquired,D(event['cash_per_share'])*100,'original_100_shares'),
                         (bonus_acquired,D(event['cash_per_share'])*10,'bonus_10_shares')]
            for lot_date,income,basis in incomes:
                calc=calculate_dividend_tax(acquired=lot_date,record_date=record,
                    disposal_settlement=date(2025,12,31),taxable_income=income,
                    account_type='mainland_individual_unrestricted_sse_szse')
                # Independent rate expectation for these specific multi-year holdings.
                expected=income*D('.05') if record<date(2015,9,8) else D(0)
                if calc.total_tax!=expected:
                    raise ValueError('Independent terminal holding-band check failed')
                rows.append({'record_date':event['record_date'],'assumed_acquired':str(lot_date),
                    'income':str(income),'basis':basis,'final_tax':str(calc.total_tax),
                    'additional_tax':str(calc.additional_tax)})
        total=sum(D(r['final_tax']) for r in rows)
        additional=sum(D(r['additional_tax']) for r in rows)
        if total!=D('22.37') or additional!=0:
            raise ValueError('Unexpected terminal sensitivity; review before reporting')
        scenarios.append({'bonus_date_assumption':mode,'hypothetical_disposal_settlement':'2025-12-31',
            'rows':rows,'final_tax_cny':str(total),'additional_tax_cny':str(additional)})
    out=ROOT/'runtime/strategy-validation'/('moutai-terminal-tax-sensitivity-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir()
    write_json(out/'result.json',{'symbol':'600519','actual_entry_run':str(RUN.relative_to(ROOT)),
        'actual_entry_manifest_sha256':digest(RUN/'manifest.json'),'scenarios':scenarios,
        'interpretation':'Both tested bonus-date conventions produce the same hypothetical terminal tax for this no-sale path.',
        'final_tax_operationally_approved':False,'sale_executed':False,'strategy_backtest_complete':False,
        'limitations':['The two dates are explicit scenarios, not proven Chinese settlement conventions.',
            'The 2015 taxable base is inferred from disclosed initial withholding divided by 5%; not a general stock-dividend rule.',
            'No hypothetical sale is posted to the actual ledger; sale price, selling fees and settlement execution are not invented.',
            'This equality does not apply to earlier sales, partial disposals, reinvestment or value-strategy turnover.',
            'Cash-tax timing before hypothetical disposal is not established by final tax arithmetic.']})
    write_json(out/'manifest.json',{'script_sha256':digest(Path(__file__)),
        'tax_component_sha256':digest(ROOT/'src/value_investment_agent/dividend_tax.py'),
        'result_sha256':digest(out/'result.json')})
    print(json.dumps({'output':str(out),'scenarios':len(scenarios),'additional_tax_each':'0',
        'sale_executed':False,'final_tax_operationally_approved':False}))

if __name__=='__main__':
    main()
