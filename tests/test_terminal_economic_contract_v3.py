"""Direct economic tests for the v3 post-forecast capital-use contract."""
from copy import deepcopy
from decimal import Decimal as D

import pytest

from value_investment_agent.domain.valuation.joint_capital_cash_path_v3 import (
    SCOPE,
    compile_joint_capital_cash_path,
    value_terminal_economic_contract,
)
from value_investment_agent.valuation_models.residual_income_path_v3 import (
    ResidualIncomePathScenarioInputs,
    scenario_calculation,
)


def stable_case():
    historical = dict(scope=SCOPE, currency='CNY', revenue='100', cost='80',
        surcharges='0', selling='0', admin='0', research='0', pre_tax_profit='20',
        tax='0', parent_profit='20', nonrecurring='0', da='0', opening_cash='20',
        opening_distribution_capacity='100', cash_floor='10')
    years = [dict(year=year, revenue_growth='0', cost_ratio='0.8',
        target_payout_ratio='0.85', accessible_profit_ratio='0.95',
        net_maintenance_cash_cny='2', operating_wc_cash_cny='1',
        commitment_cash_cny='0', reserve_ratio='0.1') for year in range(1, 11)]
    drivers = dict(years=years, operating_allocation='0',
        new_operating_return='0', new_liquidity_return='0')
    terminal = dict(net_maintenance_cash_cny='2', operating_wc_cash_cny='1',
        commitment_cash_cny='0', accessible_profit_ratio='0.95',
        target_payout_ratio='0.85', reserve_ratio='0.1', profit_scale='1',
        rationale='Legacy earnings remain flat; retained cash earns no return.',
        terminal_mechanism='recursive_capital_use_and_owner_distribution_v1',
        terminal_start_year=11,
        first_distribution_timing='end_of_terminal_year_1',
        legacy_profit_dynamics='constant_after_profit_scale_transition',
        commitment_occurrences=0, restricted_cash_release_cny='0',
        restricted_cash_release_year=None,
        convergence_tolerance_cny='0.0000000001', max_tail_years=2000)
    return dict(start_book='100', historical=historical, drivers=drivers,
        terminal_policy=terminal)


def test_zero_growth_counterexample_values_tail_at_200_not_325():
    result = compile_joint_capital_cash_path(**stable_case())
    valued = value_terminal_economic_contract(
        result['terminal_economic_contract'], D('0.08'))
    independent_benchmark = result['terminal_distribution'] / D('0.08')
    assert result['terminal_distribution'] == D('16')
    assert abs(valued['equity_value'] - independent_benchmark) < D('1e-9')
    assert abs(valued['distribution_value'] - independent_benchmark) < D('1e-9')
    assert valued['equity_value'] < D('325')
    assert result['terminal_growth_status'] == 'NON_AUTHORITATIVE_ACCOUNTING_DIAGNOSTIC'


@pytest.mark.parametrize(('profit', 'payout', 'required_return'), [
    (D('30'), D('0.7'), D('0.10')),
    (D('12'), D('0.5'), D('0.06')),
])
def test_zero_growth_benchmark_is_not_hardcoded(profit, payout, required_return):
    args = stable_case()
    revenue = profit / D('0.2')
    args['historical'].update(revenue=format(revenue, 'f'),
        cost=format(revenue * D('0.8'), 'f'),
        pre_tax_profit=format(profit, 'f'), parent_profit=format(profit, 'f'))
    for row in args['drivers']['years']:
        row['target_payout_ratio'] = str(payout)
    args['terminal_policy']['target_payout_ratio'] = str(payout)
    result = compile_joint_capital_cash_path(**args)
    valued = value_terminal_economic_contract(
        result['terminal_economic_contract'], required_return)
    assert abs(valued['equity_value']
        - result['terminal_distribution'] / required_return) < D('1e-9')


def test_productive_reinvestment_supports_growth_while_idle_cash_does_not():
    idle = compile_joint_capital_cash_path(**stable_case())
    idle_value = value_terminal_economic_contract(
        idle['terminal_economic_contract'], D('0.12'))
    productive_args = stable_case()
    productive_args['drivers'].update(
        operating_allocation='0.5', new_operating_return='0.08')
    productive = compile_joint_capital_cash_path(**productive_args)
    productive_value = value_terminal_economic_contract(
        productive['terminal_economic_contract'], D('0.12'))
    assert productive_value['equity_value'] > idle_value['equity_value']
    assert productive_value['last_row']['new_operating_profit'] > 0


