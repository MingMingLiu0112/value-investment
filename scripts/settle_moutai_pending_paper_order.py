#!/usr/bin/env python3
"""Settle one already-frozen 600519 paper order against a verified opening.

This consumer intentionally contains no valuation or commercial assumptions.
It accepts an explicit, independently prepared opening-session record and the
persisted virtual account, then delegates all limit, budget, T+1 and fee checks
to the shared ledger.  It never substitutes a close for an opening price.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime
from decimal import Decimal, ROUND_HALF_EVEN
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.virtual_account import VirtualAccount, replay


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def project_file(path: Path, label: str) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(ROOT.resolve()):
        raise ValueError(f"{label} must remain under the project root")
    return resolved


def load_opening(path: Path, order: dict) -> tuple[dict, dict]:
    """Require the exact execution evidence a frozen order needs.

    The producer of this document is deliberately separate: quote retrieval and
    market-status verification may evolve without granting the ledger authority
    to infer a price or a status.
    """
    source = json.loads(path.read_text(encoding="utf-8"))
    required = ("symbol", "session", "opening_price_cny", "close_price_cny",
                "execution_ready", "price_limit_down", "price_limit_up",
                "security_status", "corporate_action_status", "evidence_refs")
    if any(key not in source for key in required) or source["symbol"] != "600519":
        raise ValueError("Opening-session evidence is incomplete or has the wrong symbol")
    terms = order.get("execution_terms") or {}
    if source["session"] != terms.get("valid_session"):
        raise ValueError("Opening session does not match frozen order validity")
    if source["execution_ready"] is not True:
        raise ValueError("Opening-session evidence is not execution-ready")
    if source["security_status"] != "tradable" or source["corporate_action_status"] != "none":
        raise ValueError("Security or corporate-action state prohibits settlement")
    if not isinstance(source["evidence_refs"], list) or not source["evidence_refs"]:
        raise ValueError("Opening-session evidence requires pinned source references")
    session = {
        "date": source["session"], "open": str(source["opening_price_cny"]),
        "close": str(source["close_price_cny"]), "execution_ready": True,
        "execution_status": "verified_next_open_paper_execution",
        "execution_reason": "Opening, price-limit, security and corporate-action evidence were supplied.",
        "next_open_fill_eligible": True,
        "price_limit_down": str(source["price_limit_down"]),
        "price_limit_up": str(source["price_limit_up"]),
    }
    return session, source


def load_fee_policy(path: Path, valid_session: str) -> tuple[dict, dict]:
    """Load a one-session paper fee policy rather than extending a stale rate."""
    policy = json.loads(path.read_text(encoding="utf-8"))
    scenario = policy.get("commission_scenario") or {}
    manifest = policy.get("source_manifest") or {}
    if (policy.get("policy_version") != "sse-current-paper-fees-v1"
            or policy.get("exchange") != "SSE" or policy.get("valid_session") != valid_session
            or policy.get("execution_ready") is not True
            or policy.get("broker_invoice_verified") is not False
            or not isinstance(manifest.get("path"), str)
            or not isinstance(manifest.get("sha256"), str)):
        raise ValueError("Frozen fee policy does not cover this settlement session")
    manifest_path = project_file(ROOT / manifest["path"], "Fee-policy source manifest")
    if digest(manifest_path) != manifest["sha256"]:
        raise ValueError("Frozen fee-policy source manifest changed")
    rate, minimum = (Decimal(str(scenario.get("rate"))), Decimal(str(scenario.get("minimum_cny"))))
    if not rate.is_finite() or rate < 0 or not minimum.is_finite() or minimum < 0:
        raise ValueError("Frozen fee policy has invalid commission terms")
    return policy, {"path": str(path.relative_to(ROOT)), "sha256": digest(path)}


def frozen_sse_paper_fee(policy: dict):
    """Return the fee calculator constrained to the policy's sole valid session.

    The statutory constants are those captured by the policy's pinned primary
    sources: 0.01 per mille transfer fee and post-2023 0.5 per mille sell-side
    stamp duty.  This remains a paper scenario, never a broker invoice.
    """
    scenario = policy["commission_scenario"]
    rate, minimum = Decimal(str(scenario["rate"])), Decimal(str(scenario["minimum_cny"]))
    valid_session = policy["valid_session"]
    def calculate(side: str, quantity: int, price: Decimal, session) -> Decimal:
        if session.isoformat() != valid_session:
            raise ValueError("Frozen fee policy cannot be reused outside its valid session")
        turnover = Decimal(quantity) * price
        statutory = turnover * Decimal("0.00001")
        if side == "sell":
            statutory += turnover * Decimal("0.0005")
        return (statutory + max(turnover * rate, minimum)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
    return calculate


def settle(state_path: Path, opening_path: Path, fee_policy_path: Path, output_dir: Path) -> dict:
    state_path, opening_path, fee_policy_path = (project_file(state_path, "State file"),
        project_file(opening_path, "Opening evidence"), project_file(fee_policy_path, "Fee policy"))
    account = VirtualAccount.from_dict(json.loads(state_path.read_text(encoding="utf-8")))
    if account.pending_order is None:
        raise ValueError("No pending paper order exists")
    if "execution_terms" not in account.pending_order:
        raise ValueError("Legacy unbounded paper order cannot be settled")
    session, opening = load_opening(opening_path, account.pending_order)
    policy, policy_ref = load_fee_policy(fee_policy_path, session["date"])
    account, journal = replay([session], {}, account, fee_calculator=frozen_sse_paper_fee(policy))
    staged = state_path.with_name("." + state_path.name + ".stage")
    staged.write_text(json.dumps(account.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(staged, state_path)
    output_dir.mkdir(parents=True, exist_ok=False)
    journal_path = output_dir / "journal.json"
    journal_path.write_text(json.dumps(journal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {
        "symbol": "600519", "run_type": "bounded_pending_paper_order_settlement",
        "state_path": str(state_path.relative_to(ROOT)), "state_sha256_after": digest(state_path),
        "opening_evidence_path": str(opening_path.relative_to(ROOT)), "opening_evidence_sha256": digest(opening_path),
        "fee_policy": policy_ref,
        "opening_session": opening["session"], "new_journal_rows": len(journal),
        "fill": journal[0]["fill"], "rejected_order_reason": journal[0]["rejected_order_reason"],
        "pending_order": account.pending_order, "ending_cash_cny": str(account.cash),
        "ending_shares": account.shares, "trade_approved": False, "live_eligible": False,
        "limitation": "Paper-ledger settlement under declared assumptions only; it is not a broker fill or investment instruction.",
    }
    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_dir / "manifest.json").write_text(json.dumps({
        "script_sha256": digest(Path(__file__)), "journal_sha256": digest(journal_path),
        "summary_sha256": digest(summary_path)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-file", type=Path, required=True)
    parser.add_argument("--opening-evidence", type=Path, required=True)
    parser.add_argument("--fee-policy", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(settle(args.state_file, args.opening_evidence, args.fee_policy, args.output_dir.resolve()), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
