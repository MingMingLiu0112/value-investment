#!/usr/bin/env python3
"""Replay paper-decision states against archived, point-in-time Moutai inputs.

The archived inputs deliberately have no approved historical intrinsic value.
This runner must therefore demonstrate blocked daily decisions and zero orders,
not manufacture a historical trading result.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from value_investment_agent.historical_validation import NOT_PIT_SAFE
from value_investment_agent.simulation_state import DecisionInput, evaluate

INPUT = ROOT / "runtime/strategy-validation/moutai-daily-research-inputs-20260909T161900156334Z/daily-inputs.json"
INPUT_HASH = "2a3e748c43f1f25371da12aed478bfd1f1c96d0fe957609720e53043207e7a9f"
LEGACY_INPUT = ROOT / "runtime/strategy-validation/moutai-legacy-signal-sensitivity-20260909T112051809228Z/daily-conditions.csv"
LEGACY_INPUT_HASH = "8f92cdda20575deecba6cf63de5e2d83a93ff814cf42421bf4836e9cc342bf50"
RULE_VERSION = "moutai-paper-state-v1"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_legacy_references() -> dict[str, dict]:
    if digest(LEGACY_INPUT) != LEGACY_INPUT_HASH:
        raise ValueError("Pinned legacy reference input changed")
    with LEGACY_INPUT.open(encoding="utf-8", newline="") as stream:
        rows = [row for row in csv.DictReader(stream) if row["threshold_pct"] == "30"]
    if len(rows) != 2674 or len({row["date"] for row in rows}) != len(rows):
        raise ValueError("Unexpected legacy reference coverage")
    return {row["date"]: row for row in rows}


def build_decisions(rows: list[dict], legacy_references: dict[str, dict]) -> list[dict]:
    decisions = []
    for row in rows:
        legacy = legacy_references[row["date"]]
        decision = evaluate(DecisionInput(
            price=Decimal(row["close"]), value=None, holding_shares=0,
            data_ready=True, valuation_approved=False, account_ready=False,
            execution_ready=False, thesis_intact=None, trade_session_open=True,
            blockers=tuple(row["blockers"]) + ("unapproved_legacy_pe_pb_reference",),
        ))
        decisions.append({
            "date": row["date"], "decision_at": row["decision_at"],
            "close": row["close"], "annual_source_id": row["annual_source_id"],
            "legacy_reference_unadjusted": legacy["reference_unadjusted"],
            "legacy_reference_exdate_cash_scenario": legacy["reference_exdate_cash_scenario"],
            "legacy_reference_condition": legacy["condition_unadjusted"],
            "legacy_reference_status": "unapproved_PE18_PB4_equal_blend_not_DCF",
            "rule_version": RULE_VERSION, "state": decision["state"],
            "action": decision["action"], "reasons": decision["reasons"],
            "trade_approved": decision["trade_approved"],
        })
    return decisions


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if digest(INPUT) != INPUT_HASH:
        raise ValueError("Pinned daily research inputs changed")
    rows = json.loads(INPUT.read_text(encoding="utf-8"))
    if len(rows) != 2674 or rows[0]["date"] != "2015-01-05" or rows[-1]["date"] != "2025-12-31":
        raise ValueError("Unexpected historical input coverage")
    decisions = build_decisions(rows, load_legacy_references())
    if any(row["action"] != "no_order" or row["trade_approved"] for row in decisions):
        raise ValueError("Research-only historical inputs must not generate paper orders")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output_dir or ROOT / "runtime/strategy-validation" / f"moutai-paper-decisions-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    evidence = output / "daily-decisions.json"
    evidence.write_text(json.dumps(decisions, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (output / "daily-decisions.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["date", "decision_at", "close", "annual_source_id", "legacy_reference_unadjusted", "legacy_reference_exdate_cash_scenario", "legacy_reference_condition", "legacy_reference_status", "rule_version", "state", "action", "reasons", "trade_approved"])
        writer.writeheader()
        for row in decisions:
            writer.writerow({**row, "reasons": ";".join(row["reasons"])})
    summary = {
        "symbol": "600519", "rule_version": RULE_VERSION, "input_path": str(INPUT.relative_to(ROOT)),
        "input_sha256": INPUT_HASH, "rows": len(decisions), "first_date": decisions[0]["date"],
        "last_date": decisions[-1]["date"], "states": dict(Counter(row["state"] for row in decisions)),
        "orders": 0, "validation_classification": NOT_PIT_SAFE,
        "validation_admission_status": "NOT_ADMITTED", "approved_value_model_sessions": 0,
        "strategy_backtest_complete": False, "trade_approved": False,
        "legacy_reference": {"path": str(LEGACY_INPUT.relative_to(ROOT)), "sha256": LEGACY_INPUT_HASH,
                             "status": "PE18/PB4 equal blend is visible for counterevidence only, not an approved historical value."},
        "interpretation": "Historical daily decision trace completed, but all dates are blocked because no approved historical value, paper account or execution admission exists. The old PE18/PB4 reference is retained as counterevidence, not promoted to value.",
    }
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {"rule_version": RULE_VERSION, "outputs": {path.name: digest(path) for path in output.iterdir() if path.is_file()}}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    latest = ROOT / "runtime/strategy-validation/moutai-paper-decisions-latest.json"
    latest.write_text(json.dumps({"path": str(output.relative_to(ROOT)), "summary_sha256": digest(output / "summary.json")}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), **summary}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
