#!/usr/bin/env python3
"""Produce a synthetic two-session P2 settlement receipt.

The fixture exists only to exercise the shared decision -> frozen order ->
next-open settlement chain.  It is deliberately not an observed quote, Moutai
valuation, historical replay, or trade instruction.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from value_investment_agent.virtual_account import VirtualAccount, replay

from run_moutai_virtual_account import synthetic_inputs
from settle_moutai_pending_paper_order import settle


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    sessions, decisions = synthetic_inputs(bounded_orders=True)
    first, second = sessions[:2]
    decision = decisions[first["date"]]
    # `synthetic_inputs` reaches proposed_entry through the shared state
    # machine and position-sizing implementation before freezing its terms.
    account, creation_journal = replay([first], {first["date"]: decision})
    if account.pending_order is None or creation_journal[0]["created_order"] is None:
        raise ValueError("Synthetic fixture did not create a pending bounded order")
    state_path = output / "state.json"
    state_path.write_text(json.dumps(account.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    source_manifest = output / "fee-source-manifest.json"
    source_manifest.write_text(json.dumps({"synthetic": True, "scope": "mechanism only"}, indent=2) + "\n", encoding="utf-8")
    fee_policy = output / "fee-policy.json"
    fee_policy.write_text(json.dumps({
        "policy_version": "sse-current-paper-fees-v1", "exchange": "SSE",
        "valid_session": second["date"], "execution_ready": True,
        "broker_invoice_verified": False,
        "source_manifest": {"path": str(source_manifest.relative_to(ROOT)), "sha256": digest(source_manifest)},
        "commission_scenario": {"rate": "0.0003", "minimum_cny": "5"},
        "synthetic_fixture": True,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    opening = output / "opening-evidence.json"
    opening.write_text(json.dumps({
        "symbol": "600519", "session": second["date"], "opening_price_cny": second["open"],
        "close_price_cny": second["close"], "execution_ready": True,
        "price_limit_down": second["price_limit_down"], "price_limit_up": second["price_limit_up"],
        "security_status": "tradable", "corporate_action_status": "none",
        "evidence_refs": [{"synthetic": True, "scope": "mechanism only"}],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    settlement = settle(state_path, opening, fee_policy, output / "settlement")
    before_replay = json.loads(state_path.read_text(encoding="utf-8"))
    # The order was consumed; a second attempt must refuse rather than mutate.
    replay_refused = False
    try:
        settle(state_path, opening, fee_policy, output / "settlement-replay")
    except ValueError as exc:
        replay_refused = str(exc) == "No pending paper order exists"
    if not replay_refused or json.loads(state_path.read_text(encoding="utf-8")) != before_replay:
        raise ValueError("Synthetic settlement replay was not idempotently refused")
    receipt = {
        "run_type": "synthetic_p2_pending_order_settlement_fixture",
        "created_decision_state": decision["state"], "created_quantity": decision["quantity"],
        "creation_journal": creation_journal, "settlement": settlement,
        "second_settlement_refused_without_mutation": replay_refused,
        "synthetic": True, "trade_approved": False, "live_eligible": False,
        "limitation": "Synthetic mechanism fixture only; it is not Moutai market data, a historical backtest, a valuation result, or an investment instruction.",
    }
    receipt_path = output / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({
        "script_sha256": digest(Path(__file__)), "receipt_sha256": digest(receipt_path),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output_dir or ROOT / "runtime/strategy-validation" / f"moutai-p2-settlement-fixture-{stamp}"
    print(json.dumps({"output": str(output), **run(output.resolve())}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
