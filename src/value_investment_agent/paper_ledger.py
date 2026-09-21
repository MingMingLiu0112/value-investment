"""Immutable-state ledger for research-only paper decisions.

The ledger deliberately has no synthetic opening capital.  Until an account
contract and an approved valuation exist, it captures the absence of orders
instead of manufacturing cash returns or paper performance.
"""
from __future__ import annotations

from datetime import date


def build_blocked_ledger(decisions: list[dict]) -> list[dict]:
    """Create one non-tradeable ledger row for each chronological decision."""
    if not decisions:
        raise ValueError("At least one decision is required")
    rows: list[dict] = []
    previous: date | None = None
    for index, decision in enumerate(decisions):
        current = date.fromisoformat(decision["date"])
        if previous is not None and current <= previous:
            raise ValueError("Decision dates must be strictly increasing")
        previous = current
        next_date = decisions[index + 1]["date"] if index + 1 < len(decisions) else None
        if decision.get("action") != "no_order" or decision.get("trade_approved") is not False:
            raise ValueError("Blocked research ledger cannot accept an order or trade approval")
        reasons = list(dict.fromkeys(decision.get("reasons") or ()))
        if not reasons:
            raise ValueError("Blocked research ledger requires recorded reasons")
        rows.append({
            "date": decision["date"],
            "decision_at": decision["decision_at"],
            "state": decision["state"],
            "decision_action": decision["action"],
            "next_eligible_execution_date": next_date,
            "pending_order": None,
            "executed_order": None,
            "cash_cny": None,
            "holding_shares": 0,
            "marked_portfolio_value_cny": None,
            "performance_available": False,
            "blockers": reasons,
            "decision_evidence": {
                "annual_source_id": decision["annual_source_id"],
                "rule_version": decision["rule_version"],
            },
        })
    return rows
