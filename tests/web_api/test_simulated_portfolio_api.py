"""Persistent HTTP hypotheses use real journals, source readers and FIFO arithmetic."""
from copy import deepcopy
from datetime import datetime, timezone
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from test_source_native_candidate_v2 import synthetic_native
from test_hotspot_simulated_lifecycle import _seal
from value_investment_agent.application.product.source_native_candidate_v2 import prepare_source_native_candidate
from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.application.portfolio import simulated_portfolio_workbench as workbench
from value_investment_agent.application.portfolio.private_portfolio_service import PrivateJournal
from value_investment_agent.presentation.web_api.simulated_portfolio_routes import register_simulated_portfolio_routes


URL = '/api/v1/simulated-portfolio'


def client(root):
    api = FastAPI()
    register_simulated_portfolio_routes(api, project=root)
    return TestClient(api, base_url='http://127.0.0.1:8001', client=('127.0.0.1', 12345))


def read(http):
    result = http.get(URL)
    assert result.status_code == 200, result.text
    return result.json()


def request(view, key, **extra):
    return dict(confirmed_hypothetical=True, idempotency_key=key,
        expected_revision=view['account']['revision'], **extra)


def initialize(http):
    view = read(http)
    payload = request(view, 'initialize', as_of='2026-10-20', cash_cny='10000',
        confirmed_at=view['server_now'], confirmation_note='Explicit TEST_ONLY paper capital')
    response = http.post(URL + '/initialize', json=payload)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def sources(synthetic_native, monkeypatch):
    root, package_ref, ledger_ref = synthetic_native
    destination = root / 'runtime/source-native-pending/TEST_ONLY'
    candidate = prepare_source_native_candidate(root=root, package_binding=package_ref,
        ledger_binding=ledger_ref, output_dir=destination, now=datetime.now(timezone.utc))
    symbol = candidate['symbol']
    (root / 'config').mkdir(exist_ok=True)
    (root / 'config/user-research-workflow-v1.json').write_text(json.dumps(dict(
        schema_version='user-research-workflow-v1', action='no_order',
        supplemental_review_candidates={symbol: dict(path=(destination / 'candidate.json').relative_to(root).as_posix(),
            sha256=sha256_file(destination / 'candidate.json'))})), encoding='utf-8')
    binding = _seal(root)
    (root / 'config/hotspot-replay-review-v1.json').write_text(json.dumps(dict(action='no_order',
        simulated_hotspot_lifecycle_receipt_binding=binding)), encoding='utf-8')
    native = workbench._source_bound_cases
    monkeypatch.setattr(workbench, '_source_bound_cases', lambda project, symbols, now:
        native(project, (symbol,), now))
    from value_investment_agent.application.portfolio import private_portfolio_service
    monkeypatch.setattr(private_portfolio_service, 'resolve_private_root',
        lambda *a, **k: pytest.fail('Simulation cannot resolve a private account'))
    return root, symbol


def prepare_and_confirm(http, view, symbol, *, tx='paper-buy', side='BUY', quantity='100', day='2026-10-21'):
    payload = request(view, tx, fill=dict(transaction_id=tx, side=side, sleeve='CORE_VALUE',
        symbol=symbol, exchange='SSE', quantity=quantity, price_cny='10', fees_cny='5', trade_date=day))
    prepared = http.post(URL + '/prepare-fill', json=payload)
    assert prepared.status_code == 200, prepared.text
    draft = prepared.json()
    confirm = request(draft, tx + '-confirm',
        prepared_record_sha256=draft['mutation']['record_sha256'],
        confirmed_at=draft['server_now'], confirmation_note='Manual simulated fill only')
    response = http.post(URL + '/confirm-fill', json=confirm)
    assert response.status_code == 200, response.text
    return response.json(), confirm


