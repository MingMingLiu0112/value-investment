"""TEST_ONLY independent-provider and debt-detail counterexamples."""
from copy import deepcopy
from datetime import datetime,timezone
import pytest
from value_investment_agent.domain.discovery.financial_source_comparison_v1 import compare_observations,debt_details
NOW=datetime(2026,11,2,8,tzinfo=timezone.utc)
PERIOD='2025-12-31'


def p(field='cash',value='100',provider='eastmoney',**kw):
    host='datacenter-web.eastmoney.com' if provider=='eastmoney' else 'quotes.sina.cn'
    unit='CNY' if field in {'cash','short_term_borrowings','long_term_borrowings','bonds_payable','lease_liabilities_noncurrent','current_portion_long_term_debt','long_term_payables_noncurrent'} else 'percent'
    return dict(symbol='600001',field_name=field,value=value,unit=unit,currency='CNY',period_label=PERIOD,
        metadata=dict(statement_scope='consolidated',source_refs=[dict(path='runtime/'+provider+'.json',sha256=('a' if provider=='eastmoney' else 'b')*64,
            source_url='https://'+host+'/api',acquired_at='2026-11-02T07:00:00+00:00')]),**kw)


def check(left,right):
    return compare_observations(left,right,symbol='600001',period=PERIOD,evaluated_at=NOW)


def test_two_providers_match_but_never_grant_admission_or_complete_debt():
    r=check([p()],[p(provider='sina')]);f=r['fields'][0]
    assert f['status']=='MATCHED' and r['matched_count']==1
    assert not r['formal_admission'] and not r['complete_debt_verified']
    assert r['action']=='no_order' and len(f['primary_refs'])==1


def test_conflict_preserved_no_averaging_or_threshold_relaxation():
    r=check([p()],[p(value='100.02',provider='sina')])
    assert r['fields'][0]['status']=='CONFLICT' and r['conflict_count']==1
    assert r['fields'][0]['absolute_difference']=='0.02'


@pytest.mark.parametrize('change',['future','naive','scope','period','unit','currency','nan','hash','bool'])
def test_invalid_source_not_counted(change):
    q=p(provider='sina')
    if change=='future':q['metadata']['source_refs'][0]['acquired_at']='2099-01-01T00:00:00+00:00'
    elif change=='naive':q['metadata']['source_refs'][0]['acquired_at']='2026-11-02T07:00:00'
    elif change=='scope':q['metadata']['statement_scope']='parent'
    elif change=='period':q['period_label']='2024-12-31'
    elif change=='unit':q['unit']='CNY 100M'
    elif change=='currency':q['currency']='USD'
    elif change=='nan':q['value']='NaN'
    elif change=='hash':q['metadata']['source_refs'][0]['sha256']='z'*64
    elif change=='bool':q['value']=True
    assert check([p()],[q])['matched_count']==0


def test_same_provider_mirrors_not_independent():
    q=p();q['metadata']['source_refs'][0]['source_url']='https://emweb.securities.eastmoney.com/other'
    assert check([p()],[q])['fields'][0]['status']=='NOT_COMPARABLE'


def test_missing_and_zero_are_different_and_ambiguous_debt_not_added():
    rows=[p('short_term_borrowings','0'),p('long_term_borrowings','10'),p('lease_liabilities_noncurrent','2'),
          p('current_portion_long_term_debt','80'),p('long_term_payables_noncurrent','90')]
    r=debt_details(rows,symbol='600001',period=PERIOD,evaluated_at=NOW)
    assert r['identified_total']=='12' and not r['complete_debt_verified']
    assert next(x for x in r['components'] if x['field']=='short_term_borrowings')['value']=='0'
    assert next(x for x in r['components'] if x['field']=='bonds_payable')['value'] is None
    assert next(x for x in r['components'] if x['field']=='current_portion_long_term_debt')['status']=='NEEDS_NOTE_CLASSIFICATION'


