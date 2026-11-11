"""Generic cash constraints, capital accounting and annual RI compatibility."""
from copy import deepcopy
from decimal import Decimal as D, localcontext
from types import SimpleNamespace

import pytest

from value_investment_agent.domain.valuation.joint_capital_cash_path_v2 import (
    SCOPE, compile_joint_capital_cash_path,
)
from value_investment_agent.valuation_models.residual_income_path_v2 import (
    ResidualIncomePathScenarioInputs,
    scenario_calculation,
)


def inputs(archetype='a'):
    historical = dict(scope=SCOPE, currency='CNY', revenue='1000', cost='200',
        surcharges='100', selling='50', admin='50', research='20', pre_tax_profit='600',
        tax='150', parent_profit='405', nonrecurring='5', da='30', opening_cash='100',
        opening_distribution_capacity='200', cash_floor='20')
    ratio, growth = '0.2', '0.01'
    if archetype == 'b':
        historical.update(revenue='2000', cost='1200', surcharges='80', selling='100',
            admin='120', research='100', pre_tax_profit='400', tax='80',
            parent_profit='288', nonrecurring='8', da='60')
        ratio, growth = '0.6', '0.02'
    drivers = dict(operating_allocation='0.3', new_operating_return='0.08',
        new_liquidity_return='0.01', years=[dict(year=year, revenue_growth=growth,
            cost_ratio=ratio, target_payout_ratio='0.8', accessible_profit_ratio='0.9',
            net_maintenance_cash_cny='5', operating_wc_cash_cny='3',
            commitment_cash_cny='40' if year == 1 else '0', reserve_ratio='0.1')
            for year in range(1, 11)])
    terminal = dict(net_maintenance_cash_cny='5', operating_wc_cash_cny='3',
        commitment_cash_cny='2', accessible_profit_ratio='0.9',
        target_payout_ratio='0.8', reserve_ratio='0.1', profit_scale='1',
        rationale='Explicit recurring capital needs, access and reserve hypothesis.')
    return dict(start_book='1000', historical=historical, drivers=drivers, terminal_policy=terminal)


@pytest.mark.parametrize('archetype', ['a', 'b'])
def test_two_distinct_enterprise_inputs_reconcile_and_feed_ri(archetype):
    args = inputs(archetype)
    result = compile_joint_capital_cash_path(**args)
    assert len(result['rows']) == len(result['forecast_roe']) == len(result['forecast_retentions']) == 10
    assert result['action'] == 'no_order'
    for i, row in enumerate(result['rows']):
        assert abs(row['clean_surplus_residual']) < D('1e-40')
        assert abs(row['capital_identity_residual']) < D('1e-40')
        assert row['closing_distribution_capacity'] >= 0
        assert row['closing_cash'] >= D(args['historical']['cash_floor'])
        assert row['distribution'] == min(row['target_distribution'],
            row['cash_distribution_limit'], row['capacity_distribution_limit'])
        assert result['forecast_roe'][i] == row['forecast_roe']
        assert result['forecast_retentions'][i] == row['retention']
        if i:
            previous = result['rows'][i-1]
            assert row['opening_book'] == previous['closing_book']
            assert row['opening_cash'] == previous['closing_cash']
            assert row['opening_unremitted'] == previous['closing_unremitted']
    scenario = ResidualIncomePathScenarioInputs(cost_of_equity=D('0.2'),
        forecast_roes=result['forecast_roe'], forecast_retentions=result['forecast_retentions'],
        terminal_roe=result['terminal_roe'], terminal_growth=result['terminal_growth'])
    facts = SimpleNamespace(operating_inputs={'start_book_equity': D(args['start_book']),
        'ordinary_shares': D('100')}, valuation_timing=None)
    consumed = scenario_calculation(facts, scenario)
    for source, actual in zip(result['rows'], consumed['forecast_years'], strict=True):
        for field, external in [('profit', 'net_income_assumption_cny'),
                ('distribution', 'dividend_assumption_cny'),
                ('closing_book', 'closing_book_equity_cny')]:
            assert abs(source[field] - D(actual[external])) < D('1e-39')
    assert abs(result['terminal_distribution'] - D(consumed['terminal_first_dividend_cny'])) < D('1e-39')


def test_archetypes_produce_different_earnings_and_retention():
    a, b = (compile_joint_capital_cash_path(**inputs(k)) for k in ('a', 'b'))
    assert a['forecast_roe'] != b['forecast_roe']
    assert a['rows'][0]['profit'] != b['rows'][0]['profit']


