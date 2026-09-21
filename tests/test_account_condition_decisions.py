"""Synthetic conditions generate decisions against the evolving account."""
from decimal import Decimal
from datetime import date
import pytest

from value_investment_agent.simulation_state import DecisionInput, evaluate
from value_investment_agent.paper_sizing import size_entry_or_add
from value_investment_agent.virtual_account import VirtualAccount, replay


def test_conditions_generate_entry_hold_exit_and_reentry_once():
    sessions = [{"date": f"2026-01-{day:02}", "open": "70", "close": "70", "execution_ready": True}
                for day in (5, 6, 7, 8, 9, 12)]
    seen = []

    def decide(bar, snapshot):
        seen.append((bar["date"], snapshot["shares"]))
        state = evaluate(DecisionInput(
            price=Decimal(bar["close"]), value=Decimal("100"),
            holding_shares=snapshot["shares"], data_ready=True,
            valuation_approved=False, research_model_ready=True,
            account_ready=True, execution_ready=True,
            thesis_intact=bar["date"] not in {"2026-01-07", "2026-01-08"},
            trade_session_open=True,
        ))
        # Fixed one-lot fixture tests integration, not an approved sizing policy.
        return {**state, "decision_id": "condition-fixture-" + bar["date"], "quantity": 100}

    account, journal = replay(sessions, {}, decision_provider=decide)
    assert [row["decision"] for row in journal] == [
        "proposed_entry", "paper_hold", "proposed_exit", "watch", "proposed_entry", "paper_hold"]
    assert [(row["date"], row["fill"]["side"]) for row in journal if row["fill"]] == [
        ("2026-01-06", "buy"), ("2026-01-08", "sell"), ("2026-01-12", "buy")]
    assert account.shares == 100
    assert seen[1][1] == 100 and seen[3][1] == 0
    before = account.to_dict()
    _, repeated = replay(sessions, {}, account, decision_provider=decide)
    assert repeated == [] and account.to_dict() == before and len(seen) == 6


@pytest.mark.parametrize("ready,reason", [(False, "session_not_executable"), (None, "execution_state_unknown")])
def test_next_session_gate_rejects_generated_order_without_cash_or_share_change(ready, reason):
    sessions = [{"date": "2026-01-05", "open": "70", "close": "70"},
                {"date": "2026-01-06", "open": "70", "close": "70", "execution_ready": ready}]
    def decide(bar, snapshot):
        state = evaluate(DecisionInput(
            price=Decimal(bar["close"]), value=Decimal("100"), holding_shares=snapshot["shares"],
            data_ready=True, valuation_approved=False, research_model_ready=True,
            account_ready=True, execution_ready=bar.get("execution_ready", True) is True,
            thesis_intact=True, trade_session_open=True))
        return {**state, "decision_id": "gate-" + bar["date"], "quantity": 100}
    account, journal = replay(sessions, {}, decision_provider=decide)
    assert journal[0]["created_order"]
    assert journal[1]["fill"] is None
    assert journal[1]["rejected_order_reason"] == reason
    assert account.cash == Decimal("1000000") and account.shares == 0
    assert account.pending_order is None


