"""One TEST_ONLY account through Web risk, both sleeves, T+1 sells and replay."""
from copy import deepcopy
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from test_w5_private_portfolio_e2e import (
    BASELINE, POLICY, BUY_FILL, INITIALIZE_PATH, POLICY_PREPARE_PATH,
    POLICY_CONFIRM_PATH, RISK_PATH, PORTFOLIO_PATH, _prepare_fill,
    _confirmed_fill, _assert_private_headers,
)
from value_investment_agent.application.portfolio import private_risk_preview as preview
from value_investment_agent.application.portfolio import private_risk_projection as projection
from value_investment_agent.application.portfolio import held_continuity as continuity
from value_investment_agent.application.portfolio import private_portfolio_service as ledger
from value_investment_agent.application.portfolio.private_portfolio_service import (
    PrivateJournal, PrivatePortfolioService,
)
from value_investment_agent.domain.portfolio.dual_sleeve_risk import REPORT_SCHEMA
from value_investment_agent.domain.portfolio.security_attributes import official_observation
from value_investment_agent.presentation.web_api import private_routes


NOW = datetime.fromisoformat("2026-10-14T20:00:00+08:00")
SYMBOL = "300364"
PREVIEW = "/api/v1/private/portfolio/risk-preview"
POLICY_VIEW = "/api/v1/private/portfolio/policy"


