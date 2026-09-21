#!/usr/bin/env python3
"""Create a dated, fail-closed paper-execution evidence record for 600519."""
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
sys.path.insert(0, str(ROOT / "scripts"))

from build_moutai_current_daily_simulation import load_quote
from value_investment_agent.current_execution_contract import build_current_execution_contract


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quote-report", type=Path, required=True)
    parser.add_argument("--suspension-evidence", type=Path, required=True)
    parser.add_argument("--prior-close", required=True)
    parser.add_argument("--liquidity-evidence", type=Path)
    parser.add_argument("--fee-policy-evidence", type=Path)
    parser.add_argument("--slippage-bps", default="10")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    quote_report = args.quote_report.resolve()
    _, _, _, next_session = load_quote(quote_report)
    contract = build_current_execution_contract(
        root=ROOT, quote_report=quote_report, suspension_evidence=args.suspension_evidence,
        liquidity_evidence=args.liquidity_evidence, fee_policy_evidence=args.fee_policy_evidence,
        next_session=datetime.fromisoformat(next_session["date"] + "T00:00:00").date(),
        prior_close=Decimal(args.prior_close), slippage_bps=Decimal(args.slippage_bps))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = (args.output_dir or ROOT / "runtime/strategy-validation" /
              f"moutai-current-execution-contract-{stamp}").resolve()
    if not output.is_relative_to(ROOT.resolve()):
        raise ValueError("Output must remain under the project root")
    output.mkdir(parents=True, exist_ok=False)
    evidence = output / "evidence.json"
    evidence.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({"script_sha256": digest(Path(__file__)),
        "evidence_sha256": digest(evidence)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pointer = ROOT / "runtime/strategy-validation/moutai-current-execution-contract-latest.json"
    pointer.write_text(json.dumps({"path": str(output.relative_to(ROOT)), "sha256": digest(evidence)},
                                  ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "execution_ready": contract["execution_ready"],
                      "blockers": contract["blockers"], "trade_approved": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
