"""Legacy free text must block risk, never crash or imply risk appetite."""
import pytest
from fastapi.testclient import TestClient

from value_investment_agent.presentation.web_api import private_routes
from value_investment_agent.presentation.web_api.app import create_app
from value_investment_agent.application.portfolio.private_portfolio_service import PrivateJournal, PrivatePortfolioService
from value_investment_agent.application.portfolio.private_risk_projection import build_risk_input


@pytest.mark.parametrize("tolerance", ["TEST_ONLY arbitrary text", "balanced", None])
def test_cash_only_first_use_with_legacy_risk_text_is_readable_and_blocked(tmp_path, monkeypatch, tolerance):
    journal = tmp_path / "TEST_ONLY-first-use.jsonl"
    monkeypatch.setattr(private_routes, "resolve_private_root", lambda **kwargs: journal)
    secret = "TEST_ONLY-bootstrap-" + "x" * 40
    client = TestClient(create_app(tmp_path, port=8791, bootstrap_secret=secret),
        base_url="http://127.0.0.1:8791", client=("127.0.0.1", 51000))
    client.headers.update({"host": "127.0.0.1:8791", "origin": "http://127.0.0.1:8791"})
    unlock = client.post("/api/v1/private/session/unlock", json={"bootstrap_token": secret})
    assert unlock.status_code == 200
    client.headers["x-local-session"] = unlock.json()["token"]
    initialized = client.post("/api/v1/private/portfolio/initialize", json={
        "idempotency_key": "init", "expected_revision": 0, "account_scope": "TEST_ONLY_SYNTHETIC",
        "as_of": "2026-10-14", "cash_cny": "10000", "holdings": [], "sleeve_allocations": {},
        "policy": {"risk_tolerance": tolerance} if tolerance is not None else {}, "confirmed_at": "2026-10-14T20:00:00+08:00",
        "confirmation_note": "TEST ONLY"})
    assert initialized.status_code == 200, initialized.text
    before = journal.read_bytes()
    risk = client.get("/api/v1/private/portfolio/risk")
    assert risk.status_code == 200, risk.text
    result = risk.json()
    assert result["status"] == "BLOCKED_PRIVATE_INPUT"
    assert "risk_tolerance" in result["blockers"]
    assert result["engine"]["position_guidance"] is None
    assert result["engine"]["trade_eligible"] is False
    assert result["facts"]["cash_cny"] == "10000"
    service = PrivatePortfolioService(PrivateJournal(journal))
    replayed = service._replay(service.records())
    assert build_risk_input(replayed, sellable_as_of=replayed.state.last_trade_date)["portfolio"]["policy"]["risk_tolerance"] == "UNKNOWN"
    assert journal.read_bytes() == before
