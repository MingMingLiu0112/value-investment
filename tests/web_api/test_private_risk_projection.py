"""WEB-D2 P1: the confirmed journal really drives the dual-sleeve risk engine."""
from __future__ import annotations

from value_investment_agent.domain.portfolio.dual_sleeve_risk import REPORT_SCHEMA

RISK_PATH = "/api/v1/private/portfolio/risk"
INITIALIZE_PATH = "/api/v1/private/portfolio/initialize"
PREPARE_PATH = "/api/v1/private/fills/prepare"
CONFIRM_PATH = "/api/v1/private/fills/confirm"
RECONCILE_PATH = "/api/v1/private/portfolio/reconcile"

BASELINE = {
    "idempotency_key": "init-1",
    "expected_revision": 0,
    "account_scope": "acct-demo",
    "as_of": "2026-10-10",
    "cash_cny": "500000.00",
    "holdings": [{"symbol": "600519", "exchange": "SSE", "quantity": "1000",
                  "cost_basis_cny": "1500000.00"}],
    "sleeve_allocations": {"600519": {"CORE_VALUE": "600", "HOTSPOT_SATELLITE": "400"}},
    "policy": {"investable_assets_cny": "2000000", "minimum_cash_cny": "100000",
               "max_single_security_pct": "10", "max_single_industry_pct": "30"},
    "confirmation_note": "initial confirm",
    "confirmed_at": "2026-10-10T20:00:00+08:00",
    "policy_as_of": "2026-10-10",
}
FILL = {
    "idempotency_key": "fill-1",
    "expected_revision": 1,
    "fill": {"transaction_id": "T1", "side": "BUY", "sleeve": "CORE_VALUE",
             "symbol": "600519", "exchange": "SSE", "quantity": "200",
             "price_cny": "1500.00", "fees_cny": "5.00", "trade_date": "2026-10-12",
             "next_sell_session": "2026-10-13", "trading_unit": "100"},
}


def risk(client):
    response = client.get(RISK_PATH)
    assert response.status_code == 200, response.text
    return response.json()


def test_risk_endpoint_requires_the_local_operator(make_client):
    client = make_client(authorize=False)
    assert client.get(RISK_PATH).status_code == 401


def test_unconnected_portfolio_reports_not_connected(client):
    body = risk(client)
    assert body["action"] == "no_order"
    assert body["status"] == "NOT_CONNECTED"
    assert body["blockers"] == ["PRIVATE_PORTFOLIO_NOT_CONNECTED"]
    assert body["engine"] is None
    assert body["facts"] is None


def test_confirmed_baseline_invokes_the_real_engine_and_lists_exact_gaps(client):
    client.post(INITIALIZE_PATH, json=BASELINE)
    body = risk(client)
    assert body["status"] == "BLOCKED_PRIVATE_INPUT"
    assert body["engine"]["schema_version"] == REPORT_SCHEMA
    assert body["engine"]["acceptance_authority"] == "NONE"
    assert body["engine"]["trade_eligible"] is False
    assert body["engine"]["position_guidance"] is None
    blockers = set(body["blockers"])
    assert blockers == set(body["engine"]["blockers"])
    # Fields the journal really carries must NOT be reported as missing.
    assert "investable_assets_cny" not in blockers
    assert "minimum_cash_cny" not in blockers
    assert "max_single_security_pct" not in blockers
    assert "max_single_industry_pct" not in blockers
    # Fields nobody has supplied yet stay precise gaps, never invented defaults.
    assert {"time_horizon_years", "concentration_allowed", "risk_tolerance"} <= blockers
    assert "holding_market_value" in blockers
    assert "reconciliation" in blockers


def test_facts_carry_confirmed_costs_and_never_a_market_value(client):
    client.post(INITIALIZE_PATH, json=BASELINE)
    facts = risk(client)["facts"]
    assert facts["cash_cny"] == "500000.00"
    assert facts["cost_basis_total_cny"] == "1500000.00"
    assert facts["price_status"] == "PRICE_NOT_ADMITTED"
    assert facts["reconciliation_status"] == "PENDING_RECONCILIATION"
    position = facts["positions"][0]
    assert position["symbol"] == "600519"
    assert position["quantity"] == "1000"
    assert position["market_value_cny"] is None
    assert position["unrealized_pnl_cny"] is None
    assert [row["sleeve"] for row in position["sleeves"]] == ["CORE_VALUE", "HOTSPOT_SATELLITE"]


def test_confirmed_fill_and_reconciliation_update_the_projection(client):
    client.post(INITIALIZE_PATH, json=BASELINE)
    prepared = client.post(PREPARE_PATH, json=FILL).json()
    client.post(CONFIRM_PATH, json={
        "idempotency_key": "fill-1-confirm", "expected_revision": 2,
        "prepared_record_sha256": prepared["record_sha256"],
        "confirmed_at": "2026-10-12T21:00:00+08:00", "confirmation_note": "confirmed"})
    client.post(RECONCILE_PATH, json={
        "idempotency_key": "reconcile-1", "expected_revision": 3,
        "reconciled_at": "2026-10-12T21:05:00+08:00", "confirmation_note": "reconciled"})
    body = risk(client)
    assert body["facts"]["cash_cny"] == "199995.00"
    # Confirmed buy fees are capitalised into cost, exactly like the ledger replay.
    assert body["facts"]["cost_basis_total_cny"] == "1800005.00"
    assert body["facts"]["reconciliation_status"] == "RECONCILED"
    assert body["facts"]["confirmed_fill_count"] == 1
    blockers = set(body["blockers"])
    assert "reconciliation" not in blockers
    assert "holding_market_value" in blockers
    assert body["engine"]["trade_eligible"] is False


def test_corrupt_journal_fails_closed_without_running_the_engine(client, workspace):
    _, private = workspace
    client.post(INITIALIZE_PATH, json=BASELINE)
    journal = private / "portfolio" / "journal.jsonl"
    journal.write_text(journal.read_text(encoding="utf-8") + "{broken\n", encoding="utf-8")
    body = risk(client)
    assert body["status"] == "PRIVATE_JOURNAL_INVALID"
    assert body["engine"] is None
    assert body["facts"] is None
