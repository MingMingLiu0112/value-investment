"""Disposable real-service accounting demonstration, never strategy validation."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import json

import pytest

from value_investment_agent.application.portfolio.simulated_trade_journey import run_simulated_trade_journey
from value_investment_agent.application.portfolio.simulated_trade_journey import run_source_bound_simulated_trade_journey
from test_pending_candidate_supplement import registered


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


def _manual_request(symbol, *, reference=True):
    # Historical hypothetical execution, recorded at the actual service clock.
    return dict(fill=dict(transaction_id='SIMULATED-MANUAL-' + symbol, side='BUY', sleeve='CORE_VALUE',
        symbol=symbol, exchange='SSE', quantity='100', price_cny='10', fees_cny='5',
        trade_date='2026-10-23', next_sell_session='2026-10-26', trading_unit='100'),
        **({'research_reference': 'HISTORICAL_RECONSTRUCTION'} if reference else {}))


def _assert_source_wait(result):
    assert result['schema_version'] == 'source-bound-simulated-trade-journey-v1'
    assert result['namespace'] == 'SIMULATED' and result['action'] == 'no_order'
    assert result['strategy_validated'] is result['approval_changed'] is False
    assert result['broker_execution_permission'] is False
    for case in result['cases']:
        assert case['research']['candidate_binding']['sha256']
        assert case['research']['research_version'] == case['plan']['research_version']
        assert case['research']['thesis'] and case['research']['thesis_breakers']
        assert case['plan']['candidate_action'] == 'NO_ACTION'
        assert case['evaluation']['eligibility'] is False
        assert [slot['intent'] for slot in case['action_slots']] == ['BUY', 'ADD', 'HOLD', 'REDUCE', 'EXIT', 'WAIT']
        assert all(slot['outcome'] in {'NO_ACTION', 'WAIT'} and slot['reasons']
                   and slot['review_quantity'] is None and not slot['formal_eligibility'] for slot in case['action_slots'])


def test_source_read_default_does_not_create_a_journal_or_manual_fill(registered):
    root, symbol, _, _ = registered
    before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
    result = run_source_bound_simulated_trade_journey(root, datetime.now(timezone.utc), symbols=[symbol])
    _assert_source_wait(result)
    assert result['manual_rehearsal']['status'] == 'NOT_REQUESTED'
    assert result['manual_rehearsal']['fills'] == []
    assert not list(root.rglob('*.jsonl'))
    assert before == {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_source_manual_buy_derives_next_session_without_client_calendar(registered):
    root, symbol, _, _ = registered
    request = _manual_request(symbol, reference=False)
    request['fill'].pop('next_sell_session')
    result = run_source_bound_simulated_trade_journey(root, datetime.now(timezone.utc),
        symbols=[symbol], manual_fills=[request], initial_cash_cny='100000')
    fill = result['manual_rehearsal']['fills'][0]
    assert fill['fill']['next_sell_session'] == '2026-10-26'
    assert fill['t1_negative_status'] == 'REJECTED_WITHOUT_JOURNAL_WRITE'
    assert result['manual_rehearsal']['temporary_journal_removed'] is True


@pytest.mark.parametrize('field', ['candidate_binding', 'research_version', 'symbol', 'missing'])
def test_changed_user_visible_source_is_rejected_before_a_journal(registered, field):
    root, symbol, _, _ = registered
    read = run_source_bound_simulated_trade_journey(root, datetime.now(timezone.utc), symbols=[symbol])
    case = read['cases'][0]
    expected = dict(symbol=symbol, candidate_binding=dict(case['research']['candidate_binding']),
                    research_version=case['research']['research_version'])
    if field == 'candidate_binding':
        expected[field]['sha256'] = '0' * 64
    elif field in {'symbol', 'research_version'}:
        expected[field] = 'CHANGED'
    else:
        expected.pop('research_version')
    before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
    with pytest.raises(ValueError, match='Research changed'):
        run_source_bound_simulated_trade_journey(root, datetime.now(timezone.utc), symbols=[symbol],
            initial_cash_cny='100000', manual_fills=[_manual_request(symbol)], expected_candidates=[expected])
    assert before == {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_source_rehearsal_does_not_force_wait_on_an_unexpected_admitted_decision(registered, monkeypatch):
    from value_investment_agent.application.decision import public_strategy_assessment
    root, symbol, _, _ = registered
    monkeypatch.setattr(public_strategy_assessment, 'project_actionable_evaluation',
        lambda *args, **kwargs: dict(eligibility=True, decision_action='BUY_REVIEW'))
    with pytest.raises(ValueError, match='cannot represent admitted'):
        run_source_bound_simulated_trade_journey(root, datetime.now(timezone.utc), symbols=[symbol])
    assert not list(root.rglob('*.jsonl'))


@pytest.mark.parametrize('reference', [False, True])
def test_source_manual_service_journal_restart_and_t1_do_not_create_strategy_permission(registered, reference):
    root, symbol, _, _ = registered
    protected = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
    result = run_source_bound_simulated_trade_journey(root, datetime.now(timezone.utc), symbols=[symbol],
        manual_fills=[_manual_request(symbol, reference=reference)], initial_cash_cny='100000')
    _assert_source_wait(result)
    manual = result['manual_rehearsal']
    assert manual['restart_equal'] is manual['same_session_sell_rejected'] is True
    assert manual['temporary_journal_removed'] is True
    assert manual['account_state']['cash_cny'] == '98995'
    assert manual['journal_receipt']['record_count'] == (4 if reference else 3)
    row, = manual['fills']
    assert row['prepared_cash_unchanged'] is row['confirmation_idempotent'] is True
    assert row['snapshot_status'] == 'SNAPSHOT_UNAVAILABLE_NO_EXACT_PUBLISHED_RESEARCH'
    assert row['fill']['judgment_snapshot'] is None
    assert row['original_entry_advisory_eligible'] is False
    assert row['fill']['research_version'] == result['cases'][0]['research']['research_version']
    if reference:
        assert row['historical_reference_scope'] == 'NOT_ORIGINAL_PIT_ENTRY'
        assert 'HISTORICAL_RECONSTRUCTION_NOT_ORIGINAL_PIT_ENTRY' in row['entry_blockers']
    else:
        assert row['historical_reference_status'] == 'NOT_REQUESTED'
    assert protected == {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('fault', ['candidate', 'source', 'registry'])
def test_source_drift_is_not_relabelled_as_simulated_research(registered, fault):
    root, symbol, candidate, registry = registered
    path = {'candidate': candidate, 'source': root / 'runtime/original.md', 'registry': registry}[fault]
    path.write_bytes(path.read_bytes() + b'changed')
    with pytest.raises((ValueError, KeyError)):
        run_source_bound_simulated_trade_journey(root, datetime.now(timezone.utc), symbols=[symbol],
            manual_fills=[_manual_request(symbol)], initial_cash_cny='100000')
    assert not list(root.rglob('*.jsonl'))


def test_source_drift_after_manual_confirmation_discards_attribution_and_cleans_up(registered, monkeypatch):
    from value_investment_agent.application.portfolio import simulated_trade_journey as service
    root, symbol, _, _ = registered
    original = service.PrivatePortfolioService.confirm_fill

    def drift(self, request):
        result = original(self, request)
        path = root / 'runtime/original.md'
        if path.read_bytes()[-1:] != b'!':
            path.write_bytes(path.read_bytes() + b'!')
        return result

    monkeypatch.setattr(service.PrivatePortfolioService, 'confirm_fill', drift)
    with pytest.raises(ValueError, match='hash mismatch'):
        run_source_bound_simulated_trade_journey(root, datetime.now(timezone.utc), symbols=[symbol],
            manual_fills=[_manual_request(symbol, reference=False)], initial_cash_cny='100000')
    assert not list(root.rglob('*.jsonl'))
    assert not list((root / '.tmp').glob('source-bound-simulated-*'))


@pytest.mark.parametrize('fault', ['future_clock', 'naive_clock', 'future_trade', 'caller_snapshot', 'actual_entry'])
def test_source_journey_does_not_accept_temporal_or_approval_shortcuts(registered, fault):
    root, symbol, _, _ = registered
    now = datetime.now(timezone.utc)
    request = _manual_request(symbol)
    if fault == 'future_clock': now += timedelta(days=1)
    elif fault == 'naive_clock': now = now.replace(tzinfo=None)
    elif fault == 'future_trade': request['fill']['trade_date'] = (now + timedelta(days=1)).date().isoformat()
    elif fault == 'caller_snapshot': request['fill']['judgment_snapshot'] = {'approved': True}
    else: request['research_reference'] = 'CONTEMPORANEOUS'
    with pytest.raises(ValueError):
        run_source_bound_simulated_trade_journey(root, now, symbols=[symbol], manual_fills=[request], initial_cash_cny='100000')
    assert not list(root.rglob('*.jsonl'))


def test_requested_backdated_second_fill_is_rejected_by_original_ledger(registered):
    root, symbol, _, _ = registered
    first = _manual_request(symbol, reference=False)
    earlier = _manual_request(symbol, reference=False)
    earlier['fill'].update(transaction_id='SIMULATED-EARLIER', trade_date='2026-10-22', next_sell_session='2026-10-23')
    with pytest.raises(ValueError, match='trade date precedes confirmed state'):
        run_source_bound_simulated_trade_journey(root, datetime.now(timezone.utc), symbols=[symbol],
            manual_fills=[first, earlier], initial_cash_cny='100000')
    assert not list(root.rglob('*.jsonl'))


def test_t1_probe_does_not_treat_older_sellable_lots_as_a_settlement_failure(registered):
    root, symbol, _, _ = registered
    older = _manual_request(symbol, reference=False)
    older['fill'].update(transaction_id='SIMULATED-OLDER', trade_date='2026-10-22', next_sell_session='2026-10-23')
    result = run_source_bound_simulated_trade_journey(root, datetime.now(timezone.utc), symbols=[symbol],
        manual_fills=[older, _manual_request(symbol, reference=False)], initial_cash_cny='100000')
    manual = result['manual_rehearsal']
    assert manual['fills'][0]['t1_negative_status'] == 'REJECTED_WITHOUT_JOURNAL_WRITE'
    assert manual['fills'][1]['t1_negative_status'] == 'NOT_APPLICABLE_OLDER_SELLABLE_LOTS'
    assert manual['t1_negative_checks'] == 1
    assert manual['restart_equal'] is True
    assert manual['account_state']['cash_cny'] == '97990'
    assert manual['temporary_journal_removed'] is True


def test_actual_two_company_source_read_and_explicit_manual_rehearsal(tmp_path, monkeypatch):
    """Opt-in public originals; journal writes only in the test workspace .tmp."""
    import os
    import io
    import socket
    from pathlib import Path
    from value_investment_agent.application.portfolio import private_portfolio_service
    location = os.environ.get('SOURCE_BOUND_SIMULATED_REAL_ROOT')
    if not location:
        pytest.skip('Explicit retained public source root not provided')
    monkeypatch.setattr(private_portfolio_service, 'resolve_private_root',
        lambda **kwargs: pytest.fail('No private account resolver'))
    root = Path(location)
    original_open = io.open

    def isolated_open(file, mode='r', *args, **kwargs):
        path = Path(file).resolve()
        assert not {'.private', 'private-data', 'private'} & set(path.parts), 'private data read'
        if any(flag in mode for flag in 'wax+'):
            assert path.is_relative_to(tmp_path / '.tmp'), 'write outside disposable journal'
        return original_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(io, 'open', isolated_open)
    monkeypatch.setattr(socket.socket, 'connect', lambda *args, **kwargs: pytest.fail('No network'))
    from value_investment_agent.application.portfolio import simulated_trade_journey as journey
    monkeypatch.setattr(journey, 'review_dual_sleeve_risk',
        lambda *args, **kwargs: pytest.fail('No production/synthetic risk override'))
    now = datetime.now(timezone.utc)
    read = run_source_bound_simulated_trade_journey(root, now, symbols=('600519', '600887'), workspace_root=tmp_path)
    _assert_source_wait(read)
    assert read['manual_rehearsal']['status'] == 'NOT_REQUESTED'
    result = run_source_bound_simulated_trade_journey(root, now, symbols=('600519', '600887'), workspace_root=tmp_path,
        manual_fills=[_manual_request(symbol) for symbol in ('600519', '600887')], initial_cash_cny='100000')
    _assert_source_wait(result)
    manual = result['manual_rehearsal']
    assert manual['account_state']['cash_cny'] == '97990'
    assert manual['account_state']['confirmed_fees_cny'] == '10'
    assert manual['restart_equal'] is manual['same_session_sell_rejected'] is manual['temporary_journal_removed'] is True
    assert len(manual['fills']) == 2
    assert all(row['original_entry_advisory_eligible'] is False for row in manual['fills'])
    assert not list(tmp_path.rglob('*.jsonl'))
    print(json.dumps(dict(companies=[dict(symbol=case['symbol'], research=case['research'],
        verdict=case['evaluation']['decision_action'], reason=case['evaluation']['decision_reason'],
        slots={slot['intent']: slot['outcome'] for slot in case['action_slots']}) for case in result['cases']],
        accounting=manual['account_state'], checks={key: manual[key] for key in
            ('restart_equal', 'same_session_sell_rejected', 'temporary_journal_removed')},
        journal_receipt=manual['journal_receipt'], snapshots=[dict(symbol=row['symbol'],
            status=row['snapshot_status'], recorded_at=row['recorded_at'],
            historical_reference_scope=row['historical_reference_scope']) for row in manual['fills']]), ensure_ascii=False))
