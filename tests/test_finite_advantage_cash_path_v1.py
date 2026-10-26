"""TEST_ONLY economic hypotheses; not company facts or approved policies."""
from copy import deepcopy
from decimal import Decimal, getcontext, localcontext
import json

import pytest

from value_investment_agent.domain.valuation.finite_advantage_cash_path_v1 import (
    SCOPE, build_finite_advantage_cash_path,
)


def capital(year, gap='0'):
    return dict(year=year, scope=SCOPE, rationale='TEST_ONLY net maintenance hypothesis, not observed capex',
        funding_treatment='NET_NEEDS_DEDUCTED_HERE_NOT_IN_UPSTREAM_MAPPING',
        maintenance_basis='EXPLICIT_NET_GAP_ASSUMPTION', net_maintenance_gap_cny=gap,
        project_cash_cny='0', maintenance_project_overlap_cny='0',
        operating_wc_increase_cny='0', fund_call_cny='0',
        other_noncash_adjustment_cny='0', net_financing_cny='0')


def distribution(year):
    return dict(year=year, payout_ratio='1', newly_withheld_fraction='0', release_fraction='0',
        reserve_transfer_fraction='0', reserve_policy_rationale='TEST_ONLY continuation assumes no further transfer; not established law',
        capacity_mapping_rationale='TEST_ONLY funds available for owner payout; not parent legal profit')


@pytest.fixture
def inputs():
    return dict(opening_state=dict(scope=SCOPE, currency='CNY', book_equity_cny='1000',
        cash_cny='300', unremitted_assets_cny='0', distribution_capacity_cny='500',
        cash_floor_cny='100', uncalled_fund_commitment_cny='0', selected_project_budget_cny='0',
        ordinary_shares='10'), legacy_profit_rows=[dict(year=i, profit_cny='150') for i in range(1, 6)],
        capital_cash_rows=[capital(i) for i in range(1, 8)],
        distribution_rows=[distribution(i) for i in range(1, 8)],
        fade_policy=dict(cost_of_equity='0.1', fade_years=2, incremental_cash_yield='0'),
        terminal_policy=dict(method='ZERO_GROWTH_KE_RETURN_FULL_PAYOUT',
            rationale='TEST_ONLY finite advantage ends; economic normal-return book continuity',
            equity_pricing_assumption='ECONOMIC_BOOK_PRICING_NOT_LIQUIDATION_FACT',
            distribution_constraint_rationale='TEST_ONLY explicit legally-permitted payout hypothesis, not certification',
            capital_cash_row=capital(8), distribution_row=distribution(8)))


def test_supported_finite_ri_and_ddm(inputs):
    original = deepcopy(inputs)
    precision = getcontext().prec
    result = build_finite_advantage_cash_path(**inputs)
    assert result['status'] == 'CONDITIONAL_RESEARCH_VALUATION'
    assert result['valuation']['usable']
    assert Decimal(result['valuation']['equity_value_cny']) > 1000
    assert abs(Decimal(result['valuation']['ri_ddm_residual_cny'])) < Decimal('1e-40')
    assert [Decimal(row['profit_cny']) for row in result['rows'][-2:]] == [125, 100]
    assert all(Decimal(row['clean_surplus_residual_cny']) == 0 for row in result['rows'])
    assert result['terminal']['terminal_ri_cny'] == '0'
    assert result['action'] == 'no_order' and not result['economic_approval']
    assert not result['formal_eligibility'] and not result['price_admission']
    assert inputs == original and getcontext().prec == precision
    json.dumps(result, allow_nan=False)


def test_missing_terminal_is_not_silent_zero(inputs):
    inputs['terminal_policy'] = None
    result = build_finite_advantage_cash_path(**inputs)
    assert len(result['rows']) == 7
    assert result['terminal']['terminal_ri_cny'] is None
    assert result['valuation']['equity_value_cny'] is None


def test_persistent_conversion_keeps_assets_not_profit_loss(inputs):
    for row in inputs['distribution_rows']:
        row['newly_withheld_fraction'] = '.1'
    result = build_finite_advantage_cash_path(**inputs)
    assert Decimal(result['rows'][0]['profit_cny']) == 150
    assert Decimal(result['rows'][0]['withheld_cny']) == 15
    assert Decimal(result['rows'][0]['closing_unremitted_assets_cny']) == 15
    assert Decimal(result['rows'][0]['closing_cash_cny']) == 285
    assert not result['valuation']['usable']
    assert 'TERMINAL_no_unremitted_assets' in result['blockers']


