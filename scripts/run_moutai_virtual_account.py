#!/usr/bin/env python3
"""Run an auditable 600519 virtual-account ledger from explicit inputs.

The default synthetic path verifies accounting branches only.  It is never
market history and is deliberately labelled as such in every output.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.virtual_account import VirtualAccount, dated_research_fee, replay, ORDER_TERMS_VERSION
from value_investment_agent.virtual_account import current_sse_research_fee
from value_investment_agent.historical_fees import verify_current_sse_policy
from value_investment_agent.paper_sizing import size_entry_or_add, size_one_third_reduce
from value_investment_agent.simulation_state import DecisionInput, evaluate


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def synthetic_inputs(bounded_orders: bool = False) -> tuple[list[dict], dict[str, dict]]:
    sessions = [
        {"date": "2026-01-05", "open": "100", "close": "100", "execution_ready": True},
        {"date": "2026-01-06", "open": "100", "close": "120", "execution_ready": True},
        {"date": "2026-01-07", "open": "120", "close": "120", "execution_ready": True},
        {"date": "2026-01-08", "open": "120", "close": "120", "execution_ready": True},
        {"date": "2026-01-09", "open": "120", "close": "120", "execution_ready": True},
    ]
    entry_state = evaluate(DecisionInput(
        price=Decimal("100"), value=Decimal("200"), holding_shares=0,
        data_ready=True, valuation_approved=False, research_model_ready=True,
        account_ready=True, execution_ready=True, thesis_intact=True, trade_session_open=True,
    ))
    entry_sizing = size_entry_or_add(nav=Decimal("1000000"), cash=Decimal("1000000"),
                                     current_shares=0, price=Decimal("100"), tranche_index=0)
    reduce_state = evaluate(DecisionInput(
        price=Decimal("120"), value=Decimal("100"), holding_shares=entry_sizing["quantity"],
        data_ready=True, valuation_approved=False, research_model_ready=True,
        account_ready=True, execution_ready=True, thesis_intact=True, trade_session_open=True,
    ))
    reduce_sizing = size_one_third_reduce(sellable_shares=entry_sizing["quantity"])
    if entry_state["state"] != "proposed_entry" or reduce_state["state"] != "proposed_reduce":
        raise ValueError("Synthetic condition fixture no longer reaches its registered state branches")
    if not entry_sizing["quantity"] or not reduce_sizing["quantity"]:
        raise ValueError("Synthetic sizing fixture cannot create registered board-lot orders")
    decisions = {
        "2026-01-05": {**entry_state, "decision_id": "synthetic-entry-001", "quantity": entry_sizing["quantity"]},
        "2026-01-06": {**reduce_state, "decision_id": "synthetic-reduce-001", "quantity": reduce_sizing["quantity"]},
    }
    if bounded_orders:
        for row in sessions:
            row.update(price_limit_down="80", price_limit_up="150")
        for day, valid, limit, budget in (("2026-01-05", "2026-01-06", "101", "40000"),
                                           ("2026-01-06", "2026-01-07", "119", "0")):
            decisions[day]["execution_terms"] = {
                "version": ORDER_TERMS_VERSION, "valid_session": valid,
                "limit_price": limit, "cash_budget_cny": budget, "liquidity_budget_cny": "40000",
                "liquidity_as_of": day, "slippage_bps": "10",
                "basis_id": "synthetic-only-10bps-boundary-fixture-v1",
            }
    return sessions, decisions


def load_input(path: Path) -> tuple[list[dict], dict[str, dict], list[dict]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("symbol") != "600519" or not isinstance(value.get("sessions"), list) or not isinstance(value.get("decisions"), dict):
        raise ValueError("Input requires symbol=600519 plus sessions and date-keyed decisions")
    cash_events = value.get("cash_events", [])
    if not isinstance(cash_events, list):
        raise ValueError("cash_events must be a list when supplied")
    return value["sessions"], value["decisions"], cash_events


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, help="approved real or research input JSON")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--state-file", type=Path, help="persistent virtual-account snapshot; never a broker account")
    parser.add_argument("--synthetic", action="store_true", help="run the deterministic execution-path fixture")
    parser.add_argument("--fee-model", choices=("flat", "historical_sse", "reviewed_current_sse"), default="flat")
    parser.add_argument("--bounded-orders", action="store_true",
                        help="require frozen next-session limits, budgets, validity and explicit slippage; not model admission")
    args = parser.parse_args()
    if bool(args.input) == bool(args.synthetic):
        parser.error("Specify exactly one of --input or --synthetic")
    if args.synthetic:
        sessions, decisions = synthetic_inputs(args.bounded_orders)
        cash_events = []
        input_kind = "synthetic_execution_validation"
        limitation = "Synthetic prices and decisions validate execution mechanics only; they are not a historical backtest or investment recommendation."
        input_hash = None
    else:
        sessions, decisions, cash_events = load_input(args.input)
        input_kind = "explicit_input_requires_separate_data_model_admission"
        limitation = "This runner records simulation mechanics only. Input admissibility, model approval and live eligibility remain separate gates."
        input_hash = digest(args.input)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output_dir or ROOT / "runtime/strategy-validation" / f"moutai-virtual-account-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    account = VirtualAccount()
    if args.state_file and args.state_file.exists():
        account = VirtualAccount.from_dict(json.loads(args.state_file.read_text(encoding="utf-8")))
    if args.bounded_orders:
        proposals = [row for row in decisions.values() if row.get("state") in
                     {"proposed_entry", "proposed_add", "proposed_reduce", "proposed_exit"}]
        if account.pending_order:
            proposals.append(account.pending_order)
        if any("execution_terms" not in row for row in proposals):
            raise ValueError("Bounded-order mode refuses a legacy unconstrained proposal or restored order")
    opening_cash = account.cash
    fee_calculator = None
    fee_policy = None
    if args.fee_model == "historical_sse":
        fee_calculator = lambda side, quantity, price, traded_on: dated_research_fee(
            side, quantity, price, traded_on, exchange="SSE")
    elif args.fee_model == "reviewed_current_sse":
        fee_policy = verify_current_sse_policy(ROOT)
        fee_calculator = current_sse_research_fee
    account, journal = replay(sessions, decisions, account, cash_events=cash_events, fee_calculator=fee_calculator)
    if args.state_file:
        args.state_file.parent.mkdir(parents=True, exist_ok=True)
        staged = args.state_file.with_name("." + args.state_file.name + ".stage")
        staged.write_text(json.dumps(account.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(staged, args.state_file)
    (output / "journal.json").write_text(json.dumps(journal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    fills = [row["fill"] for row in journal if row["fill"]]
    summary = {
        "symbol": "600519", "run_type": input_kind, "input_sha256": input_hash,
        "opening_cash_cny": str(opening_cash), "ending_cash_cny": str(account.cash),
        "ending_shares": account.shares, "ending_nav_cny": str(account.marked_nav()),
        "new_journal_rows": len(journal), "processed_session_count": len(account.processed_sessions),
        "filled_orders": fills, "pending_order": account.pending_order,
        "fee_model": args.fee_model,
        "fee_policy": fee_policy,
        "bounded_orders_required": args.bounded_orders,
        "bounded_order_fill_count": sum("execution_terms" in row for row in fills),
        "live_eligible": False, "trade_approved": False, "limitation": limitation,
    }
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {"script_sha256": digest(Path(__file__)),
                "engine_sha256": digest(ROOT / "src/value_investment_agent/virtual_account.py"),
                "statutory_fee_engine_sha256": digest(ROOT / "src/value_investment_agent/historical_fees.py"),
                "outputs": {p.name: digest(p) for p in output.iterdir()}}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), **summary}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
