"""Join authenticated historical inputs without treating disclosure snapshots as fills."""
import csv
import json
from decimal import Decimal
from fractions import Fraction
from datetime import datetime, timezone
from pathlib import Path
from build_moutai_repurchase_timeline import select
from replay_moutai_distributions import digest, write_json

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'runtime/strategy-validation'
INPUTS={
    'shares':('moutai-daily-share-basis-20260909T094243932846Z/daily-share-basis.csv','53a103f1a64563f59d69facc66a1e368f1c1386192ffc602d9606233c90ae55e'),
    'basis':('moutai-daily-value-basis-20260909T093122642929Z/daily-basis.csv','8d56646ef9b8ac28e06380e2df1ddc370de1c2c5ac5053eca33830dad9526ff6'),
    'repurchases':('moutai-repurchase-timeline-20260909T095306550689Z/evidence.json','ecedd2581bcc153837d7ddd499b46d5740355e4fe321bb707a8ed157678bbe0c'),
    'capex':('moutai-historical-capex-20260909T151021561841Z/evidence.json','f048c729cb7185f224ac8b012db46b0fa155dacbb10296f3aa70670e2f6244d8'),
    'da':('moutai-historical-da-20260909T151724111908Z/evidence.json','920a9c7f590b61f7c5aa4f55ee05d09651cd108593a82933fb5fe8524a8998ad'),
    'operating':('moutai-historical-operating-20260909T153641310560Z/evidence.json','fe952be7cdbe0d6c1369462b0141301e77b72847e49f872fc938ceb41c2f896e'),
    'capital':('moutai-historical-capital-20260909T153535637673Z/evidence.json','9e1e49492b4877f47627c6a4575a77abe306d659880536bc213f3198a17923c8'),
    'tax_balances':('moutai-historical-tax-balances-20260909T154641919700Z/evidence.json','4afc117e321304ae5c216ad49c4c067c46a385e2a295836084412410bee45af2'),
    'capital_classification':('moutai-capital-classification-20260909T155347719586Z/evidence.json','955c5afc9e7fd8be89645198a272d601af524334dfb433c1c6e21b78a2d85fe5'),
}


def classification_at(evidence, decision_at, annual_source_id):
    """Carry known presentation constraints; never roll old balances forward."""
    decision = datetime.fromisoformat(decision_at)
    selected = {}
    for key in ('prepayments_2013', 'revenue_standard_transition'):
        item = evidence[key]
        available = datetime.fromisoformat(item['source']['available_at'])
        if available > decision:
            continue
        if key == 'prepayments_2013' and item['source']['source_id'] != annual_source_id:
            continue
        selected[key] = item
    return selected


