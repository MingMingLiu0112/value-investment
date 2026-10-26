"""WEB-D2 P1: the confirmed journal really drives the dual-sleeve risk engine."""
from __future__ import annotations

from datetime import date

from value_investment_agent.application.portfolio.private_portfolio_service import (
    PrivateJournal,
    PrivatePortfolioService,
)
from value_investment_agent.application.portfolio.private_risk_projection import build_risk_input
from value_investment_agent.domain.portfolio.dual_sleeve_risk import REPORT_SCHEMA

RISK_PATH = "/api/v1/private/portfolio/risk"
PORTFOLIO_PATH = "/api/v1/portfolio"
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


SECOND_FILL = {
    "idempotency_key": "fill-2",
    "expected_revision": 4,
    "fill": {"transaction_id": "T2", "side": "BUY", "sleeve": "CORE_VALUE",
             "symbol": "600519", "exchange": "SSE", "quantity": "100",
             "price_cny": "1520.00", "fees_cny": "5.00", "trade_date": "2026-10-13",
             "next_sell_session": "2026-10-14", "trading_unit": "100"},
}


def confirm_fill(client, *, key: str, expected_revision: int, prepared_sha: str, confirmed_at: str):
    response = client.post(CONFIRM_PATH, json={
        "idempotency_key": key, "expected_revision": expected_revision,
        "prepared_record_sha256": prepared_sha,
        "confirmed_at": confirmed_at, "confirmation_note": "confirmed"})
    assert response.status_code == 200, response.text
    return response.json()


def reconcile(client, *, key: str, expected_revision: int, reconciled_at: str, **extra):
    response = client.post(RECONCILE_PATH, json={
        "idempotency_key": key, "expected_revision": expected_revision,
        "reconciled_at": reconciled_at, "confirmation_note": "reconciled", **extra})
    assert response.status_code == 200, response.text
    return response.json()


def initialize_fill_and_reconcile(client):
    """INITIALIZE -> FILL -> CONFIRM -> RECONCILE; returns the reconcile response."""
    client.post(INITIALIZE_PATH, json=BASELINE)
    prepared = client.post(PREPARE_PATH, json=FILL).json()
    confirm_fill(client, key="fill-1-confirm", expected_revision=2,
                 prepared_sha=prepared["record_sha256"], confirmed_at="2026-10-12T21:00:00+08:00")
    return reconcile(client, key="reconcile-1", expected_revision=3,
                     reconciled_at="2026-10-12T21:05:00+08:00")


def confirm_second_fill(client):
    prepared = client.post(PREPARE_PATH, json=SECOND_FILL).json()
    confirm_fill(client, key="fill-2-confirm", expected_revision=5,
                 prepared_sha=prepared["record_sha256"], confirmed_at="2026-10-13T21:00:00+08:00")


def test_new_fill_after_reconciliation_supersedes_the_snapshot(client, workspace):
    initialize_fill_and_reconcile(client)
    assert risk(client)["facts"]["reconciliation_status"] == "RECONCILED"

    confirm_second_fill(client)

    body = risk(client)
    facts = body["facts"]
    assert facts["confirmed_fill_count"] == 2
    assert facts["cash_cny"] == "47990.00"
    assert facts["cost_basis_total_cny"] == "1952010.00"
    # The old reconciliation snapshot must no longer be presented as current.
    assert facts["reconciliation_status"] == "PENDING_RECONCILIATION"
    assert "reconciliation" in body["blockers"]
    superseded = facts["reconciliation"]
    assert superseded["status"] == "PENDING_RECONCILIATION"
    assert superseded["superseded"] is True
    assert superseded["snapshot_version"] == 1
    assert superseded["state_version"] == 2
    assert superseded["scope"] == "INTERNAL_JOURNAL_REPLAY"

    # Whatever the risk engine receives must equal the latest confirmed state.
    _, private = workspace
    service = PrivatePortfolioService(PrivateJournal(private / "portfolio" / "journal.jsonl"))
    replayed = service._replay(service.records())
    risk_input = build_risk_input(replayed, sellable_as_of=date(2026, 10, 14))
    snapshot = risk_input["portfolio"]["snapshot"]
    # A freshly projected snapshot of the current confirmed state, not the stored one.
    assert snapshot["snapshot_id"] == f"private-journal-projection-{replayed.state.version}"
    assert snapshot["reconciliation_status"] == "PENDING_RECONCILIATION"
    assert snapshot["cash_cny"] == "47990.00"
    assert [(row["symbol"], row["quantity"]) for row in snapshot["holdings"]] == [("600519", "1300")]


def test_reconciliation_after_the_new_fill_restores_consistency(client):
    initialize_fill_and_reconcile(client)
    confirm_second_fill(client)
    reconcile(client, key="reconcile-2", expected_revision=6,
              reconciled_at="2026-10-13T21:05:00+08:00")

    body = risk(client)
    facts = body["facts"]
    assert facts["reconciliation_status"] == "RECONCILED"
    assert facts["reconciliation"]["superseded"] is False
    assert facts["reconciliation"]["snapshot_version"] == 2
    assert facts["reconciliation"]["state_version"] == 2
    assert "reconciliation" not in body["blockers"]


def test_reconciliation_distinguishes_internal_replay_from_external_account_evidence(client):
    # Default: the snapshot is an internal replay of the user-confirmed journal.
    body = initialize_fill_and_reconcile(client)
    assert body["reconciliation_scope"] == "INTERNAL_JOURNAL_REPLAY"
    view = client.get(PORTFOLIO_PATH).json()
    assert view["reconciliation"]["scope"] == "INTERNAL_JOURNAL_REPLAY"
    assert view["reconciliation"]["status"] == "RECONCILED"

    confirm_second_fill(client)
    body = reconcile(client, key="reconcile-2", expected_revision=6,
                     reconciled_at="2026-10-13T21:05:00+08:00",
                     account_evidence={"id": "broker-statement-2026-10-13",
                                       "kind": "broker_statement"})
    assert body["reconciliation_scope"] == "EXTERNAL_ACCOUNT_STATEMENT"
    view = client.get(PORTFOLIO_PATH).json()
    assert view["reconciliation"]["scope"] == "EXTERNAL_ACCOUNT_STATEMENT"
    assert view["reconciliation"]["superseded"] is False
