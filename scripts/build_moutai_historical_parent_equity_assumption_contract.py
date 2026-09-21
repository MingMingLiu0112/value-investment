#!/usr/bin/env python3
"""Freeze the missing point-in-time assumptions required before historical replay."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INPUTS = {
    "window_registration": ROOT / "runtime/strategy-validation/moutai-historical-parent-equity-window-registration-20260920T044823Z/evidence.json",
    "q3_parent_equity": ROOT / "runtime/strategy-validation/moutai-2014-q3-parent-equity-20260920T044648Z/evidence.json",
    "capital_coverage": ROOT / "runtime/strategy-validation/moutai-2014-q3-window-capital-bridge-20260920T050443Z/evidence.json",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build() -> dict[str, object]:
    data = {name: json.loads(path.read_text(encoding="utf-8")) for name, path in INPUTS.items()}
    window = data["window_registration"]["window"]
    if data["q3_parent_equity"]["published_date"] != "2014-10-30":
        raise ValueError("Unexpected Q3 source timing")
    if "clean_surplus_unresolved" not in data["capital_coverage"]["status"]:
        raise ValueError("Capital coverage no longer reflects the open bridge")
    return {
        "contract_version": "moutai-historical-parent-equity-assumptions-v1",
        "symbol": "600519",
        "window": window,
        "known_before_window": {
            "parent_equity_q3_cny": data["q3_parent_equity"]["facts"]["parent_equity_cny"],
            "parent_profit_9m_cny": data["q3_parent_equity"]["facts"]["parent_profit_ytd_cny"],
            "issued_shares": data["q3_parent_equity"]["facts"]["issued_shares_cny_par_value"],
            "source_published_date": data["q3_parent_equity"]["published_date"],
        },
        "forbidden_inputs": [
            "Any 2015-01 decision may not use the 2026 current cost-of-equity policy or its 2015-2025 full-sample beta.",
            "No annual report, price, corporate action, benchmark, forecast, fee or execution result published after a decision may be backfilled into that decision.",
            "The Q3 parent-equity amount may not be converted into a January book value by subtracting later distributions without a reviewed accounting bridge.",
        ],
        "required_assumptions": [
            {"id": "risk_free_rate", "requirement": "CNY nominal risk-free proxy observable before each decision date, with source, maturity and compounding recorded.", "status": "missing"},
            {"id": "beta_policy", "requirement": "Pre-decision return window, benchmark, total-return treatment, minimum observations and estimation method frozen without future returns.", "status": "missing"},
            {"id": "equity_risk_premium", "requirement": "Dated China ERP source or an explicitly bounded alternative available before each decision date.", "status": "missing"},
            {"id": "profit_and_payout_policy", "requirement": "Treatment of 9M profit, annualisation, retention, payout, fade and terminal regime with economic support and counterevidence.", "status": "missing"},
            {"id": "equity_bridge", "requirement": "Q3-to-decision clean-surplus and capital-action bridge matching the listed-parent-equity claim.", "status": "missing"},
        ],
        "inputs": {str(path.relative_to(ROOT)): digest(path) for path in INPUTS.values()},
        "replay_eligible": False,
        "formal_fair_value": None,
        "valuation_approved": False,
        "historical_trade_backtest_complete": False,
        "simulation_eligible": False,
        "trade_approved": False,
        "live_eligible": False,
        "conclusion": "assumption_contract_registered_not_replay_eligible",
    }


def main() -> int:
    payload = build()
    output = ROOT / "runtime/strategy-validation" / ("moutai-historical-parent-equity-assumptions-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    output.mkdir(parents=True, exist_ok=False)
    evidence = output / "evidence.json"
    evidence.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "conclusion": payload["conclusion"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
