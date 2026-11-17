"""TEST_ONLY annual cash adapter; synthetic hypotheses, no real-source acceptance."""
from copy import deepcopy
from datetime import date
from decimal import Decimal as D

import pytest

from value_investment_agent.domain.valuation import operating_profit_cash_path_v1 as mod
from value_investment_agent.domain.valuation import joint_capital_cash_path_v4 as v4
from value_investment_agent.valuation_models.residual_income import QualityCompounderFacts
from value_investment_agent.valuation_models.residual_income_path_v4 import scenario_calculation


@pytest.fixture
def inputs():
    cash = dict(target_payout_ratio='1', accessible_profit_ratio='1', reserve_ratio='0',
                net_maintenance_cash_cny='0', operating_wc_cash_cny='0', commitment_cash_cny='0')
    opening = dict(as_of='2026-12-31', scope=v4.SCOPE, currency='CNY', book_equity_cny='100',
        cash_cny='20', unremitted_cny='0', distribution_capacity_cny='100',
        operating_capital_cny='80', productive_capital_cny='0', cash_floor_cny='10', ordinary_shares='10')
    annual = [dict(year=i, period_start=f'{2026+i}-01-01', period_end=f'{2026+i}-12-31',
        scope='consolidated', currency='CNY', group_pbt_cny='25',
        tax_assumption=dict(basis='effective_rate', value='0.2'), signed_nci_cny='0',
        cash_policy=dict(cash, scope=v4.SCOPE, currency='CNY')) for i in range(1, 11)]
    terminal = dict(cash, profit_scale='1', rationale='TEST_ONLY explicit constant legacy earnings',
        terminal_mechanism='recursive_capital_use_and_owner_distribution_v2', terminal_start_year=11,
        first_distribution_timing='end_of_terminal_year_1', legacy_profit_dynamics='constant_after_profit_scale_transition',
        commitment_occurrences=0, restricted_cash_release_cny='0', restricted_cash_release_year=None,
        convergence_tolerance_cny='0.01', max_tail_years=1000)
    return dict(opening_state=opening, annual_rows=annual,
        capital_policy=dict(operating_allocation='0', new_operating_return='0', new_liquidity_return='0'),
        terminal_policy=terminal, cost_of_equity='0.1', profit_basis=mod.PROFIT_BASIS)


def test_full_annual_cash_and_existing_v4_valuation(inputs, monkeypatch):
    before = deepcopy(inputs)
    calls = []
    real_step = v4._step
    def traced_step(**kwargs):
        calls.append(kwargs['year'])
        return real_step(**kwargs)
    monkeypatch.setattr(v4, '_step', traced_step)
    result = mod.compile_operating_profit_cash_path(**inputs)
    assert inputs == before and calls[:10] == list(range(1, 11)) and 11 in calls
    assert result['action'] == 'no_order' and not result['formal_eligibility']
    assert result['funding_status'] == 'FUNDED' and len(result['rows']) == 10
    for row in result['rows']:
        assert row['profit'] == row['distribution'] == D('20')
        assert row['forecast_roe'] == D('.2') and row['retention'] == 0
        assert row['clean_surplus_residual'] == row['capital_identity_residual'] == 0
    facts = QualityCompounderFacts(symbol='123456', as_of=date(2026, 12, 31), verified=False,
        confidence='TEST_ONLY', evidence_refs=[], blockers=[],
        operating_inputs=dict(start_book_equity=D('100'), ordinary_shares=D('10')))
    calculation = scenario_calculation(facts, result['typed_scenario'])
    assert abs(D(calculation['conditional_equity_value_cny']) - D('200')) < D('1e-24')
    assert abs(D(calculation['per_share_value']) - D('20')) < D('1e-24')
    assert abs(D(calculation['dividend_crosscheck_difference_cny'])) < D('1e-24')
    assert result['terminal_valuation']['equity_value'] == D('200')
    assert result['terminal_economic_contract'].opening_book == result['rows'][-1]['closing_book']


def test_signed_nci_and_explicit_tax_amount_are_not_historical_ratios(inputs):
    inputs['annual_rows'][0].update(signed_nci_cny='-2', tax_assumption=dict(basis='amount_cny', value='5'))
    result = mod.compile_operating_profit_cash_path(**inputs)
    assert result['rows'][0]['legacy_parent_profit'] == D('22')
    assert result['rows'][1]['legacy_parent_profit'] == D('20')
    assert result['earnings_bridge']['rows'][0]['bridge_residual_cny'] == '0'


def test_cash_access_and_capacity_constraints_reuse_step(inputs):
    inputs['opening_state']['distribution_capacity_cny'] = '0'
    inputs['annual_rows'][0]['cash_policy'].update(accessible_profit_ratio='0.5', reserve_ratio='0.8')
    result = mod.compile_operating_profit_cash_path(**inputs)
    row = result['rows'][0]
    assert row['cash_distribution_limit'] == D('20')
    assert row['capacity_distribution_limit'] == row['distribution'] == D('4')
    assert row['closing_unremitted'] == D('10')
    assert row['capital_identity_residual'] == 0


