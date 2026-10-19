"""CORE capital ceilings share the existing two-sleeve portfolio constraints."""
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal

import pytest

from test_dual_sleeve_risk import synthetic_input
from test_portfolio_risk_assessment import GENERATED_AT
from value_investment_agent.domain.portfolio.dual_sleeve_risk import review_dual_sleeve_risk


def inputs():
    data = synthetic_input()
    source = data['hotspot_request']
    request = {key: source[key] for key in ('symbol', 'entry_price_cny', 'entry_slippage_cny',
        'buy_fee_fraction', 'minimum_buy_fee_cny', 'lot_size', 'max_trade_notional_cny',
        'quote_as_of', 'available_at', 'valid_until', 'liquidity_verified', 'limit_up', 'limit_down')}
    data['hotspot_request'] = None
    return data, request


@pytest.mark.parametrize('cap,quantity', [('0.15', 0), ('0.25', 100)])
def test_core_counts_both_sleeves_for_same_security_cap(cap, quantity):
    data, request = inputs()
    data['shared_budget']['cross_sleeve_single_stock_cap'] = cap
    before = deepcopy(data)
    report = review_dual_sleeve_risk(data, core_request=request, generated_at=GENERATED_AT, allow_synthetic=True)
    review = report['core_quantity_review']
    assert review['review_quantity'] == quantity
    assert review['mechanical_stop_required'] is False
    assert 'stressed_loss_cny' not in review
    assert Decimal(review['cash_required_cny']) + 1000 <= Decimal(cap)*10000
    assert report['position_guidance'] is None and report['trade_eligible'] is False
    assert data == before


@pytest.mark.parametrize('change', ['cash_floor', 'risk_unknown', 'limit', 'illiquid', 'future', 'expired', 'budget'])
def test_core_cannot_bypass_shared_risk_and_execution_vetoes(change):
    data, request = inputs()
    if change == 'cash_floor':
        data['portfolio']['policy']['minimum_cash_cny'] = '9000'
    elif change == 'risk_unknown':
        data['allocations'][1]['committed_risk_cny'] = None
    elif change == 'limit':
        request['limit_up'] = True
    elif change == 'illiquid':
        request['liquidity_verified'] = False
    elif change == 'future':
        request['available_at'] = (GENERATED_AT + timedelta(seconds=1)).isoformat()
    elif change == 'expired':
        request['valid_until'] = (GENERATED_AT - timedelta(seconds=1)).isoformat()
    else:
        request['max_trade_notional_cny'] = '1'
    report = review_dual_sleeve_risk(data, core_request=request, generated_at=GENERATED_AT, allow_synthetic=True)
    assert report['core_quantity_review']['review_quantity'] in (None, 0)


def test_core_tranche_budget_includes_minimum_fee_without_rounding_up():
    data, request = inputs()
    request.update(max_trade_notional_cny='1001', entry_price_cny='10', entry_slippage_cny='0',
        buy_fee_fraction='0', minimum_buy_fee_cny='2')
    result = review_dual_sleeve_risk(data, core_request=request, generated_at=GENERATED_AT, allow_synthetic=True)
    assert result['core_quantity_review']['review_quantity'] == 0
    request['max_trade_notional_cny'] = '1002'
    result = review_dual_sleeve_risk(data, core_request=request, generated_at=GENERATED_AT, allow_synthetic=True)
    assert result['core_quantity_review']['review_quantity'] == 100
    assert result['core_quantity_review']['cash_required_cny'] == '1002'
