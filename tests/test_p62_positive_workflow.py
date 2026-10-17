"""TEST_ONLY positive integration; synthetic qualification is never real approval."""
from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
import hashlib
import json

import pytest

from test_private_ips_policy import full_policy
from test_portfolio_risk_assessment import _attributes
from test_value_action_plan import _policy
from test_value_decision_explanation import synthetic_restored
from value_investment_agent.application.decision.value_action_plan import project_value_action_plan
from value_investment_agent.application.portfolio import judgment_snapshot
from value_investment_agent.application.portfolio.private_portfolio_service import (
    PrivateJournal, PrivatePortfolioService,
)
from value_investment_agent.application.portfolio.private_risk_projection import build_risk_input
from value_investment_agent.application.product.dual_sleeve_risk import append_dual_sleeve_manual_record
from value_investment_agent.application.product.value_decision_explanation import project_value_decision_explanation
from value_investment_agent.domain.portfolio.dual_sleeve_records import validate_manual_history
from value_investment_agent.domain.portfolio.dual_sleeve_risk import review_dual_sleeve_risk


@pytest.fixture
def qualified_test_plan():
    restored = synthetic_restored("BUY_CANDIDATE")
    original = deepcopy(restored.recommendation.as_policy())
    explanation = project_value_decision_explanation(restored, evidence_scope="SYNTHETIC_TEST")
    policy = replace(_policy(explanation), model_id=restored.recommendation.input_model_id)
    plan = project_value_action_plan(restored, evidence_scope="SYNTHETIC_TEST", policy=policy)
    assert explanation["verification"]["repository_replay"] is True
    assert plan["candidate_action"] == "BUY_CANDIDATE" and plan["action_intent"] == "OPEN"
    assert plan["entry_condition"]["triggered"] is True
    assert plan["formal_eligibility"] is True and plan["formal_eligibility_blockers"] == []
    assert plan["portfolio_eligibility"] is None and plan["requires_human_review"] is True
    assert plan["position_guidance"] is None and plan["action"] == "no_order"
    assert restored.recommendation.as_policy() == original
    return plan


def _simulated_review(service, *, day, mark=None, review_hour=21):
    """Copy replayed TEST_ONLY facts into an explicit hypothetical risk contract.

    The journal's ACTUAL schema is not production authority. Marks, attributes
    and committed risk below are explicit test assumptions, not verified quotes.
    """
    service.reconcile({"idempotency_key": f"reconcile-{day}-{review_hour}", "expected_revision": len(service.records()),
        "reconciled_at": f"{day}T{review_hour - 1:02}:02:00+08:00",
        "confirmation_note": "TEST_ONLY internal arithmetic"})
    replayed = service._replay(service.records())
    prices = ({lot.symbol: {"price_cny": str(mark), "trade_date": day} for lot in replayed.state.lots}
              if mark is not None else {})
    now = datetime.fromisoformat(f"{day}T{review_hour:02}:00:00+08:00")
    data = build_risk_input(replayed, sellable_as_of=date.fromisoformat(day),
                           generated_at=now, namespace="SIMULATED", _prices=prices)
    data["portfolio"]["snapshot"]["namespace"] = "SIMULATED"
    data["shared_budget"]["policy_scope"] = "SYNTHETIC_POLICY_ONLY"
    data["security_attributes"] = [_attributes(symbol).as_policy()
                                   for symbol in sorted({lot.symbol for lot in replayed.state.lots})]
    for allocation in data["allocations"]:
        allocation["committed_risk_cny"] = "100"  # Explicit hypothetical exposure, not inferred stop risk.
    before = service.journal.path.read_bytes()
    original = deepcopy(data)
    report = review_dual_sleeve_risk(data, generated_at=now, allow_synthetic=True)
    assert data == original and service.journal.path.read_bytes() == before
    assert report["namespace"] == "SIMULATED"
    assert report["sensitivity"] == "SIMULATED_DEMONSTRATION"
    assert report["acceptance_authority"] == "NONE" and report["trade_eligible"] is False
    assert report["position_guidance"] is None and report["action"] == "no_order"
    return report


