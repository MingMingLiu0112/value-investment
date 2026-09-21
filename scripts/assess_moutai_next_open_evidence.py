#!/usr/bin/env python3
"""Assess only the next-session opening observation for a pending 600519 paper order."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, time
from decimal import Decimal
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.quote_session_collection import resolve_session_reference
from value_investment_agent.quote_sessions import parse_quote


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_open(report_path: Path) -> tuple[dict, dict]:
    bundle_path = report_path.with_name("bundle.json")
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    now = datetime.fromisoformat(bundle["finished_at"])
    reference = (bundle.get("references") or {}).get("600519")
    resolved = resolve_session_reference(reference, bundle.get("documents"))
    quotes = {provider: parse_quote(resolved[provider], provider, "600519", now)
              for provider in ("tencent", "sina")}
    dates = {datetime.fromisoformat(item["observed_trade_at"]).date().isoformat() for item in quotes.values()}
    openings = {item["opening_price"] for item in quotes.values()}
    if len(dates) != 1 or len(openings) != 1:
        raise ValueError("Opening evidence requires one date and an exact dual-source opening")
    stamp = min(datetime.fromisoformat(item["observed_trade_at"]) for item in quotes.values())
    if stamp.time() < time(9, 30):
        raise ValueError("Opening evidence predates the regular session")
    return {
        "date": next(iter(dates)), "opening_price_cny": str(next(iter(openings))),
        "provider_times": {name: item["observed_trade_at"] for name, item in quotes.items()},
        "provider_source_hashes": {name: item["sha256"] for name, item in quotes.items()},
        "provider_source_urls": {name: item["source_url"] for name, item in quotes.items()},
        "bundle": {"path": str(bundle_path.relative_to(ROOT)), "sha256": digest(bundle_path)},
    }, resolved


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prior-close-report", type=Path, required=True)
    parser.add_argument("--open-report", type=Path, required=True)
    parser.add_argument("--suspension-evidence", type=Path, required=True)
    args = parser.parse_args()
    prior = json.loads(args.prior_close_report.read_text(encoding="utf-8"))
    row = next((item for item in prior.get("observations", []) if item.get("symbol") == "600519"), None)
    if not row or (row.get("result") or {}).get("passed") is not True:
        raise ValueError("A verified prior close report is required")
    opening, _ = load_open(args.open_report.resolve())
    prior_date = (row["result"] or {})["expected_session"]
    if opening["date"] <= prior_date:
        raise ValueError("Opening evidence does not follow the verified close")
    suspension_path = args.suspension_evidence.resolve()
    suspension = json.loads(suspension_path.read_text(encoding="utf-8"))
    expected_window = prior_date.replace("-", "") + ".." + opening["date"].replace("-", "")
    if (not suspension_path.is_relative_to(ROOT.resolve()) or suspension.get("symbol") != "600519"
            or suspension.get("window") != expected_window
            or suspension.get("suspension_status") != "no_official_listed_stop_resume_records_returned"):
        raise ValueError("Current official suspension evidence is incomplete")
    evidence = {
        "symbol": "600519", "assessment_version": "moutai-next-open-evidence-v1",
        "prior_close": {"date": prior_date, "price_cny": row["observed_price"],
                        "report_path": str(args.prior_close_report.resolve().relative_to(ROOT)),
                        "report_sha256": digest(args.prior_close_report.resolve())},
        "next_open": opening,
        "suspension_evidence": {"path": str(suspension_path.relative_to(ROOT)),
                                  "sha256": digest(suspension_path),
                                  "status": suspension["suspension_status"]},
        "execution_ready": False,
        "execution_status": "opening_crosschecked_price_limit_and_security_status_pending",
        "limitations": [
            "This validates the opening field from two public quote responses, not a broker fill.",
            "Price-limit/security status, order-book liquidity and a frozen order limit are not yet bound.",
            "This evidence must not change the prior close decision or backfill a hypothetical fill.",
        ],
        "trade_approved": False, "live_eligible": False,
    }
    output = ROOT / "runtime/company-research" / ("600519-next-open-evidence-" + datetime.now().strftime("%Y%m%dT%H%M%SZ"))
    output.mkdir(parents=True, exist_ok=False)
    path = output / "evidence.json"
    path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({"script_sha256": digest(Path(__file__)), "evidence_sha256": digest(path)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "next_open": opening, "execution_ready": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
