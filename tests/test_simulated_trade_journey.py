"""Disposable real-service accounting demonstration, never strategy validation."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from decimal import Decimal
import json

import pytest

from value_investment_agent.application.portfolio.simulated_trade_journey import run_simulated_trade_journey


NOW = datetime.fromisoformat('2026-10-23T20:00:00+08:00')


def test_full_journey_cash_fees_t1_idempotency_restart_and_cleanup(tmp_path):
    sentinel = tmp_path / 'existing-user-data.txt'
    sentinel.write_bytes(b'leave unchanged')
    result = run_simulated_trade_journey(tmp_path, NOW)
    assert result['namespace'] == 'SIMULATED'
    assert result['actual_account_used'] is result['strategy_validated'] is False
    assert result['action'] == 'no_order'
    assert result['broker_execution_permission'] is result['approval_changed'] is False
    assert all(result['checks'].values())
    assert json.loads(json.dumps(result, allow_nan=False)) == result
    assert sentinel.read_bytes() == b'leave unchanged'
    assert list((tmp_path / '.tmp').iterdir()) == []
    assert [row['label'] for row in result['steps']] == [
        'CORE_BUY', 'HOTSPOT_BUY', 'CORE_ADD', 'HOLD', 'T_PLUS_ONE_REJECTED',
        'CORE_REDUCE', 'CORE_EXIT', 'HOTSPOT_EXIT']
    trades = [row for row in result['steps'] if row.get('fees_cny')]
    assert len(trades) == 6
    for row in trades:
        assert row['before']['cash_cny'] == row['prepared_state']['cash_cny']
        assert row['before']['positions'] == row['prepared_state']['positions']
        assert row['prepared_state']['pending_draft'] is True
        assert row['after']['pending_draft'] is False
        assert row['confirmation_idempotent'] is True
        before, after = Decimal(row['before']['cash_cny']), Decimal(row['after']['cash_cny'])
        gross, fee = Decimal(row['quantity']) * Decimal(row['price_cny']), Decimal(row['fees_cny'])
        assert after == before + (gross if row['intention'] == 'SELL' else -gross) - fee
        state = row['after']
        assert sum(map(Decimal, state['sleeve_cash_cny'].values()), Decimal(state['cash_reserve_cny'])) == after
        assert row['risk_review']['namespace'] == 'SIMULATED'
        assert row['risk_review']['trade_eligible'] is False
    final = result['final_state']
    assert final['cash_cny'] == '10170'
    assert final['positions'] == []
    assert final['realized_pnl_cny'] == '170'
    assert final['confirmed_fees_cny'] == '30'
    assert result['final_risk_review']['aggregate']['total_assets_cny'] == '10170'
    assert result['journal_receipt']['retained'] is False


def test_risk_engine_combines_same_security_across_sleeves_and_limits_buys(tmp_path):
    result = run_simulated_trade_journey(tmp_path, NOW)
    core, hotspot, add, hold, rejected, reduce, exit_core, exit_hotspot = result['steps']
    for row, key in ((core, 'core_quantity_review'), (hotspot, 'hotspot_quantity_review'), (add, 'core_quantity_review')):
        assert row['risk_review'][key]['review_quantity'] >= 100
    risk = hold['risk_review']
    overlap, = risk['aggregate']['duplicated_security_exposure'].values()
    assert sum(Decimal(row['quantity']) for row in overlap) == 300
    assert risk['aggregate']['cash_cny'] == '7085'
    assert rejected['rejected_without_journal_write'] is True
    assert rejected['before'] == rejected['after']
    assert all(sleeve['sellable_quantity'] == '0' for position in hold['after']['positions'] for sleeve in position['sleeves'])
    assert all(Decimal(sleeve['sellable_quantity']) > 0 for position in reduce['before']['positions'] for sleeve in position['sleeves'])
    assert reduce['intention'] == exit_core['intention'] == exit_hotspot['intention'] == 'SELL'
    assert result['actual_engine_provenance']['separate_ledger'] is False
    assert result['actual_engine_provenance']['monkeypatch'] is False


def test_simultaneous_runs_are_isolated_and_have_identical_accounting(tmp_path):
    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = list(pool.map(lambda _: run_simulated_trade_journey(tmp_path, NOW), range(2)))
    assert first['final_state'] == second['final_state']
    assert first['journal_receipt']['sha256'] != second['journal_receipt']['sha256']
    assert list((tmp_path / '.tmp').iterdir()) == []


@pytest.mark.parametrize('now', [datetime(2026, 10, 23), datetime.fromisoformat('2026-10-19T20:00:00+08:00')])
def test_invalid_clock_does_not_create_journal(tmp_path, now):
    with pytest.raises(ValueError):
        run_simulated_trade_journey(tmp_path, now)
    assert not list(tmp_path.rglob('*.jsonl'))
