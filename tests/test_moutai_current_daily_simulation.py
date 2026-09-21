from datetime import date
from decimal import Decimal
import importlib.util
from pathlib import Path

import pytest

from value_investment_agent.virtual_account import VirtualAccount, replay


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "moutai_current_daily", ROOT / "scripts/build_moutai_current_daily_simulation.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_close_only_current_input_blocks_cross_date_model_without_inventing_a_fill():
    report = ROOT / "runtime/quote-sessions/20260916T085009803628Z/report.json"
    payload = MODULE.build(report)
    assert payload["decision"]["state"] == "blocked"
    assert "current_model_stale_for_quote_session" in payload["decision"]["reasons"]
    assert "p1_current_model_not_admitted" not in payload["decision"]["reasons"]
    assert payload["trade_approved"] is False


def test_archived_same_date_p1_evidence_is_replayable_but_stays_watch_when_price_lacks_margin():
    report = ROOT / "runtime/quote-sessions/20260916T085009803628Z/report.json"
    research = ROOT / "runtime/company-research"
    payload = MODULE.build(
        report,
        model_evidence=research / "600519-consolidated-parent-equity-residual-income-current-20260917T054806Z/evidence.json",
        scope_review_evidence=research / "600519-current-equity-scope-review-20260917T054807Z/evidence.json",
        thesis_evidence=research / "600519-current-thesis-20260917T061804Z/evidence.json",
        admission_evidence=research / "600519-current-valuation-admission-20260918T013206Z/evidence.json",
    )
    assert payload["observed_at"].startswith("2026-09-16")
    assert payload["thesis"]["compatible_with_quote_session"] is True
    assert payload["p1_admission"]["p1_current_model_admitted"] is True
    assert payload["decision"]["state"] == "watch"
    assert payload["decision"]["action"] == "no_order"
    assert Decimal(payload["decision"]["safety_margin"]) < Decimal("0")
    assert payload["trade_approved"] is False


def test_archived_same_date_execution_contract_still_cannot_force_an_order():
    report = ROOT / "runtime/quote-sessions/20260916T085009803628Z/report.json"
    research = ROOT / "runtime/company-research"
    payload = MODULE.build(
        report,
        execution_contract=ROOT / "runtime/strategy-validation/moutai-date-consistent-execution-contract-20260920T150000Z/evidence.json",
        model_evidence=research / "600519-consolidated-parent-equity-residual-income-current-20260917T054806Z/evidence.json",
        scope_review_evidence=research / "600519-current-equity-scope-review-20260917T054807Z/evidence.json",
        thesis_evidence=research / "600519-current-thesis-20260917T061804Z/evidence.json",
        admission_evidence=research / "600519-current-valuation-admission-20260918T013206Z/evidence.json",
    )
    assert payload["execution_contract"]["execution_ready"] is True
    assert payload["execution_contract"]["next_session"] == "2026-09-17"
    assert payload["decision"]["state"] == "watch"
    assert payload["decision"]["action"] == "no_order"
    assert payload["trade_approved"] is False


def test_p1_admission_rejects_a_model_from_a_different_evidence_chain():
    report = ROOT / "runtime/quote-sessions/20260916T085009803628Z/report.json"
    research = ROOT / "runtime/company-research"
    with pytest.raises(ValueError, match="different valuation model"):
        MODULE.build(
            report,
            model_evidence=research / "600519-consolidated-parent-equity-residual-income-current-20260917T054806Z/evidence.json",
            scope_review_evidence=research / "600519-current-equity-scope-review-20260917T054807Z/evidence.json",
            thesis_evidence=research / "600519-current-thesis-20260917T061804Z/evidence.json",
            admission_evidence=research / "600519-current-valuation-admission-20260920T060750Z/evidence.json",
        )


def test_close_only_session_rejects_a_pending_order_without_inventing_fill():
    account = VirtualAccount()
    account.pending_order = {"order_id": "pending", "side": "buy", "requested_quantity": 100,
                             "submitted_on": "2026-09-15", "decision_state": "proposed_entry"}
    session = {"date": "2026-09-16", "open": None, "close": "1258", "execution_ready": False}
    account, journal = replay([session], {}, account)
    assert journal[0]["fill"] is None
    assert journal[0]["rejected_order_reason"] == "execution_state_unknown"
    assert account.shares == 0 and account.cash == Decimal("1000000")


def test_entry_proposal_freezes_a_next_session_budget_limit_and_liquidity_basis():
    terms = MODULE.bounded_execution_terms(
        decision={"state": "proposed_entry", "quantity": 100,
                  "sizing": {"permitted_budget_cny": "40000"}},
        observed_at=MODULE.datetime.fromisoformat("2026-09-18T15:00:00+08:00"),
        value=Decimal("1500"),
        execution={"execution_ready": True, "path": "runtime/contract.json", "sha256": "a" * 64,
                   "next_session": "2026-09-21", "slippage_bps": "10", "liquidity_budget_cny": "500000"},
        model_ref={"sha256": "b" * 64}, admission={"sha256": "c" * 64},
    )
    assert terms == {
        "version": "next-session-bounded-order-v1", "valid_session": "2026-09-21",
        "limit_price": "1050.00", "cash_budget_cny": "40000", "liquidity_budget_cny": "500000",
        "liquidity_as_of": "2026-09-18", "slippage_bps": "10",
        "basis_id": "600519-p2-2026-09-18-bbbbbbbbbbbb-cccccccccccc-aaaaaaaaaaaa",
    }


def test_reduce_proposal_uses_dated_value_as_a_net_proceeds_floor():
    terms = MODULE.bounded_execution_terms(
        decision={"state": "proposed_reduce", "quantity": 100,
                  "sizing": {"permitted_budget_cny": "0"}},
        observed_at=MODULE.datetime.fromisoformat("2026-09-18T15:00:00+08:00"),
        value=Decimal("1200.123"),
        execution={"execution_ready": True, "path": "runtime/contract.json", "sha256": "a" * 64,
                   "next_session": "2026-09-21", "slippage_bps": "10", "liquidity_budget_cny": "500000"},
        model_ref={"sha256": "b" * 64}, admission={"sha256": "c" * 64},
    )
    assert terms["limit_price"] == "1200.12"
    assert terms["cash_budget_cny"] == "0"
