#!/usr/bin/env python3
"""Build a point-in-time Moutai historical-PE cross-check, not fair value."""
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
MIN_PRIOR_SESSIONS = 252
QUANTILES = (("low", Decimal("0.20")), ("mid", Decimal("0.50")), ("high", Decimal("0.80")))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def percentile(values: list[Decimal], probability: Decimal) -> Decimal:
    """Type-7 linear percentile; caller supplies a nonempty ordered sample."""
    if not values or not (Decimal(0) <= probability <= Decimal(1)):
        raise ValueError("Invalid percentile input")
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def build(rows: list[dict]) -> list[dict]:
    result: list[dict] = []
    prior_multiples: list[Decimal] = []
    for row in rows:
        price = Decimal(row["close"])
        eps = Decimal(row["annual_profit_per_bonus_adjusted_share"])
        if price <= 0 or eps <= 0:
            raise ValueError("Nonpositive historical price or annual per-share profit")
        if row["decision_at"] < row["annual_available_at"]:
            raise ValueError("Future annual EPS leaked into PE cross-check")
        observed_multiple = price / eps
        base = {"date": row["date"], "decision_at": row["decision_at"],
                "annual_source_id": row["annual_source_id"], "report_period": row["report_period"],
                "annual_available_at": row["annual_available_at"], "price_close_cny": str(price),
                "annual_profit_per_bonus_adjusted_share_cny": str(eps),
                "observed_historical_pe": str(observed_multiple),
                "prior_session_count": len(prior_multiples), "formal_fair_value": None,
                "valuation_approved": False, "trade_approved": False}
        if len(prior_multiples) < MIN_PRIOR_SESSIONS:
            result.append({**base, "status": "blocked_insufficient_prior_pe_observations", "cases": []})
        else:
            cases = []
            for name, probability in QUANTILES:
                multiple = percentile(prior_multiples, probability)
                cases.append({"scenario": name, "prior_pe_percentile": str(probability),
                              "prior_pe_multiple": str(multiple),
                              "conditional_value_per_share_cny": str(eps * multiple)})
            result.append({**base, "status": "historical_relative_pe_research_only", "cases": cases})
        # Append only after the decision so today's close never informs today's range.
        prior_multiples.append(observed_multiple)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if digest(INPUT) != INPUT_SHA256:
        raise ValueError("Pinned daily Moutai research inputs changed")
    values = build(json.loads(INPUT.read_text(encoding="utf-8")))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output_dir or ROOT / "runtime/strategy-validation" / f"moutai-historical-pe-crosscheck-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    daily = output / "daily-values.json"
    daily.write_text(json.dumps(values, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    eligible = [row for row in values if row["status"] == "historical_relative_pe_research_only"]
    summary = {"symbol": "600519", "rule_version": "moutai-historical-relative-pe-crosscheck-v1",
               "sessions": len(values), "blocked_before_prior_sample": len(values) - len(eligible),
               "relative_pe_research_sessions": len(eligible), "minimum_prior_sessions": MIN_PRIOR_SESSIONS,
               "formal_fair_value": None, "valuation_approved": False, "trade_approved": False,
               "interpretation": "This is a point-in-time relative-valuation cross-check. Each range uses only prior daily observed PE values calculated with then-available annual per-share profit. It is not an intrinsic value, forecast PE, approved order signal, or strategy-performance result.",
               "limitations": ["Daily observations are serially correlated and do not create independent valuation evidence", "Reported annual EPS is not a forward normalised-profit forecast", "Unadjusted price and annual per-share basis require separate corporate-action review before any order-bearing use"]}
    summary_path = output / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({"input_sha256": INPUT_SHA256, "script_sha256": digest(Path(__file__)), "outputs": {"daily-values.json": digest(daily), "summary.json": digest(summary_path)}}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ROOT / "runtime/strategy-validation/moutai-historical-pe-crosscheck-latest.json").write_text(
        json.dumps({"path": str(output.relative_to(ROOT)), "daily_values_sha256": digest(daily),
                    "summary_sha256": digest(summary_path)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), **summary}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
