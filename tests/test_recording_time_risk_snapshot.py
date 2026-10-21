"""Only isolated journals and test trust roots; never resolve real private data."""
from copy import deepcopy
from datetime import timedelta
import hashlib
import json

import pytest

from test_private_risk_preview import actual_contract_preview, register_hotspot_contract, NOW, ASSUMPTIONS
from value_investment_agent.application.portfolio import judgment_snapshot as snapshots
from value_investment_agent.application.portfolio import private_risk_preview as preview
from value_investment_agent.application.portfolio.private_portfolio_service import PrivatePortfolioService, JournalConflict


@pytest.fixture
def recording(actual_contract_preview, tmp_path, monkeypatch):
    ledger, legacy, _, packet, _, _ = actual_contract_preview
    ledger._clock = lambda: NOW
    register_hotspot_contract(tmp_path, legacy)
    packet['price_conditions']['items'][0]['price_action_plan'] = deepcopy(legacy)
    packet['content_sha256'] = 'c' * 64
    monkeypatch.setattr(snapshots, 'load_current_packet', lambda root: (deepcopy(packet), None))
    request = dict(idempotency_key='recorded-fill', expected_revision=len(ledger.records()),
        fill=dict(transaction_id='isolated-recording-risk', symbol='300364', exchange='SZSE',
            side='BUY', sleeve='HOTSPOT_SATELLITE', quantity='200', price_cny='10', fees_cny='5',
            trade_date='2026-10-14', next_sell_session='2026-10-15', trading_unit='100',
            decision_id='hotspot-300364', research_version=legacy['research_version']),
        risk_preview={'assumptions': deepcopy(ASSUMPTIONS)})
    def provider(selected):
        return preview.preview_private_hotspot_risk(ledger.journal, repository_root=tmp_path,
            generated_at=NOW, payload=selected, authenticated_subject='LOCAL_OPERATOR')
    return ledger, request, provider, packet


def confirm_and_reload(ledger, digest):
    ledger.confirm_fill(dict(idempotency_key='confirm-recorded-fill', expected_revision=len(ledger.records()),
        prepared_record_sha256=digest, confirmed_at=NOW.isoformat(), confirmation_note='Isolated recorded execution'))
    return PrivatePortfolioService(ledger.journal).portfolio_view()['trades'][0]['judgment_snapshot']


