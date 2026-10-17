"""Integrated registration retains the existing local authorization boundary."""
import pytest
from fastapi.testclient import TestClient
from value_investment_agent.presentation.web_api import private_routes
from value_investment_agent.presentation.web_api.app import create_app


@pytest.mark.parametrize("method,path", [
    ("get", "/api/v1/private/portfolio/risk-context/300364"),
    ("post", "/api/v1/private/portfolio/costs/confirm"),
    ("post", "/api/v1/private/portfolio/reconciliation/confirm"),
    ("get", "/api/v1/value-policy-review/600887/status"),
    ("post", "/api/v1/value-policy-review/600887/preview"),
    ("post", "/api/v1/value-policy-review/600887/confirm"),
])
def test_integrated_private_routes_require_session_and_same_origin(tmp_path, monkeypatch, method, path):
    journal = tmp_path / "TEST_ONLY-journal.jsonl"
    monkeypatch.setattr(private_routes, "resolve_private_root", lambda **kwargs: journal)
    secret = "TEST_ONLY-bootstrap-" + "c" * 40
    client = TestClient(create_app(tmp_path, port=8791, bootstrap_secret=secret),
        base_url="http://127.0.0.1:8791", client=("127.0.0.1", 51000))
    client.headers.update({"host": "127.0.0.1:8791", "origin": "http://127.0.0.1:8791"})
    send = lambda: getattr(client, method)(path, **({"json": {}} if method == "post" else {}))
    assert send().status_code == 401
    token = client.post("/api/v1/private/session/unlock", json={"bootstrap_token": secret}).json()["token"]
    client.headers.update({"x-local-session": token, "origin": "https://untrusted.invalid"})
    assert send().status_code == 403
    assert not journal.exists()
    assert not (tmp_path / "runtime/value-policy-review").exists()


def test_local_frontend_assets_are_not_cached_across_product_rebuilds(tmp_path):
    bundle = tmp_path / "web/dist"
    bundle.mkdir(parents=True)
    (bundle / "index.html").write_text("<main>current shell</main>", encoding="utf-8")
    (bundle / "umi.js").write_text("current bundle", encoding="utf-8")
    client = TestClient(create_app(tmp_path))
    for path in ("/daily", "/umi.js"):
        assert client.get(path).headers["cache-control"] == "no-store"
    (bundle / "umi.js").write_text("new bundle", encoding="utf-8")
    assert client.get("/umi.js").text == "new bundle"
