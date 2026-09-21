#!/usr/bin/env python3
"""Replay a bounded, point-in-time per-share distributable-earnings experiment.

This is intentionally separate from the incomplete FCFF bridge.  It uses the
then-available parent-company earnings per reviewed share basis and stops
using an annual snapshot once a later distribution changes its equity bridge.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "runtime/strategy-validation/moutai-daily-research-inputs-20260909T161900156334Z/daily-inputs.json"
INPUT_SHA256 = "2a3e748c43f1f25371da12aed478bfd1f1c96d0fe957609720e53043207e7a9f"
VALUE_BASIS = ROOT / "runtime/strategy-validation/moutai-daily-value-basis-20260909T093122642929Z/daily-basis.csv"
VALUE_BASIS_SHA256 = "8d56646ef9b8ac28e06380e2df1ddc370de1c2c5ac5053eca33830dad9526ff6"
VERSION = "moutai-historical-distributable-earnings-v1"
SCENARIOS = (
    ("bear", Decimal("0.80"), Decimal("0.50"), Decimal("0.12"), Decimal("0.02")),
    ("base", Decimal("0.90"), Decimal("0.65"), Decimal("0.10"), Decimal("0.03")),
    ("bull", Decimal("1.00"), Decimal("0.80"), Decimal("0.08"), Decimal("0.04")),
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def value_per_share(eps: Decimal, earnings_fraction: Decimal, payout: Decimal,
                    required_return: Decimal, growth: Decimal) -> Decimal:
    if eps <= 0 or not (Decimal(0) < earnings_fraction <= 1 and Decimal(0) < payout <= 1):
        raise ValueError("Invalid per-share earnings scenario")
    if not (Decimal(0) <= growth < required_return):
        raise ValueError("Growth must be nonnegative and below required return")
    return eps * earnings_fraction * payout * (Decimal(1) + growth) / (required_return - growth)


def build(rows: list[dict], value_basis: dict[str, dict]) -> list[dict]:
    result = []
    for row in rows:
        if row["decision_at"] < row["annual_available_at"]:
            raise ValueError("Future annual earnings leaked into replay")
        basis = value_basis.get(row["date"])
        if basis is None or basis["source_id"] != row["annual_source_id"]:
            raise ValueError("Daily price and research-source basis mismatch")
        if basis["post_report_bonus_events"] == "1":
            result.append({"date": row["date"], "annual_source_id": row["annual_source_id"],
                           "status": "blocked_post_report_bonus_share_basis_missing",
                           "conditional_value_low_cny": None, "conditional_value_high_cny": None})
            continue
        eps = Decimal(row["annual_profit_per_bonus_adjusted_share"])
        cases = []
        for name, fraction, payout, required_return, growth in SCENARIOS:
            cases.append({"scenario": name, "earnings_fraction": str(fraction), "payout_ratio": str(payout),
                          "required_return": str(required_return), "terminal_growth": str(growth),
                          "conditional_value_per_share_cny": str(value_per_share(eps, fraction, payout, required_return, growth))})
        values = [Decimal(case["conditional_value_per_share_cny"]) for case in cases]
        result.append({"date": row["date"], "annual_source_id": row["annual_source_id"],
                       "report_period": row["report_period"], "available_at": row["annual_available_at"],
                       "price_close_cny": row["close"], "parent_profit_per_reviewed_share_cny": str(eps),
                       "cash_distributions_since_report": row["distributions_since_report"],
                       "cases": cases, "conditional_value_low_cny": str(min(values)),
                       "conditional_value_high_cny": str(max(values)), "status": "conditional_research_only"})
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if digest(INPUT) != INPUT_SHA256:
        raise ValueError("Pinned daily research input changed")
    if digest(VALUE_BASIS) != VALUE_BASIS_SHA256:
        raise ValueError("Pinned daily value basis changed")
    import csv
    with VALUE_BASIS.open(encoding="utf-8", newline="") as stream:
        value_basis = {row["date"]: row for row in csv.DictReader(stream)}
    rows = build(json.loads(INPUT.read_text(encoding="utf-8")), value_basis)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output_dir or ROOT / "runtime/strategy-validation" / f"moutai-historical-distributable-earnings-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    evidence = output / "daily-values.json"
    evidence.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {"symbol": "600519", "rule_version": VERSION, "sessions": len(rows),
               "sessions_with_conditional_range": sum(row["status"] == "conditional_research_only" for row in rows),
               "sessions_blocked_after_bonus_share_event": sum(row["status"] != "conditional_research_only" for row in rows),
               "formal_fair_value": None, "valuation_approved": False, "trade_approved": False,
               "strategy_backtest_complete": False,
               "interpretation": "A point-in-time distributable-earnings range uses explicit payout, return and growth experiments. Cash distributions are retained for the separate account ledger; only post-report bonus-share events block the per-share comparison. It does not prove those assumptions, supply a complete equity bridge, or approve a historical or current trade."}
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({"input_sha256": INPUT_SHA256, "value_basis_sha256": VALUE_BASIS_SHA256, "script_sha256": digest(Path(__file__)), "outputs": {"daily-values.json": digest(evidence), "summary.json": digest(output / "summary.json")}}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ROOT / "runtime/strategy-validation/moutai-historical-distributable-earnings-latest.json").write_text(
        json.dumps({"path": str(output.relative_to(ROOT)), "summary_sha256": digest(output / "summary.json"),
                    "daily_values_sha256": digest(evidence)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), **summary}, ensure_ascii=False))


if __name__ == "__main__":
    raise SystemExit(main())
