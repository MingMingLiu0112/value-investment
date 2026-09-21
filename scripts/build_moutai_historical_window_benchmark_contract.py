#!/usr/bin/env python3
"""Bind official gross-TRI coverage for the registered 600519 history window.

The current archive proves that the selected dates have levels. It does not
prove that a later API response preserves the version available at each 2015
decision date, so this contract deliberately does not accept a benchmark for
historical strategy approval.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRATION = ROOT / "runtime/strategy-validation/moutai-historical-window-registration-20260918T121703Z/evidence.json"
DAILY_INPUTS = ROOT / "runtime/strategy-validation/moutai-daily-research-inputs-20260909T161900156334Z/daily-inputs.json"
SOURCE_DIR = ROOT / "runtime/strategy-validation/official-benchmark-probe-20260909T162408904845Z"
PINS = {
    "H00300": ("沪深300全收益指数", "CSI 300 Total Return Index", "c8d2aef30a3a421737e8c643f934ba29612626215d7d9d9c73ecb7e78875ef63"),
    "H00932": ("中证主要消费全收益指数", "CSI Consumer Staples Total Return Index", "37c69bbbf9401be987b280dbb21f6ca90ff51d4e9205844c70d245b8b0f831aa"),
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build() -> dict:
    registration = json.loads(REGISTRATION.read_text(encoding="utf-8"))
    daily_inputs = json.loads(DAILY_INPUTS.read_text(encoding="utf-8"))
    window = registration["window"]
    dates = [row["date"] for row in daily_inputs if window["start"] <= row["date"] <= window["end"]]
    if len(dates) != window["sessions"] or dates != sorted(set(dates)):
        raise ValueError("Registered window dates are incomplete or duplicated")
    series = {}
    for code, (name_cn, name_en, expected_hash) in PINS.items():
        path = SOURCE_DIR / f"{code}.response"
        if digest(path) != expected_hash:
            raise ValueError(f"Pinned benchmark response changed: {code}")
        rows = json.loads(path.read_text(encoding="utf-8"))["data"]
        selected = [row for row in rows if f"{row['tradeDate'][:4]}-{row['tradeDate'][4:6]}-{row['tradeDate'][6:]}" in dates]
        if len(selected) != len(dates):
            raise ValueError(f"Benchmark coverage mismatch: {code}")
        values = {}
        for row in selected:
            day = f"{row['tradeDate'][:4]}-{row['tradeDate'][4:6]}-{row['tradeDate'][6:]}"
            if day in values or row["indexCode"] != code or row["indexNameCnAll"] != name_cn or row["indexNameEnAll"] != name_en:
                raise ValueError(f"Benchmark identity or date duplication failed: {code}")
            level = Decimal(str(row["close"]))
            if not level.is_finite() or level <= 0:
                raise ValueError(f"Invalid benchmark level: {code} {day}")
            values[day] = str(level)
        if list(values) != dates:
            raise ValueError(f"Benchmark date order mismatch: {code}")
        series[code] = {
            "official_name_cn": name_cn,
            "official_name_en": name_en,
            "levels": values,
            "source_response": str(path.relative_to(ROOT)),
            "source_sha256": expected_hash,
        }
    return {
        "symbol": "600519",
        "contract_version": "moutai-historical-window-benchmark-v1",
        "window": window,
        "dates": dates,
        "series": series,
        "coverage_verified": True,
        "historical_version_verified": False,
        "same_period_benchmark_accepted": False,
        "strategy_backtest_complete": False,
        "trade_approved": False,
        "limitations": [
            "The archived official responses were fetched in 2026; they establish returned historical levels, not the revision/version that was available at each 2015 decision time.",
            "Both series are gross total-return indices. A paper account with cash dividends, trading fees and tax is not automatically comparable without an explicitly aligned return convention.",
            "This contract supplies no company valuation, decision, order, fill or performance conclusion.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    result = build()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output_dir or ROOT / "runtime/strategy-validation" / f"moutai-historical-window-benchmark-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    evidence = output / "evidence.json"
    evidence.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({"script_sha256": digest(Path(__file__)), "evidence_sha256": digest(evidence)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "coverage_verified": result["coverage_verified"],
                      "accepted": result["same_period_benchmark_accepted"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
