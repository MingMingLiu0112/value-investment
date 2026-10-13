"""HTTP contract for the local-only private portfolio routes."""
import json

from fastapi.testclient import TestClient

from conftest import TEST_BOOTSTRAP, open_session
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

FILL = {
    "idempotency_key": "fill-1",
    "expected_revision": 1,
    "fill": {"transaction_id": "T1", "side": "BUY", "sleeve": "CORE_VALUE",
             "symbol": "600519", "exchange": "SSE", "quantity": "200",
             "price_cny": "1500.00", "fees_cny": "5.00", "trade_date": "2026-10-12",
             "next_sell_session": "2026-10-13", "trading_unit": "100"},
}


def test_disconnected_portfolio_is_a_200_business_state(client):
    response = client.get("/api/v1/portfolio")
    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "no_order"
    assert body["status"] == "NOT_CONNECTED"
    assert body["positions"] == []
    assert "PRICE_NOT_ADMITTED" in body["blockers"]


def test_missing_private_root_is_200_on_read_and_503_on_write(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setenv("VALUE_INVESTMENT_PRIVATE_ROOT", str(tmp_path / "absent"))
    client = TestClient(create_app(project, port=8791, bootstrap_secret=TEST_BOOTSTRAP),
                        base_url="http://127.0.0.1:8791", client=("127.0.0.1", 51000))
    client.headers.update({"host": "127.0.0.1:8791", "origin": "http://127.0.0.1:8791"})
    client.headers["x-local-session"] = open_session(client)
    read = client.get("/api/v1/portfolio")
    assert read.status_code == 200
    assert read.json()["status"] == "NOT_CONNECTED"
    assert "PRIVATE_ROOT_UNAVAILABLE" in read.json()["blockers"]
    write = client.post("/api/v1/private/portfolio/initialize", json=BASELINE)
    assert write.status_code == 503
    assert write.json()["status"] == "PRIVATE_ROOT_UNAVAILABLE"


def test_initialize_is_idempotent_and_revision_bounded(client, workspace):
    _, private = workspace
    first = client.post("/api/v1/private/portfolio/initialize", json=BASELINE)
    assert first.status_code == 200
    body = first.json()
    assert body["status"] == "BASELINE_CONFIRMED"
    assert body["revision"] == 1
    assert body["action"] == "no_order"
    assert len(body["record_sha256"]) == 64
    replay = client.post("/api/v1/private/portfolio/initialize", json=BASELINE)
    assert replay.json()["record_sha256"] == body["record_sha256"]
    journal = private / "portfolio" / "journal.jsonl"
    assert len(journal.read_text(encoding="utf-8").splitlines()) == 1
    conflict = client.post("/api/v1/private/portfolio/initialize",
                           json={**BASELINE, "cash_cny": "1.00"})
    assert conflict.status_code == 409
    assert conflict.json()["status"] == "IDEMPOTENCY_CONFLICT"


def test_second_initialize_is_409(client):
    client.post("/api/v1/private/portfolio/initialize", json=BASELINE)
    response = client.post("/api/v1/private/portfolio/initialize",
                           json={**BASELINE, "idempotency_key": "init-2"})
    assert response.status_code == 409
    assert response.json()["status"] == "ALREADY_INITIALIZED"


def test_stale_revision_is_409(client):
    client.post("/api/v1/private/portfolio/initialize", json=BASELINE)
    response = client.post("/api/v1/private/fills/prepare", json={**FILL, "expected_revision": 9})
    assert response.status_code == 409
    assert response.json()["status"] == "VERSION_CONFLICT"


def test_full_fill_lifecycle_through_http(client, workspace):
    client.post("/api/v1/private/portfolio/initialize", json=BASELINE)
    prepared = client.post("/api/v1/private/fills/prepare", json=FILL)
    assert prepared.status_code == 200
    draft = prepared.json()
    assert draft["status"] == "FILL_PREPARED"
    assert draft["draft"]["status"] == "DRAFT_UNRECONFIRMED"
    assert draft["draft"]["cash_cny"] == "199995.00"
    assert client.get("/api/v1/portfolio").json()["positions"][0]["quantity"] == "1000"

    confirmed = client.post("/api/v1/private/fills/confirm", json={
        "idempotency_key": "fill-1-confirm", "expected_revision": 2,
        "prepared_record_sha256": draft["record_sha256"],
        "confirmed_at": "2026-10-12T21:00:00+08:00", "confirmation_note": "confirmed"})
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "FILL_CONFIRMED"
    assert confirmed.json()["cash_cny"] == "199995.00"

    reconciled = client.post("/api/v1/private/portfolio/reconcile", json={
        "idempotency_key": "reconcile-1", "expected_revision": 3,
        "reconciled_at": "2026-10-12T21:05:00+08:00", "confirmation_note": "reconciled"})
    assert reconciled.status_code == 200
    assert reconciled.json()["status"] == "RECONCILED"
    assert reconciled.json()["snapshot"]["holdings"][0]["quantity"] == "1200"

    view = client.get("/api/v1/portfolio").json()
    assert view["status"] == "CONNECTED"
    assert view["revision"] == 4
    assert view["realized_pnl_cny"] == "0"
    assert view["valuation"]["status"] == "PRICE_NOT_ADMITTED"


def test_duplicate_transaction_is_409(client):
    client.post("/api/v1/private/portfolio/initialize", json=BASELINE)
    draft = client.post("/api/v1/private/fills/prepare", json=FILL).json()
    client.post("/api/v1/private/fills/confirm", json={
        "idempotency_key": "fill-1-confirm", "expected_revision": 2,
        "prepared_record_sha256": draft["record_sha256"],
        "confirmed_at": "2026-10-12T21:00:00+08:00", "confirmation_note": "confirmed"})
    response = client.post("/api/v1/private/fills/prepare", json={**FILL, "idempotency_key": "fill-2", "expected_revision": 3})
    assert response.status_code == 409
    assert response.json()["status"] == "DUPLICATE_TRANSACTION"


def test_confirm_without_draft_is_409(client):
    client.post("/api/v1/private/portfolio/initialize", json=BASELINE)
    response = client.post("/api/v1/private/fills/confirm", json={
        "idempotency_key": "confirm-1", "expected_revision": 1,
        "prepared_record_sha256": "0" * 64,
        "confirmed_at": "2026-10-12T21:00:00+08:00", "confirmation_note": "nope"})
    assert response.status_code == 409
    assert response.json()["status"] == "NO_CONFIRMABLE_DRAFT"


def test_validation_failures_are_422(client):
    bad_symbol = client.post("/api/v1/private/portfolio/initialize",
                             json={**BASELINE, "holdings": [{"symbol": "60051", "exchange": "SSE",
                                                             "quantity": "10", "cost_basis_cny": "1"}]})
    assert bad_symbol.status_code == 422
    assert bad_symbol.json()["status"] == "VALIDATION_FAILED"
    bad_amount = client.post("/api/v1/private/portfolio/initialize",
                             json={**BASELINE, "cash_cny": "1,000"})
    assert bad_amount.status_code == 422
    malformed = client.post("/api/v1/private/portfolio/initialize", content=b"{",
                            headers={"Content-Type": "application/json"})
    assert malformed.status_code == 422
    assert malformed.json()["status"] == "VALIDATION_FAILED"
    assert client.get("/api/v1/portfolio").json()["status"] == "NOT_CONNECTED"


def test_cross_site_origin_is_rejected(client, workbench_origin):
    remote = client.post("/api/v1/private/portfolio/initialize", json=BASELINE,
                         headers={"Origin": "https://example.com"})
    assert remote.status_code == 403
    assert remote.json()["status"] == "ORIGIN_REJECTED"
    prefetch = client.post("/api/v1/private/portfolio/initialize", json=BASELINE,
                           headers={"Sec-Fetch-Site": "cross-site"})
    assert prefetch.status_code == 403
    local = client.post("/api/v1/private/portfolio/initialize", json=BASELINE,
                        headers={"Origin": workbench_origin.replace("127.0.0.1", "localhost")})
    assert local.status_code == 200
    aliased = client.post("/api/v1/private/fills/prepare", json=FILL,
                          headers={"Referer": f"{workbench_origin}/portfolio"})
    assert aliased.status_code == 200


def test_tampered_journal_hides_positions(client, workspace):
    _, private = workspace
    client.post("/api/v1/private/portfolio/initialize", json=BASELINE)
    journal = private / "portfolio" / "journal.jsonl"
    record = json.loads(journal.read_text(encoding="utf-8").splitlines()[0])
    record["body"]["cash_cny"] = "99999999.00"
    journal.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
    response = client.get("/api/v1/portfolio")
    assert response.status_code == 200
    assert response.json()["status"] == "NOT_CONNECTED"
    assert "PRIVATE_JOURNAL_INVALID" in response.json()["blockers"]
    assert response.json()["positions"] == []


def test_private_journal_never_lands_in_the_repository(client, workspace):
    project, private = workspace
    client.post("/api/v1/private/portfolio/initialize", json=BASELINE)
    assert (private / "portfolio" / "journal.jsonl").is_file()
    assert not list(project.rglob("journal.jsonl"))
    assert client.get("/api/v1/system/status").json()["portfolio"] == "CONNECTED"


def test_openapi_lists_private_routes(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/private/portfolio/initialize" in paths
    assert "/api/v1/private/fills/prepare" in paths
    assert "/api/v1/private/fills/confirm" in paths
    assert "/api/v1/private/portfolio/reconcile" in paths
    assert "/api/v1/private/session" in paths
def test_cancel_voids_the_draft_and_unblocks_the_next_fill(client):
    client.post("/api/v1/private/portfolio/initialize", json=BASELINE)
    draft = client.post("/api/v1/private/fills/prepare", json=FILL).json()
    cancelled = client.post("/api/v1/private/fills/cancel", json={
        "idempotency_key": "cancel-1", "expected_revision": 2,
        "prepared_record_sha256": draft["record_sha256"],
        "cancelled_at": "2026-10-12T20:30:00+08:00", "reason": "录入有误"})
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "FILL_CANCELLED"
    assert cancelled.json()["cancelled_transaction_id"] == "T1"
    view = client.get("/api/v1/portfolio").json()
    assert view["cash_cny"] == "500000.00"
    assert view["positions"][0]["quantity"] == "1000"
    assert view["pending_draft"] is None
    retried = client.post("/api/v1/private/fills/prepare",
                          json={**FILL, "idempotency_key": "fill-2", "expected_revision": 3})
    assert retried.status_code == 200
    assert retried.json()["draft"]["cash_cny"] == "199995.00"


