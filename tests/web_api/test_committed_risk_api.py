"""Real authenticated routes with isolated TEST_ONLY journal declarations."""
from copy import deepcopy

from test_private_portfolio_api import BASELINE, FILL

PATH = '/api/v1/private/portfolio/committed-risk'


def declaration(client):
    baseline = deepcopy(BASELINE)
    baseline['account_scope'] = 'TEST_ONLY_RISK_DECLARATION_API'
    assert client.post('/api/v1/private/portfolio/initialize', json=baseline).status_code == 200
    response = client.get(PATH)
    assert response.status_code == 200, response.text
    view = response.json()
    return dict(expected_revision=view['revision'], account_scope=view['account_scope'],
        journal_tip_sha256=view['journal_tip_sha256'], idempotency_key='TEST_ONLY-first',
        read_and_confirmed=True, confirmation_note='TEST_ONLY user declaration, no real approval',
        amounts=[dict(symbol=row['symbol'], sleeve=row['sleeve'], committed_risk_cny='1000',
                      evidence_ref='TEST_ONLY explicit risk assessment') for row in view['allocations']])


def test_read_and_write_require_current_private_session(make_client):
    client = make_client(authorize=False)
    for response in (client.get(PATH), client.post(PATH + '/confirm', json={})):
        assert response.status_code == 401
        assert response.headers['cache-control'] == 'no-store'


def test_empty_account_is_disconnected_not_a_zero_risk_approval(client):
    response = client.get(PATH)
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'NOT_CONNECTED'
    assert response.json()['formal_eligibility'] is False


def test_confirm_reload_correct_and_reject_stale_without_altering_bookkeeping(client):
    payload = declaration(client)
    before = client.get('/api/v1/portfolio').json()
    confirmed = client.post(PATH + '/confirm', json=payload)
    assert confirmed.status_code == 200, confirmed.text
    result = confirmed.json()
    assert result['status'] == 'COMMITTED_RISK_CONFIRMED'
    assert result['revision'] == payload['expected_revision'] + 1
    assert result['namespace'] == 'SIMULATED'
    assert result['qualification_status'] == 'TEST_ONLY_NOT_ACTUAL'
    assert result['formal_eligibility'] is False
    assert result['changes_holdings'] is False
    assert result['request_binding']['journal_tip_sha256'] == payload['journal_tip_sha256']
    assert client.post(PATH + '/confirm', json=payload).json() == result
    current = client.get(PATH).json()
    assert current['confirmation_status'] == 'CONFIRMED'
    assert all(row['committed_risk_cny'] == '1000' for row in current['allocations'])
    corrected = {**payload, 'expected_revision': current['revision'],
        'journal_tip_sha256': current['journal_tip_sha256'], 'idempotency_key': 'TEST_ONLY-correct',
        'amounts': [{**row, 'committed_risk_cny': '1500'} for row in payload['amounts']]}
    response = client.post(PATH + '/confirm', json=corrected)
    assert response.status_code == 200, response.text
    assert all(row['committed_risk_cny'] == '1500' for row in client.get(PATH).json()['allocations'])
    stale = client.post(PATH + '/confirm', json={**payload, 'idempotency_key': 'TEST_ONLY-stale'})
    assert stale.status_code == 409
    after = client.get('/api/v1/portfolio').json()
    for key in ('cash_cny', 'positions', 'realized_pnl_cny', 'trades'):
        assert after[key] == before[key]
    assert confirmed.headers['cache-control'] == 'no-store'


def test_no_client_signature_or_missing_ack_and_draft_keeps_known_facts(client):
    payload = declaration(client)
    for changes in ({'authenticated_subject': 'FORGED'}, {'read_and_confirmed': False},
                    {'amounts': []}, {'account_scope': 'OTHER'}):
        response = client.post(PATH + '/confirm', json={**payload, **changes})
        assert response.status_code in (409, 422), response.text
    prepared = client.post('/api/v1/private/fills/prepare', json=deepcopy(FILL))
    assert prepared.status_code == 200, prepared.text
    risk = client.get('/api/v1/private/portfolio/risk')
    assert risk.status_code == 200, risk.text
    assert risk.json()['facts']['cash_cny'] is not None
    assert client.get(PATH).status_code == 200


def test_tampered_declaration_is_rejected_but_known_accounting_remains_readable(client, workspace):
    payload = declaration(client)
    assert client.post(PATH + '/confirm', json=payload).status_code == 200
    _, private = workspace
    original = next(private.rglob('input.json'))
    original.write_text('{}', encoding='utf-8')
    assert client.get(PATH).status_code == 422
    risk = client.get('/api/v1/private/portfolio/risk')
    assert risk.status_code == 200, risk.text
    assert 'COMMITTED_RISK_SOURCE_REJECTED' in risk.json()['blockers']
    assert risk.json()['committed_risk']['status'] == 'SOURCE_REJECTED'
    assert risk.json()['facts']['cash_cny'] is not None
    assert client.get('/api/v1/portfolio').json()['positions']