def test_signed_non_parent_loss_allows_parent_profit_above_group_post_tax():
    args = inputs()
    args['start_book'] = '50000000000'
    args['historical'].update(revenue='118190421114.75', cost='82733294780.325',
        pre_tax_profit='12034018510.64', tax='2231858993.45',
        parent_profit='10123316983.69', nonrecurring='0',
        opening_cash='10000000000', opening_distribution_capacity='20000000000',
        cash_floor='1000000000')
    args['drivers'].update(new_operating_return='0', new_liquidity_return='0')
    for row in args['drivers']['years']:
        row.update(revenue_growth='0', cost_ratio='0.7')
    before = deepcopy(args)
    result = compile_joint_capital_cash_path(**args)
    assert result['historical_non_parent_profit'] == D('-321157466.50')
    assert result['parent_attribution_ratio'] > 1
    with localcontext() as context:
        context.prec = 48
        assert result['parent_attribution_ratio'] == D('10123316983.69') / D('9802159517.19')
        for row in result['rows']:
            assert row['legacy_parent_profit'] > row['pre_tax_profit'] - row['tax']
            assert abs(row['legacy_parent_profit'] - D('10123316983.69')) < D('1e-35')
            assert row['parent_attribution_ratio'] == result['parent_attribution_ratio']
            assert row['historical_non_parent_profit'] == D('-321157466.50')
    for row in [*result['rows'], result['terminal']]:
        assert abs(row['capital_identity_residual']) < D('1e-35')
        assert abs(row['clean_surplus_residual']) < D('1e-35')
    assert result['terminal']['parent_attribution_ratio'] == result['parent_attribution_ratio']
    assert any('not an ordinary-share ownership percentage' in item for item in result['limitations'])
    assert args == before


def test_cash_constraint_reduces_dividend_without_error_or_invented_financing():
    args = inputs()
    args['historical']['opening_cash'] = '20'
    args['drivers']['years'][0].update(accessible_profit_ratio='0.2', target_payout_ratio='1')
    result = compile_joint_capital_cash_path(**args)
    row = result['rows'][0]
    assert 0 < row['distribution'] < row['target_distribution']
    assert row['distribution'] == row['cash_distribution_limit']
    assert row['closing_cash'] == D('20')
    assert row['closing_unremitted'] == row['profit'] * D('0.8')
    assert row['retention'] > 0


def test_reserve_and_capacity_limit_distribution_without_spending_cash():
    args = inputs()
    args['historical'].update(opening_cash='900', opening_distribution_capacity='0')
    args['drivers']['years'][0].update(target_payout_ratio='1', reserve_ratio='0.5')
    row = compile_joint_capital_cash_path(**args)['rows'][0]
    assert row['distribution'] == row['capacity_distribution_limit'] == row['profit'] / 2
    assert row['closing_distribution_capacity'] == 0


def test_terminal_recurring_needs_remain_explicit_and_constrain_distribution():
    args = inputs()
    args['drivers'].update(operating_allocation='0', new_operating_return='0', new_liquidity_return='0')
    args['terminal_policy'].update(net_maintenance_cash_cny='150', operating_wc_cash_cny='100',
        commitment_cash_cny='50', accessible_profit_ratio='0.5', target_payout_ratio='1',
        reserve_ratio='0.2', profit_scale='0.9')
    result = compile_joint_capital_cash_path(**args)
    terminal = result['terminal']
    assert terminal['mandatory_cash'] == D('300')
    assert terminal['profit'] == result['rows'][-1]['profit'] * D('0.9')
    assert terminal['reserve_transfer'] == terminal['profit'] * D('0.2')
    assert result['terminal_distribution'] < terminal['target_distribution']
    with localcontext() as context:
        context.prec = 48
        assert result['terminal_retention'] == (terminal['profit']-terminal['distribution']) / terminal['profit']
        assert result['terminal_growth'] == result['terminal_retention'] * result['terminal_roe']


def test_once_only_commitment_is_not_repeated_or_given_incremental_return():
    args = inputs()
    args['terminal_policy']['commitment_cash_cny'] = '0'
    result = compile_joint_capital_cash_path(**args)
    assert sum(row['commitment_cash_cny'] for row in result['rows']) == 40
    assert result['terminal']['commitment_cash_cny'] == 0
    assert result['rows'][0]['new_operating_profit'] == 0
    with localcontext() as context:
        context.prec = 48
        assert result['rows'][1]['new_operating_profit'] == (
            result['rows'][0]['discretionary_operating_addition'] * D('0.08'))


