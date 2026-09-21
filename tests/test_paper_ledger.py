from value_investment_agent.paper_ledger import build_blocked_ledger
import pytest


def decision(day, **overrides):
    row = {"date": day, "decision_at": day + "T15:00:00+08:00", "state": "blocked",
           "action": "no_order", "trade_approved": False, "reasons": ["valuation_not_approved"],
           "annual_source_id": "cninfo:test", "rule_version": "test-v1"}
    row.update(overrides)
    return row


def test_blocked_ledger_records_next_session_without_cash_or_performance():
    ledger = build_blocked_ledger([decision("2025-01-02"), decision("2025-01-03")])
    assert ledger[0]["next_eligible_execution_date"] == "2025-01-03"
    assert ledger[1]["next_eligible_execution_date"] is None
    assert all(row["cash_cny"] is None and row["holding_shares"] == 0 for row in ledger)
    assert all(not row["performance_available"] and row["executed_order"] is None for row in ledger)


def test_blocked_ledger_rejects_nonchronological_or_approved_orders():
    with pytest.raises(ValueError, match="strictly increasing"):
        build_blocked_ledger([decision("2025-01-03"), decision("2025-01-02")])
    with pytest.raises(ValueError, match="cannot accept"):
        build_blocked_ledger([decision("2025-01-02", action="propose_entry_review")])
