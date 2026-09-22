"""Frozen daily-simulation execution policy for the 600519 paper account.

This module records the framework 9.3 execution contract as a versioned policy.
It does not generate valuations, orders, fills, or live-trading approval.
"""
from __future__ import annotations

from datetime import date
from typing import Any


POLICY_VERSION = "moutai-daily-simulation-paper-execution-policy-v1"
IMPLEMENTED_STATUS = "implemented_for_paper_execution_only"


RULES: dict[str, Any] = {
    "sequence": {
        "before_new_decision": [
            "Settle any pre-existing bounded order and corporate action only when complete execution-time evidence exists.",
            "Never use the new close, next-session open, high, low, or full turnover to rewrite the prior session decision.",
        ],
        "after_new_decision": [
            "Build one dated decision from the verified close and disclosures already available at that close.",
            "Freeze the earliest next-session bounded order only after the dated execution contract is ready.",
            "Persist the virtual account idempotently, then publish only when a business-relevant state changed.",
        ],
    },
    "information_boundary": {
        "decision_window": "Verified close plus disclosures available at decision time; no next-session open or full-day volume.",
        "fill_window": "The named next valid session open only; no inferred opening price.",
        "prohibited": [
            "Using next-day market data to create a prior-day signal or budget.",
            "Using a later financial disclosure to rewrite an earlier opening decision.",
            "Reusing a contract after its explicit valid session expires without a new review.",
        ],
    },
    "fill_assumption": {
        "price": "Next valid session open plus adverse slippage, rounded against the paper account.",
        "order": "Versioned limit, valid session, cash or net-proceeds floor, liquidity date and decision basis.",
        "label": "A simulated fill is a stated daily-bar assumption, never a verified real fill.",
    },
    "reject_or_defer": {
        "reject": [
            "suspension, unknown trading status, opening at or beyond price limit, no prior-session liquidity basis",
            "unprocessable corporate action affecting the paper account",
            "buy all-in cost above its ceiling or sell net proceeds below its floor",
        ],
        "defer": [
            "Missing execution-time evidence defers the order; expiry requires a fresh decision review.",
            "No later market data may automatically extend a stale signal.",
        ],
    },
    "quantity_constraints": [
        "T+1 sellable shares",
        "A-share board lots",
        "cash and fees",
        "frozen position budget",
        "prior-known liquidity budget and date",
    ],
    "fee_and_stress": {
        "base": "A dated statutory/paper fee scenario; unknown broker terms remain explicit scenarios, never zero.",
        "stress": "Report adverse slippage, lower participation and at least one delayed-session scenario.",
    },
    "reporting": {
        "required": ["rejection reason", "deferral reason", "fee scenario", "account delta", "policy and evidence versions"],
        "boundary": "Policy implementation is not historical strategy evidence, simulation eligibility, or R2 readiness.",
    },
}


REQUIRED_POLICY_KEYS = (
    "policy_version",
    "symbol",
    "observed_session",
    "valid_session",
    "execution_contract",
    "rules",
    "implementation_status",
    "real_fill_verified",
    "trade_approved",
    "live_eligible",
)


def validate_policy(policy: dict[str, Any]) -> dict[str, Any]:
    """Validate a dated policy without changing any execution or approval state."""
    if not isinstance(policy, dict):
        raise ValueError("Daily simulation policy must be a JSON object")
    missing = [key for key in REQUIRED_POLICY_KEYS if key not in policy]
    if missing:
        raise ValueError("Daily simulation policy is missing keys: " + ", ".join(missing))
    if policy["policy_version"] != POLICY_VERSION:
        raise ValueError("Unknown daily simulation policy version")
    if policy["symbol"] != "600519":
        raise ValueError("Daily simulation policy is outside the 600519 scope")
    observed = date.fromisoformat(policy["observed_session"])
    valid = date.fromisoformat(policy["valid_session"])
    if valid <= observed:
        raise ValueError("Policy valid session must follow the observed session")
    if policy["implementation_status"] != IMPLEMENTED_STATUS:
        raise ValueError("Daily simulation policy is not marked as implemented")
    if policy["real_fill_verified"] is not False:
        raise ValueError("A simulated daily policy cannot claim a verified real fill")
    if policy["trade_approved"] is not False or policy["live_eligible"] is not False:
        raise ValueError("Daily simulation policy crossed an approval boundary")
    rules = policy["rules"]
    if not isinstance(rules, dict) or set(rules) != set(RULES):
        raise ValueError("Daily simulation policy rule set changed")
    contract = policy["execution_contract"]
    if (not isinstance(contract, dict) or not isinstance(contract.get("path"), str)
            or not isinstance(contract.get("sha256"), str)):
        raise ValueError("Daily simulation policy requires a hash-pinned execution contract")
    return policy


def build_policy(*, execution_contract: dict[str, Any],
                 execution_contract_ref: dict[str, str],
                 observed_session: str, valid_session: str) -> dict[str, Any]:
    """Bind the frozen framework 9.3 rules to one observed-to-valid session pair."""
    if (execution_contract.get("symbol") != "600519"
            or execution_contract.get("contract_version") != "current-next-session-paper-execution-v1"
            or execution_contract.get("observed_session") != observed_session
            or execution_contract.get("valid_session") != valid_session
            or type(execution_contract.get("execution_ready")) is not bool
            or execution_contract.get("trade_approved") is not False
            or execution_contract.get("live_eligible") is not False):
        raise ValueError("Execution contract is incompatible with the daily simulation policy")
    return validate_policy({
        "policy_version": POLICY_VERSION,
        "symbol": "600519",
        "observed_session": observed_session,
        "valid_session": valid_session,
        "execution_contract": execution_contract_ref,
        "execution_ready": execution_contract["execution_ready"],
        "blockers": list(execution_contract.get("blockers") or []),
        "rules": RULES,
        "implementation_status": IMPLEMENTED_STATUS,
        "real_fill_verified": False,
        "trade_approved": False,
        "live_eligible": False,
        "limitation": (
            "Paper-execution policy registration only. It proves neither next-session depth, queue priority, "
            "a real fill, historical strategy effectiveness, simulation eligibility, nor live-trading readiness."
        ),
    })