def test_da_is_not_added_again_and_explicit_wc_release_moves_capital_to_cash():
    args = inputs()
    args['drivers']['years'][0]['operating_wc_cash_cny'] = '-3'
    result = compile_joint_capital_cash_path(**args)
    row = result['rows'][0]
    with localcontext() as context:
        context.prec = 48
        assert row['mandatory_cash'] == 42
        assert row['closing_cash'] == (row['opening_cash'] + row['accessible_profit']
            - row['mandatory_cash'] - row['distribution'] - row['discretionary_operating_addition'])
    args['historical']['da'] = '300'
    assert compile_joint_capital_cash_path(**args)['forecast_roe'] == result['forecast_roe']


def test_unfunded_mandatory_needs_report_shortfall_and_zero_distribution():
    args = inputs()
    args['drivers']['years'][0]['commitment_cash_cny'] = '10000'
    args['drivers']['new_liquidity_return'] = '0'
    result = compile_joint_capital_cash_path(**args)
    assert result['funding_status'] == 'SHORTFALL'
    assert result['rows'][0]['distribution'] == 0
    assert result['rows'][0]['funding_shortfall'] > 0


def test_terminal_growth_above_required_return_is_left_for_consumer_to_reject():
    args = inputs()
    args['terminal_policy'].update(target_payout_ratio='0', profit_scale='2')
    result = compile_joint_capital_cash_path(**args)
    assert result['terminal_growth'] == result['terminal_roe'] > D('0.01')
    with pytest.raises(ValueError):
        ResidualIncomePathScenarioInputs(cost_of_equity=D('0.01'),
            forecast_roes=result['forecast_roe'], forecast_retentions=result['forecast_retentions'],
            terminal_roe=result['terminal_roe'], terminal_growth=result['terminal_growth'])


def test_inputs_are_unchanged_and_local_decimal_context_isolated():
    args = inputs()
    before = deepcopy(args)
    normal = compile_joint_capital_cash_path(**args)
    with localcontext() as context:
        context.prec = 5
        low = compile_joint_capital_cash_path(**args)
    assert normal == low
    assert args == before
    normal['terminal_policy']['rationale'] = 'changed output'
    assert args == before


@pytest.mark.parametrize('fault', [
    'scope', 'currency', 'year', 'year_bool', 'year_string', 'nine_years', 'eleven_years',
    'float', 'int', 'decimal', 'nan', 'infinity', 'whitespace', 'unknown_history',
    'unknown_driver', 'unknown_year', 'unknown_terminal', 'missing_terminal',
    'empty_rationale', 'bad_access', 'bad_cost', 'bad_growth', 'negative_commitment',
    'negative_capacity', 'bad_tax', 'bad_attribution', 'negative_attribution', 'negative_scale',
])
def test_strict_scope_year_numeric_and_future_field_rejection(fault):
    args = inputs()
    h, d, t = args['historical'], args['drivers'], args['terminal_policy']
    if fault == 'scope': h['scope'] = 'consolidated'
    elif fault == 'currency': h['currency'] = 'USD'
    elif fault == 'year': d['years'][0]['year'] = 2
    elif fault == 'year_bool': d['years'][0]['year'] = True
    elif fault == 'year_string': d['years'][0]['year'] = '1'
    elif fault == 'nine_years': d['years'].pop()
    elif fault == 'eleven_years': d['years'].append(deepcopy(d['years'][-1]))
    elif fault in ('float', 'int', 'decimal', 'nan', 'infinity', 'whitespace'):
        h['revenue'] = {'float': 1000.0, 'int': 1000, 'decimal': D('1000'),
            'nan': 'NaN', 'infinity': 'Infinity', 'whitespace': ' 1000'}[fault]
    elif fault == 'unknown_history': h['future_profit'] = '1'
    elif fault == 'unknown_driver': d['future_return'] = '1'
    elif fault == 'unknown_year': d['years'][0]['future_cash'] = '1'
    elif fault == 'unknown_terminal': t['future_override'] = '1'
    elif fault == 'missing_terminal': t.pop('commitment_cash_cny')
    elif fault == 'empty_rationale': t['rationale'] = ' '
    elif fault == 'bad_access': t['accessible_profit_ratio'] = '1.1'
    elif fault == 'bad_cost': d['years'][0]['cost_ratio'] = '-0.1'
    elif fault == 'bad_growth': d['years'][0]['revenue_growth'] = '-1'
    elif fault == 'negative_commitment': t['commitment_cash_cny'] = '-1'
    elif fault == 'negative_capacity': h['opening_distribution_capacity'] = '-1'
    elif fault == 'bad_tax': h['tax'] = h['pre_tax_profit']
    elif fault == 'bad_attribution': h['parent_profit'] = '0'
    elif fault == 'negative_attribution': h['parent_profit'] = '-1'
    elif fault == 'negative_scale': t['profit_scale'] = '0'
    with pytest.raises(ValueError):
        compile_joint_capital_cash_path(**args)
