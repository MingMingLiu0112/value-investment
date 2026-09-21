#!/usr/bin/env python3
"""Freeze a short-lived SSE paper-fee policy from freshly archived sources."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from value_investment_agent.historical_fees import CURRENT_SSE_EVIDENCE


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--valid-session", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    manifest_path = args.source_manifest.resolve()
    output = args.output_dir.resolve()
    if not manifest_path.is_relative_to(ROOT.resolve()) or not output.is_relative_to(ROOT.resolve()):
        raise ValueError("Inputs and output must remain under the project root")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    captured = datetime.fromisoformat(manifest["created_at"]).date()
    valid = date.fromisoformat(args.valid_session)
    if not captured < valid <= date.fromordinal(captured.toordinal() + 7):
        raise ValueError("A paper-fee policy may cover only the next seven calendar days")
    sources = {row["source_id"]: row for row in manifest.get("sources", [])}
    if set(sources) != set(CURRENT_SSE_EVIDENCE):
        raise ValueError("Current fee source set is incomplete")
    for source_id, (url, expected_hash) in CURRENT_SSE_EVIDENCE.items():
        row = sources[source_id]
        if row.get("url") != url or row.get("sha256") != expected_hash:
            raise ValueError(f"Unexpected current fee source: {source_id}")
    policy = {
        "policy_version": "sse-current-paper-fees-v1", "exchange": "SSE",
        "valid_session": valid.isoformat(), "captured_on": captured.isoformat(),
        "source_manifest": {"path": str(manifest_path.relative_to(ROOT)), "sha256": digest(manifest_path)},
        "commission_scenario": {"rate": "0.0003", "minimum_cny": "5", "rounding": "total_fee_to_cent_half_even"},
        "broker_invoice_verified": False, "execution_ready": True,
        "limitations": ["Only a paper-research fee scenario; not a broker invoice.",
                        "The policy expires after its explicit valid session."],
        "trade_approved": False, "live_eligible": False,
    }
    output.mkdir(parents=True, exist_ok=False)
    evidence = output / "evidence.json"
    evidence.write_text(json.dumps(policy, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({"script_sha256": digest(Path(__file__)),
        "evidence_sha256": digest(evidence)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "valid_session": valid.isoformat(), "trade_approved": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
