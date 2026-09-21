"""Explicit early-SSE fee experiments, not evidence of actual broker charges."""
from datetime import date
from decimal import Decimal as D
from types import SimpleNamespace
import pytest
from value_investment_agent.research_commission import DatedResearchCommission

def make(day, **overrides):
    options=dict(price_feed=SimpleNamespace(datetime=SimpleNamespace(date=lambda _:day)),
        exchange='SSE',commission_rate=D('.0003'),minimum_commission=D('5'),
        scenario_id='test-legacy-explicit',legacy_face_value_per_share=D('1'),
        legacy_broker_rate=D('.0003'),legacy_broker_minimum=D('0'),
        legacy_basis_ref='synthetic-face-value-and-broker-fee-assumption-not-source-proof')
    options.update(overrides)
    return DatedResearchCommission(**options)

def test_legacy_fee_uses_face_value_not_market_price_and_keeps_unverified_status():
    result=make(date(2015,7,31)).fee_breakdown(100,10)
    assert result['transfer_basis_cny']==D('100')
    assert result['csdc_transfer_unrounded_cny']==D('.03')
    assert result['legacy_broker_retained_assumption_cny']==D('.03')
    assert result['total_unrounded_cny']==D('5.06')
    assert result['full_cost_verified'] is False
    assert result['legacy_basis_ref'].startswith('synthetic')

def test_policy_boundary_disables_legacy_retained_fee_even_with_parameters():
    result=make(date(2015,8,3),legacy_broker_minimum=D('10')).fee_breakdown(100,10)
    assert result['total_unrounded_cny']==D('5.02')
    assert result['legacy_broker_retained_assumption_cny']==0
    assert result['legacy_assumptions_applied'] is False

def test_retained_minimum_and_sell_tax_are_separate():
    result=make(date(2015,7,31),legacy_broker_minimum=D('1')).fee_breakdown(-100,10)
    assert result['stamp_duty_unrounded_cny']==D('1')
    assert result['total_unrounded_cny']==D('7.03')

@pytest.mark.parametrize('options',[
    {'legacy_face_value_per_share':None}, {'legacy_face_value_per_share':D('0')},
    {'legacy_broker_rate':D('NaN')},{'legacy_broker_minimum':D('-1')},
    {'legacy_basis_ref':''},{'exchange':'SZSE'},
])
def test_partial_or_invalid_legacy_assumptions_rejected(options):
    with pytest.raises(ValueError):
        make(date(2015,7,31),**options)
