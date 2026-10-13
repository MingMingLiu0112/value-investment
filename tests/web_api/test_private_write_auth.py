"""WEB-D2 P0.1: private reads and writes only accept the local operator."""
from __future__ import annotations

from fastapi.testclient import TestClient

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
    token = client.get(SESSION_PATH).json()["token"]
    response = client.post(INITIALIZE_PATH, json=BASELINE,
                           headers={"x-local-session": token})
    assert response.status_code == 200
    assert response.json()["status"] == "BASELINE_CONFIRMED"


def test_logout_invalidates_the_token_and_a_new_handshake_works(make_client):
    client = make_client(authorize=False)
    old = client.get(SESSION_PATH).json()["token"]
    signed_out = client.post("/api/v1/private/session/logout",
                             headers={"x-local-session": old})
    assert signed_out.status_code == 200
    assert signed_out.json()["status"] == "SIGNED_OUT"
    rejected = client.post(INITIALIZE_PATH, json=BASELINE, headers={"x-local-session": old})
    assert rejected.status_code == 401
    fresh = client.get(SESSION_PATH).json()["token"]
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
            assert response.json()["status"] == "LOCAL_AUTHORIZATION_REQUIRED"
    assert INITIALIZE_PATH in guarded
    assert "/api/v1/private/fills/prepare" in guarded
    assert "/api/v1/private/fills/confirm" in guarded
    assert "/api/v1/private/fills/cancel" in guarded
    assert "/api/v1/private/portfolio/reconcile" in guarded
    assert "/api/v1/private/session/logout" in guarded


def test_replayed_authorized_write_is_idempotent(client, workspace):
    _, private = workspace
    first = client.post(INITIALIZE_PATH, json=BASELINE)
    replay = client.post(INITIALIZE_PATH, json=BASELINE)
    assert first.status_code == replay.status_code == 200
    assert first.json()["record_sha256"] == replay.json()["record_sha256"]
    assert len(_journal(private).read_text(encoding="utf-8").splitlines()) == 1