def test_debt_conflict_not_summed_and_inputs_not_mutated():
    rows=[p('short_term_borrowings','10'),p('short_term_borrowings','20',provider='sina')];before=deepcopy(rows)
    r=debt_details(rows,symbol='600001',period=PERIOD,evaluated_at=NOW)
    assert r['identified_total'] is None
    assert r['components'][0]['status']=='CONFLICT' and rows==before


def test_scope_ratio_alias_cannot_relabel_parent_cash_as_group():
    x=p('cash');x['metadata']['statement_scope']='PROVIDER_SUMMARY_NOT_STATUTORY_VERIFIED'
    assert check([x],[p(provider='sina')])['matched_count']==0


def test_debt_projection_preserves_null_and_absent_and_source_cells():
    from value_investment_agent.domain.discovery.financial_source_comparison_v1 import debt_observations
    ref=p()['metadata']['source_refs'][0]
    points=debt_observations({'600001':dict(raw=dict(CURRENCY='CNY',SHORT_LOAN=0,BOND_PAYABLE=None),source_ref=ref)},period=PERIOD)
    rows={x['field_name']:x for x in points}
    assert rows['short_term_borrowings']['value']=='0'
    assert rows['bonds_payable']['value'] is None and rows['bonds_payable']['metadata']['source_cell_status']=='NULL'
    assert rows['long_term_borrowings']['metadata']['source_cell_status']=='ABSENT'
    assert all(not x['metadata']['complete_debt_verified'] for x in points)


def test_sina_same_table_scale_cancelled_but_no_unit_no_cash_or_cross_table_ratio():
    from value_investment_agent.domain.discovery.financial_source_comparison_v1 import sina_observations
    ref=p(provider='sina')['metadata']['source_refs'][0]
    def table(**raw):return dict(scope='consolidated',currency='CNY',source_ref=ref,rows=[dict(field=k,value=str(v),unit=None) for k,v in raw.items()])
    data=dict(symbols={'600001':dict(period=PERIOD,statements=dict(balance=table(TOTASSET=100,TOTLIAB=20,CURFDS=50),income=table(BIZTOTINCO=200,NETPROFIT=10,BIZINCO=200,BIZCOST=100,PARENETP=8),cashflow=table(MANANETR=12)),comparatives={'2024-12-31':dict(income=table(BIZTOTINCO=100,PARENETP=4))})})
    rows={r['field_name']:r for r in sina_observations(data)}
    assert rows['net_margin']['value']=='5.00' and rows['debt_ratio']['value']=='20.0'
    assert 'revenue_yoy' not in rows and 'net_income_yoy' not in rows
    assert 'cash' not in rows and 'operating_cash_flow_to_net_income' not in rows
    assert rows['gross_margin']['value']=='50.0'
    for t in [*data['symbols']['600001']['statements'].values(),data['symbols']['600001']['comparatives']['2024-12-31']['income']]:
        for r in t['rows']:r['unit']='CNY'
    rows={r['field_name']:r for r in sina_observations(data)}
    assert rows['cash']['value']=='50' and rows['operating_cash_flow_to_net_income']['value']=='120.0'
    assert rows['revenue_yoy']['value']=='100' and rows['net_income_yoy']['value']=='100'


def test_cash_cannot_use_a_ratio_scope():
    q=p();q['metadata']['statement_scope']='explicit_reported_ratio'
    assert check([q],[p(provider='sina')])['matched_count']==0


def test_same_table_different_units_are_rejected_not_cancelled():
    from value_investment_agent.domain.discovery.financial_source_comparison_v1 import sina_observations
    ref=p(provider='sina')['metadata']['source_refs'][0]
    income=dict(scope='consolidated',currency='CNY',source_ref=ref,rows=[
        dict(field='BIZTOTINCO',value='100',unit='万元'),dict(field='NETPROFIT',value='10',unit='元')])
    data=dict(symbols={'600001':dict(period=PERIOD,statements={'income':income},comparatives={})})
    assert not any(r['field_name']=='net_margin' for r in sina_observations(data))
