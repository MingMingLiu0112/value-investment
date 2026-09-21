"""Auditable, non-executing state machine for paper-investment research.

This module decides a research state only.  Order generation and broker access
are intentionally outside its scope.
"""
from dataclasses import dataclass
from decimal import Decimal


WATCH = "watch"
BLOCKED = "blocked"
PROPOSED_ENTRY = "proposed_entry"
PAPER_HOLD = "paper_hold"
PAUSE_ADDITIONS = "pause_additions"
PROPOSED_REDUCE = "proposed_reduce"
PROPOSED_EXIT = "proposed_exit"


@dataclass(frozen=True)
class DecisionInput:
    price: Decimal | None
    value: Decimal | None
    holding_shares: int
    data_ready: bool
    valuation_approved: bool
    account_ready: bool
    execution_ready: bool
    thesis_intact: bool | None
    trade_session_open: bool
    blockers: tuple[str, ...] = ()
    research_model_ready: bool = False
    addition_review_requested: bool = False
    last_actual_entry_price: Decimal | None = None
    new_evidence_available: bool = False


def evaluate(input_row: DecisionInput) -> dict:
    """Return one explainable paper-research state without creating an order."""
    if input_row.holding_shares < 0:
        raise ValueError("Long-only paper state requires nonnegative shares")
    reasons = list(dict.fromkeys(input_row.blockers))
    if input_row.thesis_intact is False:
        reasons.append("thesis_broken")
    elif input_row.thesis_intact is None:
        reasons.append("thesis_not_confirmed")
    # A known thesis failure is a position-risk event.  Preserve its exit review
    # even when data needed for a new valuation or order is unavailable.
    if input_row.holding_shares and input_row.thesis_intact is False:
        return {"state": PROPOSED_EXIT, "action": "propose_exit_review", "reasons": reasons,
                "safety_margin": None, "trade_approved": False}
    if not input_row.data_ready:
        reasons.append("data_not_ready")
    # A frozen, point-in-time research model may drive a segregated paper
    # experiment. It never changes the separate formal-valuation or live-order
    # approval returned by this state machine.
    if not input_row.valuation_approved and not input_row.research_model_ready:
        reasons.append("valuation_not_approved")
    if not input_row.account_ready:
        reasons.append("paper_account_not_ready")
    if input_row.price is None or input_row.price <= 0:
        reasons.append("effective_price_missing")
    if input_row.value is None or input_row.value <= 0:
        reasons.append("approved_value_missing")
    readiness_reasons = [reason for reason in reasons if reason not in {"thesis_broken", "thesis_not_confirmed"}]
    if input_row.blockers or readiness_reasons:
        return {"state": BLOCKED, "action": "no_order", "reasons": reasons,
                "safety_margin": None, "trade_approved": False}

    safety_margin = (input_row.value - input_row.price) / input_row.value
    # A non-actionable watch result must not be labelled as a failed order just
    # because next-session execution evidence has not been collected. Execution
    # evidence remains mandatory before any entry or valuation-driven reduction.
    execution_required = (
        (input_row.holding_shares == 0 and input_row.thesis_intact is True
         and safety_margin >= Decimal("0.30"))
        or (input_row.holding_shares > 0 and input_row.price > input_row.value)
    )
    if execution_required and not input_row.execution_ready:
        reasons.append("execution_not_ready")
    if execution_required and not input_row.trade_session_open:
        reasons.append("next_trade_session_unavailable")
    if execution_required and (not input_row.execution_ready or not input_row.trade_session_open):
        return {"state": BLOCKED, "action": "no_order", "reasons": reasons,
                "safety_margin": str(safety_margin), "trade_approved": False}
    if input_row.holding_shares == 0 and input_row.thesis_intact is not True:
        state, action = WATCH, "no_order"
    elif input_row.holding_shares == 0 and safety_margin >= Decimal("0.30"):
        state, action = PROPOSED_ENTRY, "propose_entry_review"
    elif input_row.holding_shares and input_row.price > input_row.value:
        state, action = PROPOSED_REDUCE, "propose_reduce_review"
    elif input_row.holding_shares and input_row.thesis_intact is None:
        state, action = PAUSE_ADDITIONS, "no_order"
    elif input_row.holding_shares and input_row.addition_review_requested:
        if input_row.last_actual_entry_price is None or input_row.last_actual_entry_price <= 0:
            state, action = PAUSE_ADDITIONS, "no_order"
            reasons.append("last_actual_entry_price_missing")
        elif safety_margin < Decimal("0.30"):
            state, action = PAUSE_ADDITIONS, "no_order"
            reasons.append("addition_safety_margin_not_met")
        elif (input_row.new_evidence_available
              or input_row.price <= input_row.last_actual_entry_price * Decimal("0.95")):
            state, action = "proposed_add", "propose_add_review"
        else:
            state, action = PAUSE_ADDITIONS, "no_order"
            reasons.append("addition_requires_new_evidence_or_5pct_lower_price")
    elif input_row.holding_shares:
        state, action = PAPER_HOLD, "no_order"
    else:
        state, action = WATCH, "no_order"
    return {"state": state, "action": action, "reasons": reasons,
            "safety_margin": str(safety_margin), "trade_approved": False}
