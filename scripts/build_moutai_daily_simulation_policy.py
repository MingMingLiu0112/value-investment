#!/usr/bin/env python3
"""Create a separately dated 600519 daily paper-execution policy receipt."""
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

from build_moutai_current_daily_simulation import load_execution_contract, load_quote
from value_investment_agent.daily_simulation_policy import build_policy


IMPLEMENTATION_FILES = [
    "src/value_investment_agent/daily_simulation_policy.py",
    "src/value_investment_agent/current_execution_contract.py",
    "src/value_investment_agent/simulation_state.py",
    "src/value_investment_agent/virtual_account.py",
    "src/value_investment_agent/paper_sizing.py",
    "scripts/build_moutai_current_daily_simulation.py",
    "scripts/settle_moutai_pending_paper_order.py",
]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quote-report", type=Path, required=True)
    parser.add_argument("--execution-contract", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    quote_report = args.quote_report.resolve()
    contract_path = args.execution_contract.resolve()
    if not quote_report.is_relative_to(ROOT.resolve()) or not contract_path.is_relative_to(ROOT.resolve()):
        raise ValueError("Quote report and execution contract must remain under the project root")
    if contract_path.name != "evidence.json":
        raise ValueError("Execution contract must be an archived evidence.json")
    price, observed_at, _quote, next_session = load_quote(quote_report)
    execution = load_execution_contract(contract_path, observed_at, next_session)
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    observed_session = observed_at.date().isoformat()
    valid_session = next_session["date"]
    policy = build_policy(
        execution_contract=contract,
        execution_contract_ref={"path": str(contract_path.relative_to(ROOT)), "sha256": digest(contract_path)},
        observed_session=observed_session,
        valid_session=valid_session,
    )
    if policy["execution_ready"] != execution["execution_ready"]:
        raise ValueError("Daily simulation policy disagrees with the execution-contract summary")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = (args.output_dir or ROOT / "runtime/strategy-validation" /
              f"moutai-daily-simulation-policy-{stamp}").resolve()
    if not output.is_relative_to(ROOT.resolve()):
        raise ValueError("Output must remain under the project root")
    output.mkdir(parents=True, exist_ok=False)
    evidence = output / "evidence.json"
    evidence.write_text(json.dumps(policy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({
        "script_sha256": digest(Path(__file__)),
        "evidence_sha256": digest(evidence),
        "implementation_hashes": {path: digest(ROOT / path) for path in IMPLEMENTATION_FILES},
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pointer = ROOT / "runtime/strategy-validation/moutai-daily-simulation-policy-latest.json"
    pointer.write_text(json.dumps({"path": str(output.relative_to(ROOT)), "sha256": digest(evidence)},
                                  ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "observed_session": observed_session,
        "valid_session": valid_session,
        "execution_ready": execution["execution_ready"],
        "trade_approved": False,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
