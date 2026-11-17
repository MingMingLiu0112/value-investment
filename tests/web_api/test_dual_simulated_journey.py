"""HTTP contract over the real public-source readers and temporary portfolio service."""
from copy import deepcopy
from datetime import date
import json

from fastapi.testclient import TestClient
import pytest

from test_pending_candidate_supplement import registered
from test_hotspot_simulated_lifecycle import _seal
from value_investment_agent.application.portfolio import simulated_trade_journey as journey
from value_investment_agent.presentation.web_api.app import create_app
from value_investment_agent.presentation.web_api import dual_simulated_journey_routes as routes


URL = '/api/v1/simulated-trade-journey/dual-sleeve'


def _request(core='600887', hotspot='600519'):
    def fill(symbol, sleeve):
        return dict(intent='BUY', rationale='Explicit TEST_ONLY hypothesis, not strategy advice',
            fill=dict(transaction_id='test-' + sleeve, side='BUY', sleeve=sleeve,
                symbol=symbol, exchange='SSE', quantity='100', price_cny='10', fees_cny='5',
                trade_date='2026-10-21', trading_unit='100'),
            entry_narrative=dict(thesis='TEST_ONLY hypothesis', hold_logic='Only if the hypothesis survives',
                invalidation_conditions=['Evidence contradicts the hypothesis']))
    return dict(confirmed_hypothetical=True,
        expected_sources=dict(core=[dict(symbol=core, candidate_binding=dict(path='runtime/test.json', sha256='a'*64),
            research_version='TEST_ONLY')], hotspot=dict(symbol=hotspot,
                receipt_binding=dict(path='runtime/test.json', sha256='b'*64), entry_freeze_sha256='c'*64)),
        test_only_account=dict(namespace='TEST_ONLY', confirmed=True, opening_day='2026-10-21',
            initial_cash_cny='10000', policy=journey._policy(date(2026, 10, 21)),
            hypothetical_marks={core: '10', hotspot: '10'}),
        manual_fills=[fill(core, 'CORE_VALUE'), fill(hotspot, 'HOTSPOT_SATELLITE')])


def test_missing_sources_rejects_without_default_demo_or_private_access(tmp_path, monkeypatch):
    from value_investment_agent.application.portfolio import private_portfolio_service
    monkeypatch.setattr(private_portfolio_service, 'resolve_private_root',
        lambda *a, **k: pytest.fail('Public read cannot resolve an ACTUAL account'))
    response = TestClient(create_app(root=tmp_path)).get(URL)
    assert response.status_code == 409 and response.json()['action'] == 'no_order'
    assert response.headers['cache-control'] == 'no-store'
    assert not list(tmp_path.rglob('*.jsonl'))


@pytest.mark.parametrize('fault', ['confirmation', 'numeric_confirmation', 'account_confirmation', 'actual',
    'workspace', 'clock', 'missing_identity', 'extra_identity', 'sell_session', 'authority',
    'numeric_quantity', 'nonfinite_price', 'empty', 'too_many', 'entry_override'])
def test_untrusted_http_scope_rejected_before_application(tmp_path, monkeypatch, fault):
    payload = _request()
    item = payload['manual_fills'][0]
    if fault == 'confirmation': payload.pop('confirmed_hypothetical')
    elif fault == 'numeric_confirmation': payload['confirmed_hypothetical'] = 1
    elif fault == 'account_confirmation': payload['test_only_account']['confirmed'] = 1
    elif fault == 'actual': payload['test_only_account']['namespace'] = 'ACTUAL'
    elif fault == 'workspace': payload['workspace_root'] = '../private'
    elif fault == 'clock': payload['now'] = '2027-01-01T00:00:00Z'
    elif fault == 'missing_identity': payload.pop('expected_sources')
    elif fault == 'extra_identity': payload['expected_sources']['approval'] = True
    elif fault == 'sell_session': item['fill']['next_sell_session'] = '2026-10-21'
    elif fault == 'authority': item['fill']['strategy_admitted'] = True
    elif fault == 'numeric_quantity': item['fill']['quantity'] = 100
    elif fault == 'nonfinite_price': item['fill']['price_cny'] = 'NaN'
    elif fault == 'empty': payload['manual_fills'] = []
    elif fault == 'too_many': payload['manual_fills'] *= 7
    else: item['fill']['entry_context'] = {'approved': True}
    monkeypatch.setattr(routes, '_run', lambda *a, **k: pytest.fail('Validation must precede use case'))
    response = TestClient(create_app(root=tmp_path)).post(URL, json=payload)
    assert response.status_code == 422 and response.json()['action'] == 'no_order'
    assert not list(tmp_path.rglob('*.jsonl'))


@pytest.fixture
def client_sources(registered, monkeypatch):
    root, symbol, _, _ = registered
    binding = _seal(root)
    (root / 'config/hotspot-replay-review-v1.json').write_text(json.dumps(dict(action='no_order',
        simulated_hotspot_lifecycle_receipt_binding=binding)), encoding='utf-8')
    actual = routes.run_source_bound_dual_sleeve_journey
    # Select the registered synthetic company, retaining all native verification/accounting.
    monkeypatch.setattr(routes, 'run_source_bound_dual_sleeve_journey',
        lambda **kwargs: actual(**dict(kwargs, core_symbols=(symbol,))))
    return TestClient(create_app(root=root)), root, symbol


