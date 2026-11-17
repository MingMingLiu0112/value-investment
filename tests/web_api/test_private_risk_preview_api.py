from fastapi.testclient import TestClient

from value_investment_agent.presentation.web_api import private_routes
from value_investment_agent.presentation.web_api.app import create_app


def test_preview_requires_authentication_and_never_writes(tmp_path, monkeypatch):
    journal = tmp_path / "TEST_ONLY-preview.jsonl"
    monkeypatch.setattr(private_routes, "resolve_private_root", lambda **kwargs: journal)
    secret = "TEST_ONLY-bootstrap-" + "p" * 40
    client = TestClient(create_app(tmp_path, port=8791, bootstrap_secret=secret),
        base_url="http://127.0.0.1:8791", client=("127.0.0.1", 51000))
    client.headers.update({"host": "127.0.0.1:8791", "origin": "http://127.0.0.1:8791"})
    route = "/api/v1/private/portfolio/risk-preview"
    assert client.post(route, json={"symbol": "300364"}).status_code == 401
    token = client.post("/api/v1/private/session/unlock", json={"bootstrap_token": secret}).json()["token"]
    client.headers["x-local-session"] = token
    client.headers["origin"] = "http://example.invalid"
    assert client.post(route, json={"symbol": "300364"}).status_code == 403
    client.headers["origin"] = "http://127.0.0.1:8791"
    response = client.post(route, json={"symbol": "300364", "assumptions": {}})
    assert response.status_code == 200
    assert response.json()["sizing_preview"]["review_quantity"] is None
    assert response.json()["action"] == "no_order"
    assert not journal.exists()
    forged = client.post(route, json={"symbol": "300364", "formal_eligibility": True})
    assert forged.status_code == 422
    assert not journal.exists()