def test_web_first_single_private_account_full_loop(client, make_client, workspace, monkeypatch):
    project, private = workspace

    def no_network(*args, **kwargs):
        pytest.fail("TEST_ONLY full loop must not acquire network data")

    monkeypatch.setattr("requests.sessions.Session.request", no_network)
    clock = [NOW]

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls.fromtimestamp(clock[0].timestamp(), tz=tz or clock[0].tzinfo)

    monkeypatch.setattr(private_routes, "datetime", FixedDatetime)
    monkeypatch.setattr(ledger, "datetime", FixedDatetime)
    # Only public verified-market boundaries are synthetic. These seams are not
    # proof of publication/admission; no private state or engine result is mocked.
    plan = {"symbol": SYMBOL, "research_version": "TEST_ONLY_FULL_LOOP",
            "case_sha256": "a" * 64, "entry_trigger_price": "10", "invalidation_price": "9.8",
            "market_trade_date": "2026-10-14", "data_available_at": "2026-10-14T15:01:00+08:00",
            "expires_after_session": "2026-10-15", "formal_eligibility": False,
            "current_reference_close": {}}
    monkeypatch.setattr(preview, "_current_plan", lambda *args: (
        {"publication_id": "TEST_ONLY_PUBLIC_PLAN_SEAM", "plan": deepcopy(plan)}, None))
    observation = official_observation(
        {"symbol": SYMBOL, "name": "TEST_ONLY", "exchange": "SZSE", "board": "CHINEXT",
         "listed_on": "2000-01-01", "security_type": "A股"}, industry_code="I",
        known_at=NOW - timedelta(hours=1), valid_until=NOW + timedelta(days=1),
        evidence_refs=[{"id": "TEST_ONLY_PUBLIC_ATTRIBUTE_SEAM", "path": "TEST_ONLY.json", "sha256": "b" * 64}],
    )
    monkeypatch.setattr(preview, "load_verified_security_attributes", lambda *args, **kwargs: [deepcopy(observation)])
    monkeypatch.setattr(projection, "_verified_attributes", lambda *args, **kwargs: [deepcopy(observation)])

    # Start cash-only: no held-security mark is needed to obtain the initial
    # account projection. A confirmed fill is a simulated manual record, not an order.
    initialized = client.post(INITIALIZE_PATH, json={
        **deepcopy(BASELINE), "idempotency_key": "full-loop-baseline", "account_scope": "TEST_ONLY_FULL_LOOP",
        "as_of": "2026-10-14", "confirmed_at": "2026-10-14T16:00:00+08:00",
    })
    _assert_private_headers(initialized)
    assert initialized.status_code == 200, initialized.text
    assert initialized.json()["status"] == "BASELINE_CONFIRMED"
    initial = client.get(PORTFOLIO_PATH).json()
    assert initial["revision"] == 1 and initial["positions"] == []
    assert Decimal(initial["cash_cny"]) == Decimal("10000")

    prepared_policy = client.post(POLICY_PREPARE_PATH, json={
        "idempotency_key": "full-loop-ips-prepare", "expected_revision": 1,
        "policy": {**deepcopy(POLICY), "hotspot_single_trade_risk_pct": "2",
                   "max_single_security_pct": "60", "max_single_industry_pct": "80",
                   "concentration_allowed": True},
    })
    assert prepared_policy.status_code == 200, prepared_policy.text
    assert prepared_policy.json()["missing_fields"] == []
    confirmed_policy = client.post(POLICY_CONFIRM_PATH, json={
        "idempotency_key": "full-loop-ips-confirm", "expected_revision": 2,
        "prepared_record_sha256": prepared_policy.json()["record_sha256"],
        "confirmed_at": "2026-10-14T17:00:00+08:00", "confirmation_note": "TEST_ONLY_IPS_BOTH_SLEEVES",
    })
    assert confirmed_policy.status_code == 200, confirmed_policy.text
    assert confirmed_policy.json()["status"] == "POLICY_CONFIRMED"
    policy_view = client.get(POLICY_VIEW).json()
    assert policy_view["status"] == "CONFIRMED"

    reconciled = client.post("/api/v1/private/portfolio/reconcile", json={
        "idempotency_key": "full-loop-synthetic-statement", "expected_revision": 3,
        "reconciled_at": "2026-10-14T18:00:00+08:00", "confirmation_note": "TEST_ONLY_SYNTHETIC_STATEMENT",
        "account_evidence": {"id": "TEST_ONLY_STATEMENT_NO_REAL_ACCOUNT", "kind": "broker_statement"},
    })
    assert reconciled.status_code == 200, reconciled.text
    journal = private / "portfolio/journal.jsonl"
    before_preview = journal.read_bytes()
    assumptions = {field: "0" for field in preview.ASSUMPTION_FIELDS}
    assumptions.update(lot_size="1", max_trade_notional_cny="1500", minimum_buy_fee_cny="1",
                       minimum_sell_fee_cny="1", gap_stress_cny="0.05",
                       entry_slippage_cny="0.01", exit_slippage_cny="0.01")
    choices = {"acknowledged": True,
               "execution": {"liquid": True, "limit_up": False, "limit_down": False},
               "holding_risks": [],
               "security_risks": [{"symbol": SYMBOL, "cyclical": False, "common_factors": []}]}
    requested = client.post(PREVIEW, json={"symbol": SYMBOL, "assumptions": assumptions, "scenario": choices})
    assert requested.status_code == 200, requested.text
    risk = requested.json()
    assert risk["facts"]["account_scope"] == "TEST_ONLY_FULL_LOOP"
    assert risk["facts"]["revision"] == 4
    assert Decimal(risk["facts"]["cash_cny"]) == Decimal("10000")
    scenario = risk["scenario_preview"]
    assert scenario["status"] == "QUANTITY_REVIEW_ONLY", scenario["blockers"]
    assert scenario["review_quantity"] > 0
    assert scenario["projection"]["account_revision"] == 4
    assert scenario["scope"] == "HYPOTHETICAL_CONFIRMED_ACCOUNT_PROJECTION"
    assert scenario["engine"]["schema_version"] == REPORT_SCHEMA
    assert scenario["engine"]["namespace"] == scenario["namespace"] == "SIMULATED"
    assert scenario["engine"]["acceptance_authority"] == "NONE"
    assert scenario["formal_eligibility"] is scenario["trade_eligible"] is False
    assert scenario["formal_review_quantity"] is None
    assert risk["sizing_preview"]["review_quantity"] is None
    assert risk["sizing_preview"]["formal_eligibility"] is False
    assert "CANDIDATE_LIQUIDITY_UNKNOWN" in risk["sizing_preview"]["blockers"]
    assert journal.read_bytes() == before_preview

    manual_fill = {**deepcopy(BUY_FILL), "transaction_id": "TEST_ONLY_FULL_LOOP_MANUAL_BUY",
                   "symbol": SYMBOL, "exchange": "SZSE", "sleeve": "HOTSPOT_SATELLITE",
                   "trade_date": "2026-10-14", "next_sell_session": "2026-10-15"}
    assert Decimal(manual_fill["quantity"]) <= Decimal(str(scenario["review_quantity"]))
    prepared_fill = _prepare_fill(client, fill=manual_fill, key="full-loop-fill-prepare", expected_revision=4)
    assert prepared_fill.status_code == 200, prepared_fill.text
    # Preparation alone must leave cash, holdings and confirmed history unchanged.
    pending = client.get(PORTFOLIO_PATH).json()
    assert pending["cash_cny"] == initial["cash_cny"] and pending["positions"] == []
    assert pending["trades"] == []
    confirmed_fill = _confirmed_fill(client, prepared=prepared_fill.json(), key="full-loop-fill-confirm",
                                     expected_revision=5, at="2026-10-14T19:00:00+08:00")
    assert confirmed_fill.status_code == 200, confirmed_fill.text
    assert confirmed_fill.json()["status"] == "FILL_CONFIRMED"
    held = client.get(PORTFOLIO_PATH).json()
    assert held["revision"] == 6
    assert Decimal(held["cash_cny"]) == Decimal("8999")
    assert len(held["positions"]) == 1
    position = held["positions"][0]
    assert position["symbol"] == SYMBOL and Decimal(position["quantity"]) == 100
    assert Decimal(position["cost_cny"]) == Decimal("1001")
    assert position["sleeves"][0]["sleeve"] == "HOTSPOT_SATELLITE"
    assert len(held["trades"]) == 1
    assert held["trades"][0]["transaction_id"] == manual_fill["transaction_id"]

    before_review = journal.read_bytes()
    review = client.get(RISK_PATH)
    _assert_private_headers(review)
    assert review.status_code == 200, review.text
    reviewed = review.json()
    assert reviewed["facts"]["revision"] == 6
    assert reviewed["facts"]["confirmed_fill_count"] == 1
    assert Decimal(reviewed["facts"]["cash_cny"]) == Decimal("8999")
    assert reviewed["facts"]["reconciliation_status"] == "PENDING_RECONCILIATION"
    assert reviewed["engine"]["trade_eligible"] is False
    assert reviewed["engine"]["position_guidance"] is None
    assert "reconciliation" in reviewed["blockers"]
    stale_preview = client.post(PREVIEW, json={"symbol": SYMBOL, "assumptions": assumptions,
                                               "scenario": choices})
    assert stale_preview.status_code == 200, stale_preview.text
    assert stale_preview.json()["scenario_preview"]["review_quantity"] is None
    assert "reconciliation" in stale_preview.json()["scenario_preview"]["blockers"]
    assert journal.read_bytes() == before_review

    # A fresh app/session replays the same account, confirmed IPS and trade history.
    restarted = make_client()
    replayed_response = restarted.get(PORTFOLIO_PATH)
    _assert_private_headers(replayed_response)
    assert replayed_response.status_code == 200, replayed_response.text
    replayed = replayed_response.json()
    for field in ("revision", "cash_cny", "positions", "trades", "realized_pnl_cny"):
        assert replayed[field] == held[field]
    assert restarted.get(POLICY_VIEW).json() == {**policy_view, "revision": 6}
    assert restarted.get(RISK_PATH).json()["facts"] == reviewed["facts"]
    service = PrivatePortfolioService(PrivateJournal(journal))
    assert len(service.records()) == 6
    same_day = service.portfolio_view(today=NOW.date())
    assert Decimal(same_day["positions"][0]["sleeves"][0]["sellable_quantity"]) == 0
    assert journal.read_bytes() == before_review
    assert not list(project.rglob("journal.jsonl"))

    # Both sleeves own the same symbol; cash is one shared account balance.
    core_buy = {**manual_fill, "transaction_id": "TEST_ONLY_CORE_BUY", "sleeve": "CORE_VALUE"}
    core_prepared = _prepare_fill(client, fill=core_buy, key="core-buy-prepare", expected_revision=6)
    assert core_prepared.status_code == 200, core_prepared.text
    core_confirmed = _confirmed_fill(client, prepared=core_prepared.json(), key="core-buy-confirm",
                                     expected_revision=7, at="2026-10-14T19:30:00+08:00")
    assert core_confirmed.status_code == 200, core_confirmed.text
    both = client.get(PORTFOLIO_PATH).json()
    assert both["revision"] == 8
    assert len(both["positions"]) == 1
    assert Decimal(both["cash_cny"]) == Decimal("7998")
    assert Decimal(both["positions"][0]["quantity"]) == 200
    assert Decimal(both["positions"][0]["cost_cny"]) == Decimal("2002")
    sleeves_before = {row["sleeve"]: row for row in both["positions"][0]["sleeves"]}
    assert set(sleeves_before) == {"CORE_VALUE", "HOTSPOT_SATELLITE"}
    for row in sleeves_before.values():
        assert Decimal(row["quantity"]) == 100
        assert Decimal(row["cost_cny"]) == 1001
        assert Decimal(row["sellable_quantity"]) == 0

    sell = {"transaction_id": "TEST_ONLY_EARLY_SELL", "side": "SELL",
            "sleeve": "HOTSPOT_SATELLITE", "symbol": SYMBOL, "exchange": "SZSE",
            "quantity": "50", "price_cny": "12", "fees_cny": "2", "trade_date": "2026-10-14"}
    before_rejected = journal.read_bytes()
    early = _prepare_fill(client, fill=sell, key="early-sell", expected_revision=8)
    assert early.status_code == 422, early.text
    assert "insufficient sellable" in early.json()["detail"]
    assert journal.read_bytes() == before_rejected
    assert client.get(PORTFOLIO_PATH).json() == both

    clock[0] = NOW + timedelta(days=1)
    unlocked = client.get(PORTFOLIO_PATH).json()
    for row in unlocked["positions"][0]["sleeves"]:
        assert Decimal(row["sellable_quantity"]) == 100
    # The other sleeve's shares cannot fund a sell beyond this sleeve's 100.
    oversized = _prepare_fill(client, fill={**sell, "transaction_id": "TEST_ONLY_CROSS_SLEEVE_SELL",
        "trade_date": "2026-10-15", "quantity": "150"}, key="oversized-sell", expected_revision=8)
    assert oversized.status_code == 422, oversized.text
    assert "insufficient sellable" in oversized.json()["detail"]
    assert journal.read_bytes() == before_rejected

    partial = {**sell, "transaction_id": "TEST_ONLY_PARTIAL_SELL", "trade_date": "2026-10-15"}
    sell_prepared = _prepare_fill(client, fill=partial, key="partial-sell-prepare", expected_revision=8)
    assert sell_prepared.status_code == 200, sell_prepared.text
    pending_sell = client.get(PORTFOLIO_PATH).json()
    for field in ("cash_cny", "positions", "trades", "realized_pnl_cny"):
        assert pending_sell[field] == unlocked[field]
    sold_response = _confirmed_fill(client, prepared=sell_prepared.json(), key="partial-sell-confirm",
                                    expected_revision=9, at="2026-10-15T19:00:00+08:00")
    assert sold_response.status_code == 200, sold_response.text
    sold = client.get(PORTFOLIO_PATH).json()
    assert sold["revision"] == 10
    # 10000 - 2*(100*10+1) + (50*12-2); cost removed is 1001/2.
    assert Decimal(sold["cash_cny"]) == Decimal("8596")
    assert Decimal(sold["realized_pnl_cny"]) == Decimal("97.5")
    assert len(sold["positions"]) == 1
    remaining = sold["positions"][0]
    assert Decimal(remaining["quantity"]) == 150
    assert Decimal(remaining["cost_cny"]) == Decimal("1501.5")
    sleeves_after = {row["sleeve"]: row for row in remaining["sleeves"]}
    assert sleeves_after["CORE_VALUE"] == next(
        row for row in unlocked["positions"][0]["sleeves"] if row["sleeve"] == "CORE_VALUE")
    assert Decimal(sleeves_after["HOTSPOT_SATELLITE"]["quantity"]) == 50
    assert Decimal(sleeves_after["HOTSPOT_SATELLITE"]["cost_cny"]) == Decimal("500.5")
    assert Decimal(sleeves_after["HOTSPOT_SATELLITE"]["sellable_quantity"]) == 50
    assert [row["transaction_id"] for row in sold["trades"]] == [
        manual_fill["transaction_id"], core_buy["transaction_id"], partial["transaction_id"]]

    # Public selection has dropped this symbol. Real held projection still tracks
    # the journal position, without inventing a verified retained market plan.
    selected = [{"symbol": SYMBOL, "price_action_plan": deepcopy(plan)}]
    monkeypatch.setattr(continuity, "load_price_conditions", lambda *a, **k: {"items": deepcopy(selected)})
    monkeypatch.setattr(continuity, "load_registered_value_action_plans", lambda *a, **k: {"items": []})
    held_route = "/api/v1/private/portfolio/held-continuity"
    before_tracking = journal.read_bytes()
    selected_response = client.get(held_route)
    assert selected_response.status_code == 200, selected_response.text
    assert selected_response.json()["items"][0]["selected_today"] is True
    selected.clear()
    selected.extend({"symbol": f"60000{i}", "price_action_plan": {
        **deepcopy(plan), "symbol": f"60000{i}"}} for i in range(5))
    assert len(selected) == 5 and SYMBOL not in {row["symbol"] for row in selected}
    dropped_response = client.get(held_route)
    assert dropped_response.status_code == 200, dropped_response.text
    dropped = dropped_response.json()
    assert dropped["revision"] == 10
    assert len(dropped["items"]) == 1
    tracked = dropped["items"][0]
    assert tracked["symbol"] == SYMBOL and Decimal(tracked["quantity"]) == 150
    assert tracked["selected_today"] is False
    assert tracked["tracking_basis"] == "ACTUAL_HELD_SECURITY_NOT_RANKING"
    assert tracked["formal_eligibility"] is False
    assert tracked["personal_sell_permission"] is False
    assert tracked["strategy_plan"] is None
    assert tracked["data_gaps"]
    assert tracked["sleeves"] == remaining["sleeves"]

    final_restart = make_client()
    replayed_final = final_restart.get(PORTFOLIO_PATH)
    _assert_private_headers(replayed_final)
    assert replayed_final.status_code == 200, replayed_final.text
    assert replayed_final.json() == sold
    assert final_restart.get(POLICY_VIEW).json() == {**policy_view, "revision": 10}
    restarted_tracking = final_restart.get(held_route)
    assert restarted_tracking.status_code == 200, restarted_tracking.text
    assert restarted_tracking.json()["items"] == dropped["items"]
    final_risk = final_restart.get(RISK_PATH).json()
    assert final_risk["facts"]["confirmed_fill_count"] == 3
    assert Decimal(final_risk["facts"]["cash_cny"]) == Decimal("8596")
    assert final_risk["engine"]["trade_eligible"] is False
    assert final_risk["engine"]["position_guidance"] is None
    assert len(service.records()) == 10
    assert journal.read_bytes() == before_tracking
    assert not list(project.rglob("journal.jsonl"))
