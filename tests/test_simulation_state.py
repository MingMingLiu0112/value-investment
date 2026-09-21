from decimal import Decimal

import pytest

from value_investment_agent.simulation_state import (BLOCKED, PAUSE_ADDITIONS, PROPOSED_ENTRY,
                                                      PROPOSED_EXIT, DecisionInput, evaluate)


def base(**changes):
    values = dict(price=Decimal("70"), value=Decimal("100"), holding_shares=0,
                  data_ready=True, valuation_approved=True, account_ready=True,
                  execution_ready=True, thesis_intact=True, trade_session_open=True, blockers=())
    values.update(changes)
    return DecisionInput(**values)


def test_missing_approved_value_blocks_without_order():
    result = evaluate(base(value=None, valuation_approved=False))
    assert result["state"] == BLOCKED
    assert result["action"] == "no_order"
    assert "valuation_not_approved" in result["reasons"]


def test_explicit_research_model_can_propose_a_paper_review_without_formal_approval():
    result = evaluate(base(valuation_approved=False, research_model_ready=True))
    assert result["state"] == PROPOSED_ENTRY
    assert result["action"] == "propose_entry_review"
    assert result["trade_approved"] is False


def test_unavailable_execution_does_not_turn_a_non_actionable_watch_into_a_block():
    result = evaluate(base(price=Decimal("1258"), value=Decimal("478"), execution_ready=False,
                           trade_session_open=False, valuation_approved=False, research_model_ready=True))
    assert result["state"] == "watch"
    assert result["action"] == "no_order"
    assert result["safety_margin"] is not None
    assert "execution_not_ready" not in result["reasons"]


def test_discount_only_proposes_a_review_not_an_order():
    result = evaluate(base())
    assert result["state"] == PROPOSED_ENTRY
    assert result["action"] == "propose_entry_review"
    assert result["trade_approved"] is False


def test_broken_thesis_with_position_proposes_exit_review():
    result = evaluate(base(holding_shares=100, thesis_intact=False))
    assert result["state"] == PROPOSED_EXIT
    assert result["action"] == "propose_exit_review"


def test_broken_thesis_with_position_is_not_hidden_by_missing_price_or_value():
    result = evaluate(base(holding_shares=100, thesis_intact=False, data_ready=False, price=None, value=None))
    assert result["state"] == PROPOSED_EXIT
    assert result["action"] == "propose_exit_review"
    assert "thesis_broken" in result["reasons"]


def test_unknown_thesis_cannot_propose_entry_from_discount_alone():
    result = evaluate(base(thesis_intact=None))
    assert result["state"] == "watch"
    assert result["action"] == "no_order"
    assert "thesis_not_confirmed" in result["reasons"]


@pytest.mark.parametrize("reason", ["thesis_broken", "thesis_not_confirmed"])
def test_upstream_risk_blocker_is_not_discarded_by_local_ready_thesis(reason):
    result = evaluate(base(thesis_intact=True, blockers=(reason,)))
    assert result["state"] == BLOCKED
    assert result["action"] == "no_order"
    assert reason in result["reasons"]


@pytest.mark.parametrize("shares", [0, 100])
@pytest.mark.parametrize("thesis", [False, None])
@pytest.mark.parametrize("unavailable", [{}, {"data_ready": False, "price": None},
                                       {"valuation_approved": False, "value": None},
                                       {"execution_ready": False}, {"trade_session_open": False}])
def test_thesis_risk_never_approves_additions_or_disappears(shares, thesis, unavailable):
    result = evaluate(base(holding_shares=shares, thesis_intact=thesis, **unavailable))
    assert result["state"] != PROPOSED_ENTRY
    assert result["trade_approved"] is False
    assert ("thesis_broken" if thesis is False else "thesis_not_confirmed") in result["reasons"]
    if shares and thesis is False:
        assert result["state"] == PROPOSED_EXIT
        assert result["action"] == "propose_exit_review"
    elif set(unavailable) & {"data_ready", "valuation_approved"}:
        assert result["state"] == BLOCKED
    elif unavailable:
        assert result["state"] in {"watch", PAUSE_ADDITIONS}
        assert result["action"] == "no_order"
    else:
        assert result["state"] == ("pause_additions" if shares else "watch")
        assert result["action"] == "no_order"


def test_addition_requires_explicit_review_and_a_registered_trigger():
    result = evaluate(base(holding_shares=100, addition_review_requested=True,
                           last_actual_entry_price=Decimal("70")))
    assert result["state"] == PAUSE_ADDITIONS
    assert "addition_requires_new_evidence_or_5pct_lower_price" in result["reasons"]
    assert evaluate(base(holding_shares=100, addition_review_requested=True,
                         last_actual_entry_price=Decimal("70"), new_evidence_available=True))["state"] == "proposed_add"
    assert evaluate(base(holding_shares=100, price=Decimal("66.50"), addition_review_requested=True,
                         last_actual_entry_price=Decimal("70")))["state"] == "proposed_add"


def test_addition_never_assumes_a_missing_prior_actual_price():
    result = evaluate(base(holding_shares=100, addition_review_requested=True))
    assert result["state"] == PAUSE_ADDITIONS
    assert "last_actual_entry_price_missing" in result["reasons"]


@pytest.mark.parametrize("thesis", [None, False])
@pytest.mark.parametrize("price,new_evidence", [("70", True), ("66.50", False), ("66.50", True)])
def test_addition_trigger_cannot_override_unknown_or_broken_thesis(thesis, price, new_evidence):
    result = evaluate(base(holding_shares=100, thesis_intact=thesis, price=Decimal(price),
                           addition_review_requested=True, last_actual_entry_price=Decimal("70"),
                           new_evidence_available=new_evidence))
    assert result["state"] == (PAUSE_ADDITIONS if thesis is None else PROPOSED_EXIT)
    assert result["action"] == ("no_order" if thesis is None else "propose_exit_review")
    assert ("thesis_not_confirmed" if thesis is None else "thesis_broken") in result["reasons"]
    assert result["trade_approved"] is False


def test_unknown_thesis_still_allows_valuation_reduction_review():
    result = evaluate(base(holding_shares=300, thesis_intact=None, price=Decimal("110"),
                           addition_review_requested=True, new_evidence_available=True))
    assert result["state"] == "proposed_reduce"
    assert "thesis_not_confirmed" in result["reasons"]
    assert result["trade_approved"] is False