@pytest.mark.parametrize("price", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_prices_fail_before_account_mutation(price):
    from value_investment_agent.virtual_account import VirtualAccount
    account = VirtualAccount()
    before = account.to_dict()
    with pytest.raises(ValueError):
        replay([{"date": "2026-01-05", "open": price, "close": "70"}], {}, account)
    assert account.to_dict() == before


@pytest.mark.parametrize("status,reason", [
    ("blocked_daily_bar_contains_partial_session_suspension", "session_not_executable"),
    ("daily_bar_present_execution_rules_incomplete", "execution_state_unknown"),
])
def test_existing_contract_status_cannot_be_overridden_by_ready_flag(status, reason):
    sessions = [{"date": "2026-01-05", "open": "70", "close": "70"},
                {"date": "2026-01-06", "open": "70", "close": "70",
                 "execution_status": status, "execution_ready": True}]
    account, journal = replay(sessions, {"2026-01-05": {
        "state": "proposed_entry", "decision_id": "status-check", "quantity": 100}})
    assert journal[1]["rejected_order_reason"] == reason
    assert account.shares == 0 and account.cash == Decimal("1000000")


def test_dynamic_decision_without_execution_evidence_cannot_fill():
    sessions = [{"date": f"2026-01-{day:02}", "open": "70", "close": "70"} for day in (5, 6)]
    account, journal = replay(sessions, {}, decision_provider=lambda bar, account: {
        "state": "proposed_entry", "decision_id": bar["date"], "quantity": 100})
    assert journal[1]["rejected_order_reason"] == "execution_state_unknown"
    assert account.shares == 0


def test_condition_generated_addition_fills_next_session_once():
    sessions = [{"date": "2026-01-05", "open": "65", "close": "65", "execution_ready": True},
                {"date": "2026-01-06", "open": "65", "close": "65", "execution_ready": True},
                {"date": "2026-01-07", "open": "65", "close": "65", "execution_ready": True}]
    account = VirtualAccount(cash=Decimal("100000"), shares=100,
                             lots=[(date(2026, 1, 4), 100)])

    def decide(bar, snapshot):
        state = evaluate(DecisionInput(
            price=Decimal(bar["close"]), value=Decimal("100"), holding_shares=snapshot["shares"],
            data_ready=True, valuation_approved=False, research_model_ready=True,
            account_ready=True, execution_ready=True, thesis_intact=True, trade_session_open=True,
            addition_review_requested=bar["date"] == "2026-01-05",
            last_actual_entry_price=Decimal("70"), new_evidence_available=bar["date"] == "2026-01-05"))
        return {**state, "decision_id": "add-fixture-" + bar["date"], "quantity": 100}

    account, journal = replay(sessions, {}, account, decision_provider=decide)
    assert journal[0]["decision"] == "proposed_add"
    fill = journal[1]["fill"]
    assert fill["side"] == "buy"
    assert fill["quantity"] == 100
    assert fill["price"] == "65"
    assert fill["fee_cny"] == "5.00"
    assert account.shares == 200
    before = account.to_dict()
    _, repeated = replay(sessions, {}, account, decision_provider=decide)
    assert repeated == [] and account.to_dict() == before


@pytest.mark.parametrize("thesis", [None, True])
@pytest.mark.parametrize("price,new_evidence", [("70", True), ("66.50", False), ("66.50", True)])
def test_thesis_gates_condition_generated_sized_addition_and_account(thesis, price, new_evidence):
    sessions = [{"date": f"2026-01-{day:02}", "open": price, "close": price,
                 "execution_ready": True} for day in (5, 6)]
    initial_cash = Decimal("1000000")
    account = VirtualAccount(cash=initial_cash, shares=100, lots=[(date(2026, 1, 2), 100)])
    sized = []

    def decide(bar, snapshot):
        state = evaluate(DecisionInput(
            price=Decimal(bar["close"]), value=Decimal("100"), holding_shares=snapshot["shares"],
            data_ready=True, valuation_approved=False, research_model_ready=True,
            account_ready=True, execution_ready=True, thesis_intact=thesis, trade_session_open=True,
            addition_review_requested=bar["date"] == "2026-01-05",
            last_actual_entry_price=Decimal("70"), new_evidence_available=new_evidence))
        decision = {**state, "decision_id": "thesis-add-" + bar["date"]}
        if state["state"] == "proposed_add":
            sizing = size_entry_or_add(
                nav=Decimal(snapshot["cash"]) + Decimal(snapshot["shares"]) * Decimal(bar["close"]),
                cash=Decimal(snapshot["cash"]), current_shares=snapshot["shares"],
                price=Decimal(bar["close"]), tranche_index=1)
            sized.append(sizing)
            decision["quantity"] = sizing["quantity"]
        return decision

    account, journal = replay(sessions, {}, account, decision_provider=decide)
    if thesis is None:
        assert all(row["decision"] == "pause_additions" for row in journal)
        assert all(row["created_order"] is None and row["fill"] is None for row in journal)
        assert all("thesis_not_confirmed" in row["decision_details"]["reasons"] for row in journal)
        assert not sized and not account.filled_order_ids
        assert account.cash == initial_cash and account.shares == 100
    else:
        assert len(sized) == 1 and sized[0]["quantity"] > 0
        assert journal[0]["decision"] == "proposed_add"
        assert journal[1]["fill"]["quantity"] == sized[0]["quantity"]
        assert account.shares == 100 + sized[0]["quantity"] and account.cash < initial_cash
    before = account.to_dict()
    _, repeated = replay(sessions, {}, account, decision_provider=decide)
    assert repeated == [] and account.to_dict() == before
