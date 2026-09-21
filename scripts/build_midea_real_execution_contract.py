#!/usr/bin/env python3
"""Freeze Midea's archived daily bars with disclosed suspension constraints.

This creates a point-in-time execution-input contract, not a valuation, signal,
or trading backtest.  A daily bar is insufficient evidence for an intraday
fill, particularly on the separately disclosed afternoon suspension date.
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

from check_midea_suspensions import EVENTS, PRICES, evidence
from collect_historical_prices import parse_bars


PARTIAL_SESSION = {
    "date": "2016-06-16",
    "start_session": "afternoon_open",
    "resume_date": "2016-06-17",
    "resume_session": "morning_open",
    "announcement_id": "1202372209",
    "sha256": "b062b6285ae31b52ee53b1855ac25766866b06debaaa356e30d450d84208c37b",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_midea_bars() -> tuple[list[dict], list[dict]]:
    manifest = json.loads((PRICES / "manifest.json").read_text(encoding="utf-8"))
    entries = sorted((row for row in manifest["requests"] if row["symbol"] == "sz000333"),
                     key=lambda row: row["year"])
    if [row["year"] for row in entries] != list(range(2015, 2026)):
        raise ValueError("Unexpected Midea archived-year coverage")
    bars: list[dict] = []
    references: list[dict] = []
    for entry in entries:
        raw_path = PRICES / entry["raw_file"]
        if digest(raw_path) != entry["sha256"]:
            raise ValueError(f"Price evidence hash mismatch: {entry['year']}")
        parsed = parse_bars(raw_path.read_bytes(), "sz000333", entry["year"])
        bars.extend(parsed)
        references.append({"year": entry["year"], "url": entry["url"],
                           "sha256": entry["sha256"], "raw_file": str(raw_path.relative_to(ROOT))})
    dates = [row["date"] for row in bars]
    if dates != sorted(set(dates)):
        raise ValueError("Midea archived bars are duplicate or unordered")
    return bars, references


def suspension_constraints() -> tuple[list[dict], dict]:
    full_days = []
    for start, resume, ident, expected_hash in EVENTS:
        path = ROOT / "runtime/historical-filing-index/20260908T161018674043Z/pdfs" / f"000333-{ident}.pdf"
        source = evidence(path, expected_hash, resume, ident)
        full_days.append({"start_date": start, "resume_date": resume,
                          "start_session": "morning_open", "resume_session": "morning_open",
                          "source": source})
    partial_path = ROOT / "runtime/historical-filing-index/20260908T161018674043Z/pdfs/000333-1202372209.pdf"
    partial_source = evidence(partial_path, PARTIAL_SESSION["sha256"], "2016-06-17",
                              PARTIAL_SESSION["announcement_id"])
    return full_days, partial_source


def apply_constraints(bars: list[dict], full_days: list[dict], partial: dict) -> list[dict]:
    sessions = []
    for bar in bars:
        day = bar["date"]
        forbidden = [event for event in full_days if event["start_date"] <= day < event["resume_date"]]
        if forbidden:
            raise ValueError(f"Daily bar conflicts with full-day suspension: {day}")
        status = "daily_bar_present_execution_rules_incomplete"
        limitation = None
        if day == PARTIAL_SESSION["date"]:
            status = "blocked_daily_bar_contains_partial_session_suspension"
            limitation = "Daily OHLC cannot prove whether an order could execute before the afternoon halt."
        sessions.append({"date": day, "open": bar["open"], "close": bar["close"],
                         "execution_status": status, "execution_limitation": limitation})
    if not any(row["date"] == PARTIAL_SESSION["date"] for row in sessions):
        raise ValueError("Partial-session evidence date absent from archived bars")
    return sessions


def build_contract() -> dict:
    bars, price_references = load_midea_bars()
    full_days, partial_source = suspension_constraints()
    sessions = apply_constraints(bars, full_days, partial_source)
    full_day_dates = {row["date"] for row in sessions}
    for event in full_days:
        if any(event["start_date"] <= day < event["resume_date"] for day in full_day_dates):
            raise ValueError("Full-day suspension was not excluded")
        if event["resume_date"] not in full_day_dates:
            raise ValueError("Resumption-date daily bar missing")
    return {
        "symbol": "000333",
        "contract_version": "midea-real-execution-input-v1",
        "input_scope": "authenticated_archived_daily_OHLC_and_reviewed_suspension_constraints",
        "sessions": sessions,
        "full_day_suspensions": full_days,
        "partial_session_suspension": {**PARTIAL_SESSION, "source": partial_source,
                                        "daily_bar_treatment": "blocked_no_daily_bar_fill_permission"},
        "price_references": price_references,
        "decisions": {},
        "formal_fair_value": None,
        "valuation_approved": False,
        "trade_approved": False,
        "interpretation": "This permits later chronological execution-mechanics research only. It does not establish a complete exchange calendar, price-limit/liquidity conditions, intraday order eligibility, a value signal, or an order.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output_dir or ROOT / "runtime/strategy-validation" / f"midea-real-execution-contract-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    contract = build_contract()
    input_path = output / "input.json"
    input_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {key: contract[key] for key in ("symbol", "contract_version", "input_scope", "formal_fair_value", "valuation_approved", "trade_approved", "interpretation")}
    summary.update({"sessions": len(contract["sessions"]), "full_day_suspensions": len(contract["full_day_suspensions"]),
                    "partial_session_days_blocked": sum(row["execution_status"].startswith("blocked") for row in contract["sessions"]),
                    "input_sha256": digest(input_path)})
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({"script_sha256": digest(Path(__file__)), "outputs": {path.name: digest(path) for path in output.iterdir()}}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), **summary}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