def test_recurring_needs_reduce_value_and_one_time_commitment_is_not_repeated():
    base = compile_joint_capital_cash_path(**stable_case())
    base_value = value_terminal_economic_contract(
        base['terminal_economic_contract'], D('0.08'))['equity_value']
    higher = stable_case()
    higher['terminal_policy'].update(
        net_maintenance_cash_cny='3', operating_wc_cash_cny='2')
    higher_value = value_terminal_economic_contract(
        compile_joint_capital_cash_path(**higher)['terminal_economic_contract'],
        D('0.08'))['equity_value']
    assert higher_value < base_value

    once = stable_case()
    once['terminal_policy'].update(
        commitment_cash_cny='4', commitment_occurrences=1)
    once_value = value_terminal_economic_contract(
        compile_joint_capital_cash_path(**once)['terminal_economic_contract'],
        D('0.08'))
    assert once_value['first_row']['commitment_cash_cny'] == D('4')
    assert once_value['last_row']['commitment_cash_cny'] == 0


def test_restricted_cash_release_requires_explicit_single_use_assumption():
    args = stable_case()
    for row in args['drivers']['years']:
        row['accessible_profit_ratio'] = '0.5'
    args['terminal_policy']['accessible_profit_ratio'] = '0.5'
    trapped = compile_joint_capital_cash_path(**args)
    trapped_value = value_terminal_economic_contract(
        trapped['terminal_economic_contract'], D('0.08'))['equity_value']
    released = deepcopy(args)
    released['terminal_policy'].update(
        restricted_cash_release_cny='20', restricted_cash_release_year=1)
    released_result = compile_joint_capital_cash_path(**released)
    released_value = value_terminal_economic_contract(
        released_result['terminal_economic_contract'], D('0.08'))
    assert released_value['equity_value'] > trapped_value
    assert released_value['first_row']['restricted_cash_release_cny'] == D('20')
    assert released_value['last_row']['restricted_cash_release_cny'] == 0


def test_unfunded_and_nonconvergent_terminal_paths_fail_closed():
    unfunded = stable_case()
    unfunded['terminal_policy'].update(net_maintenance_cash_cny='100000')
    with pytest.raises(ValueError, match='unfunded'):
        value_terminal_economic_contract(
            compile_joint_capital_cash_path(**unfunded)['terminal_economic_contract'],
            D('0.08'))

    explosive = stable_case()
    explosive['drivers'].update(
        operating_allocation='1', new_operating_return='0.5')
    explosive['terminal_policy'].update(
        target_payout_ratio='0', max_tail_years=40)
    with pytest.raises(ValueError, match='did not converge'):
        value_terminal_economic_contract(
            compile_joint_capital_cash_path(**explosive)['terminal_economic_contract'],
            D('0.08'))


def test_v3_ri_consumes_terminal_equity_minus_closing_book():
    result = compile_joint_capital_cash_path(**stable_case())
    scenario = ResidualIncomePathScenarioInputs(
        cost_of_equity=D('0.08'), forecast_roes=result['forecast_roe'],
        forecast_retentions=result['forecast_retentions'],
        terminal_roe=result['terminal_roe'], terminal_growth=result['terminal_growth'],
        terminal_economic_contract=result['terminal_economic_contract'])
    facts = type('Facts', (), {'operating_inputs': {
        'start_book_equity': D('100'), 'ordinary_shares': D('10')},
        'valuation_timing': None})()
    calculation = scenario_calculation(facts, scenario)
    assert calculation['model_version'] == 'residual-income-equity-path-v3'
    assert calculation['terminal_mechanism'] == 'recursive_capital_use_and_owner_distribution'
    assert abs(D(calculation['dividend_crosscheck_difference_cny'])) < D('0.01')


def test_v3_scenario_cannot_fall_back_to_legacy_terminal_growth():
    result = compile_joint_capital_cash_path(**stable_case())
    with pytest.raises(ValueError, match='require a terminal economic contract'):
        ResidualIncomePathScenarioInputs(
            cost_of_equity=D('0.08'), forecast_roes=result['forecast_roe'],
            forecast_retentions=result['forecast_retentions'],
            terminal_roe=result['terminal_roe'], terminal_growth=result['terminal_growth'],
            terminal_economic_contract=None,
        )
