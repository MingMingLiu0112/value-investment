"""Authenticated Entry Thesis boundary; no writes to the user's actual journal."""
from copy import deepcopy

from test_private_portfolio_api import BASELINE, FILL


PATH = "/api/v1/private/portfolio/entry-thesis"


def test_entry_thesis_read_requires_operator_session(make_client):
    client = make_client(authorize=False)
    response = client.get(PATH)
    assert response.status_code == 401
    assert response.json()["action"] == "no_order"


def test_entry_thesis_write_requires_operator_session(make_client):
    client = make_client(authorize=False)
    response = client.post(PATH + "/confirm", json={"authenticated_subject": "forged"})
    assert response.status_code == 401
    assert response.json()["action"] == "no_order"


def test_entry_thesis_read_is_empty_not_ready_before_account_intake(client):
    response = client.get(PATH)
    assert response.status_code == 200
    result = response.json()
    assert result["action"] == "no_order"
    assert result["status"] == "NOT_CONNECTED"
    assert result["items"] == []


def _buy(client):
    baseline = deepcopy(BASELINE)
    baseline["account_scope"] = "TEST_ONLY_THESIS_API"
    assert client.post("/api/v1/private/portfolio/initialize", json=baseline).status_code == 200
    prepared = client.post("/api/v1/private/fills/prepare", json=FILL)
    assert prepared.status_code == 200
    confirmed = client.post("/api/v1/private/fills/confirm", json={
        "idempotency_key": "TEST_ONLY-fill-confirm", "expected_revision": 2,
        "prepared_record_sha256": prepared.json()["record_sha256"],
        "confirmed_at": "2026-10-12T16:00:00+08:00", "confirmation_note": "TEST_ONLY fill"})
    assert confirmed.status_code == 200
    view = client.get(PATH).json()
    row = view["items"][0]
    return {"idempotency_key": "TEST_ONLY-thesis-confirm", "expected_revision": view["revision"],
        "fill_record_sha256": row["fill_record_sha256"], "binding_mode": "HISTORICAL_RECONSTRUCTION",
        "read_and_confirmed": True, "confirmation_note": "TEST_ONLY now reconstructed, not PIT",
        "reconstruction": {"thesis": "TEST_ONLY original belief now recalled",
            "hold_logic": "TEST_ONLY depends on business evidence", "invalidation_conditions": ["TEST_ONLY loss of thesis"]}}


def test_authenticated_reconstruction_replays_and_revokes_without_changing_balances(client, workspace):
    payload = _buy(client)
    _, private = workspace
    journal = private / "portfolio/journal.jsonl"
    before_bytes = journal.read_bytes()
    balances = client.get("/api/v1/portfolio").json()
    response = client.post(PATH + "/confirm", json=payload)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "PERSONAL_ENTRY_THESIS_CONFIRMED"
    assert result["confirmation"]["authenticated_subject"] == "LOCAL_OPERATOR"
    assert result["confirmation"]["original_pit_proven"] is False
    assert result["changes_holdings"] is False
    assert client.post(PATH + "/confirm", json=payload).json() == result
    view = client.get(PATH).json()
    assert view["items"][0]["current_binding"]["record_sha256"] == result["record_sha256"]
    assert len(view["items"][0]["history"]) == 1
    stale = client.post(PATH + "/confirm", json={**payload, "idempotency_key": "TEST_ONLY-stale"})
    assert stale.status_code == 409
    revoke = client.post(PATH + "/revoke", json={"idempotency_key": "TEST_ONLY-revoke",
        "expected_revision": view["revision"], "confirmation_record_sha256": result["record_sha256"],
        "confirmation_note": "TEST_ONLY correction", "read_and_confirmed": True})
    assert revoke.status_code == 200, revoke.text
    final = client.get(PATH).json()
    assert final["items"][0]["current_binding"] is None
    assert len(final["items"][0]["history"]) == 2
    after = client.get("/api/v1/portfolio").json()
    assert after["cash_cny"] == balances["cash_cny"]
    assert after["positions"] == balances["positions"]
    assert journal.read_bytes().startswith(before_bytes)
    assert response.headers["cache-control"] == "no-store"


def test_client_cannot_supply_authenticated_identity_or_skip_read_acknowledgement(client):
    payload = _buy(client)
    for extra in ({"authenticated_subject": "other-user"}, {"read_and_confirmed": False}):
        response = client.post(PATH + "/confirm", json={**payload, **extra})
        assert response.status_code == 422, response.text
    assert client.get(PATH).json()["items"][0]["current_binding"] is None


def test_logged_out_session_cannot_confirm_or_read(client):
    payload = _buy(client)
    client.post("/api/v1/private/session/logout")
    assert client.post(PATH + "/confirm", json=payload).status_code == 401
    assert client.get(PATH).status_code == 401