@pytest.mark.parametrize("mark_delta,expected_warnings", [
    ("0.05", []), ("0", ["HOTSPOT_SATELLITE:budget_exceeded"]),
])
def test_qualified_value_plan_simulated_risk_manual_fills_cold_replay_and_review(
        tmp_path, monkeypatch, qualified_test_plan, mark_delta, expected_warnings):
    plan = qualified_test_plan
    # The inherited fixture has a known Tuesday and subsequent exchange sessions.
    assert plan["decision_as_of"] == "2026-09-22"
    symbol = plan["symbol"]
    buy_price = Decimal(plan["entry_trigger_price"])
    sell_price = buy_price + Decimal("2")
    quantity, fee = Decimal("100"), Decimal("5")
    service = PrivatePortfolioService(PrivateJournal(tmp_path / "TEST_ONLY-P62.jsonl"))
    service.initialize({"idempotency_key": "init", "expected_revision": 0,
        "account_scope": "TEST_ONLY_SYNTHETIC_P62_NOT_REAL_APPROVAL", "as_of": "2026-09-21",
        "cash_cny": "10000", "holdings": [], "sleeve_allocations": {}, "policy": {},
        "confirmed_at": "2026-09-21T20:00:00+08:00", "confirmation_note": "TEST_ONLY"})
    policy = full_policy()
    policy.update(effective_date="2026-09-22", emergency_cash_cny="100",
                  liquidity_needs_cny="100", max_cyclical_exposure_pct="70", tax_regime="TEST_ONLY")
    policy["sleeves"]["CORE_VALUE"]["cash_cny"] = "7000"
    _, digest = service.prepare_policy({"idempotency_key": "ips", "expected_revision": 1, "policy": policy})
    service = PrivatePortfolioService(PrivateJournal(service.journal.path))
    service.confirm_policy({"idempotency_key": "ips-confirm", "expected_revision": len(service.records()),
        "prepared_record_sha256": digest, "confirmed_at": "2026-09-21T20:01:00+08:00",
        "confirmation_note": "TEST_ONLY simulated human IPS confirmation"})
    assert service.policy_view()["status"] == "CONFIRMED"
    initial = _simulated_review(service, day="2026-09-22", review_hour=19)
    assert initial["status"] == "RISK_REVIEW_CALCULATED" and initial["blockers"] == []
    assert initial["sleeves"]["CORE_VALUE"]["available_funds_cny"] == "7000"

    packet = {"publication_id": "TEST_ONLY-P62", "content_sha256": "a" * 64,
              "value_price_conditions": {symbol: deepcopy(plan)}}
    # Replace only the publication storage boundary; qualification and engines run for real.
    monkeypatch.setattr(judgment_snapshot, "load_current_packet", lambda root: (packet, None))
    captured = None
    for side, price, day in (("BUY", buy_price, "2026-09-22"), ("SELL", sell_price, "2026-09-24")):
        before = service.portfolio_view(today=date.fromisoformat(day))
        _, digest = service.prepare_fill({"idempotency_key": side, "expected_revision": len(service.records()),
            "fill": {"transaction_id": "TEST_ONLY-" + side, "side": side, "sleeve": "CORE_VALUE",
                "symbol": symbol, "exchange": "SSE", "quantity": str(quantity), "price_cny": str(price),
                "fees_cny": str(fee), "trade_date": day, "trading_unit": "100" if side == "BUY" else None,
                "next_sell_session": "2026-09-23" if side == "BUY" else None,
                "decision_id": symbol, "research_version": plan["research_version"]}}, repository_root=tmp_path)
        assert service.portfolio_view(today=date.fromisoformat(day))["cash_cny"] == before["cash_cny"]
        service = PrivatePortfolioService(PrivateJournal(service.journal.path))
        assert service.portfolio_view()["pending_draft"]["prepared_record_sha256"] == digest
        request = {"idempotency_key": side + "-confirm", "expected_revision": len(service.records()),
            "prepared_record_sha256": digest, "confirmed_at": day + "T20:00:00+08:00",
            "confirmation_note": "TEST_ONLY human simulated fill; no broker order"}
        confirmation = service.confirm_fill(request)
        assert service.confirm_fill(request) == confirmation
        view = service.portfolio_view(today=date.fromisoformat(day))
        if side == "BUY":
            assert Decimal(view["cash_cny"]) == Decimal("10000") - quantity * buy_price - fee
            assert Decimal(view["positions"][0]["cost_cny"]) == quantity * buy_price + fee
            assert view["positions"][0]["sleeves"][0]["sellable_quantity"] == "0"
            assert service.portfolio_view(today=date(2026, 9, 23))["positions"][0]["sleeves"][0]["sellable_quantity"] == "100"
            captured = deepcopy(view["trades"][0]["judgment_snapshot"])
            assert captured["plan"] == plan and captured["trade_time_availability_proven"] is False
            assert captured["personal_risk_at_trade"] is None
            # Distinguish a small hypothetical gain from fee-only equity loss:
            # the latter really reduces the satellite's shared equity cap.
            unrealized = quantity * Decimal(mark_delta) - fee
            risk = _simulated_review(service, day=day, mark=buy_price + Decimal(mark_delta))
            assert risk["status"] == ("REVIEW_REQUIRED" if expected_warnings else "RISK_REVIEW_CALCULATED")
            assert risk["blockers"] == expected_warnings
            assert Decimal(risk["aggregate"]["total_assets_cny"]) == Decimal("10000") + unrealized
            assert risk["aggregate"]["existing_risk_assessment"]["status"] == "PASS"
            assert Decimal(risk["sleeves"]["CORE_VALUE"]["unrealized_pnl_cny"]) == unrealized
            # A later publication cannot rewrite the saved recording-time judgment.
            packet["value_price_conditions"][symbol]["entry_trigger_price"] = "999"
        else:
            assert view["positions"] == []
            assert Decimal(view["cash_cny"]) == Decimal("10190")
            assert Decimal(view["realized_pnl_cny"]) == quantity * (sell_price - buy_price) - 2 * fee

    service = PrivatePortfolioService(PrivateJournal(service.journal.path))
    final = service.portfolio_view(today=date(2026, 9, 24))
    assert final["trades"][0]["judgment_snapshot"] == captured
    assert [trade["side"] for trade in final["trades"]] == ["BUY", "SELL"]
    assert final["positions"] == [] and final["total_equity_cny"] == "10190.00"
    closed_risk = _simulated_review(service, day="2026-09-24")
    assert closed_risk["status"] == "REVIEW_REQUIRED"
    assert closed_risk["blockers"] == ["CORE_VALUE:budget_exceeded"]
    assert Decimal(closed_risk["aggregate"]["total_assets_cny"]) == Decimal(final["total_equity_cny"])

    # A separate SIMULATED PLAN/REVIEW chain records reflection, never another fill.
    journal_before = service.journal.path.read_bytes()
    now = datetime.fromisoformat("2026-09-24T21:00:00+08:00")
    body = dict(record_id="TEST_ONLY-plan", kind="PLAN", namespace="SIMULATED", sleeve="CORE_VALUE",
        symbol=symbol, recorded_at="2026-09-22T21:00:00+08:00", trade_date=plan["decision_as_of"],
        research_version_sha256=hashlib.sha256(plan["research_version"].encode()).hexdigest(),
        candidate_action=plan["candidate_action"], observed_price_cny=str(buy_price),
        reason="TEST_ONLY qualified synthetic value plan; no actual approval", risk_budget_cny="1400",
        invalidation_condition="Fundamental thesis and liquidity review, not an invented mechanical stop",
        user_confirmation="PENDING", plan_record_sha256=None, fill=None, retrospective=None,
        evidence_ref=captured["snapshot_sha256"])
    directory = tmp_path / ".tmp/TEST_ONLY-review"
    first = append_dual_sleeve_manual_record(root=tmp_path, directory=directory, body=body,
        expected_head_sha256=None, synthetic=True, generated_at=now)
    review_body = dict(body, record_id="TEST_ONLY-review", kind="REVIEW", user_confirmation="USER_CONFIRMED",
        recorded_at=now.isoformat(), trade_date="2026-09-24", plan_record_sha256=first["record_sha256"],
        retrospective="TEST_ONLY: two confirmed simulated fills; net realized PnL=" + final["realized_pnl_cny"]
        + "; closed quantity=0; synthetic risk review=" + closed_risk["status"] + "; no real approval")
    receipt = append_dual_sleeve_manual_record(root=tmp_path, directory=directory, body=review_body,
        expected_head_sha256=first["record_sha256"], synthetic=True, generated_at=now)
    history = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(directory.glob("*.json"))]
    assert validate_manual_history(history, namespace="SIMULATED", generated_at=now) == receipt["record_sha256"]
    assert receipt["kind"] == "REVIEW" and receipt["changes_holdings"] is False
    assert receipt["acceptance_authority"] == "NONE" and receipt["action"] == "no_order"
    assert history[-1]["body"]["fill"] is None
    assert service.journal.path.read_bytes() == journal_before
