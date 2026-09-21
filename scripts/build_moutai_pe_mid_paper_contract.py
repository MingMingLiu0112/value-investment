#!/usr/bin/env python3
"""Create an isolated 2015-2024 Moutai median-PE paper experiment contract."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from value_investment_agent.simulation_state import DecisionInput, PROPOSED_ENTRY, PROPOSED_REDUCE, evaluate


WINDOW_END = "2024-12-31"
QUANTITY = 100


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_decisions(values: list[dict], window_end: str | None = WINDOW_END) -> tuple[dict[str, dict], list[dict]]:
    orders: dict[str, dict] = {}
    trace: list[dict] = []
    logical_holding = False
    for row in values:
        if window_end is not None and row["date"] > window_end:
            break
        if row["status"] != "historical_relative_pe_research_only":
            trace.append({"date": row["date"], "state": "blocked", "action": "no_order",
                          "reason": row["status"], "model_scope": "relative_pe_research_only"})
            continue
        mid = next(case for case in row["cases"] if case["scenario"] == "mid")
        decision = evaluate(DecisionInput(
            price=Decimal(row["price_close_cny"]), value=Decimal(mid["conditional_value_per_share_cny"]),
            holding_shares=QUANTITY if logical_holding else 0, data_ready=True,
            valuation_approved=False, research_model_ready=True, account_ready=True,
            execution_ready=True, thesis_intact=True, trade_session_open=True, blockers=(),
        ))
        trace.append({"date": row["date"], "state": decision["state"], "action": decision["action"],
                      "reasons": decision["reasons"], "safety_margin": decision["safety_margin"],
                      "price_close_cny": row["price_close_cny"], "mid_value_cny": mid["conditional_value_per_share_cny"],
                      "prior_pe_multiple": mid["prior_pe_multiple"], "model_scope": "relative_pe_research_only"})
        if decision["state"] == PROPOSED_ENTRY:
            orders[row["date"]] = {"decision_id": f"pe-mid-entry-{row['date']}", "state": PROPOSED_ENTRY, "quantity": QUANTITY}
            logical_holding = True
        elif decision["state"] == PROPOSED_REDUCE:
            orders[row["date"]] = {"decision_id": f"pe-mid-exit-{row['date']}", "state": PROPOSED_REDUCE, "quantity": QUANTITY}
            logical_holding = False
    return orders, trace


def main() -> int:
    pointer = json.loads((ROOT / "runtime/strategy-validation/moutai-historical-pe-crosscheck-latest.json").read_text(encoding="utf-8"))
    directory = (ROOT / pointer["path"]).resolve()
    values_path = directory / "daily-values.json"
    if not directory.is_relative_to(ROOT.resolve()) or digest(values_path) != pointer["daily_values_sha256"]:
        raise ValueError("Pinned PE cross-check values changed")
    values = json.loads(values_path.read_text(encoding="utf-8"))
    orders, trace = build_decisions(values)
    from build_moutai_real_execution_contract import build_contract
    contract = build_contract()
    contract["sessions"] = [row for row in contract["sessions"] if row["date"] <= WINDOW_END]
    contract["cash_events"] = [row for row in contract["cash_events"] if row["payment_date"] <= WINDOW_END]
    if not contract["sessions"] or contract["sessions"][-1]["date"] != WINDOW_END:
        raise ValueError("Execution window does not end on reviewed 2024 session")
    contract.update({"contract_version": "moutai-pe-mid-paper-contract-v1", "decisions": orders,
                     "research_simulation_eligible": True, "formal_fair_value": None,
                     "valuation_approved": False, "trade_approved": False,
                     "interpretation": "Pre-registered median prior-PE research experiment. It uses the unchanged 30% entry margin and exits when close exceeds the daily median-relative value. It is not intrinsic value, a formal valuation, or a live-trading input."})
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = ROOT / "runtime/strategy-validation" / f"moutai-pe-mid-paper-contract-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    input_path = output / "input.json"
    trace_path = output / "daily-decisions.json"
    input_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    trace_path.write_text(json.dumps(trace, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {"symbol": "600519", "rule_version": contract["contract_version"], "window_end": WINDOW_END,
               "sessions": len(contract["sessions"]), "cash_events": len(contract["cash_events"]),
               "blocked_sessions": sum(row["state"] == "blocked" for row in trace), "research_decision_sessions": sum(row["state"] != "blocked" for row in trace),
               "proposed_entries": sum(row["state"] == PROPOSED_ENTRY for row in trace), "proposed_exits": sum(row["state"] == PROPOSED_REDUCE for row in trace),
               "formal_fair_value": None, "valuation_approved": False, "trade_approved": False,
               "interpretation": "The 2015-2024 window excludes unresolved 2025 repurchase/cancellation scope. This is a segregated paper experiment, not a validated strategy or investment recommendation."}
    summary_path = output / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({"pe_crosscheck_pointer": pointer, "script_sha256": digest(Path(__file__)), "outputs": {path.name: digest(path) for path in (input_path, trace_path, summary_path)}}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ROOT / "runtime/strategy-validation/moutai-pe-mid-paper-contract-latest.json").write_text(
        json.dumps({"path": str(output.relative_to(ROOT)), "summary_sha256": digest(summary_path)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), **summary}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