def test_public_get_and_explicit_post_share_real_one_ledger_without_admission(client_sources, monkeypatch):
    client, root, symbol = client_sources
    from value_investment_agent.application.portfolio import private_portfolio_service
    monkeypatch.setattr(private_portfolio_service, 'resolve_private_root',
        lambda *a, **k: pytest.fail('No private root for temporary public simulation'))
    before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
    response = client.get(URL)
    assert response.status_code == 200, response.text
    read = response.json()
    assert read['manual_rehearsal']['status'] == 'NOT_REQUESTED'
    assert before == {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
    payload = _request(symbol)
    stale = client.post(URL, json=payload)
    assert stale.status_code == 409 and stale.json()['status'] == 'RESEARCH_VERSION_CHANGED'
    payload['expected_sources'] = read['source_identity']
    response = client.post(URL, json=payload)
    assert response.status_code == 200, response.text
    result = response.json()
    assert response.headers['cache-control'] == 'no-store'
    assert result['formal_eligibility'] is result['strategy_validated'] is result['approval_changed'] is False
    assert result['position_guidance'] is None and result['action'] == 'no_order'
    manual = result['manual_rehearsal']
    assert manual['account_state']['cash_cny'] == '7990'
    assert manual['account_state']['confirmed_fees_cny'] == '10'
    assert len(manual['account_state']['aggregate_holdings']) == 2
    assert manual['temporary_journal_removed'] is manual['restart_equal'] is True
    assert manual['actual_account_used'] is manual['persistent_simulated_portfolio'] is False
    assert before == {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('fault', ['policy', 'wrong_symbol', 'wrong_exchange', 'empty_narrative', 'future',
    'duplicate', 'missing_entry', 'budget'])
def test_application_refusals_stay_409_and_remove_temp_journal(client_sources, fault):
    client, root, symbol = client_sources
    payload = _request(symbol)
    payload['expected_sources'] = client.get(URL).json()['source_identity']
    item = payload['manual_fills'][0]
    if fault == 'policy': payload['test_only_account']['policy']['sleeves']['CORE_VALUE']['cash_cny'] = '99999'
    elif fault == 'wrong_symbol': item['fill']['symbol'] = '600000'
    elif fault == 'wrong_exchange': item['fill']['exchange'] = 'SZSE'
    elif fault == 'empty_narrative': item.pop('entry_narrative')
    elif fault == 'future': item['fill']['trade_date'] = '2099-01-01'
    elif fault == 'duplicate': payload['manual_fills'][1]['fill']['transaction_id'] = item['fill']['transaction_id']
    elif fault == 'missing_entry': item['intent'] = 'ADD'; item.pop('entry_narrative')
    else: item['fill']['price_cny'] = '101'
    before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
    response = client.post(URL, json=payload)
    assert response.status_code == 409, response.text
    assert response.json()['status'] == 'SIMULATED_REHEARSAL_REJECTED'
    assert before == {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_server_source_pointer_race_is_not_success(client_sources, monkeypatch):
    client, root, _ = client_sources
    actual = routes.run_source_bound_dual_sleeve_journey
    def change_after_read(**kwargs):
        result = actual(**kwargs)
        path = root / 'config/hotspot-replay-review-v1.json'
        path.write_bytes(path.read_bytes() + b'\n')
        return result
    monkeypatch.setattr(routes, 'run_source_bound_dual_sleeve_journey', change_after_read)
    assert client.get(URL).status_code == 409


@pytest.mark.parametrize('cross_batch', [False, True])
def test_http_sell_explanation_matches_real_fifo_entries(client_sources, cross_batch):
    client, root, symbol = client_sources
    payload = _request(symbol)
    payload['expected_sources'] = client.get(URL).json()['source_identity']
    first = payload['manual_fills'][0]
    first['fill']['transaction_id'] = 'core-A'
    first['entry_narrative']['thesis'] = 'Original A thesis'
    second = deepcopy(first)
    second['fill']['transaction_id'] = 'core-B'
    second['entry_narrative']['thesis'] = 'Original B thesis'
    payload['manual_fills'].append(second)
    sell = dict(intent='EXIT' if cross_batch else 'REDUCE', rationale='TEST_ONLY manual sale review',
        fill=dict(transaction_id='sell', side='SELL', sleeve='CORE_VALUE', symbol=symbol,
            exchange='SSE', quantity='200' if cross_batch else '100', price_cny='10', fees_cny='5',
            trade_date='2026-10-22'))
    if cross_batch:
        sell['entry_rationales'] = {'core-A': 'Review A hypothesis', 'core-B': 'Review B hypothesis'}
    else:
        sell['entry_transaction_id'] = 'core-B'
    payload['manual_fills'].append(sell)
    response = client.post(URL, json=payload)
    if not cross_batch:
        assert response.status_code == 409
    else:
        assert response.status_code == 200, response.text
        result = response.json()
        sold = result['manual_rehearsal']['fills'][-1]
        assert sold['original_entry_reference'] is sold['original_entry_transaction_id'] is None
        assert [row['transaction_id'] for row in sold['consumed_original_entries']] == ['core-A', 'core-B']
        assert [row['original_entry_reference']['narrative']['thesis'] for row in sold['consumed_original_entries']] == [
            'Original A thesis', 'Original B thesis']
        assert [row['quantity'] for row in sold['consumed_original_entries']] == ['100', '100']
        assert result['manual_rehearsal']['temporary_journal_removed'] is True
        assert result['formal_eligibility'] is False
    assert not list(root.glob('.tmp/source-bound-dual-*'))
