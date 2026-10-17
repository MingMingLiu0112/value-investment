from fastapi.testclient import TestClient
from value_investment_agent.presentation.web_api.app import create_app
from value_investment_agent.application.decision import value_price_policy


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
