from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

import pytest

from value_investment_agent.application.portfolio.account_observations import load_account_observations
from value_investment_agent import private_portfolio_intake as intake


@pytest.fixture
def observed(tmp_path, monkeypatch):
    # CI temp is inside its checkout; retain all other private path checks.
    monkeypatch.setattr(intake, '_containing_git_root', lambda path: None)
    private, repo = tmp_path / 'private', tmp_path / 'repo'
    account = private / 'accounts' / 'TEST_ONLY'
    folder = account / 'intake'
    folder.mkdir(parents=True)
    (folder / 'image.jpg').write_bytes(b'TEST_ONLY evidence')
    value = dict(schema_version='private-account-screenshot-observation-v1', action='no_order',
        namespace='ACTUAL_USER_PROVIDED', account_label='TEST_ONLY', snapshot_date='2026-10-23',
        displayed_clock_time='09:58', trade_eligible=False, formal_eligibility=False,
        active_portfolio_journal_written=False, evidence=dict(image='image.jpg',
            sha256=sha256((folder / 'image.jpg').read_bytes()).hexdigest()),
        observed_totals={'total_assets_cny': '1005'}, reconciliation={},
        holdings=[dict(symbol='000001', name='TEST_ONLY', quantity_inferred='100',
            displayed_price_cny='10', market_value_cny='1000',
            sleeve='UNASSIGNED', sellable_quantity=None)])
    def write(value, relative='intake/snapshot.json'):
        raw = json.dumps(value).encode()
        (folder / 'snapshot.json').write_bytes(raw)
        (account / 'current-observation.json').write_text(json.dumps(dict(
            schema_version='private-account-current-observation-v1', action='no_order',
            snapshot_path=relative, snapshot_sha256=sha256(raw).hexdigest())), encoding='utf-8')
    write(value)
    return private, repo, folder, value, write


def test_source_bound_observation_never_becomes_trading_ledger(observed):
    private, repo, folder, value, _ = observed
    before = {p: p.read_bytes() for p in private.rglob('*') if p.is_file()}
    result = load_account_observations(private_root=private, repository_root=repo)
    assert result['accounts'][0]['holdings'] == value['holdings']
    assert result['accounts'][0]['active_trading_ledger'] is False
    assert result['trade_eligible'] is False
    assert {p: p.read_bytes() for p in private.rglob('*') if p.is_file()} == before


@pytest.mark.parametrize('fault', ['snapshot', 'image', 'traversal', 'quantity', 'eligibility', 'sleeve'])
def test_tamper_or_false_authority_is_withheld(observed, fault):
    private, repo, folder, original, write = observed
    value = deepcopy(original)
    if fault == 'quantity': value['holdings'][0]['quantity_inferred'] = '999'
    if fault == 'eligibility': value['trade_eligible'] = True
    if fault == 'sleeve': value['holdings'][0]['sleeve'] = 'CORE_VALUE'
    write(value, '../another-account.json' if fault == 'traversal' else 'intake/snapshot.json')
    if fault == 'snapshot': (folder / 'snapshot.json').write_bytes(b'{}')
    if fault == 'image': (folder / 'image.jpg').write_bytes(b'changed')
    result = load_account_observations(private_root=private, repository_root=repo)
    assert result['accounts'] == [] and result['unavailable_count'] == 1


def test_private_route_requires_local_session_and_never_reads_while_locked(observed, monkeypatch):
    from fastapi.testclient import TestClient
    from value_investment_agent.presentation.web_api import private_routes
    from value_investment_agent.presentation.web_api.app import create_app
    private, repo, folder, value, _ = observed
    repo.mkdir()
    monkeypatch.setattr(private_routes, 'resolve_private_root', lambda **kw: private / 'portfolio' / 'journal.jsonl')
    secret = 'TEST_ONLY-' + 'p' * 48
    client = TestClient(create_app(repo, port=8791, bootstrap_secret=secret),
        base_url='http://127.0.0.1:8791', client=('127.0.0.1', 51000))
    client.headers.update({'host': '127.0.0.1:8791', 'origin': 'http://127.0.0.1:8791'})
    route = '/api/v1/private/portfolio/account-observations'
    assert client.get(route).status_code == 401
    client.headers['x-local-session'] = client.post('/api/v1/private/session/unlock',
        json={'bootstrap_token': secret}).json()['token']
    result = client.get(route)
    assert result.status_code == 200 and result.headers['cache-control'] == 'no-store'
    assert result.json()['accounts'][0]['account_label'] == 'TEST_ONLY'
    client.headers['origin'] = 'http://example.invalid'
    assert client.get(route).status_code == 403
