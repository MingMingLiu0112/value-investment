from copy import deepcopy
from decimal import Decimal
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import os

import pytest

from value_investment_agent.domain.hotspot.quantitative_validation import compare_frozen_portfolio_accounts


def fixture():
    protocol = dict(initial_cash_cny='2500', costs=dict(commission_rate='0', minimum_commission_cny='5',
        sell_tax_rate='0', transfer_fee_rate='0', slippage_bps='0',
        effective_start='2026-01-01T00:00:00+08:00', effective_end='2026-12-31T23:59:59+08:00'))
    fold = dict(id='test', test_start='2026-10-19T09:30:00+08:00', test_end='2026-10-20T15:00:00+08:00')
    bars, orders = [], []
    for symbol, ending in [('000001', '12'), ('000002', '8')]:
        for day, hour, close in [(19, '10:30', '10'), (19, '15:00', '10'), (20, '15:00', ending)]:
            bars.append(dict(symbol=symbol, time=f'2026-10-{day}T{hour}:00+08:00', open='10', close=close,
                limit_down='5', limit_up='15', suspended=False, liquidity_cny='100000'))
        orders.append(dict(id=symbol, symbol=symbol, side='BUY', quantity=200, fold='test',
            decision_at='2026-10-19T10:00:00+08:00', available_at='2026-10-19T09:00:00+08:00',
            execute_at='2026-10-19T10:30:00+08:00', limit_price='14', liquidity_budget_cny='10000'))
    inputs = {key:dict(bars=deepcopy(bars), orders=deepcopy(orders)) for key in ('0', '1', '2')}
    benchmarks = {key:[dict(order, quantity=100, id='b-' + order['id']) for order in orders]
                  for key in ('0', '1', '2')}
    return protocol, inputs, benchmarks, fold


def test_common_cash_competition_and_matched_basket_are_computed_not_averaged():
    args = fixture()
    before = deepcopy(args)
    result = compare_frozen_portfolio_accounts(*args)
    base = result['scenarios'][1]
    assert base['strategy']['rejection_counts'] == {'CASH': 1}
    assert base['strategy']['filled_order_count'] == 1
    assert base['benchmark']['filled_order_count'] == 2
    assert base['strategy']['ending_equity_cny'] == '2895.00'
    assert base['benchmark']['ending_equity_cny'] == '2490.00'
    assert Decimal(base['strategy_net_return']) > 0 and Decimal(base['benchmark_net_return']) < 0
    assert len(base['paired_daily_excess']) == 2
    assert base['uncertainty']['statistical_coverage_claim'] is False
    assert base['strategy']['ending_weights'].keys() == {'000001'}
    assert result['formal_eligibility'] is False and result['action'] == 'no_order'
    assert args == before


def test_each_cost_scenario_consumes_its_own_prechecked_order_inputs():
    protocol, inputs, benchmarks, fold = fixture()
    inputs['2']['orders'] = []
    result = compare_frozen_portfolio_accounts(protocol, inputs, benchmarks, fold)
    assert result['scenarios'][1]['strategy']['filled_order_count'] == 1
    assert result['scenarios'][2]['strategy']['filled_order_count'] == 0


def test_preflight_rejection_is_retained_without_old_isolated_cash_results():
    protocol, inputs, benchmarks, fold = fixture()
    inputs['2'].update(orders=[], preflight_rejected=[dict(order_id='not-submitted',
        reason='SLIPPAGE_OUTSIDE_OBSERVED_BAR')], frozen_intention_count=1)
    result = compare_frozen_portfolio_accounts(protocol, inputs, benchmarks, fold)
    lane = result['scenarios'][2]['strategy']
    assert lane['frozen_intention_count'] == lane['unfilled_count'] == 1
    assert lane['unfilled_rate'] == '1'
    assert lane['rejection_counts'] == {'SLIPPAGE_OUTSIDE_OBSERVED_BAR': 1}


def test_optional_arch_stationary_interval_is_paired_reproducible_and_not_admission():
    pytest.importorskip('arch')
    from value_investment_agent.application.hotspot.quantitative_validation import compute_paired_stationary_uncertainty
    from value_investment_agent.domain.execution.exchange_calendar import is_exchange_session
    rows, day = [], date(2026, 1, 5)
    while len(rows) < 28:
        if is_exchange_session('SSE', day):
            rows.append(dict(date=day.isoformat(), daily_excess_cash=str(len(rows) / 10000),
                             daily_excess_pool=str((len(rows) - 15) / 10000)))
        day += timedelta(days=1)
    parameters = dict(block_length=10, resamples=200, confidence='0.95', seed=17, minimum_effective_blocks=12)
    first = compute_paired_stationary_uncertainty(rows, parameters)
    assert first == compute_paired_stationary_uncertainty(rows, parameters)
    assert first['sample_status'] == 'INSUFFICIENT'
    assert first['upper_bound'] is None and first['strict_oos_admitted'] is False


def test_actual_retained_shared_account_diagnostic():
    root = os.environ.get('HOTSPOT_PAIRED_BENCHMARK_ROOT')
    if not root:
        pytest.skip('Actual retained public sources are not distributed with this test')
    from value_investment_agent.application.hotspot.strategy_execution_replay import build_retained_portfolio_benchmarks
    result = build_retained_portfolio_benchmarks(root=Path(root), now=datetime.now(timezone.utc))
    assert len(result['cohort_symbols']) == 5 and len(result['folds']) == 2
    assert all(len(fold['scenarios']) == 3 for fold in result['folds'])
    assert result['formal_eligibility'] is result['strict_oos_admitted'] is False
