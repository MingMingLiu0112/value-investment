"""W5 private ledger HTTP continuity and privacy acceptance."""
from __future__ import annotations

from decimal import Decimal


PORTFOLIO_PATH = "/api/v1/portfolio"
INITIALIZE_PATH = "/api/v1/private/portfolio/initialize"
POLICY_PREPARE_PATH = "/api/v1/private/portfolio/policy/prepare"
POLICY_CONFIRM_PATH = "/api/v1/private/portfolio/policy/confirm"
RISK_PATH = "/api/v1/private/portfolio/risk"
FILL_PREPARE_PATH = "/api/v1/private/fills/prepare"
FILL_CONFIRM_PATH = "/api/v1/private/fills/confirm"
FILL_CANCEL_PATH = "/api/v1/private/fills/cancel"

BASELINE = {
    "idempotency_key": "w5-baseline",
    "expected_revision": 0,
    "account_scope": "TEST_ONLY_W5_ACCOUNT",
    "as_of": "2026-10-09",
    "cash_cny": "10000",
    "holdings": [],
    "sleeve_allocations": {},
    "policy": {},
    "confirmation_note": "TEST_ONLY_W5_BASELINE",
    "confirmed_at": "2026-10-09T20:00:00+08:00",
}

POLICY = {
    "investable_assets_cny": "10000",
    "core_value_budget_cny": "7000",
    "hotspot_budget_cny": "2000",
    "cash_reserve_cny": "1000",
    "minimum_cash_cny": "1000",
    "max_single_security_pct": "30",
    "max_single_industry_pct": "50",
    "max_factor_pct": "100",
    "hotspot_single_trade_risk_pct": "1",
    "max_drawdown_pct": "20",
    "financing_allowed": False,
    "risk_tools_allowed": False,
    "dividend_income_goal_cny": "0",
    "effective_date": "2026-10-09",
    "time_horizon_years": "5",
    "risk_tolerance": "BALANCED",
    "concentration_allowed": False,
    "sleeves": {
        "CORE_VALUE": {"cash_cny": "7000", "risk_budget_cny": "1000"},
        "HOTSPOT_SATELLITE": {
            "cash_cny": "2000",
            "risk_budget_cny": "200",
            "single_security_risk_cny": "100",
        },
    },
}

BUY_FILL = {
    "transaction_id": "W5-BUY-1",
    "side": "BUY",
    "sleeve": "CORE_VALUE",
    "symbol": "600005",
    "exchange": "SSE",
    "quantity": "100",
    "price_cny": "10",
    "fees_cny": "1",
    "trade_date": "2026-10-12",
    "next_sell_session": "2026-10-13",
    "trading_unit": "100",
}

EARLY_SELL_FILL = {
    "transaction_id": "W5-SELL-EARLY",
    "side": "SELL",
    "sleeve": "CORE_VALUE",
    "symbol": "600005",
    "exchange": "SSE",
    "quantity": "50",
    "price_cny": "10",
    "fees_cny": "1",
    "trade_date": "2026-10-12",
}

LATER_SELL_FILL = {
    **EARLY_SELL_FILL,
    "transaction_id": "W5-SELL-NEXT-DAY",
    "trade_date": "2026-10-13",
}


def _assert_private_headers(response) -> None:
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Pragma"] == "no-cache"
    assert response.headers["Expires"] == "0"
    assert response.headers["Vary"] == "Origin, X-Local-Session"


def _journal_record_count(private_root) -> int:
    journal = private_root / "portfolio" / "journal.jsonl"
    if not journal.exists():
        return 0
    return len(journal.read_text(encoding="utf-8").splitlines())


def _confirmed_fill(client, *, prepared: dict, key: str, expected_revision: int, at: str):
    response = client.post(
        FILL_CONFIRM_PATH,
        json={
            "idempotency_key": key,
            "expected_revision": expected_revision,
            "prepared_record_sha256": prepared["record_sha256"],
            "confirmed_at": at,
            "confirmation_note": "TEST_ONLY_W5_CONFIRM",
        },
    )
    _assert_private_headers(response)
    return response


def _prepare_fill(client, *, fill: dict, key: str, expected_revision: int):
    response = client.post(
        FILL_PREPARE_PATH,
        json={
            "idempotency_key": key,
            "expected_revision": expected_revision,
            "fill": fill,
        },
    )
    _assert_private_headers(response)
    return response