@pytest.mark.parametrize('damage', ['half_year', 'missing_year', 'gap', 'overlap', 'out_of_order',
    'opening_halfyear', 'unit', 'scope', 'cash_scope', 'cash_currency', 'missing_policy',
    'missing_tax', 'missing_nci', 'float', 'capital_identity', 'no_profit_basis',
    'negative_profit', 'cash_shortfall', 'terminal_shortfall', 'terminal_method', 'missing_terminal'])
def test_invalid_or_incomplete_annual_contract_refused(inputs, damage):
    row = inputs['annual_rows'][0]
    if damage == 'half_year': row['period_end'] = '2027-06-30'
    elif damage == 'missing_year': inputs['annual_rows'].pop()
    elif damage == 'gap': inputs['annual_rows'][1]['period_start'] = '2029-01-01'
    elif damage == 'overlap': inputs['annual_rows'][1]['period_start'] = '2027-01-01'
    elif damage == 'out_of_order': row['year'] = 2
    elif damage == 'opening_halfyear': inputs['opening_state']['as_of'] = '2026-06-30'
    elif damage == 'unit': row['currency'] = 'CNY_million'
    elif damage == 'scope': row['scope'] = 'parent'
    elif damage == 'cash_scope': row['cash_policy']['scope'] = 'consolidated'
    elif damage == 'cash_currency': row['cash_policy']['currency'] = 'USD'
    elif damage == 'missing_policy': del row['cash_policy']['reserve_ratio']
    elif damage == 'missing_tax': del row['tax_assumption']
    elif damage == 'missing_nci': del row['signed_nci_cny']
    elif damage == 'float': row['group_pbt_cny'] = 25.0
    elif damage == 'capital_identity': inputs['opening_state']['operating_capital_cny'] = '81'
    elif damage == 'no_profit_basis': inputs['profit_basis'] = 'TOTAL_PROFIT'
    elif damage == 'negative_profit': row['signed_nci_cny'] = '30'
    elif damage == 'cash_shortfall': row['cash_policy']['commitment_cash_cny'] = '1000'
    elif damage == 'terminal_shortfall': inputs['terminal_policy']['net_maintenance_cash_cny'] = '1000'
    elif damage == 'terminal_method': inputs['terminal_policy']['terminal_mechanism'] = 'gordon'
    else: del inputs['terminal_policy']['restricted_cash_release_cny']
    with pytest.raises(ValueError): mod.compile_operating_profit_cash_path(**inputs)


def test_explicit_incremental_capital_returns_and_terminal_continuity(inputs):
    inputs['capital_policy'].update(operating_allocation='0.5', new_operating_return='0.05')
    for row in inputs['annual_rows']: row['cash_policy']['target_payout_ratio'] = '0.5'
    result = mod.compile_operating_profit_cash_path(**inputs)
    assert result['rows'][0]['new_operating_profit'] == 0
    assert result['rows'][1]['new_operating_profit'] == D('.25')
    assert result['rows'][1]['profit'] == D('20.25')
    assert result['terminal_economic_contract'].legacy_profit == D('20')
    assert result['terminal']['profit'] > D('20')
    assert all(row['capital_identity_residual'] == 0 for row in result['rows'])


def rolling_inputs(inputs):
    inputs['opening_state']['as_of'] = '2026-06-30'
    for i, row in enumerate(inputs['annual_rows']):
        row.update(period_start=f'{2026+i}-07-01', period_end=f'{2027+i}-06-30',
                   period_basis='ROLLING_FULL_YEAR', tax_assumption=dict(basis='amount_cny', value='5'))


def test_explicit_july_june_ten_years_including_leap_year(inputs):
    rolling_inputs(inputs)
    original = deepcopy(inputs)
    result = mod.compile_operating_profit_cash_path(**inputs)
    assert inputs == original
    assert result['rows'][0]['period_start'] == '2026-07-01'
    assert result['rows'][-1]['period_end'] == '2036-06-30'
    assert all(row['period_basis'] == 'ROLLING_FULL_YEAR' for row in result['rows'])
    assert (date.fromisoformat(result['rows'][1]['period_end']) - date.fromisoformat(result['rows'][1]['period_start'])).days + 1 == 366
    assert all(row['profit'] == D('20') for row in result['rows'])
    assert result['terminal_valuation']['equity_value'] == D('200')


@pytest.mark.parametrize('damage', ['halfyear', 'gap', 'overlap', 'missing_basis', 'mixed_basis', 'h1_basis', 'opening_mismatch'])
def test_rolling_year_requires_complete_explicit_consistent_periods(inputs, damage):
    rolling_inputs(inputs)
    if damage == 'halfyear': inputs['annual_rows'][0]['period_end'] = '2026-12-31'
    elif damage == 'gap': inputs['annual_rows'][1]['period_start'] = '2027-07-02'
    elif damage == 'overlap': inputs['annual_rows'][1]['period_start'] = '2027-06-01'
    elif damage == 'missing_basis':
        for row in inputs['annual_rows']: del row['period_basis']
    elif damage == 'mixed_basis': inputs['annual_rows'][1]['period_basis'] = 'FY'
    elif damage == 'h1_basis': inputs['annual_rows'][0]['period_basis'] = 'H1'
    else: inputs['opening_state']['as_of'] = '2026-12-31'
    with pytest.raises(ValueError): mod.compile_operating_profit_cash_path(**inputs)
