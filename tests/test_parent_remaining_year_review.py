"""TEST_ONLY input seams with real period, cash and valuation calculations."""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import pytest
from test_direct_owner_cash_compilation_v1 import sample
from value_investment_agent.application.research import parent_remaining_year_review as review
from value_investment_agent.application.research import direct_owner_cash_compilation_v1 as compiler

NOW = datetime(2026, 11, 18, tzinfo=timezone.utc)

@pytest.fixture
def case(tmp_path, monkeypatch):
    spec = sample(monkeypatch)
    compiled = compiler.compile_source_bound_owner_cash(root=tmp_path, spec=spec, now=NOW)
    compiled['evidence']['statements'][0]['cash_flow'].update(
        gross_capex_cny=dict(current='20'), investment_income_cash_cny=dict(current='5'))
    original = dict(symbol=spec['symbol'], compiled=compiled, input_descriptor_sha256='a'*64,
        source_bindings=[])
    ref = dict(path='runtime/candidate.json', sha256='c'*64)
    monkeypatch.setattr(review, '_read', lambda root, binding:
        dict(spec_binding={'path':'runtime/spec.json'},
             result_binding={'path':'runtime/result.json'}) if binding == ref else spec)
    monkeypatch.setattr(review, 'replay_direct_owner_cash_receipt', lambda **kw: deepcopy(original))
    monkeypatch.setattr(review, '_bound', lambda root, ref: None)  # TEST_ONLY old receipt seam
    full = dict(symbol=spec['symbol'], scope=spec['scope'], currency='CNY', classification='FACT',
        period_start='2025-01-01', period_end='2025-12-31', revenue='200', cost='100',
        customer_cash='200', supplier_cash='100', cfo='100', source_refs={'TEST_ONLY':True})
    current = dict(full, period_start='2026-01-01', period_end='2026-09-30', revenue='150',
        cost='75', customer_cash='135', supplier_cash='70', cfo='60')
    comparative = dict(full, period_end='2025-09-30', revenue='140', cost='70',
        customer_cash='140', supplier_cash='70', cfo='70')
    current['source_refs'] = comparative['source_refs'] = [dict(physical_page=1, excerpt='TEST_ONLY')]
    monkeypatch.setattr(review, 'read_parent_direct_cash_research', lambda **kw: {'observed':[full]})
    monkeypatch.setattr(review, 'extract_pages', lambda p: ['TEST_ONLY'])
    monkeypatch.setattr(review, 'build_quarterly_parent_operating_observations',
        lambda *a, **kw: deepcopy([current, comparative]))
    facts = dict(fields={'net_profit':dict(current='60', comparative='55')},
        cash_fields={'cash_capex':dict(current='25', comparative='10'),
            'investment_income_cash_cny':dict(current='3', comparative='2')})
    monkeypatch.setattr(review, 'parse_quarterly_parent_operating_facts', lambda *a, **kw: facts)
    path = tmp_path/'runtime/quarter.pdf'
    path.parent.mkdir(); path.write_bytes(b'TEST_ONLY original source')
    source=dict(path='runtime/quarter.pdf',sha256=sha256(path.read_bytes()).hexdigest(),
        url='https://static.cninfo.com.cn/finalpage/2026-10-30/123.PDF',acquired_at='2026-11-01T00:00:00+00:00')
    return dict(root=tmp_path,receipt_binding=ref,source=source,period_end='2026-09-30',now=NOW)

def test_retained_plan_rejects_actual_capex_conflict(case):
    result=review.review_parent_remaining_year(**case)
    assert all(r['reason']=='REMAINING_REVIEW_ANNUAL_CAPEX_BELOW_REPORTED_9M' for r in result['scenarios'].values())
    assert not result['successor_adopted']

def test_explained_same_quarter_policy_recalculates_actual_owner_model(case):
    result=review.review_parent_remaining_year(**case,capital_policy_mode='REPORTED_9M_PLUS_PRIOR_Q4')
    for row in result['scenarios'].values():
        assert row['status']=='CONDITIONAL_RECALCULATION_NOT_ADOPTED'
        assert row['annual']['full_year']['cfo']['total']=='90'
        assert row['capital_policy_changes']['gross_capex']['full_year']=='35'
        assert row['calculation']['annual_rows'][0]['direct_operating_cash_cny']=='90'
        assert row['calculation']['formal_eligibility'] is False
        assert row['implied_q4_parent_profit']=='20'
    assert result['action']=='no_order' and result['current_price_qualified'] is False

@pytest.mark.parametrize('mutation', ['future','hash','period','path'])
def test_source_contract_rejects_before_recalculation(case,mutation):
    if mutation=='future': case['source']['acquired_at']='2099-01-01T00:00:00+00:00'
    if mutation=='hash': case['source']['sha256']='f'*64
    if mutation=='period': case['period_end']='2027-09-30'
    if mutation=='path': case['source']['path']='runtime/../quarter.pdf'
    with pytest.raises(ValueError): review.review_parent_remaining_year(**case)

def test_negative_prior_q4_capex_is_not_clamped(case, monkeypatch):
    fn=review.parse_quarterly_parent_operating_facts
    facts=deepcopy(fn(None));facts['cash_fields']['cash_capex']['comparative']='21'
    monkeypatch.setattr(review,'parse_quarterly_parent_operating_facts',lambda *a,**kw:facts)
    result=review.review_parent_remaining_year(**case,capital_policy_mode='REPORTED_9M_PLUS_PRIOR_Q4')
    assert all(r['reason']=='REMAINING_REVIEW_NEGATIVE_PRIOR_Q4_CAPITAL_FLOW:gross_capex' for r in result['scenarios'].values())


def test_late_original_binding_change_rejects_entire_review(case, monkeypatch):
    checked = []
    def verify(root, binding):
        checked.append(binding['path'])
        if binding['path'] == 'runtime/result.json':
            raise ValueError('TEST_ONLY_CHANGED_ORIGINAL_RESULT')
    monkeypatch.setattr(review, '_bound', verify)
    with pytest.raises(ValueError, match='CHANGED_ORIGINAL_RESULT'):
        review.review_parent_remaining_year(**case,
            capital_policy_mode='REPORTED_9M_PLUS_PRIOR_Q4')
    assert 'runtime/candidate.json' in checked
    assert 'runtime/spec.json' in checked

def test_real_originals_and_registered_direct_receipt():
    location=os.environ.get('REMAINING_YEAR_REAL_ROOT')
    if not location: pytest.skip('Explicit retained real source root required')
    root=Path(location)
    view=json.loads((root/'.tmp/direct-f2-real-api.json').read_text(encoding='utf-8'))
    result=review.read_registered_remaining_year_review(root=root,receipt_binding=view['receipt_binding'],
        symbol='600887',now=NOW)
    assert all(r['status']=='CONDITIONAL_RECALCULATION_NOT_ADOPTED' for r in result['scenarios'].values())
    assert result['reported_facts']['cash_fields']['cfo']['current']=='39649908007.27'
    assert result['current_price_qualified'] is False