def test_w5_private_portfolio_http_e2e(client, make_client, workspace, monkeypatch):
    _, private = workspace

    future_baseline = {
        **BASELINE,
        "idempotency_key": "w5-future-baseline",
        "as_of": "2099-01-01",
        "confirmed_at": "2099-01-01T20:00:00+08:00",
    }
    future = client.post(INITIALIZE_PATH, json=future_baseline)
    _assert_private_headers(future)
    assert future.status_code == 422
    assert future.json()["status"] == "VALIDATION_FAILED"
    assert "future" in future.json()["detail"]
    assert _journal_record_count(private) == 0

    initialized = client.post(INITIALIZE_PATH, json=BASELINE)
    _assert_private_headers(initialized)
    assert initialized.status_code == 200, initialized.text
    assert initialized.json()["status"] == "BASELINE_CONFIRMED"

    policy_prepared = client.post(
        POLICY_PREPARE_PATH,
        json={"idempotency_key": "w5-policy-prepare", "expected_revision": 1, "policy": POLICY},
    )
    _assert_private_headers(policy_prepared)
    assert policy_prepared.status_code == 200, policy_prepared.text

    policy_confirmed = client.post(
        POLICY_CONFIRM_PATH,
        json={
            "idempotency_key": "w5-policy-confirm",
            "expected_revision": 2,
            "prepared_record_sha256": policy_prepared.json()["record_sha256"],
            "confirmed_at": "2026-10-10T20:00:00+08:00",
            "confirmation_note": "TEST_ONLY_W5_IPS_CONFIRM",
        },
    )
    _assert_private_headers(policy_confirmed)
    assert policy_confirmed.status_code == 200, policy_confirmed.text
    assert policy_confirmed.json()["status"] == "POLICY_CONFIRMED"

    risk = client.get(RISK_PATH)
    _assert_private_headers(risk)
    assert risk.status_code == 200, risk.text
    risk_body = risk.json()
    assert risk_body["action"] == "no_order"
    assert risk_body["engine"]["trade_eligible"] is False
    assert risk_body["engine"]["position_guidance"] is None

    buy_prepared = _prepare_fill(
        client, fill=BUY_FILL, key="w5-buy-prepare", expected_revision=3
    )
    assert buy_prepared.status_code == 200, buy_prepared.text
    assert buy_prepared.json()["status"] == "FILL_PREPARED"
    records_before_rejections = _journal_record_count(private)

    future_fill = _confirmed_fill(
        client,
        prepared=buy_prepared.json(),
        key="w5-buy-future-confirm",
        expected_revision=4,
        at="2099-01-01T20:00:00+08:00",
    )
    assert future_fill.status_code == 422
    assert future_fill.json()["status"] == "VALIDATION_FAILED"
    assert "future" in future_fill.json()["detail"]
    assert _journal_record_count(private) == records_before_rejections

    future_cancel = client.post(
        FILL_CANCEL_PATH,
        json={
            "idempotency_key": "w5-buy-future-cancel",
            "expected_revision": 4,
            "prepared_record_sha256": buy_prepared.json()["record_sha256"],
            "cancelled_at": "2099-01-01T20:00:00+08:00",
            "reason": "TEST_ONLY_FUTURE_CANCEL",
        },
    )
    _assert_private_headers(future_cancel)
    assert future_cancel.status_code == 422
    assert future_cancel.json()["status"] == "VALIDATION_FAILED"
    assert "future" in future_cancel.json()["detail"]
    assert _journal_record_count(private) == records_before_rejections

    buy_confirmed = _confirmed_fill(
        client,
        prepared=buy_prepared.json(),
        key="w5-buy-confirm",
        expected_revision=4,
        at="2026-10-12T21:00:00+08:00",
    )
    assert buy_confirmed.status_code == 200, buy_confirmed.text
    assert buy_confirmed.json()["status"] == "FILL_CONFIRMED"
    assert buy_confirmed.json()["cash_cny"] == "8999"
    bought_position = buy_confirmed.json()["positions"][0]
    assert bought_position["quantity"] == "100"

    early_sell = _prepare_fill(
        client, fill=EARLY_SELL_FILL, key="w5-early-sell-prepare", expected_revision=5
    )
    assert early_sell.status_code == 422
    assert early_sell.json()["status"] == "VALIDATION_FAILED"
    assert "insufficient sellable" in early_sell.json()["detail"]
    assert _journal_record_count(private) == 5

    sell_prepared = _prepare_fill(
        client, fill=LATER_SELL_FILL, key="w5-next-day-sell-prepare", expected_revision=5
    )
    assert sell_prepared.status_code == 200, sell_prepared.text
    sell_confirmed = _confirmed_fill(
        client,
        prepared=sell_prepared.json(),
        key="w5-next-day-sell-confirm",
        expected_revision=6,
        at="2026-10-13T21:00:00+08:00",
    )
    assert sell_confirmed.status_code == 200, sell_confirmed.text
    assert sell_confirmed.json()["cash_cny"] == "9498"
    assert sell_confirmed.json()["positions"][0]["quantity"] == "50"

    restarted = make_client()
    replayed = restarted.get(PORTFOLIO_PATH)
    _assert_private_headers(replayed)
    assert replayed.status_code == 200, replayed.text
    body = replayed.json()
    assert body["status"] == "CONNECTED"
    assert body["revision"] == 7
    assert body["cash_cny"] == "9498"
    assert Decimal(body["realized_pnl_cny"]) == Decimal("-1.5")
    assert body["positions"][0]["quantity"] == "50"
    assert Decimal(body["positions"][0]["cost_cny"]) == Decimal("500.5")
    assert len(body["trades"]) == 2

    unauthorized = client.get(PORTFOLIO_PATH, headers={"x-local-session": "invalid"})
    _assert_private_headers(unauthorized)
    assert unauthorized.status_code == 401

    forbidden = client.post(
        INITIALIZE_PATH,
        json={**BASELINE, "idempotency_key": "w5-cross-site"},
        headers={"Origin": "https://example.com"},
    )
    _assert_private_headers(forbidden)
    assert forbidden.status_code == 403

    conflict = client.post(
        INITIALIZE_PATH,
        json={**BASELINE, "idempotency_key": "w5-second-baseline"},
    )
    _assert_private_headers(conflict)
    assert conflict.status_code == 409

    malformed = client.post(
        INITIALIZE_PATH,
        content=b"{",
        headers={"Content-Type": "application/json"},
    )
    _assert_private_headers(malformed)
    assert malformed.status_code == 422

    records_before_unavailable = _journal_record_count(private)
    project, _ = workspace
    monkeypatch.setenv("VALUE_INVESTMENT_PRIVATE_ROOT", str(project / "absent-private-root"))
    unavailable = client.post(
        INITIALIZE_PATH,
        json={**BASELINE, "idempotency_key": "w5-unavailable"},
    )
    _assert_private_headers(unavailable)
    assert unavailable.status_code == 503
    assert unavailable.json()["status"] == "PRIVATE_ROOT_UNAVAILABLE"
    assert _journal_record_count(private) == records_before_unavailable
