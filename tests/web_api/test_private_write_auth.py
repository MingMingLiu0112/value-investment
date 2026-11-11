"""WEB-D3 P0.2: private reads and writes only accept the unlocked local operator."""
from __future__ import annotations

from fastapi.testclient import TestClient

from conftest import TEST_BOOTSTRAP, UNLOCK_PATH, open_session, operator_headers
from value_investment_agent.presentation.web_api.app import create_app

BASELINE = {
    "idempotency_key": "init-1",
    "expected_revision": 0,
    "account_scope": "acct-demo",
    "as_of": "2026-10-10",
    "cash_cny": "500000.00",
    "holdings": [{"symbol": "600519", "exchange": "SSE", "quantity": "1000",
                  "cost_basis_cny": "1500000.00"}],
    "sleeve_allocations": {"600519": {"CORE_VALUE": "600", "HOTSPOT_SATELLITE": "400"}},
    "policy": {"investable_assets_cny": "2000000", "max_single_security_pct": "10"},
    "confirmation_note": "initial confirm",
    "confirmed_at": "2026-10-10T20:00:00+08:00",
}
SESSION_PATH = "/api/v1/private/session"
INITIALIZE_PATH = "/api/v1/private/portfolio/initialize"


def _journal(private):
    return private / "portfolio" / "journal.jsonl"


def test_handshake_then_authorized_write_succeeds(client, workspace):
    _, private = workspace
    response = client.post(INITIALIZE_PATH, json=BASELINE)
    assert response.status_code == 200
    assert response.json()["status"] == "BASELINE_CONFIRMED"
    assert _journal(private).read_text(encoding="utf-8").count("\n") == 1


def test_write_without_a_session_token_is_rejected_and_leaves_no_ledger(make_client, workspace):
    _, private = workspace
    client = make_client(authorize=False)
    response = client.post(INITIALIZE_PATH, json=BASELINE)
    assert response.status_code == 401
    assert response.json()["status"] == "LOCAL_AUTHORIZATION_REQUIRED"
    assert not _journal(private).exists()


def test_private_read_without_a_session_token_is_rejected(make_client):
    client = make_client(authorize=False)
    response = client.get("/api/v1/portfolio")
    assert response.status_code == 401
    assert response.json()["status"] == "LOCAL_AUTHORIZATION_REQUIRED"


def test_write_with_an_invalid_token_is_rejected(client):
    response = client.post(INITIALIZE_PATH, json=BASELINE,
                           headers={"x-local-session": "0" * 64})
    assert response.status_code == 401
    assert response.json()["status"] == "LOCAL_AUTHORIZATION_REQUIRED"


def test_write_with_an_expired_token_is_rejected(make_client, workspace):
    _, private = workspace
    client = make_client(session_ttl_seconds=-1.0)
    response = client.post(INITIALIZE_PATH, json=BASELINE)
    assert response.status_code == 401
    assert not _journal(private).exists()


def test_write_from_a_non_loopback_peer_is_rejected(make_client):
    client = make_client(authorize=False, client_address=("10.1.2.3", 51000))
    response = client.get(SESSION_PATH)
    assert response.status_code == 403
    assert response.json()["status"] == "CLIENT_NOT_LOOPBACK"


def test_foreign_host_header_is_rejected(client):
    response = client.post(INITIALIZE_PATH, json=BASELINE, headers={"host": "evil.example"})
    assert response.status_code == 403
    assert response.json()["status"] == "HOST_REJECTED"


def test_raw_http_client_is_rejected(workspace):
    project, _ = workspace
    default = TestClient(create_app(project, port=8791))
    response = default.get(SESSION_PATH, headers={"origin": "http://127.0.0.1:8791"})
    assert response.status_code == 403
    assert response.json()["status"] in {"CLIENT_NOT_LOOPBACK", "HOST_REJECTED"}
    unnamed = TestClient(create_app(project, port=8791), client=("127.0.0.1", 51000))
    forged = unnamed.get(SESSION_PATH, headers={"origin": "http://127.0.0.1:8791"})
    assert forged.status_code == 403
    assert forged.json()["status"] == "HOST_REJECTED"


def test_foreign_origin_is_rejected_even_with_a_valid_token(client):
    response = client.post(INITIALIZE_PATH, json=BASELINE,
                           headers={"origin": "https://evil.example"})
    assert response.status_code == 403
    assert response.json()["status"] == "ORIGIN_REJECTED"


def test_another_local_port_is_not_same_origin(client):
    response = client.post(INITIALIZE_PATH, json=BASELINE,
                           headers={"origin": "http://127.0.0.1:9999"})
    assert response.status_code == 403
    assert response.json()["status"] == "ORIGIN_REJECTED"


def test_cross_site_prefetch_headers_are_rejected(client):
    response = client.post(INITIALIZE_PATH, json=BASELINE,
                           headers={"sec-fetch-site": "cross-site"})
    assert response.status_code == 403


def test_cross_site_page_cannot_mint_a_token(make_client):
    client = make_client(authorize=False)
    response = client.get(SESSION_PATH, headers={"origin": "https://evil.example"})
    assert response.status_code == 403
    assert response.json()["status"] == "ORIGIN_REJECTED"


def test_tokenless_non_browser_client_is_rejected(make_client):
    client = make_client(authorize=False)
    response = client.post(INITIALIZE_PATH, json=BASELINE)
    assert response.status_code == 401


def test_token_bearing_non_browser_client_is_allowed(make_client):
    client = make_client(authorize=False)
    token = open_session(client)
    response = client.post(INITIALIZE_PATH, json=BASELINE,
                           headers={"x-local-session": token})
    assert response.status_code == 200
    assert response.json()["status"] == "BASELINE_CONFIRMED"