def main():
    for path,expected in INPUTS.values():
        if digest(BASE/path)!=expected:
            raise ValueError('Historical input hash mismatch')
    def read_rows(key):
        with (BASE/INPUTS[key][0]).open(encoding='utf-8',newline='') as stream:
            rows=list(csv.DictReader(stream))
        if len({r['date'] for r in rows})!=len(rows):
            raise ValueError('Duplicate historical date')
        return rows
    shares=read_rows('shares');basis=read_rows('basis')
    if [r['date'] for r in shares]!=[r['date'] for r in basis]:
        raise ValueError('Historical date alignment mismatch')
    snapshots=json.loads((BASE/INPUTS['repurchases'][0]).read_text(encoding='utf-8'))['snapshots']
    classification=json.loads((BASE/INPUTS['capital_classification'][0]).read_text(encoding='utf-8'))
    for key in ('prepayments_2013', 'revenue_standard_transition'):
        source=classification[key]['source']
        path=(ROOT/source['source_path']).resolve()
        if not path.is_relative_to(ROOT) or digest(path)!=source['source_sha256']:
            raise ValueError('Classification original changed')
    capex_rows=json.loads((BASE/INPUTS['capex'][0]).read_text(encoding='utf-8'))['rows']
    capex={r['source_id']:r for r in capex_rows}
    da_rows=json.loads((BASE/INPUTS['da'][0]).read_text(encoding='utf-8'))['rows']
    da={r['source_id']:r for r in da_rows}
    operating_rows=json.loads((BASE/INPUTS['operating'][0]).read_text(encoding='utf-8'))['rows']
    operating={r['source_id']:r for r in operating_rows}
    capital_rows=json.loads((BASE/INPUTS['capital'][0]).read_text(encoding='utf-8'))['rows']
    capital={r['source_id']:r for r in capital_rows}
    tax_rows=json.loads((BASE/INPUTS['tax_balances'][0]).read_text(encoding='utf-8'))['rows']
    taxes={r['source_id']:r for r in tax_rows}
    if set(taxes)!=set(capex) or len(taxes)!=len(tax_rows):
        raise ValueError('Tax balance vintage coverage differs')
    if set(capital)!=set(capex) or len(capital)!=len(capital_rows):
        raise ValueError('Capital balance vintage coverage differs')
    if set(operating)!=set(capex) or len(operating)!=len(operating_rows):
        raise ValueError('Operating vintage coverage differs')
    if set(da)!=set(capex) or len(da)!=len(da_rows):
        raise ValueError('Noncash adjustment vintage coverage differs')
    if len(capex)!=12 or len(capex)!=len(capex_rows):
        raise ValueError('Capital spending vintage coverage changed')
    for row in capex_rows:
        source=(ROOT/row['source_path']).resolve()
        if not source.is_relative_to(ROOT) or digest(source)!=row['source_sha256']:
            raise ValueError('Capital spending original changed')
        if da[row['source_id']]['source_sha256']!=row['source_sha256']:
            raise ValueError('D&A and spending use different originals')
        if operating[row['source_id']]['source_sha256']!=row['source_sha256']:
            raise ValueError('Operating and spending use different originals')
        if capital[row['source_id']]['source_sha256']!=row['source_sha256']:
            raise ValueError('Capital balances and spending use different originals')
        if taxes[row['source_id']]['source_sha256']!=row['source_sha256']:
            raise ValueError('Tax balances and spending use different originals')
    result=[]
    for share,base in zip(shares,basis):
        if share['source_id']!=base['source_id'] or share['period']!=base['report_period']:
            raise ValueError('Annual vintage mismatch')
        decision=base['date']+'T15:00:00+08:00'
        classified=classification_at(classification, decision, base['source_id'])
        spending=capex.get(base['source_id'])
        noncash=da.get(base['source_id'])
        op=operating.get(base['source_id'])
        balance=capital.get(base['source_id'])
        tax=taxes.get(base['source_id'])
        if (not spending or spending['period']!=base['report_period']
                or spending['available_at']!=base['available_at']
                or datetime.fromisoformat(spending['available_at'])>datetime.fromisoformat(decision)
                or spending['status']!='original_row_decoder_and_header_checked'):
            raise ValueError('Capital spending report/availability mismatch')
        if (not noncash or noncash['period_label']!=base['report_period']
                or noncash['available_at']!=base['available_at']
                or noncash['status']!='original_row_decoder_header_and_cfo_scope_checked'):
            raise ValueError('D&A report/availability mismatch')
        if (not op or op['period_label']!=base['report_period'] or op['available_at']!=base['available_at']
                or op['missing_required'] or not op['current_column_unit_checked']):
            raise ValueError('Operating report/availability mismatch')
        if (not balance or balance['period_label']!=base['report_period'] or balance['available_at']!=base['available_at']
                or not balance['current_column_checked'] or not balance['unit_cny_checked']):
            raise ValueError('Capital balance report/availability mismatch')
        if (not tax or tax['period_label']!=base['report_period'] or tax['available_at']!=base['available_at']
                or tax['status']!='original_tax_note_and_balance_reconciled'):
            raise ValueError('Tax balance report/availability mismatch')
        if Decimal(tax['corporate_income_tax_payable_cny'])+Decimal(tax['other_taxes_payable_cny'])!=Decimal(balance['facts']['taxes_payable']['value_cny']):
            raise ValueError('Income and other tax balances do not sum to reported total')
        net_spending=Decimal(spending['value_cny'])-Decimal(noncash['da_excluding_rou_cny'])
        if Fraction(net_spending)!=Fraction(spending['value_cny'])-Fraction(noncash['da_excluding_rou_cny']):
            raise ValueError('Independent net-spending arithmetic mismatch')
        chosen={program:select(snapshots,program,decision) for program in ('2024-09-21','2025-11-06')}
        if chosen['2025-11-06'] is not None:
            raise ValueError('Second-program post-window information leaked into backtest')
        known=chosen['2024-09-21']
        blockers=['historical_valuation_not_approved','execution_and_benchmark_not_complete']
        if int(base['post_report_distributions']):
            blockers.append('dividend_equity_recognition_bridge_missing')
        if base['date']>='2025-01-02':
            blockers.append('actual_outstanding_share_and_treasury_basis_not_complete')
        result.append({'date':base['date'],'decision_at':decision,'close':base['close'],
            'annual_source_id':base['source_id'],'annual_available_at':base['available_at'],
            'report_period':base['report_period'],
            'bonus_adjusted_share_basis':share['shares_on_reviewed_bonus_basis'],
            'annual_profit_per_bonus_adjusted_share':share['annual_profit_per_rebased_share'],
            'annual_consolidated_cash_capex_cny':spending['value_cny'],
            'capex_original_page':spending['candidates'][0]['page'],
            'capex_source_sha256':spending['source_sha256'],
            'capex_scope':'consolidated_cash_purchases_not_industrial_maintenance_or_fcff',
            'annual_da_excluding_rou_cny':noncash['da_excluding_rou_cny'],
            'da_original_page':noncash['selected']['page'],
            'annual_rou_amortization_cny':noncash['selected']['values'].get('rou_amortization',{}).get('value'),
            'annual_cash_capex_less_da_excluding_rou_cny':str(net_spending),
            'net_spending_scope':'consolidated_cash_capex_minus_nonlease_DA_not_FCFF;negative_values_retained;missing_ROU_is_unknown',
            'annual_operating_lines_cny':{k:(v['value'] if v else None) for k,v in op['facts'].items()},
            'annual_operating_subtotal_cny':op['operating_subtotal_before_financial_and_other_items'],
            'operating_original_pages':op['statement_pages'],
            'research_expense_presentation':op['research_presentation'],
            'operating_subtotal_scope':'consolidated_shared_costs_unallocated_not_approved_industrial_EBIT',
            'annual_capital_balance_lines_cny':{k:v['value_cny'] for k,v in balance['facts'].items()},
            'capital_balance_original_pages':balance['statement_pages'],
            'capital_balance_scope':'consolidated_unclassified;blank_current_not_previous_value;not_approved_operating_NWC',
            'approved_operating_nwc_cny':None,
            'known_capital_classification_evidence':classified,
            'capital_classification_rule':'project_prepaids_not_automatically_operating;presentation_reclassification_not_cashflow;unclassified_remainder_not_zero',
            'annual_corporate_income_tax_payable_cny':tax['corporate_income_tax_payable_cny'],
            'annual_other_taxes_payable_cny':tax['other_taxes_payable_cny'],
            'tax_balance_original_pages':tax['selected']['physical_page_window'],
            'tax_scope':'closing_consolidated_balance_not_cash_tax;prepaid_income_tax_and_finance_allocation_pending',
            'distributions_since_report':base['events'],
            'latest_disclosed_repurchase_source':known['source_id'] if known else None,
            'repurchase_statistical_cutoff':known['statistical_cutoff'] if known else None,
            'repurchase_available_at':known['available_at'] if known else None,
            'latest_disclosed_repurchase_shares':known['cumulative_shares'] if known else None,
            'latest_disclosed_repurchase_cash_excluding_fees':known['cumulative_cash_excluding_fees'] if known else None,
            'trade_value':None,'trade_approved':False,'blockers':blockers})
    out=BASE/('moutai-daily-research-inputs-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(exist_ok=False)
    write_json(out/'daily-inputs.json',result)
    write_json(out/'result.json',{'rows':len(result),'first_date':result[0]['date'],'last_date':result[-1]['date'],
        'days_with_disclosed_repurchase_snapshot':sum(r['latest_disclosed_repurchase_source'] is not None for r in result),
        'days_with_original_vintage_cash_capex':sum(r['annual_consolidated_cash_capex_cny'] is not None for r in result),
        'days_with_original_vintage_da':sum(r['annual_da_excluding_rou_cny'] is not None for r in result),
        'days_with_original_vintage_operating_subtotal':sum(r['annual_operating_subtotal_cny'] is not None for r in result),
        'days_with_project_prepayment_constraint':sum('prepayments_2013' in r['known_capital_classification_evidence'] for r in result),
        'days_with_disclosed_reclassification_constraint':sum('revenue_standard_transition' in r['known_capital_classification_evidence'] for r in result),
        'source_bindings':INPUTS,'second_program_future_information_excluded':True,
        'scope':'unified research inputs; not executable valuations or actual company daily fills'})
    write_json(out/'manifest.json',{'script_sha256':digest(Path(__file__)),
        'selector_script_sha256':digest(ROOT/'scripts/build_moutai_repurchase_timeline.py'),
        'outputs':{p.name:digest(p) for p in out.iterdir() if p.is_file()}})
    print(json.dumps({'output':str(out),'rows':len(result),'repurchase_snapshot_days':sum(r['latest_disclosed_repurchase_source'] is not None for r in result)}))


if __name__=='__main__':
    main()