def test_persistent_conversion_exhausts_cash_not_automatic_dividend_cut(inputs):
    inputs['opening_state']['cash_cny'] = '110'
    for row in inputs['distribution_rows']:
        row['newly_withheld_fraction'] = '.1'
    result = build_finite_advantage_cash_path(**inputs)
    assert len(result['rows']) == 1
    assert result['rows'][0]['closing_cash_cny'] == '95.0'
    assert result['rows'][0]['distribution_cny'] == '150'
    assert 'YEAR_1_CASH_FLOOR' in result['blockers']
    assert result['valuation']['equity_value_cny'] is None


def test_delay_released_once_not_new_profit(inputs):
    inputs['distribution_rows'][0]['newly_withheld_fraction'] = '.1'
    inputs['distribution_rows'][1]['release_fraction'] = '1'
    result = build_finite_advantage_cash_path(**inputs)
    assert result['valuation']['usable']
    assert Decimal(result['rows'][1]['released_cny']) == 15
    assert Decimal(result['rows'][1]['profit_cny']) == 150
    assert Decimal(result['rows'][1]['closing_unremitted_assets_cny']) == 0


def test_net_gap_reduces_cash_not_profit_or_book(inputs):
    inputs['capital_cash_rows'][0]['net_maintenance_gap_cny'] = '5'
    result = build_finite_advantage_cash_path(**inputs)
    row = result['rows'][0]
    assert Decimal(row['profit_cny']) == 150
    assert Decimal(row['closing_cash_cny']) == 295
    assert Decimal(row['closing_book_cny']) == 1000
    assert Decimal(row['residual_net_equity_component_cny']) == 705
    assert result['valuation']['usable']


def test_matched_da_branch_and_project_overlap(inputs):
    row = inputs['capital_cash_rows'][0]
    row.pop('net_maintenance_gap_cny')
    row.update(maintenance_basis='MATCHED_CAPEX_MINUS_DA_ALREADY_EXPENSED_IN_P',
               maintenance_capex_cny='10', matched_da_cny='8', project_cash_cny='4',
               maintenance_project_overlap_cny='2')
    inputs['opening_state']['selected_project_budget_cny'] = '4'
    result = build_finite_advantage_cash_path(**inputs)
    assert Decimal(result['rows'][0]['net_capital_cash_need_cny']) == 4
    assert Decimal(result['rows'][0]['closing_cash_cny']) == 296
    assert result['valuation']['usable']


@pytest.mark.parametrize('change', ['group_scope', 'double_deduct', 'noncash', 'financing', 'missing_wc', 'mixed_branches'])
def test_cash_mapping_refuses_scope_and_missing_or_double_count(inputs, change):
    row = inputs['capital_cash_rows'][0]
    if change == 'group_scope':
        row['scope'] = 'CONSOLIDATED_GROUP_DA'
    elif change == 'double_deduct':
        row['funding_treatment'] = 'ALREADY_DEDUCTED_IN_UPSTREAM'
    elif change == 'noncash':
        row['other_noncash_adjustment_cny'] = '1'
    elif change == 'financing':
        row['net_financing_cny'] = '1'
    elif change == 'missing_wc':
        del row['operating_wc_increase_cny']
    else:
        row['matched_da_cny'] = '10'
    with pytest.raises(ValueError):
        build_finite_advantage_cash_path(**inputs)


@pytest.mark.parametrize('change', ['net_gap', 'withheld', 'reserve', 'unpaid_fund', 'unpaid_project', 'book_pricing'])
def test_terminal_requires_repeatable_continuity_not_only_transition_floor(inputs, change):
    terminal = inputs['terminal_policy']
    if change == 'net_gap':
        terminal['capital_cash_row']['net_maintenance_gap_cny'] = '1'
    elif change == 'withheld':
        terminal['distribution_row']['newly_withheld_fraction'] = '.1'
    elif change == 'reserve':
        terminal['distribution_row']['reserve_transfer_fraction'] = '.1'
    elif change == 'unpaid_fund':
        inputs['opening_state']['uncalled_fund_commitment_cny'] = '10'
    elif change == 'unpaid_project':
        inputs['opening_state']['selected_project_budget_cny'] = '10'
    else:
        terminal['equity_pricing_assumption'] = 'LIQUIDATION_FACT'
    result = build_finite_advantage_cash_path(**inputs)
    assert len(result['rows']) == 7
    assert not result['valuation']['usable']
    assert result['terminal']['terminal_ri_cny'] is None


def test_missing_reserve_policy_not_inferred_from_large_stock(inputs):
    inputs['opening_state']['distribution_capacity_cny'] = '999999999'
    inputs['terminal_policy']['distribution_row']['reserve_policy_rationale'] = ''
    with pytest.raises(ValueError, match='rationale'):
        build_finite_advantage_cash_path(**inputs)


