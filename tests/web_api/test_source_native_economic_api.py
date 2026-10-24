"""Economic HTTP view verifies current candidate and leaves approval state untouched."""
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from test_source_native_economic_review_v1 import sample, synthetic_native, snapshot
from value_investment_agent.presentation.web_api import source_native_economic_routes as routes


@pytest.fixture
def published(sample):
    root, binding, candidate = sample
    registry = root / 'config/user-research-workflow-v1.json'
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(json.dumps(dict(schema_version='user-research-workflow-v1', action='no_order',
        supplemental_review_candidates={candidate['symbol']: binding})), encoding='utf-8')
    api = FastAPI()
    routes.register_source_native_economic_routes(api, project=root)
    return TestClient(api), root, candidate, binding, registry


def test_economic_view_uses_real_kernel_and_exact_pending_binding(published):
    http, root, candidate, binding, _ = published
    before = snapshot(root)
    response = http.get('/api/v1/value-economic-review/' + candidate['symbol'])
    assert response.status_code == 200, response.text
    result = response.json()
    assert response.headers['cache-control'] == 'no-store'
    assert result['candidate_binding'] == binding
    assert result['symbol'] == candidate['symbol']
    assert result['g3_status'] == 'NOT_APPROVED_FOR_THIS_PENDING_CANDIDATE'
    assert result['current_g3_status'] == 'NOT_QUERIED'
    assert result['formal_eligibility'] is result['price_admitted'] is result['approval_changed'] is False
    assert len(result['scenarios']) == 3 and len(result['five_groups']) == 5
    for row in result['scenarios']:
        assert row['original']['candidate_per_historical_share_cny'] == candidate['candidate_valuation'][row['scenario'] + '_value']
        assert row['ke_plus_200bp']['alternative_candidate_verified'] is False
    assert snapshot(root) == before


def test_current_source_drift_has_no_fallback_or_numeric_result(published):
    http, root, candidate, _, _ = published
    path = root / candidate['native_cash_ledger_binding']['path']
    path.write_bytes(path.read_bytes() + b'\nTEST_ONLY_DRIFT')
    response = http.get('/api/v1/value-economic-review/' + candidate['symbol'])
    assert response.status_code == 409
    assert response.json()['status'] == 'ECONOMIC_REVIEW_UNAVAILABLE'
    assert 'scenarios' not in response.json()


def test_concurrent_registry_change_rejects_mixed_candidate_view(published, monkeypatch):
    http, _, candidate, _, registry = published
    build = routes.build_source_native_economic_review
    def change(**kwargs):
        result = build(**kwargs)
        registry.write_text(json.dumps(dict(schema_version='user-research-workflow-v1',
            action='no_order', supplemental_review_candidates={})), encoding='utf-8')
        return result
    monkeypatch.setattr(routes, 'build_source_native_economic_review', change)
    response = http.get('/api/v1/value-economic-review/' + candidate['symbol'])
    assert response.status_code == 409
    assert response.json()['formal_eligibility'] is False


def test_missing_current_candidate_returns_unavailable_without_writes(tmp_path):
    api = FastAPI()
    routes.register_source_native_economic_routes(api, project=tmp_path)
    response = TestClient(api).get('/api/v1/value-economic-review/600519')
    assert response.status_code == 409
    assert response.json()['action'] == 'no_order'
    assert not list(tmp_path.rglob('*'))
