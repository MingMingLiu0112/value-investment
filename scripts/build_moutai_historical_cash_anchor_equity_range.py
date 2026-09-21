#!/usr/bin/env python3
"""Replay a bounded, cash-distribution-anchored equity research range for 600519.

Implemented annual cash distributions are facts; applying their past ratios to
future earnings is not.  This script keeps that distinction explicit and uses
only a payout observation available on or before each decision date.  It is a
research range, not an approved fair value or a trading input.
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
TIMELINE_POINTER = ROOT / "runtime/strategy-validation/moutai-historical-distribution-timeline-latest.json"
VERSION = "moutai-historical-cash-anchor-equity-range-v1"

# These deliberately retain the project-wide research return/growth grid. They
# are not inferred from Moutai's reported distributions or promoted to a cost
# of equity.  The payout input alone is replaced by point-in-time observations.
SCENARIOS = (("bear", Decimal("0.12"), Decimal("0.02"), "minimum_prior_observed_annual_cycle_cash_ratio"),
             ("base", Decimal("0.10"), Decimal("0.03"), "median_prior_observed_annual_cycle_cash_ratio"),
             ("bull", Decimal("0.08"), Decimal("0.04"), "maximum_prior_observed_annual_cycle_cash_ratio"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def value_per_share(eps: Decimal, payout: Decimal, required_return: Decimal, growth: Decimal) -> Decimal:
    if eps <= 0 or not (Decimal(0) < payout <= 1) or not (Decimal(0) <= growth < required_return):
        raise ValueError("Invalid cash-anchor equity inputs")
    return eps * payout * (Decimal(1) + growth) / (required_return - growth)


def load_timeline() -> tuple[list[dict], list[dict], dict]:
    reference = json.loads(TIMELINE_POINTER.read_text(encoding="utf-8"))
    directory = (ROOT / reference["path"]).resolve()
    if not directory.is_relative_to(ROOT.resolve()):
        raise ValueError("Distribution timeline escapes project root")
    paths = {"observations": directory / "observations.json", "timeline": directory / "daily-timeline.json",
             "summary": directory / "summary.json"}
    for key, path in paths.items():
        expected = reference[f"{key}_sha256"]
        if digest(path) != expected:
            raise ValueError(f"Pinned distribution {key} changed")
    observations = json.loads(paths["observations"].read_text(encoding="utf-8"))
    timeline = json.loads(paths["timeline"].read_text(encoding="utf-8"))
    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    if summary.get("valuation_approved") or summary.get("trade_approved"):
        raise ValueError("Distribution evidence unexpectedly approved")
    return observations, timeline, reference


def percentile(values: list[Decimal], position: Decimal) -> Decimal:
    """Nearest-rank selection keeps the small historical sample reproducible."""
    ordered = sorted(values)
    if not ordered:
        raise ValueError("No prior payout observations")
    index = max(0, min(len(ordered) - 1, int((len(ordered) - 1) * position)))
    return ordered[index]


def build(rows: list[dict], observations: list[dict], timeline: list[dict]) -> list[dict]:
    by_date = {row["date"]: row for row in timeline}
    observation_by_id = {row["event_id"]: row for row in observations}
    result = []
    for row in rows:
        daily = by_date.get(row["date"])
        if daily is None:
            raise ValueError("Daily distribution timeline coverage is incomplete")
        event_id = daily["latest_annual_cycle_distribution_event_id"]
        if not event_id:
            result.append({"date": row["date"], "annual_source_id": row["annual_source_id"],
                           "status": "blocked_no_prior_implemented_annual_cycle_cash_observation",
                           "conditional_value_low_cny": None, "conditional_value_high_cny": None})
            continue
        latest = observation_by_id.get(event_id)
        if latest is None or latest["status"] != "annual_cycle_cash_to_available_annual_eps":
            raise ValueError("Timeline references an unusable cash observation")
        if latest["available_for_research_at"] > row["decision_at"]:
            raise ValueError("Future cash implementation leaked into valuation replay")
        payout_history = [Decimal(item["cash_to_prior_annual_eps_ratio"]) for item in observations
                          if item["status"] == "annual_cycle_cash_to_available_annual_eps"
                          and item["available_for_research_at"] <= row["decision_at"]]
        eps = Decimal(row["annual_profit_per_bonus_adjusted_share"])
        payout_by_rule = {"minimum_prior_observed_annual_cycle_cash_ratio": min(payout_history),
                          "median_prior_observed_annual_cycle_cash_ratio": percentile(payout_history, Decimal("0.5")),
                          "maximum_prior_observed_annual_cycle_cash_ratio": max(payout_history)}
        cases = []
        for name, required_return, growth, payout_rule in SCENARIOS:
            payout = payout_by_rule[payout_rule]
            cases.append({"scenario": name, "payout_rule": payout_rule, "prior_observation_count": len(payout_history),
                          "payout_ratio_assumption": str(payout), "required_return_research_assumption": str(required_return),
                          "terminal_growth_research_assumption": str(growth),
                          "conditional_value_per_share_cny": str(value_per_share(eps, payout, required_return, growth))})
        values = [Decimal(item["conditional_value_per_share_cny"]) for item in cases]
        result.append({"date": row["date"], "decision_at": row["decision_at"], "annual_source_id": row["annual_source_id"],
                       "annual_report_period": row["report_period"], "annual_available_at": row["annual_available_at"],
                       "price_close_cny": row["close"], "parent_profit_per_reviewed_share_cny": str(eps),
                       "latest_cash_observation_event_id": event_id, "cases": cases,
                       "conditional_value_low_cny": str(min(values)), "conditional_value_high_cny": str(max(values)),
                       "status": "cash_distribution_anchored_research_only", "formal_fair_value": None,
                       "valuation_approved": False, "simulation_eligible": False, "trade_approved": False})
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if digest(INPUT) != INPUT_SHA256:
        raise ValueError("Pinned daily research input changed")
    observations, timeline, pointer = load_timeline()
    values = build(json.loads(INPUT.read_text(encoding="utf-8")), observations, timeline)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output_dir or ROOT / "runtime/strategy-validation" / f"moutai-historical-cash-anchor-equity-range-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    values_path = output / "daily-values.json"
    values_path.write_text(json.dumps(values, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {"symbol": "600519", "rule_version": VERSION, "sessions": len(values),
               "sessions_with_cash_anchor_range": sum(row["status"] == "cash_distribution_anchored_research_only" for row in values),
               "blocked_before_first_implemented_annual_cycle_observation": sum(row["status"] != "cash_distribution_anchored_research_only" for row in values),
               "formal_fair_value": None, "valuation_approved": False, "simulation_eligible": False, "trade_approved": False,
               "interpretation": "Historical implemented cash distributions anchor a bounded per-share research range. Past cash-to-EPS ratios, required returns and terminal growth are not forecasts, a formal fair value, an approved trading model, or a live recommendation."}
    summary_path = output / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {"inputs": {str(INPUT.relative_to(ROOT)): INPUT_SHA256, "distribution_timeline": pointer,
                            "script_sha256": digest(Path(__file__))},
                "outputs": {"daily-values.json": digest(values_path), "summary.json": digest(summary_path)}}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ROOT / "runtime/strategy-validation/moutai-historical-cash-anchor-equity-range-latest.json").write_text(
        json.dumps({"path": str(output.relative_to(ROOT)), "summary_sha256": digest(summary_path),
                    "daily_values_sha256": digest(values_path)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), **summary}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
