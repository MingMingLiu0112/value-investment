#!/usr/bin/env python3
"""Derive a conservative next-session paper liquidity budget from prior close data."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PARTICIPATION_RATE = Decimal("0.01")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quote-report", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report_path, output = args.quote_report.resolve(), args.output_dir.resolve()
    if not report_path.is_relative_to(ROOT.resolve()) or not output.is_relative_to(ROOT.resolve()):
        raise ValueError("Inputs and output must remain under the project root")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    rows = [row for row in report.get("observations", []) if row.get("symbol") == "600519"]
    if len(rows) != 1 or (rows[0].get("result") or {}).get("passed") is not True:
        raise ValueError("A verified 600519 dual-source quote report is required")
    bundle_path = report_path.with_name("bundle.json")
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    refs = bundle["references"]["600519"]["document_refs"]
    documents = bundle["documents"]
    tencent = documents[refs["tencent"]]
    sina = documents[refs["sina"]]
    if any(hashlib.sha256(base64.b64decode(doc["raw_base64"])).hexdigest() != doc["sha256"]
           for doc in (tencent, sina)):
        raise ValueError("Quote raw document hash mismatch")
    tencent_text = base64.b64decode(tencent["raw_base64"]).decode("gb18030")
    sina_text = base64.b64decode(sina["raw_base64"]).decode("gb18030")
    tx_matches = re.findall(r"~(\d+(?:\.\d+)?)/(\d+(?:\.\d+)?)/(\d+(?:\.\d+)?)~", tencent_text)
    if len(tx_matches) != 1:
        raise ValueError("Tencent turnover field is missing or ambiguous")
    tencent_turnover = Decimal(tx_matches[0][2])
    sina_match = re.search(r'var hq_str_sh600519="([^"]*)";', sina_text)
    if not sina_match:
        raise ValueError("Sina 600519 payload is missing")
    sina_fields = sina_match.group(1).split(",")
    if len(sina_fields) < 10:
        raise ValueError("Sina payload is incomplete")
    sina_turnover = Decimal(sina_fields[9])
    if not all(value.is_finite() and value > 0 for value in (tencent_turnover, sina_turnover)):
        raise ValueError("Turnover must be positive")
    if abs(tencent_turnover - sina_turnover) > Decimal("0.01"):
        raise ValueError("Dual-source turnover conflict")
    as_of = rows[0]["result"]["expected_session"]
    budget = (tencent_turnover * PARTICIPATION_RATE).quantize(Decimal("0.01"))
    evidence = {
        "symbol": "600519", "as_of": as_of, "quote_report_sha256": digest(report_path),
        "source_hashes": [tencent["sha256"], sina["sha256"]],
        "prior_completed_session_turnover_cny": str(tencent_turnover),
        "participation_rate": str(PARTICIPATION_RATE), "liquidity_budget_cny": str(budget),
        "scope": "Next-session paper-research budget from the prior completed session only.",
        "limitations": ["A prior-day turnover cap cannot prove next-session order-book depth or a fill.",
                        "The 1% participation rate is a frozen conservative paper assumption, not a broker instruction."],
        "trade_approved": False, "live_eligible": False,
    }
    output.mkdir(parents=True, exist_ok=False)
    path = output / "evidence.json"
    path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({"script_sha256": digest(Path(__file__)),
        "evidence_sha256": digest(path)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "as_of": as_of, "budget_cny": str(budget)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