def test_empty_get_is_read_only_and_account_survives_independent_app(sources):
    root, symbol = sources
    http = client(root)
    before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
    empty = read(http)
    assert empty['account']['status'] == 'NOT_INITIALIZED'
    assert empty['sources']['status'] == 'AVAILABLE'
    assert before == {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
    view, confirmation = prepare_and_confirm(http, initialize(http), symbol)
    assert view['account']['portfolio']['cash_cny'] == '8995'
    assert view['account']['portfolio']['positions'][0]['quantity'] == '100'
    repeated = http.post(URL + '/confirm-fill', json=confirmation)
    assert repeated.json()['mutation'] == view['mutation']
    restored = read(client(root))
    assert restored['account'] == view['account']
    assert restored['account']['risk_snapshot']['namespace'] == 'SIMULATED'
    assert restored['account']['formal_eligibility'] is False
    assert restored['account']['position_guidance'] is None
    assert (root / 'runtime/simulated-portfolios-v1/paper-dual-v1/journal.jsonl').exists()


def test_entry_freezes_displayed_source_and_idempotent_retry(sources):
    root, symbol = sources
    http = client(root)
    view, _ = prepare_and_confirm(http, initialize(http), symbol)
    source = next(row for row in view['sources']['items'] if row['sleeve'] == 'CORE_VALUE')
    payload = request(view, 'entry', fill_record_sha256=view['mutation']['record_sha256'],
        source_id=source['id'], expected_source_binding=source['candidate_binding'],
        narrative=dict(thesis='Conditional cash thesis', hold_logic='Follow the original evidence',
            invalidation_conditions=['Permanent cash impairment']), confirmation_note='TEST_ONLY reconstructed thesis')
    wrong = deepcopy(payload)
    wrong['expected_source_binding']['sha256'] = 'f' * 64
    assert http.post(URL + '/confirm-entry', json=wrong).json()['status'] == 'RESEARCH_VERSION_CHANGED'
    response = http.post(URL + '/confirm-entry', json=payload)
    assert response.status_code == 200, response.text
    result = response.json()
    entry = result['account']['entries'][0]
    assert entry['hypothesis']['thesis'] == 'Conditional cash thesis'
    assert entry['original_pit_proven'] is False
    replay = http.post(URL + '/confirm-entry', json=payload)
    assert replay.status_code == 200, replay.text
    assert replay.json()['mutation'] == result['mutation']
    assert read(client(root))['account']['entries'] == result['account']['entries']


def test_both_strategy_sleeves_spend_the_same_persistent_cash(sources):
    root, symbol = sources
    http = client(root)
    view, _ = prepare_and_confirm(http, initialize(http), symbol)
    swing = next(row for row in view['sources']['items'] if row['sleeve'] == 'HOTSPOT_SATELLITE')
    prepared = http.post(URL + '/prepare-fill', json=request(view, 'swing-buy', fill=dict(
        transaction_id='swing-buy', side='BUY', sleeve='HOTSPOT_SATELLITE',
        symbol=swing['symbol'], exchange='SSE', quantity='100', price_cny='10',
        fees_cny='5', trade_date='2026-10-21')))
    assert prepared.status_code == 200, prepared.text
    draft = prepared.json()
    confirmed = http.post(URL + '/confirm-fill', json=request(draft, 'swing-confirm',
        prepared_record_sha256=draft['mutation']['record_sha256'],
        confirmed_at=draft['server_now'], confirmation_note='Separate sleeve, same simulated capital'))
    assert confirmed.status_code == 200, confirmed.text
    result = confirmed.json()
    assert result['account']['portfolio']['cash_cny'] == '7990'
    assert len(result['account']['portfolio']['positions']) == 2
    assert len(result['account']['portfolio']['trades']) == 2
    assert read(client(root))['account'] == result['account']


def test_cancel_prepared_fill_does_not_change_cash(sources):
    root, symbol = sources
    http = client(root)
    view = initialize(http)
    prepared = http.post(URL + '/prepare-fill', json=request(view, 'draft', fill=dict(
        transaction_id='draft', side='BUY', sleeve='CORE_VALUE', symbol=symbol, exchange='SSE',
        quantity='100', price_cny='10', fees_cny='5', trade_date='2026-10-21')))
    draft = prepared.json()
    payload = request(draft, 'cancel', prepared_record_sha256=draft['mutation']['record_sha256'],
        confirmed_at=draft['server_now'], confirmation_note='Correct the hypothetical draft first')
    cancelled = http.post(URL + '/cancel-fill', json=payload)
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()['account']['portfolio']['cash_cny'] == '10000'
    assert cancelled.json()['account']['portfolio']['pending_draft'] is None
    assert cancelled.json()['account']['portfolio']['positions'] == []


def test_confirmed_correction_appends_and_survives_restart_and_retry(sources):
    root, symbol = sources
    http = client(root)
    view, _ = prepare_and_confirm(http, initialize(http), symbol)
    target = view['mutation']['record_sha256']
    journal = root / 'runtime/simulated-portfolios-v1/paper-dual-v1/journal.jsonl'
    original = journal.read_bytes()
    latest = read(http)
    payload = request(latest, 'correct-price', target_fill_record_sha256=target,
        expected_original_version=target, changes=dict(price_cny='12', fees_cny='7'),
        confirmed_at=latest['server_now'], reason='Human confirmed TEST_ONLY price and fee correction')
    response = http.post(URL + '/correct-fill', json=payload)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['account']['portfolio']['cash_cny'] == '8793'
    assert result['account']['portfolio']['trades'][0]['record_sha256'] == target
    assert journal.read_bytes().startswith(original)
    assert len(journal.read_bytes().splitlines()) == len(original.splitlines()) + 1
    correction = result['account']['fill_corrections'][target]
    assert correction['effective_version_sha256'] == result['mutation']['record_sha256']
    assert correction['original_fill']['price_cny'] == '10'
    assert correction['effective_fill']['price_cny'] == '12'
    assert result['account']['correction_reconciliation_status'] == 'INVALIDATED_RECONCILIATION_REQUIRED'
    assert http.post(URL + '/correct-fill', json=payload).json()['mutation'] == result['mutation']
    assert read(client(root))['account'] == result['account']
    before = journal.read_bytes()
    stale = dict(payload, idempotency_key='stale-correction', expected_revision=result['account']['revision'])
    assert http.post(URL + '/correct-fill', json=stale).status_code == 409
    assert journal.read_bytes() == before


@pytest.mark.parametrize('changes', [{'symbol': '600000'}, {'quantity': '0'}, {'fees_cny': '-1'}])
def test_correction_cannot_change_identity_or_invalid_numbers(tmp_path, changes):
    payload = dict(confirmed_hypothetical=True, idempotency_key='bad-correction', expected_revision=0,
        target_fill_record_sha256='a' * 64, expected_original_version='a' * 64, changes=changes,
        confirmed_at=datetime.now(timezone.utc).isoformat(), reason='TEST_ONLY')
    assert client(tmp_path).post(URL + '/correct-fill', json=payload).status_code == 422
    assert not list(tmp_path.rglob('*.jsonl'))


def test_recorded_account_remains_readable_when_current_sources_unavailable(sources, monkeypatch):
    root, symbol = sources
    http = client(root)
    view, _ = prepare_and_confirm(http, initialize(http), symbol)
    monkeypatch.setattr(workbench, '_sources', lambda *a, **k: (_ for _ in ()).throw(ValueError('Provider unavailable')))
    restored = read(http)
    assert restored['sources'] == dict(status='UNAVAILABLE', items=[])
    assert restored['account'] == view['account']
    sold, _ = prepare_and_confirm(http, restored, symbol, tx='sell', side='SELL', day='2026-10-22')
    assert sold['account']['portfolio']['positions'] == []
    assert sold['account']['portfolio']['cash_cny'] == '9990'


@pytest.mark.parametrize('fault', ['path', 'actual', 'numeric_confirmation', 'numeric_money', 'extra_policy'])
def test_untrusted_initialize_has_no_journal(tmp_path, fault):
    payload = dict(confirmed_hypothetical=True, idempotency_key='bad', expected_revision=0,
        as_of='2026-10-20', cash_cny='10000', confirmed_at=datetime.now(timezone.utc).isoformat(),
        confirmation_note='TEST_ONLY')
    if fault == 'path': payload['repository_root'] = '../private'
    elif fault == 'actual': payload['namespace'] = 'ACTUAL'
    elif fault == 'numeric_confirmation': payload['confirmed_hypothetical'] = 1
    elif fault == 'numeric_money': payload['cash_cny'] = 10000
    else: payload['policy'] = {'approved': True}
    response = client(tmp_path).post(URL + '/initialize', json=payload)
    assert response.status_code == 422
    assert not list(tmp_path.rglob('*.jsonl'))


def test_remote_origin_cannot_read_or_write_persistent_simulation(tmp_path):
    http = client(tmp_path)
    assert http.get(URL, headers={'Origin': 'https://example.com'}).status_code == 403
    assert not list(tmp_path.rglob('*.jsonl'))


def test_same_session_sell_and_stale_revision_do_not_commit(sources):
    root, symbol = sources
    http = client(root)
    view, _ = prepare_and_confirm(http, initialize(http), symbol)
    journal = root / 'runtime/simulated-portfolios-v1/paper-dual-v1/journal.jsonl'
    before = journal.read_bytes()
    sell = request(view, 'same-day', fill=dict(transaction_id='same-day', side='SELL',
        sleeve='CORE_VALUE', symbol=symbol, exchange='SSE', quantity='100', price_cny='10',
        fees_cny='5', trade_date='2026-10-21'))
    assert http.post(URL + '/prepare-fill', json=sell).status_code == 409
    sell['expected_revision'] = 0
    assert http.post(URL + '/prepare-fill', json=sell).json()['status'] == 'VERSION_CONFLICT'
    assert journal.read_bytes() == before
    assert len(PrivateJournal(journal).read()) == view['account']['revision']