def test_logout_is_durable_until_the_launcher_secret_is_presented_again(make_client):
    client = make_client(authorize=False)
    old = open_session(client)
    signed_out = client.post("/api/v1/private/session/logout",
                             headers={"x-local-session": old})
    assert signed_out.status_code == 200
    assert signed_out.json()["status"] == "SIGNED_OUT"
    rejected = client.post(INITIALIZE_PATH, json=BASELINE, headers={"x-local-session": old})
    assert rejected.status_code == 401
    # A plain re-fetch must not mint a replacement: the workbench stays locked.
    status = client.get(SESSION_PATH).json()
    assert status["status"] == "LOCKED"
    assert "token" not in status
    fresh = open_session(client)
    accepted = client.post(INITIALIZE_PATH, json=BASELINE, headers={"x-local-session": fresh})
    assert accepted.status_code == 200


def test_every_private_mutation_route_is_guarded(make_client):
    client = make_client(authorize=False)
    guarded = []
    for route in client.app.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", set()) or set()
        if path.startswith("/api/v1/private/") and "POST" in methods:
            guarded.append(path)
            response = client.post(path, json={})
            assert response.status_code == 401, f"{path} answered {response.status_code}"
            assert response.json()["status"] in {
                "LOCAL_AUTHORIZATION_REQUIRED", "LOCAL_UNLOCK_REJECTED"}
    assert INITIALIZE_PATH in guarded
    assert "/api/v1/private/fills/prepare" in guarded
    assert "/api/v1/private/fills/confirm" in guarded
    assert "/api/v1/private/fills/cancel" in guarded
    assert "/api/v1/private/portfolio/reconcile" in guarded
    assert "/api/v1/private/session/logout" in guarded
    assert UNLOCK_PATH in guarded


def test_session_status_never_returns_a_token(make_client):
    client = make_client(authorize=False)
    locked = client.get(SESSION_PATH)
    assert locked.status_code == 200
    assert locked.json()["status"] == "LOCKED"
    assert "token" not in locked.json()
    assert locked.headers.get("cache-control") == "no-store"

    token = open_session(client)
    authorized = client.get(SESSION_PATH, headers={"x-local-session": token})
    assert authorized.status_code == 200
    assert authorized.json()["status"] == "AUTHORIZED"
    assert "token" not in authorized.json()


def test_unlock_rejects_a_wrong_launcher_secret_and_leaves_no_ledger(make_client, workspace):
    _, private = workspace
    client = make_client(authorize=False)
    response = client.post(UNLOCK_PATH, json={"bootstrap_token": "f" * 64})
    assert response.status_code == 401
    assert response.json()["status"] == "LOCAL_UNLOCK_REJECTED"
    assert not _journal(private).exists()


def test_unlock_is_impossible_without_a_launcher_secret(workspace, monkeypatch):
    from value_investment_agent.presentation.web_api.local_auth import BOOTSTRAP_ENV

    project, _ = workspace
    monkeypatch.delenv(BOOTSTRAP_ENV, raising=False)
    app = create_app(project, port=8791)
    client = TestClient(app, base_url="http://127.0.0.1:8791", client=("127.0.0.1", 51000))
    client.headers.update(operator_headers())
    response = client.post(UNLOCK_PATH, json={"bootstrap_token": TEST_BOOTSTRAP})
    assert response.status_code == 401
    assert response.json()["status"] == "LOCAL_AUTHORIZATION_REQUIRED"
    assert client.get(SESSION_PATH).json()["status"] == "LOCKED"


def test_restarting_the_service_invalidates_old_tokens_and_secrets(workspace):
    project, _ = workspace
    first = TestClient(create_app(project, port=8791, bootstrap_secret="first-secret"),
                       base_url="http://127.0.0.1:8791", client=("127.0.0.1", 51000))
    first.headers.update(operator_headers())
    token = open_session(first, bootstrap="first-secret")
    first.headers["x-local-session"] = token
    assert first.get("/api/v1/portfolio").status_code == 200

    second = TestClient(create_app(project, port=8791, bootstrap_secret="second-secret"),
                        base_url="http://127.0.0.1:8791", client=("127.0.0.1", 51000))
    second.headers.update(operator_headers())
    stale = second.get("/api/v1/portfolio", headers={"x-local-session": token})
    assert stale.status_code == 401
    rejected = second.post(UNLOCK_PATH, json={"bootstrap_token": "first-secret"})
    assert rejected.status_code == 401
    fresh = open_session(second, bootstrap="second-secret")
    assert second.get("/api/v1/portfolio", headers={"x-local-session": fresh}).status_code == 200


def test_system_status_hides_the_portfolio_connection_when_locked(make_client):
    client = make_client(authorize=False)
    assert client.get("/api/v1/system/status").json()["portfolio"] == "LOCKED"
    token = open_session(client)
    unlocked = client.get("/api/v1/system/status", headers={"x-local-session": token})
    assert unlocked.json()["portfolio"] == "NOT_CONNECTED"


def test_replayed_authorized_write_is_idempotent(client, workspace):
    _, private = workspace
    first = client.post(INITIALIZE_PATH, json=BASELINE)
    replay = client.post(INITIALIZE_PATH, json=BASELINE)
    assert first.status_code == replay.status_code == 200
    assert first.json()["record_sha256"] == replay.json()["record_sha256"]
    assert len(_journal(private).read_text(encoding="utf-8").splitlines()) == 1