def test_real_preview_is_optional_immutable_recording_time_evidence(recording, tmp_path):
    ledger, request, provider, packet = recording
    calls = []
    def capture(selected):
        calls.append(deepcopy(selected))
        return provider(selected)
    prepared, digest = ledger.prepare_fill(request, repository_root=tmp_path, risk_capture_provider=capture)
    saved = deepcopy(prepared['draft']['fill']['judgment_snapshot'])
    risk = saved['personal_risk_at_trade']
    assert risk['status'] == 'SERVER_VERIFIED_RECORDING_TIME_RISK', prepared
    assert risk['scope'] == 'RECORDING_TIME_RISK_NOT_PROVEN_PRETRADE'
    assert saved['recorded_at'] == risk['verified_at']
    assert risk['review_quantity'] == 100
    assert request['fill']['quantity'] == '200'  # Recorded facts are not capped by advisory quantities.
    assert risk['formal_eligibility'] is risk['trade_eligible'] is risk['trade_time_availability_proven'] is False
    assert saved['trade_time_availability_proven'] is saved['plan']['formal_eligibility'] is False
    assert risk['journal_revision'] == request['expected_revision']
    assert risk['journal_tip_sha256'] == ledger.records()[-2]['record_sha256']
    assert calls == [{'symbol': '300364', 'assumptions': ASSUMPTIONS}]
    assert 'scenario_preview' not in risk
    unsigned = {key: value for key, value in saved.items() if key != 'snapshot_sha256'}
    assert saved['snapshot_sha256'] == hashlib.sha256(json.dumps(unsigned, ensure_ascii=False,
        sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()
    packet['publication_id'] = 'later-publication'
    prepared['draft']['fill']['judgment_snapshot']['personal_risk_at_trade']['review_quantity'] = 999
    assert ledger.prepare_fill(request, repository_root=tmp_path, risk_capture_provider=capture)[1] == digest
    assert len(calls) == 1
    assert confirm_and_reload(ledger, digest) == saved


def test_core_uses_existing_core_assumptions_and_keeps_public_eligibility(recording, actual_contract_preview, tmp_path):
    ledger, request, provider, packet = recording
    core = actual_contract_preview[2]
    core['research_version'] = 'isolated-core-version'
    packet['value_price_conditions']['300364'] = deepcopy(core)
    request['fill'].update(sleeve='CORE_VALUE', decision_id='300364', research_version=core['research_version'])
    request['risk_preview']['assumptions'] = {key: ASSUMPTIONS[key] for key in (
        'entry_slippage_cny', 'buy_fee_fraction', 'minimum_buy_fee_cny', 'lot_size', 'max_trade_notional_cny')}
    prepared, digest = ledger.prepare_fill(request, repository_root=tmp_path, risk_capture_provider=provider)
    snapshot = prepared['draft']['fill']['judgment_snapshot']
    risk = snapshot['personal_risk_at_trade']
    assert risk['status'] == 'SERVER_VERIFIED_RECORDING_TIME_RISK', prepared
    assert risk['strategy'] == 'CORE_VALUE' and risk['review_quantity'] == 100
    assert risk['formal_eligibility'] is False
    assert snapshot['plan'] == core and core['formal_eligibility'] is True
    assert confirm_and_reload(ledger, digest) == snapshot


@pytest.mark.parametrize('fault', ['account', 'revision', 'symbol', 'sleeve', 'research', 'publication',
    'future', 'old_time', 'namespace', 'source', 'exception', 'verifier_exception', 'no_provider',
    'client_result', 'client_scenario', 'missing_snapshot', 'snapshot_exception', 'sell'])
def test_invalid_optional_risk_never_prevents_recording(recording, tmp_path, monkeypatch, fault):
    ledger, request, provider, packet = recording
    if fault == 'client_result':
        request['risk_preview']['result'] = {'review_quantity': 999, 'formal_eligibility': True}
    if fault == 'client_scenario':
        request['risk_preview']['scenario'] = {'acknowledged': True}
    if fault == 'missing_snapshot':
        packet['price_conditions']['items'] = []
    if fault == 'snapshot_exception':
        monkeypatch.setattr(snapshots, 'load_current_packet', lambda *a: (_ for _ in ()).throw(RuntimeError('private-path')))
    if fault == 'sell':
        # No same-sleeve stock exists; recording must still use the original
        # ledger legality check rather than turn a buy preview into sell approval.
        request['fill']['side'] = 'SELL'
        from value_investment_agent.application.portfolio.private_portfolio_service import JournalValidationError
        with pytest.raises(JournalValidationError):
            ledger.prepare_fill(request, repository_root=tmp_path, risk_capture_provider=provider)
        return
    def capture(selected):
        if fault == 'exception':
            raise RuntimeError('private-path-must-not-be-saved')
        result = provider(selected)
        if fault == 'account': result['facts']['account_scope'] = 'foreign-account'
        if fault == 'revision': result['facts']['revision'] += 1
        if fault == 'symbol': result['actionable_decision']['symbol'] = '600519'
        if fault == 'sleeve': result['actionable_decision']['strategy'] = 'CORE_VALUE'
        if fault == 'research': result['sizing_preview']['plan_binding']['plan']['research_version'] = 'other'
        if fault == 'publication': result['sizing_preview']['plan_binding']['publication_id'] = 'other'
        if fault in {'future', 'old_time'}:
            result['actionable_decision']['generated_at'] = (NOW + timedelta(seconds=1 if fault == 'future' else -1)).isoformat()
        if fault == 'namespace': result['engine']['namespace'] = 'SIMULATED'
        if fault == 'source': (tmp_path / 'case.json').write_bytes(b'changed-source')
        if fault == 'verifier_exception':
            monkeypatch.setattr(preview, '_current_plan', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('private-path')))
        return result
    prepared, digest = ledger.prepare_fill(request, repository_root=tmp_path,
        risk_capture_provider=None if fault == 'no_provider' else capture)
    assert prepared['status'] == 'FILL_PREPARED'
    assert prepared['personal_risk_capture']['status'] == 'UNAVAILABLE'
    saved = prepared['draft']['fill']['judgment_snapshot']
    if saved is not None:
        assert saved['personal_risk_at_trade'] is None
        assert saved['personal_risk_capture']['formal_eligibility'] is False
    assert 'private-path' not in json.dumps(prepared)
    assert confirm_and_reload(ledger, digest) == saved


def test_blocked_server_risk_is_preserved_as_blocked_not_approval(recording, tmp_path):
    ledger, request, provider, _ = recording
    request['risk_preview']['assumptions']['max_trade_notional_cny'] = '1'
    prepared, digest = ledger.prepare_fill(request, repository_root=tmp_path, risk_capture_provider=provider)
    risk = prepared['draft']['fill']['judgment_snapshot']['personal_risk_at_trade']
    assert risk['status'] == 'SERVER_VERIFIED_RECORDING_TIME_RISK'
    assert risk['blockers'] and risk['review_quantity'] is None
    assert risk['decision_action'] not in {'BUY', 'ADD'}
    assert risk['formal_eligibility'] is False
    confirm_and_reload(ledger, digest)


def test_no_selection_ignores_forged_client_snapshot_and_does_not_call_provider(recording, tmp_path):
    ledger, request, _, _ = recording
    request.pop('risk_preview')
    request['fill']['judgment_snapshot'] = {'personal_risk_at_trade': {'review_quantity': 999}}
    def forbidden(_):
        pytest.fail('No opt-in must mean no risk calculation')
    prepared, _ = ledger.prepare_fill(request, repository_root=tmp_path, risk_capture_provider=forbidden)
    assert 'personal_risk_capture' not in prepared
    assert prepared['draft']['fill']['judgment_snapshot']['personal_risk_at_trade'] is None


def test_account_drift_keeps_existing_revision_conflict(recording, tmp_path):
    ledger, request, provider, _ = recording
    def capture(selected):
        result = provider(selected)
        ledger.reconcile(dict(idempotency_key='concurrent-statement', expected_revision=len(ledger.records()),
            reconciled_at=NOW.isoformat(), confirmation_note='Isolated concurrent account change'))
        return result
    with pytest.raises(JournalConflict):
        ledger.prepare_fill(request, repository_root=tmp_path, risk_capture_provider=capture)
    assert not any(row['kind'] == 'FILL_PREPARED' for row in ledger.records())


def test_lawful_sell_records_without_borrowing_buy_risk(recording, tmp_path):
    ledger, request, provider, _ = recording
    first, digest = ledger.prepare_fill(request, repository_root=tmp_path, risk_capture_provider=provider)
    confirm_and_reload(ledger, digest)
    sell = deepcopy(request)
    sell.update(idempotency_key='sell-fill', expected_revision=len(ledger.records()))
    sell['fill'].update(side='SELL', transaction_id='isolated-sell', next_sell_session=None, trade_date='2026-10-15')
    def forbidden(_):
        pytest.fail('A sell must not borrow a buy preview')
    prepared, _ = ledger.prepare_fill(sell, repository_root=tmp_path, risk_capture_provider=forbidden)
    assert prepared['status'] == 'FILL_PREPARED'
    assert prepared['personal_risk_capture']['status'] == 'UNAVAILABLE'
    assert prepared['draft']['fill']['judgment_snapshot']['personal_risk_at_trade'] is None


def test_existing_http_prepare_reuses_authenticated_preview_only(recording, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from value_investment_agent.presentation.web_api import private_routes
    from value_investment_agent.presentation.web_api.app import create_app
    ledger, request, provider, _ = recording
    class Clock:
        @staticmethod
        def now(tz=None):
            return NOW
    monkeypatch.setattr(private_routes, 'datetime', Clock)
    monkeypatch.setattr(PrivatePortfolioService, '_now', lambda self: NOW)
    monkeypatch.setattr(private_routes, 'resolve_private_root', lambda **kw: ledger.journal.path)
    calls = []
    def preview_call(journal, **kwargs):
        calls.append(deepcopy(kwargs['payload']))
        assert kwargs['authenticated_subject'] == 'LOCAL_OPERATOR'
        assert journal.path == ledger.journal.path
        # The isolated HTTP clock is also supplied by the server.
        result = provider(kwargs['payload'])
        result['actionable_decision']['generated_at'] = kwargs['generated_at'].isoformat()
        return result
    monkeypatch.setattr(private_routes, 'preview_private_hotspot_risk', preview_call)
    secret = 'TEST_ONLY-recording-risk-bootstrap-' + 'a' * 32
    client = TestClient(create_app(tmp_path, port=8791, bootstrap_secret=secret),
        base_url='http://127.0.0.1:8791', client=('127.0.0.1', 51000))
    client.headers.update({'host': '127.0.0.1:8791', 'origin': 'http://127.0.0.1:8791'})
    endpoint = '/api/v1/private/fills/prepare'
    before = ledger.journal.path.read_bytes()
    assert client.post(endpoint, json=request).status_code == 401
    assert not calls and ledger.journal.path.read_bytes() == before
    token = client.post('/api/v1/private/session/unlock', json={'bootstrap_token': secret}).json()['token']
    client.headers['x-local-session'] = token
    response = client.post(endpoint, json=request)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['status'] == 'FILL_PREPARED'
    assert calls == [{'symbol': '300364', 'assumptions': ASSUMPTIONS}]
    assert data['personal_risk_capture']['status'] == 'SERVER_VERIFIED_RECORDING_TIME_RISK'
    assert data['personal_risk_capture']['formal_eligibility'] is False
    assert 'no-store' in response.headers['cache-control']


@pytest.mark.parametrize('selected', [False, True])
def test_retrospective_distinguishes_recording_risk_from_unproven_pretrade(recording, tmp_path, selected):
    from datetime import datetime, timezone
    from value_investment_agent.application.research.agent_review.daily_retrospective import run_daily_retrospective_mock
    ledger, request, provider, _ = recording
    if not selected:
        request.pop('risk_preview')
    _, digest = ledger.prepare_fill(request, repository_root=tmp_path, risk_capture_provider=provider)
    saved = confirm_and_reload(ledger, digest)
    before = ledger.journal.path.read_bytes()
    report = run_daily_retrospective_mock(journal=ledger.journal, review_date=NOW.date(),
        generated_at=datetime(2030, 1, 1, tzinfo=timezone.utc))
    item = report['items'][0]
    assert item['recording_time_risk_status'] == ('AVAILABLE_RECORDING_TIME_ONLY' if selected else 'UNAVAILABLE')
    assert item['recording_time_personal_risk'] == saved['personal_risk_at_trade']
    assert 'PERSONAL_RISK_AT_TRADE_NOT_PROVEN' in item['evidence_gaps']
    assert ('RECORDING_TIME_PERSONAL_RISK_MISSING' in item['evidence_gaps']) is not selected
    assert item['trade_time_availability_proven'] is report['formal_eligibility'] is False
    assert ledger.journal.path.read_bytes() == before


@pytest.mark.parametrize('fault', ['tip', 'revision', 'account', 'symbol', 'strategy', 'pretrade', 'time'])
def test_retrospective_rejects_risk_binding_drift(recording, tmp_path, fault):
    from datetime import datetime, timezone
    from value_investment_agent.application.research.agent_review.daily_retrospective import _saved_recording_risk
    ledger, request, provider, _ = recording
    _, digest = ledger.prepare_fill(request, repository_root=tmp_path, risk_capture_provider=provider)
    saved = confirm_and_reload(ledger, digest)
    risk = saved['personal_risk_at_trade']
    if fault == 'tip': risk['journal_tip_sha256'] = '0' * 64
    if fault == 'revision': risk['journal_revision'] = True
    if fault == 'account': risk['account_scope'] = 'foreign'
    if fault == 'symbol': risk['symbol'] = '600519'
    if fault == 'strategy': risk['strategy'] = 'CORE_VALUE'
    if fault == 'pretrade': risk['trade_time_availability_proven'] = True
    if fault == 'time': risk['generated_at'] = '2031-01-01T00:00:00+00:00'
    result, gap = _saved_recording_risk(saved, ledger.portfolio_view()['trades'][0], ledger.records(),
        datetime(2030, 1, 1, tzinfo=timezone.utc))
    assert result is None and gap == 'RECORDING_TIME_PERSONAL_RISK_INVALID'
