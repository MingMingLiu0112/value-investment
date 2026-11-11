"""Native source readers + one disposable ledger; no strategy approval fixture."""
from copy import deepcopy
from datetime import date, datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path

import pytest

from test_pending_candidate_supplement import registered
from test_hotspot_simulated_lifecycle import _seal
from value_investment_agent.application.portfolio import simulated_trade_journey as journey
from value_investment_agent.application.portfolio.private_portfolio_service import JournalConflict


CORE, HOTSPOT = journey.CORE, journey.HOTSPOT


def _account():
    return dict(namespace='TEST_ONLY', confirmed=True, opening_day='2026-10-21',
        initial_cash_cny='10000', policy=journey._policy(date(2026, 10, 21)),
        hypothetical_marks={'600887': '10', '600519': '10', '300750': '10'})


def _fill(tx, sleeve, symbol='600887', *, intent='BUY', day='2026-10-21', entry=None):
    result = dict(intent=intent, rationale='TEST_ONLY hypothesis; not source approval or investment advice',
        fill=dict(transaction_id=tx, side='BUY' if intent in {'BUY', 'ADD'} else 'SELL',
            sleeve=sleeve, symbol=symbol, exchange='SSE' if symbol.startswith('6') else 'SZSE',
            quantity='100', price_cny='10', fees_cny='5', trade_date=day))
    if intent == 'BUY':
        result['fill']['trading_unit'] = '100'
        result['entry_narrative'] = dict(thesis='TEST_ONLY discretionary research hypothesis',
            hold_logic='Only while this hypothetical thesis remains unchanged',
            invalidation_conditions=['Permanent impairment invalidates this hypothesis'])
    else:
        result['entry_transaction_id'] = entry
    if intent == 'ADD':
        result['fill']['trading_unit'] = '100'
    return result


@pytest.fixture
def dual(registered, tmp_path, monkeypatch):
    import test_hotspot_lifecycle_bound_history as history
    import test_hotspot_simulated_lifecycle as lifecycle_fixture
    from value_investment_agent.application.hotspot.simulated_lifecycle import run_simulated_hotspot_lifecycle
    core, symbol, _, _ = registered
    # TEST_ONLY shared-security collision: native raw collection and sealed replay,
    # not a substitute for the real 600519/300750 sources tested below.
    monkeypatch.setattr(history, 'SYMBOL', symbol)
    def native_fixture_run(root, entry, current):
        return run_simulated_hotspot_lifecycle(source_root=root, workspace_root=root,
            symbol=symbol, entry_case_binding=history._binding(entry), entry_at=history.ENTRY_AT,
            followups=[dict(case_binding=history._binding(current), evaluated_at=history.CURRENT_AT)],
            generated_at=history.CURRENT_AT + journey.timedelta(days=1))
    monkeypatch.setattr(lifecycle_fixture, '_run', native_fixture_run)
    swing = tmp_path / 'swing'
    swing.mkdir()
    binding = _seal(swing)
    args = dict(core_root=core, hotspot_root=swing, workspace_root=tmp_path,
        now=datetime.now(timezone.utc), core_symbols=[symbol], hotspot_receipt_binding=binding)
    return args


def _read(args):
    return journey.run_source_bound_dual_sleeve_journey(**args)


def _manual(args, fills, **overrides):
    read = _read(args)
    params = dict(args, expected_sources=read['source_identity'], test_only_account=_account(), manual_fills=fills)
    params.update(overrides)
    return journey.run_source_bound_dual_sleeve_journey(**params)


def _assert_no_authority(result):
    assert result['formal_eligibility'] is result['strategy_validated'] is False
    assert result['position_guidance'] is None and result['action'] == 'no_order'
    for case in [*result['core_cases'], result['hotspot_case']]:
        assert len(case['action_slots']) == 6
        assert all(row['outcome'] in {'WAIT', 'NO_ACTION'} and row['review_quantity'] is None
            and row['formal_eligibility'] is False for row in case['action_slots'])
    assert 'model_context' not in result['hotspot_case']


