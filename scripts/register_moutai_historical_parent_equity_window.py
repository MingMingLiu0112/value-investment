#!/usr/bin/env python3
"""Pre-register a separate historical parent-equity model window for 600519.

It preserves the prior annual-input registration and creates no valuation.
This prevents the newly archived Q3 filing from being silently introduced into
an already defined model after inspecting a replay result.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRIOR = ROOT / "runtime/strategy-validation/moutai-historical-window-registration-20260918T121703Z/evidence.json"
Q3 = ROOT / "runtime/strategy-validation/moutai-2014-q3-parent-equity-20260920T044648Z/evidence.json"
TIMELINE = ROOT / "runtime/strategy-validation/moutai-historical-input-timeline-20260910T101416Z/timeline.json"
FIRST_DECISION_AT = "2015-01-05T15:00:00+08:00"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))


def relative(path: Path) -> str:
    return str(path.relative_to(ROOT))


def build() -> dict:
    prior, q3, timeline = load(PRIOR), load(Q3), load(TIMELINE)
    window = prior["window"]
    selected = [row for row in timeline if window["start"] <= row["date"] <= window["end"]]
    if len(selected) != window["sessions"]:
        raise ValueError("Registered sessions are absent from the frozen timeline")
    if q3["available_at"] > FIRST_DECISION_AT or q3["report_period"] != "2014-09-30":
        raise ValueError("Candidate interim filing is not a valid pre-window fact")
    if q3["valuation_approved"] or q3["trade_approved"]:
        raise ValueError("Candidate source must remain research-only")
    if any(row["decision_at"] < FIRST_DECISION_AT for row in selected):
        raise ValueError("Timeline contains a decision before the registered information cutoff")
    return {
        "registration_version": "moutai-historical-parent-equity-window-v1",
        "symbol": "600519",
        "status": "registered_pending_historical_assumption_contract",
        "model_family": "parent_equity_residual_income",
        "window": window,
        "selection_rule": "Reuse the pre-registered 20 consecutive sessions. For this separately versioned model family, use the latest archived issuer interim parent-equity report available before the first decision; no replay has been run under this registration.",
        "information_cutoff": FIRST_DECISION_AT,
        "frozen_starting_facts": {
            "source_id": q3["source_id"],
            "report_period": q3["report_period"],
            "available_at": q3["available_at"],
            "parent_equity_cny": q3["facts"]["parent_equity_cny"],
            "parent_profit_ytd_cny": q3["facts"]["parent_profit_ytd_cny"],
            "issued_shares": q3["facts"]["issued_shares_cny_par_value"],
            "reported_basic_eps_ytd_cny_per_share": q3["facts"]["reported_basic_eps_ytd_cny_per_share"],
        },
        "forbidden_substitutions": [
            "Do not replace Q3 facts with the 2014 annual report, a later comparative column, or current facts.",
            "Do not infer post-report equity from cash distribution arithmetic without a separately audited clean-surplus/capital-action bridge.",
            "Do not select cost of equity, forward ROE, retention, fade, or terminal growth after examining the window's returns.",
        ],
        "required_before_replay": [
            "A dated historical cost-of-equity evidence policy with a declared scenario range.",
            "A historical profit, retention, fade and terminal-assumption contract, including the treatment of nine-month cumulative profit.",
            "A clean-surplus/capital-action bridge from the Q3 report date to each decision date.",
            "Dated fees, next-open execution, prior-known liquidity and same-period benchmark acceptance.",
        ],
        "price_or_return_outcomes_read": False,
        "model_contract_frozen": False,
        "formal_fair_value": None,
        "valuation_approved": False,
        "historical_trade_backtest_complete": False,
        "simulation_eligible": False,
        "trade_approved": False,
        "live_eligible": False,
        "inputs": {relative(path): digest(path) for path in (PRIOR, Q3, TIMELINE)},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    result = build()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output_dir or ROOT / "runtime/strategy-validation" / f"moutai-historical-parent-equity-window-registration-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    evidence = output / "evidence.json"
    evidence.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({
        "script": relative(Path(__file__)),
        "script_sha256": digest(Path(__file__)),
        "evidence_sha256": digest(evidence),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "status": result["status"], "sessions": result["window"]["sessions"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
