from fastapi.testclient import TestClient
from value_investment_agent.presentation.web_api.app import create_app
from value_investment_agent.application.decision import value_price_policy
import json
import pytest


def test_missing_review_routes_fail_closed_without_private_auth(tmp_path):
    client = TestClient(create_app(root=tmp_path))
    for route in ("value-policy-review/600887", "hotspot-replay-review"):
        response = client.get("/api/v1/" + route)
        assert response.status_code == 409
        assert response.json()["action"] == "no_order"
    assert not list(tmp_path.rglob("*.json"))


def test_value_review_route_preserves_unapproved_scope(tmp_path, monkeypatch):
    monkeypatch.setattr(value_price_policy, "load_value_policy_review", lambda *args: {
        "model_review": {"formal_eligibility": False},
        "preparation": {"registered": False, "draft_prices": {"BUY": None}}})
    result = TestClient(create_app(root=tmp_path)).get("/api/v1/value-policy-review/600887").json()
    assert result["action"] == "no_order"
    assert result["status"] == "RESEARCH_ONLY"
    assert result["preparation"]["registered"] is False


@pytest.mark.parametrize('scope', ['DESCRIPTIVE', 'ADMITTED'])
def test_retained_review_preserves_descriptive_scope_or_rejects(tmp_path, monkeypatch, scope):
    from value_investment_agent.application.hotspot import replay_read_model, retained_source_replay
    (tmp_path / 'config').mkdir()
    pins = dict(action='no_order', manifest_sha256='legacy', structure_manifest_sha256='structure',
                retained_manifest_binding=dict(path='runtime/TEST_ONLY.json', sha256='test'))
    (tmp_path / 'config/hotspot-replay-review-v1.json').write_text(json.dumps(pins), encoding='utf-8')
    monkeypatch.setattr(replay_read_model, 'load_replay_summary', lambda **kw:
        dict(action='no_order', formal_eligibility=False, items=[]))
    calls = []
    def retained(**kw):
        calls.append(kw)
        return dict(namespace='ACTUAL', scope=scope, action='no_order', formal_eligibility=False,
                    trade_count=None, strategy_validation='NOT_PROVEN', signal_event_count=161)
    monkeypatch.setattr(retained_source_replay, 'load_retained_replay_summary', retained)
    response = TestClient(create_app(root=tmp_path)).get('/api/v1/hotspot-replay-review')
    assert calls[0]['manifest_binding'] == pins['retained_manifest_binding']
    assert response.status_code == (200 if scope == 'DESCRIPTIVE' else 409)
    if scope == 'DESCRIPTIVE':
        result = response.json()
        assert result['formal_eligibility'] is False
        assert result['retained_validation']['trade_count'] is None
        assert result['retained_validation']['strategy_validation'] == 'NOT_PROVEN'
        assert result['retained_validation']['signal_event_count'] == 161
