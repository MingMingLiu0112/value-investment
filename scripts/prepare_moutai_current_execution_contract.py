#!/usr/bin/env python3
"""Build one fail-closed dated 600519 paper-execution contract from a quote session."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_moutai_current_daily_simulation import load_quote


def run_json(*args: str) -> dict:
    completed = subprocess.run([sys.executable, "-X", "utf8", *args], cwd=ROOT,
                               text=True, encoding="utf-8", capture_output=True, check=True)
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        raise ValueError(f"No JSON output from {' '.join(args)}")
    return json.loads(lines[-1])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quote-report", type=Path, required=True)
    args = parser.parse_args()
    quote_report = args.quote_report.resolve()
    if not quote_report.is_relative_to(ROOT.resolve()):
        raise ValueError("Quote report must remain under the project root")
    price, observed_at, _quote, next_session = load_quote(quote_report)
    observed, valid = observed_at.date().isoformat(), next_session["date"]
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suspension = run_json("scripts/assess_moutai_current_suspension.py",
                          "--start", observed.replace("-", ""), "--end", valid.replace("-", ""))
    fees = run_json("scripts/archive_current_fee_sources.py")
    fee_output = ROOT / "runtime/trading-rule-evidence" / f"current-sse-paper-fee-policy-{valid}-{run_id}"
    fee = run_json("scripts/build_current_sse_fee_policy.py", "--source-manifest",
                   str(Path(fees["output"]) / "manifest.json"), "--valid-session", valid,
                   "--output-dir", str(fee_output))
    liquidity_output = ROOT / "runtime/strategy-validation" / f"moutai-prior-liquidity-budget-{observed}-{run_id}"
    liquidity = run_json("scripts/build_moutai_prior_liquidity_budget.py", "--quote-report", str(quote_report),
                         "--output-dir", str(liquidity_output))
    contract = run_json("scripts/build_moutai_current_execution_contract.py", "--quote-report", str(quote_report),
                        "--suspension-evidence", str(Path(suspension["output"]) / "evidence.json"),
                        "--fee-policy-evidence", str(Path(fee["output"]) / "evidence.json"),
                        "--liquidity-evidence", str(Path(liquidity["output"]) / "evidence.json"),
                        "--prior-close", str(price))
    if contract.get("execution_ready") is not True or contract.get("trade_approved") is not False:
        raise ValueError("Current execution contract did not retain the paper-only boundary")
    policy = run_json("scripts/build_moutai_daily_simulation_policy.py",
                      "--quote-report", str(quote_report),
                      "--execution-contract", str(Path(contract["output"]) / "evidence.json"))
    if policy.get("observed_session") != observed or policy.get("valid_session") != valid:
        raise ValueError("Daily simulation policy dates do not match the execution contract")
    print(json.dumps({"quote_session": observed, "valid_session": valid,
                      "contract": contract, "policy": policy}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
