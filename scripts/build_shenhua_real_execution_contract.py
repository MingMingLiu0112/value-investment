#!/usr/bin/env python3
"""Freeze China Shenhua daily bars against reviewed suspension evidence.

This is a chronological execution-input contract.  It deliberately does not
turn daily OHLC data, retrospective resumption dates, or incomplete dividend
coverage into a backtest, valuation, signal, or order.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from collect_historical_prices import parse_bars

PRICES = ROOT / "runtime/historical-prices/20260908T061418761988Z"
SUSPENSIONS = PRICES / "reviewed-suspensions.json"
DISTRIBUTIONS = ROOT / "docs/reviewed-cash-distributions.json"
SUSPENSIONS_SHA256 = "eeaddc1c449981cd0c601d7b9cec4959e0fb785507242912ee4b283fb9ecac9c"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_bars() -> tuple[list[dict], list[dict]]:
    manifest = json.loads((PRICES / "manifest.json").read_text(encoding="utf-8"))
    entries = sorted((row for row in manifest["requests"] if row["symbol"] == "sh601088"),
                     key=lambda row: row["year"])
    if [row["year"] for row in entries] != list(range(2015, 2026)):
        raise ValueError("Unexpected China Shenhua archived-year coverage")
    bars: list[dict] = []
    references: list[dict] = []
    for entry in entries:
        raw_path = PRICES / entry["raw_file"]
        if digest(raw_path) != entry["sha256"]:
            raise ValueError(f"Price evidence hash mismatch: {entry['year']}")
        bars.extend(parse_bars(raw_path.read_bytes(), "sh601088", entry["year"]))
        references.append({"year": entry["year"], "url": entry["url"],
                           "sha256": entry["sha256"],
                           "raw_file": str(raw_path.relative_to(ROOT))})
    dates = [row["date"] for row in bars]
    if dates != sorted(set(dates)):
        raise ValueError("China Shenhua archived bars are duplicate or unordered")
    return bars, references


def load_suspensions() -> list[dict]:
    if digest(SUSPENSIONS) != SUSPENSIONS_SHA256:
        raise ValueError("Reviewed suspension evidence changed")
    source = json.loads(SUSPENSIONS.read_text(encoding="utf-8"))
    events = [row for row in source["intervals"] if row["symbol"] == "sh601088"]
    if len(events) != 2:
        raise ValueError("Expected two China Shenhua reviewed suspension intervals")
    for event in events:
        if event["review_status"] != "official_notice_dates_read" or len(event["evidence"]) < 2:
            raise ValueError("Suspension interval lacks reviewed official notice evidence")
    return events


def dividend_scope() -> dict:
    source = json.loads(DISTRIBUTIONS.read_text(encoding="utf-8"))
    events = [row for row in source["events"] if row["symbol"] == "601088"]
    return {
        "source_path": str(DISTRIBUTIONS.relative_to(ROOT)),
        "source_sha256": digest(DISTRIBUTIONS),
        "event_count": len(events),
        "backtest_ready": False,
        "treatment": "not_applied_to_returns",
        "reason": "The reviewed distribution archive explicitly declares incomplete historical coverage and unverified tax treatment.",
    }


def build_contract() -> dict:
    bars, price_references = load_bars()
    events = load_suspensions()
    dates = {row["date"] for row in bars}
    sessions = []
    for bar in bars:
        day = bar["date"]
        prohibited = [event for event in events
                      if event["suspended_from_inclusive"] <= day < event["resumes_at_open"]]
        if prohibited:
            raise ValueError(f"Daily bar conflicts with official suspension: {day}")
        sessions.append({"date": day, "open": bar["open"], "close": bar["close"],
                         "execution_status": "daily_bar_present_execution_rules_incomplete",
                         "execution_limitation": "No intraday liquidity, price-limit, or order-book proof."})
    for event in events:
        if event["resumes_at_open"] not in dates:
            raise ValueError("Resumption-date daily bar missing")
    return {
        "symbol": "601088",
        "contract_version": "shenhua-real-execution-input-v1",
        "input_scope": "authenticated_archived_daily_OHLC_and_reviewed_suspension_constraints",
        "sessions": sessions,
        "full_day_suspensions": events,
        "suspension_source": {"path": str(SUSPENSIONS.relative_to(ROOT)), "sha256": SUSPENSIONS_SHA256},
        "cash_distribution_scope": dividend_scope(),
        "price_references": price_references,
        "decisions": {},
        "formal_fair_value": None,
        "valuation_approved": False,
        "trade_approved": False,
        "interpretation": "This permits later chronological execution-mechanics research only. Resumption dates are retrospective constraints, not strategy-known facts before their notices. It establishes neither a complete exchange calendar, returns, a value signal, nor an order.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output_dir or ROOT / "runtime/strategy-validation" / f"shenhua-real-execution-contract-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    contract = build_contract()
    input_path = output / "input.json"
    input_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {key: contract[key] for key in ("symbol", "contract_version", "input_scope", "formal_fair_value", "valuation_approved", "trade_approved", "interpretation")}
    summary.update({"sessions": len(contract["sessions"]), "full_day_suspensions": len(contract["full_day_suspensions"]),
                    "cash_distributions_applied": False, "input_sha256": digest(input_path)})
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({"script_sha256": digest(Path(__file__)), "outputs": {path.name: digest(path) for path in output.iterdir()}}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), **summary}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