def test_fund_is_asset_not_expense_and_known_budget_paid(inputs):
    inputs['opening_state']['uncalled_fund_commitment_cny'] = '20'
    inputs['capital_cash_rows'][0]['fund_call_cny'] = '20'
    result = build_finite_advantage_cash_path(**inputs)
    assert Decimal(result['rows'][0]['closing_cash_cny']) == 280
    assert Decimal(result['rows'][0]['residual_net_equity_component_cny']) == 720
    assert Decimal(result['rows'][0]['closing_book_cny']) == 1000
    assert result['valuation']['usable']


def test_weak_roe_not_assumed_to_recover(inputs):
    inputs['legacy_profit_rows'][-1]['profit_cny'] = '50'
    result = build_finite_advantage_cash_path(**inputs)
    assert len(result['rows']) == 5
    assert 'NEGATIVE_EXCESS_RETURN_NOT_ASSUMED_TO_RECOVER_TO_KE' in result['blockers']


@pytest.mark.parametrize('bad', [True, 0.1, 'NaN', 'Infinity', None])
def test_invalid_numbers_rejected(inputs, bad):
    inputs['legacy_profit_rows'][0]['profit_cny'] = bad
    with pytest.raises(ValueError):
        build_finite_advantage_cash_path(**inputs)


def test_fade_is_total_roe_not_cash_yield_added_twice(inputs):
    inputs['distribution_rows'][0]['payout_ratio'] = '.5'
    inputs['fade_policy']['incremental_cash_yield'] = '.01'
    result = build_finite_advantage_cash_path(**inputs)
    final = result['rows'][-1]
    assert abs(Decimal(final['profit_cny']) - Decimal(final['opening_book_cny']) * Decimal('.1')) < Decimal('1e-24')
    assert result['valuation']['usable']


@pytest.mark.parametrize('matched_da', [False, True])
def test_terminal_cannot_fund_maintenance_with_perpetual_wc_release(inputs, matched_da):
    row = inputs['terminal_policy']['capital_cash_row']
    if matched_da:
        row.pop('net_maintenance_gap_cny')
        row.update(maintenance_basis='MATCHED_CAPEX_MINUS_DA_ALREADY_EXPENSED_IN_P',
                   maintenance_capex_cny='10', matched_da_cny='5')
    else:
        row['net_maintenance_gap_cny'] = '5'
    row['operating_wc_increase_cny'] = '-5'
    result = build_finite_advantage_cash_path(**inputs)
    assert result['terminal']['checks']['net_maintenance_wc_balanced']
    assert not result['terminal']['checks']['net_maintenance_gap_zero']
    assert not result['terminal']['checks']['no_recurring_wc_release_or_investment']
    assert result['valuation']['equity_value_cny'] is None
    assert result['terminal']['terminal_ri_cny'] is None


def test_explicit_forecast_wc_release_remains_bounded_and_supported(inputs):
    row = inputs['capital_cash_rows'][0]
    row['net_maintenance_gap_cny'] = '5'
    row['operating_wc_increase_cny'] = '-5'
    result = build_finite_advantage_cash_path(**inputs)
    assert result['valuation']['usable']
    assert Decimal(result['rows'][0]['net_capital_cash_need_cny']) == 0
    assert result['terminal']['checks']['net_maintenance_gap_zero']
    assert result['terminal']['checks']['no_recurring_wc_release_or_investment']


@pytest.mark.parametrize('matched_da', [False, True])
def test_capital_precision_independent_of_callers_decimal_context(inputs, matched_da):
    row = inputs['capital_cash_rows'][0]
    if matched_da:
        row.pop('net_maintenance_gap_cny')
        row.update(maintenance_basis='MATCHED_CAPEX_MINUS_DA_ALREADY_EXPENSED_IN_P',
                   maintenance_capex_cny='15.12345678901234567890123456789', matched_da_cny='10')
    else:
        row['net_maintenance_gap_cny'] = '5.12345678901234567890123456789'
    with localcontext() as context:
        context.prec = 28
        expected = build_finite_advantage_cash_path(**inputs)
        assert context.prec == 28
    with localcontext() as context:
        context.prec = 6
        actual = build_finite_advantage_cash_path(**inputs)
        assert context.prec == 6
    assert actual == expected
    assert Decimal(actual['rows'][0]['net_capital_cash_need_cny']) == Decimal('5.12345678901234567890123456789')
    assert actual['valuation']['usable']
