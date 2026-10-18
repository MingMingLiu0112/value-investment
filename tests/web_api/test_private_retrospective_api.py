"""Authenticated private-only retrospective reads over synthetic existing fills."""
from datetime import datetime, timezone

from test_held_continuity_api import client_for, unlock
from test_private_ledger_candidate_fill import ledger, request, confirm

ROUTE = "/api/v1/private/portfolio/retrospective?review_date=2026-10-12"


def test_retrospective_requires_auth_keeps_journal_unchanged_and_never_publishes(ledger, tmp_path, monkeypatch):
    _, digest = ledger.prepare_fill(request(ledger))
    confirm(ledger, digest, "TEST_ONLY-retro-confirm")
    client, secret = client_for(tmp_path, ledger.journal.path, monkeypatch)
    assert client.get(ROUTE).status_code == 401
    unlock(client, secret)
    client.headers["origin"] = "https://untrusted.invalid"
    assert client.get(ROUTE).status_code == 403
    client.headers["origin"] = "http://127.0.0.1:8791"
    before = ledger.journal.path.read_bytes()
    response = client.get(ROUTE)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    result = response.json()
    assert result["mode"] == "MOCK" and result["ledger_source"] == "TEST_ONLY"
    assert len(result["items"]) == 1 and result["items"][0]["manual_fill"]["price_cny"] == "20"
    assert result["formal_eligibility"] is result["decision_changed"] is False
    assert result["approval_count"] == 0 and result["action"] == "no_order"
    assert client.get(ROUTE).json()["items"] == result["items"]
    assert ledger.journal.path.read_bytes() == before
    assert not (tmp_path / "config/current-agent-research.json").exists()
    assert client.get("/api/v1/private/portfolio/retrospective?review_date=2100-01-01").status_code == 422
    assert client.get("/api/v1/private/portfolio/retrospective?review_date=bad").status_code == 422


def test_retrospective_missing_journal_is_not_created_and_corruption_is_not_empty(ledger, tmp_path, monkeypatch):
    client, secret = client_for(tmp_path, ledger.journal.path, monkeypatch)
    unlock(client, secret)
    ledger.journal.path.write_bytes(b"not-json\n")
    response = client.get(ROUTE)
    assert response.status_code == 409 and response.json()["status"] == "JOURNAL_INVALID"
    assert ledger.journal.path.read_bytes() == b"not-json\n"
    ledger.journal.path.unlink()
    response = client.get(ROUTE)
    assert response.status_code == 200 and response.json()["status"] == "BLOCKED_PRIVATE_INPUT"
    assert not ledger.journal.path.exists()
