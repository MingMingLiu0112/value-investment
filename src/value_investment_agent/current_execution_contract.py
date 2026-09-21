"""Fail-closed evidence contract for a next-session paper order.

The contract describes execution mechanics only.  It cannot approve a value
model, create an order, or change the separate live-trading gate.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from .historical_fees import verify_current_sse_policy


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _positive(value: object, name: str) -> Decimal:
    result = Decimal(str(value))
    if not result.is_finite() or result <= 0:
        raise ValueError(f"{name} must be a positive finite number")
    return result


def _load_json(path: Path, root: Path, name: str) -> tuple[dict, dict]:
    path = path.resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"{name} must remain under the project root")
    value = json.loads(path.read_text(encoding="utf-8"))
    return value, {"path": str(path.relative_to(root)), "sha256": digest(path)}


def build_current_execution_contract(*, root: Path, quote_report: Path,
                                     suspension_evidence: Path,
                                     liquidity_evidence: Path | None,
                                     fee_policy_evidence: Path | None,
                                     next_session: date, prior_close: Decimal,
                                     slippage_bps: Decimal = Decimal("10")) -> dict:
    """Build a bounded, non-order execution contract from dated evidence."""
    quote, quote_ref = _load_json(quote_report, root, "quote report")
    rows = [row for row in quote.get("observations", []) if row.get("symbol") == "600519"]
    if len(rows) != 1 or (rows[0].get("result") or {}).get("passed") is not True:
        raise ValueError("A verified 600519 dual-source quote is required")
    observed_session = date.fromisoformat(rows[0]["result"]["expected_session"])
    if next_session <= observed_session:
        raise ValueError("Next execution session must follow the observed close")
    if not Decimal("0") <= slippage_bps < Decimal("10000"):
        raise ValueError("slippage_bps must be between 0 and 10000")

    suspension, suspension_ref = _load_json(suspension_evidence, root, "suspension evidence")
    window = suspension.get("window", "")
    if (suspension.get("symbol") != "600519" or suspension.get("official_returned_record_count") != 0
            or suspension.get("suspension_status") != "no_official_listed_stop_resume_records_returned"
            or observed_session.strftime("%Y%m%d") not in window or next_session.strftime("%Y%m%d") not in window):
        suspension_ready = False
    else:
        suspension_ready = True

    policy = verify_current_sse_policy(root)
    fee_ready = policy["valid_session"] == next_session.isoformat()
    fee_ref = None
    if fee_policy_evidence is not None:
        fee_policy, fee_ref = _load_json(fee_policy_evidence, root, "fee policy evidence")
        if (fee_policy.get("policy_version") == "sse-current-paper-fees-v1"
                and fee_policy.get("exchange") == "SSE"
                and fee_policy.get("valid_session") == next_session.isoformat()
                and fee_policy.get("broker_invoice_verified") is False
                and fee_policy.get("trade_approved") is False
                and fee_policy.get("live_eligible") is False):
            fee_ready = True
    liquidity_ready = False
    liquidity_ref = None
    liquidity_budget = None
    if liquidity_evidence is not None:
        liquidity, liquidity_ref = _load_json(liquidity_evidence, root, "liquidity evidence")
        if (liquidity.get("symbol") == "600519" and liquidity.get("as_of") == observed_session.isoformat()
                and liquidity.get("quote_report_sha256") == quote_ref["sha256"]
                and isinstance(liquidity.get("source_hashes"), list) and len(liquidity["source_hashes"]) == 2):
            liquidity_budget = _positive(liquidity.get("liquidity_budget_cny"), "liquidity_budget_cny")
            liquidity_ready = True

    prior_close = _positive(prior_close, "prior_close")
    upper = (prior_close * Decimal("1.10")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    lower = (prior_close * Decimal("0.90")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    blockers = []
    if not suspension_ready:
        blockers.append("dated_suspension_evidence_missing_or_inconclusive")
    if not fee_ready:
        blockers.append("dated_fee_policy_missing_for_next_session")
    if not liquidity_ready:
        blockers.append("prior_known_liquidity_budget_missing")
    execution_ready = not blockers
    return {
        "symbol": "600519", "contract_version": "current-next-session-paper-execution-v1",
        "observed_session": observed_session.isoformat(), "valid_session": next_session.isoformat(),
        "price_limit_down": str(lower), "price_limit_up": str(upper),
        "slippage_bps": str(slippage_bps),
        "liquidity_budget_cny": str(liquidity_budget) if liquidity_budget is not None else None,
        "execution_ready": execution_ready, "blockers": blockers,
        "evidence": {"quote": quote_ref, "suspension": suspension_ref,
                     "fee_policy": fee_ref or policy, "liquidity": liquidity_ref},
        "trade_approved": False, "live_eligible": False,
    }
