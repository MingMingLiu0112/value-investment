#!/usr/bin/env python3
"""Measure signal coverage across every displayed research-only DCF range end.

This is deliberately a coverage audit, not a performance test.  Reporting the
lower, midpoint and upper range endpoints together prevents an optimistic
endpoint from being silently selected as a historical trade rule.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALUATION_POINTER = ROOT / "runtime/strategy-validation/moutai-historical-conditional-replay-latest.json"
INPUTS = ROOT / "runtime/strategy-validation/moutai-daily-research-inputs-20260909T161900156334Z/daily-inputs.json"
MARGINS = (Decimal("0.20"), Decimal("0.30"), Decimal("0.40"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_valuation() -> Path:
    pointer = json.loads(VALUATION_POINTER.read_text(encoding="utf-8"))
    summary = ROOT / pointer["path"] / "summary.json"
    if digest(summary) != pointer["sha256"]:
        raise ValueError("Pinned historical valuation summary changed")
    valuation = summary.parent / "daily-experimental-valuation.json"
    if not valuation.is_file():
        raise ValueError("Pinned historical valuation has no daily output")
    return valuation


def analyze() -> dict:
    valuation_path = load_valuation()
    values = json.loads(valuation_path.read_text(encoding="utf-8"))
    prices = {row["date"]: Decimal(str(row["close"])) for row in json.loads(INPUTS.read_text(encoding="utf-8"))}
    endpoints = ("lower", "midpoint", "upper")
    coverage = {
        endpoint: {str(margin): {"sessions": 0, "first_date": None, "last_date": None} for margin in MARGINS}
        for endpoint in endpoints
    }
    usable = 0
    for row in values:
        low = row["experimental_value_low_cny"]
        high = row["experimental_value_high_cny"]
        if low is None or high is None:
            continue
        price = prices.get(row["date"])
        if price is None or price <= 0:
            raise ValueError("Experimental valuation date lacks a positive historical close")
        usable += 1
        values_by_endpoint = {
            "lower": Decimal(low),
            "midpoint": (Decimal(low) + Decimal(high)) / Decimal("2"),
            "upper": Decimal(high),
        }
        for endpoint, value in values_by_endpoint.items():
            safety_margin = (value - price) / value
            for margin in MARGINS:
                entry = coverage[endpoint][str(margin)]
                if safety_margin >= margin:
                    entry["sessions"] += 1
                    entry["first_date"] = entry["first_date"] or row["date"]
                    entry["last_date"] = row["date"]
    return {
        "symbol": "600519",
        "valuation_input": {"path": str(valuation_path.relative_to(ROOT)), "sha256": digest(valuation_path)},
        "price_input": {"path": str(INPUTS.relative_to(ROOT)), "sha256": digest(INPUTS)},
        "sessions": len(values),
        "sessions_with_experimental_range": usable,
        "range_endpoint_safety_margin_coverage": coverage,
        "interpretation": "Coverage only. The unresolved experimental lower, midpoint and upper endpoints are reported together. Counts are not trade signals, strategy performance, fair values or live eligibility.",
        "trade_approved": False,
    }


def resolve_output(output_dir: Path | None) -> Path:
    """Normalize CLI output paths before recording a project-relative receipt."""
    if output_dir is not None:
        return output_dir.resolve()
    return ROOT / "runtime/strategy-validation" / f"moutai-experimental-signal-coverage-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    output = resolve_output(args.output_dir)
    output.mkdir(parents=True, exist_ok=False)
    result = analyze()
    path = output / "evidence.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({"outputs": {"evidence.json": digest(path)}}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pointer = ROOT / "runtime/strategy-validation/moutai-experimental-signal-coverage-latest.json"
    pointer.write_text(json.dumps({"path": str(output.relative_to(ROOT)), "sha256": digest(path)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "coverage": result["range_endpoint_safety_margin_coverage"], "trade_approved": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
