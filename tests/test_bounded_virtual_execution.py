from copy import deepcopy
from datetime import date
from decimal import Decimal

import pytest

from value_investment_agent.virtual_account import (
    ORDER_TERMS_VERSION, VirtualAccount, dated_research_fee, replay,
)


def sessions():
    return [{"date": day, "open": "100", "close": "100", "execution_ready": True,
             "price_limit_down": "90", "price_limit_up": "110"}
            for day in ("2025-01-06", "2025-01-07", "2025-01-08")]


def proposal(state="proposed_entry", **changes):
    terms = {"version": ORDER_TERMS_VERSION, "valid_session": "2025-01-07",
             "limit_price": "101", "cash_budget_cny": "10100",
             "liquidity_budget_cny": "20000", "liquidity_as_of": "2025-01-06",
             "slippage_bps": "10", "basis_id": "synthetic-constraints-only"}
    terms.update(changes)
    return {"state": state, "decision_id": "test-order", "quantity": 100,
            "execution_terms": terms}


def test_constrained_buy_persists_then_fills_once_with_adverse_slippage_and_dated_fee():
    bars, decision = sessions(), proposal()
    account, first = replay(bars[:1], {bars[0]["date"]: decision}, fee_calculator=dated_research_fee)
    assert first[0]["fill"] is None
    decision["execution_terms"]["limit_price"] = "1"
    assert account.pending_order["execution_terms"]["limit_price"] == "101"
    account = VirtualAccount.from_dict(account.to_dict())
    account, rows = replay(bars[:2], {}, account, fee_calculator=dated_research_fee)
    assert rows[0]["fill"]["price"] == "100.10"
    assert rows[0]["fill"]["fee_cny"] == "5.10"
    assert rows[0]["fill"]["execution_scope"] == "daily_simulation_assumption_not_real_fill"
    assert rows[0]["open"] == "100"
    assert account.cash == Decimal("989984.90")
    before = deepcopy(account.to_dict())
    assert replay(bars[:2], {}, account, fee_calculator=dated_research_fee)[1] == []
    assert account.to_dict() == before


@pytest.mark.parametrize("changes,reason", [
    ({"limit_price": "100.15"}, "buy_all_in_limit_exceeded"),
    ({"cash_budget_cny": "10015"}, "reserved_cash_budget_exceeded"),
    ({"liquidity_budget_cny": "10009"}, "prior_liquidity_budget_exceeded"),
    ({"slippage_bps": "1000"}, "slippage_reaches_price_limit"),
])
def test_buy_constraints_reject_without_spending_cash(changes, reason):
    account, rows = replay(sessions()[:2], {"2025-01-06": proposal(**changes)},
                           fee_calculator=dated_research_fee)
    assert rows[1]["rejected_order_reason"] == reason
    assert rows[1]["rejected_order"]["order_id"] == "test-order"
    assert rows[1]["fill"] is None and account.shares == 0
    assert account.cash == Decimal("1000000")
    assert account.pending_order is None


@pytest.mark.parametrize("patch,reason", [
    ({"open": "102"}, "buy_all_in_limit_exceeded"),
    ({"open": "110"}, "opening_at_or_outside_price_limit"),
    ({"open": "90"}, "opening_at_or_outside_price_limit"),
    ({"price_limit_up": None}, "price_limit_state_unknown"),
    ({"execution_ready": None}, "execution_state_unknown"),
    ({"next_open_fill_eligible": False}, "session_not_executable"),
    ({"execution_status": "blocked_suspension"}, "session_not_executable"),
])
def test_gap_and_unknown_or_blocked_session_do_not_fill(patch, reason):
    bars = sessions()
    bars[1].update(patch)
    account, rows = replay(bars[:2], {bars[0]["date"]: proposal()})
    assert rows[1]["rejected_order_reason"] == reason
    assert account.shares == 0 and account.cash == Decimal("1000000")


def test_expired_signal_is_not_extended_to_the_next_supplied_session():
    bars = sessions()
    account, rows = replay([bars[0], bars[2]], {bars[0]["date"]: proposal()})
    assert rows[1]["rejected_order_reason"] == "order_expired"
    assert account.shares == 0


def test_explicit_later_session_keeps_order_pending_without_using_earlier_open():
    account, rows = replay(sessions(), {"2025-01-06": proposal(valid_session="2025-01-08")})
    assert rows[1]["fill"] is None and rows[1]["deferred_order_id"] == "test-order"
    assert rows[2]["fill"]["filled_on"] == "2025-01-08"
    assert account.shares == 100


@pytest.mark.parametrize("state", ["proposed_reduce", "proposed_exit"])
def test_sell_uses_net_floor_not_buy_ceiling_and_preserves_t1_inventory(state):
    account = VirtualAccount(shares=200, lots=[(date(2025, 1, 2), 200)])
    decision = proposal(state, limit_price="99", cash_budget_cny="0")
    account, rows = replay(sessions()[:2], {"2025-01-06": decision}, account,
                           fee_calculator=dated_research_fee)
    assert rows[1]["fill"]["price"] == "99.90"
    assert rows[1]["fill"]["fee_cny"] == "10.09"
    assert account.cash == Decimal("1009979.91") and account.shares == 100


def test_sell_rejects_net_floor_breach_after_fees_without_altering_lots():
    account = VirtualAccount(shares=100, lots=[(date(2025, 1, 2), 100)])
    account, rows = replay(sessions()[:2], {"2025-01-06": proposal("proposed_exit", limit_price="99.85")},
                           account, fee_calculator=dated_research_fee)
    assert rows[1]["rejected_order_reason"] == "sell_net_limit_not_met"
    assert account.cash == Decimal("1000000") and account.shares == 100
    assert account.lots == [(date(2025, 1, 2), 100)]


@pytest.mark.parametrize("changes", [
    {"slippage_bps": "NaN"}, {"slippage_bps": "-1"}, {"slippage_bps": "10000"},
    {"limit_price": "0"}, {"cash_budget_cny": "Infinity"}, {"basis_id": ""},
    {"valid_session": "2025-01-06"}, {"liquidity_as_of": "2025-01-07"},
    {"version": "unknown"},
])
def test_invalid_constraints_fail_before_account_changes(changes):
    account = VirtualAccount()
    before = deepcopy(account.to_dict())
    with pytest.raises(ValueError):
        replay(sessions(), {"2025-01-06": proposal(**changes)}, account)
    assert account.to_dict() == before


def test_real_contract_explicit_denial_cannot_be_ignored_by_static_decisions():
    bars = sessions()
    bars[1]["next_open_fill_eligible"] = False
    decision = {"state": "proposed_entry", "decision_id": "legacy", "quantity": 100}
    account, rows = replay(bars[:2], {"2025-01-06": decision})
    assert rows[1]["rejected_order_reason"] == "session_not_executable"
    assert account.shares == 0
