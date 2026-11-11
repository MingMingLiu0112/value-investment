"""TEST_ONLY allocation cases; no issuer or strategy approval."""
from copy import deepcopy
from decimal import Decimal as D

from test_product_continuation_cash_path_v1 import inputs
from value_investment_agent.domain.valuation.cash_constrained_product_path_v2 import build_cash_constrained_product_path
from value_investment_agent.domain.valuation.product_continuation_cash_path_v1 import build_product_continuation_cash_path

POLICY = dict(schema_version='cash-constrained-product-path-v2',
    rationale='TEST_ONLY dividends cannot use required operating cash or unavailable capacity',
    capacity_scope='CONDITIONAL_OWNER_EQUIVALENT_NOT_LEGAL_PARENT_CAPACITY')


def run(inputs):
    return build_cash_constrained_product_path(allocation_policy=POLICY, **inputs)


def test_unconstrained_path_preserves_existing_arithmetic(inputs):
    prior = deepcopy(inputs)
    old = build_product_continuation_cash_path(**inputs)
    new = run(inputs)
    assert new['valuation'] == old['valuation']
    assert all(row['actual_payout_ratio'] == '0.9' for row in new['cash_rows'])
    assert inputs == prior


def test_cash_shortfall_reduces_distribution_without_inventing_financing(inputs):
    inputs['opening_state']['cash_floor_cny'] = '2990'
    inputs['capital_cash_rows'][0]['net_maintenance_gap_cny'] = '200'
    old = build_product_continuation_cash_path(**inputs)
    assert not old['valuation']['usable']
    new = run(inputs)
    assert new['valuation']['usable']
    first = new['cash_rows'][0]
    assert D(first['distribution_cny']) < D(first['requested_distribution_cny'])
    assert first['distribution_limited_by'] == ['CASH_FLOOR']
    assert D(first['closing_cash_cny']) >= 2990
    assert first['capital_cash_input']['net_financing_cny'] == '0'
    assert abs(D(new['valuation']['ri_ddm_residual_cny'])) < D('1e-24')


def test_capacity_is_distinct_from_cash_and_reserve_is_not_cash_expense(inputs):
    inputs['opening_state']['distribution_capacity_cny'] = '0'
    inputs['distribution_rows'][0]['reserve_transfer_fraction'] = '.5'
    new = run(inputs)
    row = new['cash_rows'][0]
    assert row['distribution_limited_by'] == ['DISTRIBUTION_CAPACITY_PROXY']
    assert D(row['distribution_cny']) == D(row['profit_cny']) * D('.5')
    assert D(row['closing_cash_cny']) == D(row['opening_cash_cny']) + D(row['upstream_funds_cny']) - D(row['distribution_cny'])


def test_even_zero_dividend_cannot_hide_operating_cash_failure(inputs):
    inputs['capital_cash_rows'][0]['net_maintenance_gap_cny'] = '10000'
    result = run(inputs)
    assert not result['valuation']['usable']
    assert 'YEAR_1_CASH_FLOOR' in result['blockers']
    assert D(result['cash_rows'][0]['distribution_cny']) == 0


def test_unpaid_commitment_cannot_be_hidden_in_terminal(inputs):
    inputs['opening_state']['uncalled_fund_commitment_cny'] = '100'
    result = run(inputs)
    assert not result['valuation']['usable']
    assert 'TERMINAL_no_unpaid_selected_commitments' in result['blockers']
    assert result['cash_rows'][-1]['closing_uncalled_fund_commitment_cny'] == '100'


def test_recurring_terminal_reinvestment_is_not_silently_distributed(inputs):
    inputs['terminal_policy']['capital_cash_row']['net_maintenance_gap_cny'] = '1'
    result = run(inputs)
    assert not result['valuation']['usable']
    assert 'TERMINAL_net_maintenance_gap_zero' in result['blockers']
    assert not result['formal_eligibility'] and result['action'] == 'no_order'
