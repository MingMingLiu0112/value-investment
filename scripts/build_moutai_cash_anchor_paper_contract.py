#!/usr/bin/env python3
"""Build a research-only 600519 paper-execution contract from cash-anchor values."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from value_investment_agent.simulation_state import DecisionInput, PROPOSED_ENTRY, evaluate


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_values() -> tuple[list[dict], dict]:
    pointer = json.loads((ROOT / "runtime/strategy-validation/moutai-historical-cash-anchor-equity-range-latest.json").read_text(encoding="utf-8"))
    directory = (ROOT / pointer["path"]).resolve()
    path = directory / "daily-values.json"
    if not directory.is_relative_to(ROOT.resolve()) or digest(path) != pointer["daily_values_sha256"]:
        raise ValueError("Pinned cash-anchor research values changed")
    return json.loads(path.read_text(encoding="utf-8")), pointer


def build_decisions(values: list[dict]) -> tuple[dict[str, dict], list[dict]]:
    orders: dict[str, dict] = {}
    trace = []
    for row in values:
        if row["status"] != "cash_distribution_anchored_research_only":
            trace.append({"date": row["date"], "state": "blocked", "action": "no_order",
                          "reason": row["status"], "research_value_cny": None})
            continue
        bear = next(item for item in row["cases"] if item["scenario"] == "bear")
        decision = evaluate(DecisionInput(
            price=Decimal(row["price_close_cny"]), value=Decimal(bear["conditional_value_per_share_cny"]),
            holding_shares=0, data_ready=True, valuation_approved=False, research_model_ready=True,
            account_ready=True, execution_ready=True, thesis_intact=True, trade_session_open=True,
            blockers=(),
        ))
        trace.append({"date": row["date"], "state": decision["state"], "action": decision["action"],
                      "reasons": decision["reasons"], "safety_margin": decision["safety_margin"],
                      "research_value_cny": bear["conditional_value_per_share_cny"],
                      "model_scope": "research_model_only_not_formal_valuation"})
        if decision["state"] == PROPOSED_ENTRY:
            orders[row["date"]] = {"decision_id": f"cash-anchor-entry-{row['date']}",
                                   "state": PROPOSED_ENTRY, "quantity": 100}
    return orders, trace


def resolve_output(output_dir: Path | None) -> Path:
    """Make CLI output paths comparable with the absolute project root."""
    if output_dir is not None:
        return output_dir.resolve()
    return ROOT / "runtime/strategy-validation" / (
        "moutai-cash-anchor-paper-contract-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    values, pointer = load_values()
    orders, trace = build_decisions(values)
    output = resolve_output(args.output_dir)
    output.mkdir(parents=True, exist_ok=False)
    from build_moutai_real_execution_contract import build_contract
    contract = build_contract()
    contract.update({"contract_version": "moutai-cash-anchor-paper-contract-v1", "decisions": orders,
                     "research_simulation_eligible": True, "formal_fair_value": None,
                     "valuation_approved": False, "trade_approved": False,
                     "interpretation": "A segregated paper-research contract uses the frozen bear cash-anchor endpoint. It may create paper proposals only; it is not a formal fair value, approved strategy, or live-trading input."})
    contract_path = output / "input.json"
    trace_path = output / "daily-decisions.json"
    contract_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    trace_path.write_text(json.dumps(trace, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {"symbol": "600519", "rule_version": "moutai-cash-anchor-paper-contract-v1", "sessions": len(trace),
               "blocked_before_cash_observation": sum(row["state"] == "blocked" for row in trace),
               "research_model_decision_sessions": sum(row["state"] != "blocked" for row in trace),
               "proposed_orders": len(orders), "research_simulation_eligible": True,
               "formal_fair_value": None, "valuation_approved": False, "trade_approved": False,
               "interpretation": "All order candidates must satisfy the existing 30% safety-margin rule on the conservative bear research endpoint. Zero candidates is a model result, not a missing-model block."}
    summary_path = output / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({"cash_anchor_pointer": pointer, "script_sha256": digest(Path(__file__)),
        "outputs": {path.name: digest(path) for path in (contract_path, trace_path, summary_path)}}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ROOT / "runtime/strategy-validation/moutai-cash-anchor-paper-contract-latest.json").write_text(
        json.dumps({"path": str(output.relative_to(ROOT)), "summary_sha256": digest(summary_path)}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(json.dumps({"output": str(output), **summary}, ensure_ascii=False))


if __name__ == "__main__":
    raise SystemExit(main())