def test_default_reads_native_sources_without_constructing_account(dual, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Default dual reader must not create a journal')
    monkeypatch.setattr(journey, 'TemporaryDirectory', forbidden)
    result = _read(dual)
    _assert_no_authority(result)
    assert result['manual_rehearsal']['status'] == 'NOT_REQUESTED'
    assert result['hotspot_case']['current_signal'] is result['hotspot_case']['current_pit'] is False


def test_same_security_two_sleeves_share_one_cash_and_native_entry_reconstruction(dual):
    result = _manual(dual, [_fill('core', CORE), _fill('swing', HOTSPOT)])
    _assert_no_authority(result)
    manual = result['manual_rehearsal']
    state = manual['account_state']
    assert state['cash_cny'] == '7990'
    assert state['confirmed_fees_cny'] == '10'
    assert state['hypothetical_equity_cny'] == '9990'
    holding, = state['aggregate_holdings']
    assert holding['quantity'] == '200' and holding['market_value_cny'] == '2000'
    position, = state['positions']
    assert len(position['sleeves']) == 2
    assert state['sleeve_cash_review']['sleeves'][CORE]['cash_cny'] == '3995'
    assert state['sleeve_cash_review']['sleeves'][HOTSPOT]['cash_cny'] == '1995'
    assert state['risk_review']['status'] == 'BLOCKED_PRIVATE_INPUT'
    assert manual['restart_equal'] is manual['temporary_journal_removed'] is True
    assert manual['journal_receipt']['retained'] is False
    assert not list(dual['workspace_root'].glob('.tmp/source-bound-dual-*'))
    assert all(row['confirmation_idempotent'] and row['prepared_cash_unchanged']
        and not row['original_pit_proven'] and not row['original_entry_advisory_eligible']
        and 'HISTORICAL_RECONSTRUCTION_NOT_ORIGINAL_PIT_ENTRY' in row['entry_blockers']
        for row in manual['fills'])


def test_partial_add_reduce_exit_link_original_hypothesis_not_system_suggestion(dual):
    first = _fill('core', CORE)
    first['requested_quantity'] = '200'
    fills = [first, _fill('swing', HOTSPOT), _fill('add', CORE, intent='ADD', entry='core'),
        _fill('reduce', CORE, intent='REDUCE', day='2026-10-22', entry='core'),
        _fill('exit', CORE, intent='EXIT', day='2026-10-23', entry='add'),
        _fill('swing-exit', HOTSPOT, intent='EXIT', day='2026-10-23', entry='swing')]
    result = _manual(dual, fills)
    manual = result['manual_rehearsal']
    assert manual['account_state']['cash_cny'] == '9970'
    assert manual['account_state']['positions'] == []
    assert manual['fills'][0]['unfilled_quantity'] == '100'
    assert manual['fills'][2]['original_entry_transaction_id'] == 'core'
    assert manual['fills'][4]['original_entry_transaction_id'] == 'add'
    assert manual['fills'][2]['original_entry_reference']['narrative'] == first['entry_narrative']
    assert manual['temporary_journal_removed'] is True
    _assert_no_authority(result)


def _different_entries(sleeve):
    first, second = _fill('A', sleeve), _fill('B', sleeve)
    for name, request in (('A', first), ('B', second)):
        request['entry_narrative'] = dict(thesis=name + ' distinct thesis',
            hold_logic=name + ' distinct holding rationale',
            invalidation_conditions=[name + ' specific breaker'])
    return [first, second]


@pytest.mark.parametrize('sleeve', [CORE, HOTSPOT])
def test_fifo_sell_of_a_cannot_claim_still_held_b(dual, sleeve):
    sell = _fill('wrong', sleeve, intent='REDUCE', day='2026-10-22', entry='B')
    with pytest.raises(ValueError, match='differs from native FIFO'):
        _manual(dual, [*_different_entries(sleeve), sell])
    assert not list(dual['workspace_root'].glob('.tmp/source-bound-dual-*'))


@pytest.mark.parametrize('sleeve', [CORE, HOTSPOT])
def test_fifo_single_sell_reports_actual_a_narrative_not_b(dual, sleeve):
    sell = _fill('right', sleeve, intent='REDUCE', day='2026-10-22', entry='A')
    result = _manual(dual, [*_different_entries(sleeve), sell])
    row = result['manual_rehearsal']['fills'][-1]
    assert row['original_entry_transaction_id'] == 'A'
    consumed, = row['consumed_original_entries']
    assert consumed['transaction_id'] == 'A' and consumed['quantity'] == '100'
    assert consumed['original_entry_reference']['narrative']['thesis'] == 'A distinct thesis'
    assert consumed['manual_rationale'] == sell['rationale']
    assert row['after']['positions'][0]['quantity'] == '100'
    assert result['manual_rehearsal']['temporary_journal_removed'] is True


@pytest.mark.parametrize('sleeve', [CORE, HOTSPOT])
@pytest.mark.parametrize('intent,quantity', [('REDUCE', '150'), ('EXIT', '200')])
def test_native_cross_entry_fifo_quantities_and_separate_reason_comparisons(dual, sleeve, intent, quantity):
    sell = _fill('cross', sleeve, intent=intent, day='2026-10-22')
    sell['fill']['quantity'] = quantity
    sell['entry_rationales'] = {'A': 'A breaker occurred; review A thesis',
        'B': 'B valuation exposure reduced; compare B holding rationale'}
    result = _manual(dual, [*_different_entries(sleeve), sell])
    _assert_no_authority(result)
    row = result['manual_rehearsal']['fills'][-1]
    assert row['original_entry_transaction_id'] is row['original_entry_reference'] is None
    assert [(item['transaction_id'], item['quantity']) for item in row['consumed_original_entries']] == [
        ('A', '100'), ('B', '50' if intent == 'REDUCE' else '100')]
    for item in row['consumed_original_entries']:
        name = item['transaction_id']
        assert item['original_entry_reference']['narrative']['thesis'] == name + ' distinct thesis'
        assert item['manual_rationale'] == sell['entry_rationales'][name]
    final = result['manual_rehearsal']['account_state']
    assert final['cash_cny'] == ('9485' if intent == 'REDUCE' else '9985')
    assert final['confirmed_fees_cny'] == '15'
    assert (final['positions'] == []) is (intent == 'EXIT')
    if intent == 'REDUCE':
        assert final['positions'][0]['quantity'] == '50'
    assert result['manual_rehearsal']['restart_equal'] is result['manual_rehearsal']['temporary_journal_removed'] is True


@pytest.mark.parametrize('fault', ['single_b', 'missing_map', 'missing_a', 'extra_entry', 'blank_reason'])
@pytest.mark.parametrize('intent,quantity', [('REDUCE', '150'), ('EXIT', '200')])
def test_cross_entry_sell_refuses_incomplete_or_misleading_reason_mapping(dual, fault, intent, quantity):
    sell = _fill('cross', CORE, intent=intent, day='2026-10-22', entry=None)
    sell['fill']['quantity'] = quantity
    sell['entry_rationales'] = {'A': 'A explicit reason', 'B': 'B explicit reason'}
    if fault == 'single_b': sell['entry_transaction_id'] = 'B'
    elif fault == 'missing_map': sell.pop('entry_rationales')
    elif fault == 'missing_a': sell['entry_rationales'].pop('A')
    elif fault == 'extra_entry': sell['entry_rationales']['UNCONSUMED'] = 'Not actually consumed'
    else: sell['entry_rationales']['A'] = ' '
    with pytest.raises(ValueError, match='Multi-Entry|per-consumed-Entry|Followup must reference'):
        _manual(dual, [*_different_entries(CORE), sell])
    assert not list(dual['workspace_root'].glob('.tmp/source-bound-dual-*'))


def test_add_link_can_remain_b_without_claiming_fifo_sell_identity(dual):
    add = _fill('add-to-B', CORE, intent='ADD', entry='B')
    result = _manual(dual, [*_different_entries(CORE), add])
    row = result['manual_rehearsal']['fills'][-1]
    assert row['original_entry_transaction_id'] == 'B' and row['consumed_original_entries'] == []
    assert row['original_entry_reference']['narrative']['thesis'] == 'B distinct thesis'
    assert row['original_entry_advisory_eligible'] is False


@pytest.mark.parametrize('fault', ['t1', 'duplicate', 'wrong_sleeve', 'budget', 'cash',
    'no_fee', 'snapshot', 'entry_context', 'unconfirmed', 'version', 'future', 'exit_label'])
def test_manual_refusals_clean_disposable_ledger_without_relaxing_native_guards(dual, fault):
    fills = [_fill('core', CORE), _fill('swing', HOTSPOT)]
    account = _account()
    expected = _read(dual)['source_identity']
    if fault == 't1': fills.append(_fill('sell', CORE, intent='EXIT', entry='core'))
    elif fault == 'duplicate': fills[1]['fill']['transaction_id'] = 'core'
    elif fault == 'wrong_sleeve': fills.append(_fill('sell', HOTSPOT, intent='EXIT', day='2026-10-22', entry='core'))
    elif fault == 'budget': fills[1]['fill']['price_cny'] = '31'
    elif fault == 'cash': fills[0]['fill']['price_cny'] = '110'
    elif fault == 'no_fee': fills[1]['fill'].pop('fees_cny')
    elif fault == 'snapshot': fills[1]['fill']['judgment_snapshot'] = {'approved': True}
    elif fault == 'entry_context': fills[1]['fill']['model_context'] = {'fake': True}
    elif fault == 'unconfirmed': account['confirmed'] = False
    elif fault == 'version': expected['hotspot']['entry_freeze_sha256'] = '0' * 64
    elif fault == 'future': fills[1]['fill']['trade_date'] = '2027-01-01'
    else:
        fills.append(_fill('sell', CORE, intent='REDUCE', day='2026-10-22', entry='core'))
    messages = dict(t1='insufficient sellable shares', duplicate=None,
        wrong_sleeve='same-security/sleeve', budget='cash/shared reserve', cash='cash/shared reserve',
        no_fee='fees_cny', snapshot='Caller cannot supply', entry_context='Caller cannot supply',
        unconfirmed='confirmed TEST_ONLY', version='identities changed',
        future='nonfuture account window', exit_label='remaining position')
    with pytest.raises((ValueError, KeyError, JournalConflict), match=messages[fault]) as caught:
        journey.run_source_bound_dual_sleeve_journey(**dual, expected_sources=expected,
            test_only_account=account, manual_fills=fills)
    if fault == 'duplicate':
        assert isinstance(caught.value, JournalConflict) and caught.value.code == 'DUPLICATE_TRANSACTION'
    assert not list(dual['workspace_root'].glob('.tmp/source-bound-dual-*'))


def test_missing_marks_never_become_zero_assets_or_risk_approval(dual):
    account = _account()
    account['hypothetical_marks'] = {}
    result = _manual(dual, [_fill('core', CORE)], test_only_account=account)
    state = result['manual_rehearsal']['account_state']
    assert state['hypothetical_equity_cny'] is None
    assert state['aggregate_holdings'][0]['market_value_cny'] is None
    assert state['risk_review']['status'] == 'BLOCKED_PRIVATE_INPUT'


def test_late_source_drift_rejects_even_after_bookkeeping_and_removes_journal(dual, monkeypatch):
    original = journey.PrivatePortfolioService.confirm_fill
    def drift(service, request):
        result = original(service, request)
        candidate = dual['core_root'] / 'runtime/pending/candidate.json'
        candidate.write_bytes(candidate.read_bytes() + b' ')
        return result
    monkeypatch.setattr(journey.PrivatePortfolioService, 'confirm_fill', drift)
    with pytest.raises(ValueError):
        _manual(dual, [_fill('core', CORE)])
    assert not list(dual['workspace_root'].glob('.tmp/source-bound-dual-*'))


@pytest.mark.parametrize('fault', ['receipt', 'bar'])
def test_native_swing_source_corruption_cannot_create_account(dual, fault):
    root = dual['hotspot_root']
    receipt = root / dual['hotspot_receipt_binding']['path']
    data = json.loads(receipt.read_bytes())
    target = receipt if fault == 'receipt' else root / data['source_bindings'][0]['path']
    target.write_bytes(target.read_bytes() + b' ')
    with pytest.raises(ValueError):
        _read(dual)
    assert not list(dual['workspace_root'].glob('.tmp/source-bound-dual-*'))


def test_real_native_value_and_sealed_swing_shared_cash_with_no_private_or_network(tmp_path, monkeypatch):
    core_location = os.environ.get('DUAL_JOURNEY_CORE_ROOT')
    swing_location = os.environ.get('DUAL_JOURNEY_SWING_ROOT')
    if not core_location or not swing_location:
        pytest.skip('Explicit public retained roots required')
    import io
    import socket
    from value_investment_agent.application.portfolio import private_portfolio_service
    core, swing = Path(core_location), Path(swing_location)
    config = swing / 'config/hotspot-replay-review-v1.json'
    config_hash = sha256(config.read_bytes()).hexdigest()
    binding = json.loads(config.read_bytes())['simulated_hotspot_lifecycle_receipt_binding']
    assert binding['path'] == 'runtime/swing-simulated-lifecycle/74bb1ed2e7944ea08d484464293409a6/receipt.json'
    assert binding['sha256'] == '677f5ae729ae9962b01caa3c00949f683838a98f197fc04b029649c4cc2d195a'
    native_open = io.open
    def guarded_open(file, mode='r', *args, **kwargs):
        path = Path(file).resolve()
        assert not {'.private', 'private', 'private-data'} & set(path.parts)
        if any(flag in mode for flag in 'wax+'):
            assert path.is_relative_to(tmp_path / '.tmp')
        return native_open(file, mode, *args, **kwargs)
    monkeypatch.setattr(io, 'open', guarded_open)
    monkeypatch.setattr(socket.socket, 'connect', lambda *args, **kwargs: pytest.fail('No network'))
    monkeypatch.setattr(private_portfolio_service, 'resolve_private_root',
        lambda **kwargs: pytest.fail('No private account resolver'))
    args = dict(core_root=core, hotspot_root=swing, workspace_root=tmp_path,
        now=datetime.now(timezone.utc), core_symbols=['600519'], hotspot_receipt_binding=binding)
    read = _read(args)
    candidate = read['source_identity']['core'][0]['candidate_binding']
    assert candidate['path'] == 'runtime/source-native-pending/3bb7bfe05c3f4c7d9a52d34b07588087/candidate.json'
    assert candidate['sha256'] == 'bfba1fb08f316cd4791e2f8d36490a86345e969d1f2c97663fb7a1e42aa912d8'
    assert read['core_cases'][0]['research']['confidence'] == '\u4f4e'
    assert read['core_cases'][0]['evaluation']['decision_action'] in {'WAIT', 'UNASSESSABLE'}
    assert read['hotspot_case']['entry_reference']['original_protection_price'] == '218.450'
    _assert_no_authority(read)
    result = _manual(args, [_fill('core', CORE, '600519'), _fill('swing', HOTSPOT, '300750')])
    _assert_no_authority(result)
    assert result['manual_rehearsal']['account_state']['cash_cny'] == '7990'
    assert len(result['manual_rehearsal']['account_state']['positions']) == 2
    assert result['manual_rehearsal']['temporary_journal_removed'] is True
    assert config_hash == sha256(config.read_bytes()).hexdigest()
    bad_swing = deepcopy(args)
    bad_swing['hotspot_receipt_binding'] = dict(binding, sha256='0' * 64)
    with pytest.raises(ValueError, match='hash mismatch'):
        _read(bad_swing)
    bad = deepcopy(result['source_identity'])
    bad['core'][0]['candidate_binding']['sha256'] = '0' * 64
    with pytest.raises(ValueError):
        journey.run_source_bound_dual_sleeve_journey(**args, expected_sources=bad,
            test_only_account=_account(), manual_fills=[_fill('never', CORE, '600519')])
    print(json.dumps(dict(source_identity=read['source_identity'],
        core_verdict=read['core_cases'][0]['evaluation']['decision_action'],
        hotspot_current_signal=read['hotspot_case']['current_signal'],
        hotspot_protection=read['hotspot_case']['entry_reference']['original_protection_price'],
        state=result['manual_rehearsal']['account_state'],
        removed=result['manual_rehearsal']['temporary_journal_removed']), ensure_ascii=False))
