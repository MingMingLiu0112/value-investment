from copy import deepcopy
from decimal import Decimal
from datetime import datetime, timezone
from pathlib import Path
import os

import pytest

from value_investment_agent.domain.hotspot.strategy_execution_replay import replay_shared_strategy_execution
from test_hotspot_strategy_execution_replay import fixture
from value_investment_agent.domain.hotspot.current_price import aggregate_sessions
from value_investment_agent.domain.hotspot.quantitative_validation import simulate_fold


def shared_fixture():
    data = fixture()
    bars = {symbol: deepcopy(data['bars_by_period']) for symbol in ('000001', '000002')}
    states = {symbol: deepcopy(data['stock_states']) for symbol in bars}
    return dict(bars_by_symbol=bars, stock_states_by_symbol=states, spec=data['spec'],
                costs=data['costs'], initial_cash='1500')


def test_rejected_shared_entry_remains_flat_and_cannot_generate_a_sell():
    args = shared_fixture()
    before = deepcopy(args)
    result = replay_shared_strategy_execution(**args)
    fold = result['folds'][0]
    assert fold['rejection_counts']['CASH'] == 1
    assert fold['rejection_counts']['T_PLUS_ONE'] == 1
    assert {fill['symbol'] for fill in fold['fills']} == {'000001'}
    assert not any(intent['side'] == 'SELL' and intent['symbol'] == '000002'
                   for intent in fold['generated_intentions'])
    assert all(row['state'] == 'FLAT' and row['original_protection'] is None
               for row in fold['state_trace'] if row['symbol'] == '000002')
    held = [row for row in fold['state_trace'] if row['symbol'] == '000001'
            and row['state'] != 'FLAT']
    assert held and len({row['original_protection'] for row in held}) == 1
    assert fold['trade_count'] == 1
    assert result['formal_eligibility'] is result['strict_oos_admitted'] is False
    assert result['action'] == 'no_order' and args == before


def test_strict_missing_states_produces_no_phantom_holdings():
    args = shared_fixture()
    args.pop('stock_states_by_symbol')
    result = replay_shared_strategy_execution(**args)
    assert all(not fold['fills'] and fold['right_censored_positions'] == 0 for fold in result['folds'])
    assert all(row['state'] == 'FLAT' for fold in result['folds'] for row in fold['state_trace'])
    assert sum(fold['rejection_counts'].get('MISSING_DATED_STOCK_STATUS', 0)
               for fold in result['folds']) > 0


def test_new_trigger_after_cash_release_can_enter_without_phantom_prior_holding():
    args = shared_fixture()
    args['costs'].update(commission_rate='0', sell_tax_rate='0', transfer_fee_rate='0', slippage_bps='0')
    bars = args['bars_by_symbol']['000002']['60m']
    bars[9].update(close='10.8', high='10.9', volume='300')
    bars[10].update(open='10.5', close='10.6', high='10.8', low='10.4')
    args['bars_by_symbol']['000002']['daily'] = aggregate_sessions(bars)
    result = replay_shared_strategy_execution(**args)
    part = result['folds'][0]
    assert [(fill['symbol'], fill['side']) for fill in part['fills']] == [
        ('000001', 'BUY'), ('000001', 'SELL'), ('000002', 'BUY')]
    assert part['ending_cash_cny'] == '315.00'
    second_buy = next(row for row in part['generated_intentions'] if row['symbol'] == '000002'
                      and row['decision_at'].startswith('2026-10-12T11:30'))
    assert second_buy['side'] == 'BUY'
    assert all(row['side'] != 'SELL' for row in part['generated_intentions'] if row['symbol'] == '000002')
    assert all(Decimal(row['entry_invalidation']) == Decimal('9.8') for row in part['generated_intentions']
               if row['symbol'] == '000001' and row['side'] == 'SELL')
    reversed_args = deepcopy(args)
    reversed_args['bars_by_symbol'] = dict(reversed(list(reversed_args['bars_by_symbol'].items())))
    assert replay_shared_strategy_execution(**reversed_args)['folds'][0]['fills'] == part['fills']
    folded = simulate_fold(dict(initial_cash_cny='1500', costs=args['costs']), part['simulator_inputs'],
        dict(id='development', test_start='2026-10-08T09:30:00+08:00', test_end='2026-10-15T15:00:00+08:00'))
    assert folded['fills'] == part['fills'] and folded['ending_cash_cny'] == part['ending_cash_cny']


def test_actual_source_feedback_and_paired_final_account_reconcile():
    root = os.environ.get('HOTSPOT_SHARED_FEEDBACK_ROOT')
    if not root:
        pytest.skip('Retained public price originals are not distributed with this test')
    from value_investment_agent.application.hotspot.strategy_execution_replay import build_shared_feedback_portfolio_benchmarks
    result = build_shared_feedback_portfolio_benchmarks(root=Path(root), now=datetime.now(timezone.utc),
                                                     initial_cash_cny='5000')
    assert result['state_feedback'] == 'SIMULATED_FILLS_NOT_INTENTIONS_DRIVE_POSITIONS'
    assert result['formal_eligibility'] is result['dated_tradability_proven'] is False
    for fold in result['folds']:
        for lane in fold['scenarios']:
            ledger = {}
            for fill in lane['strategy']['fills']:
                if fill['side'] == 'BUY':
                    assert fill['symbol'] not in ledger
                    ledger[fill['symbol']] = fill['quantity']
                else:
                    assert ledger.pop(fill['symbol']) == fill['quantity']
            trace = {(row['symbol'], row['completed_at']): row for row in lane['strategy']['state_trace']}
            for intent in lane['strategy']['generated_intentions']:
                if intent['side'] == 'SELL':
                    label = datetime.fromisoformat(intent['decision_at']).strftime('%Y-%m-%d %H:%M:%S')
                    assert trace[intent['symbol'], label]['state'] == 'EXIT_PENDING'
