#!/usr/bin/env python3
"""Compare residual-income scenario mechanics with verified historical book growth."""
from __future__ import annotations

import hashlib
import argparse
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from value_moutai_consolidated_parent_equity import build_current, current_value

CURRENT_POINTER = ROOT / "runtime/company-research/600519-consolidated-parent-equity-residual-income-current-latest.json"
FACTS = ROOT / "runtime/company-research/600519-consolidated-parent-equity-inputs-20260914T104011Z/evidence.json"
FACTS_SHA256 = "3ba2b4caa8584100fc41c2ec76ad04794a49dde215cc334abe5a879275dba728"
MODEL = ROOT / "runtime/company-research/600519-consolidated-parent-equity-residual-income-20260914T104426Z/evidence.json"
MODEL_SHA256 = "284eb3bc348bd6c931e043fed1f06304449d32decdb114761b2a6c6dab358d26"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path, expected: str) -> dict:
    if digest(path) != expected:
        raise ValueError(f"Pinned input changed: {path.name}")
    return json.loads(path.read_text(encoding="utf-8"))


def cagr(start: Decimal, end: Decimal, years: int) -> Decimal:
    if min(start, end) <= 0 or years <= 0:
        raise ValueError("Invalid CAGR inputs")
    with localcontext() as context:
        context.prec = 42
        return (end / start) ** (Decimal("1") / years) - Decimal("1")


def build() -> dict[str, object]:
    facts = load(FACTS, FACTS_SHA256)
    model = load(MODEL, MODEL_SHA256)
    chain = facts.get("chain") or []
    scenarios = model.get("results") or []
    if (len(chain) != 12 or len(scenarios) != 3
            or model.get("inputs", {}).get("facts") != {"path": str(FACTS.relative_to(ROOT)), "sha256": FACTS_SHA256}):
        raise ValueError("Unexpected review coverage")
    bvps = [Decimal(row["ending_book_value_per_issued_share_cny"]) for row in chain]
    historical = {
        "2014_to_2025_book_value_per_share_cagr": str(cagr(bvps[0], bvps[-1], 11)),
        "2020_to_2025_book_value_per_share_cagr": str(cagr(bvps[6], bvps[-1], 5)),
        "2024_to_2025_book_value_per_share_growth": str(bvps[-1] / bvps[-2] - Decimal("1")),
    }
    scenario_review = []
    for scenario in scenarios:
        annuals = scenario["forecast_years"]
        implied_growth = [
            Decimal(year["closing_book_equity_cny"]) / Decimal(year["opening_book_equity_cny"]) - Decimal("1")
            for year in annuals
        ]
        if any(Decimal(year["retention_assumption"]) != Decimal("0.30") for year in annuals):
            raise ValueError("Explicit-period retention changed")
        if any(value <= 0 for value in implied_growth):
            raise ValueError("Scenario predicts nonpositive book growth")
        scenario_review.append({
            "scenario": scenario["scenario"],
            "explicit_book_growth_range": [str(min(implied_growth)), str(max(implied_growth))],
            "terminal_growth": scenario["terminal_growth"],
            "terminal_roe": scenario["terminal_roe"],
            "terminal_roe_below_all_observed_ending_equity_profit_ratios": Decimal(scenario["terminal_roe"]) < min(
                Decimal(row["ending_equity_profit_ratio"]) for row in chain
            ),
        })
    return {
        "symbol": "600519",
        "review_version": "moutai-consolidated-parent-equity-assumption-review-v2",
        "inputs": {
            "facts": {"path": str(FACTS.relative_to(ROOT)), "sha256": FACTS_SHA256},
            "model": {"path": str(MODEL.relative_to(ROOT)), "sha256": MODEL_SHA256},
        },
        "historical_book_growth": historical,
        "scenario_review": scenario_review,
        "findings": [
            "All five explicit-year book-growth rates are positive and can be compared with verified book-value-per-share history.",
            "Terminal ROE is below the full observed ending-equity/profit-ratio range in every scenario, so the model does not assume permanent historical premium ROE.",
            "Historical alignment is a plausibility screen only. It does not validate forecast profit, payout, retention, terminal growth, or the cost-of-equity proxy.",
        ],
        "conclusion": "historical_anchor_consistent_but_forecast_assumptions_not_independently_validated",
        "valuation_approved": False,
        "simulation_eligible": False,
        "trade_approved": False,
    }


def bounded_implied_growth(target: Decimal, value_at, lower: Decimal, upper: Decimal) -> dict:
    """Invert a registered interval without extending it to manufacture a fit."""
    if (not all(x.is_finite() for x in (target, lower, upper))
            or target <= 0 or lower <= -1 or lower >= upper):
        raise ValueError("Invalid inverse-valuation bounds")
    lo_value, hi_value = value_at(lower), value_at(upper)
    if (not lo_value.is_finite() or not hi_value.is_finite()
            or not 0 < lo_value < hi_value):
        raise ValueError("Inverse valuation requires positive increasing endpoint values")
    result = {"growth_bounds": [str(lower), str(upper)],
              "value_bounds_cny": [str(lo_value), str(hi_value)],
              "target_price_cny": str(target), "implied_growth": None}
    if not lo_value <= target <= hi_value:
        return {**result, "status": "above_registered_envelope" if target > hi_value else "below_registered_envelope"}
    for _ in range(80):
        middle = (lower + upper) / 2
        value = value_at(middle)
        if not value.is_finite() or not lo_value <= value <= hi_value:
            raise ValueError("Non-monotonic inverse-valuation path")
        if abs(value - target) <= Decimal("0.000001"):
            return {**result, "status": "conditional_solution", "implied_growth": str(middle),
                    "repriced_value_cny": str(value)}
        if value < target:
            lower, lo_value = middle, value
        else:
            upper, hi_value = middle, value
    raise ValueError("Inverse valuation did not converge")


def review_current(quote_report: Path, model_evidence: Path | None = None) -> dict:
    """Reproduce one pinned model against a verified close from its own session."""
    if model_evidence is None:
        reference = json.loads(CURRENT_POINTER.read_text(encoding="utf-8"))
        model_path = (ROOT / reference["path"] / "evidence.json").resolve()
        expected_sha256 = reference["sha256"]
    else:
        model_path = model_evidence.resolve()
        expected_sha256 = digest(model_path)
    quote_report = quote_report.resolve()
    if not model_path.is_relative_to(ROOT) or not quote_report.is_relative_to(ROOT):
        raise ValueError("Review inputs must remain under the project root")
    model = load(model_path, expected_sha256)
    policy_path = (ROOT / model["policy"]["path"]).resolve()
    if digest(policy_path) != model["policy"]["sha256"]:
        raise ValueError("Current model policy changed")
    at = datetime.fromisoformat(model["valuation_at"])
    # Recompute at the archived as-of, never relabel old event coverage as today.
    recomputed = build_current(policy_path, at)
    if recomputed != model:
        raise ValueError("Current model does not reproduce from its pinned dependencies")
    report = json.loads(quote_report.read_text(encoding="utf-8"))
    quotes = [row for row in report.get("observations", []) if row.get("symbol") == "600519"]
    if len(quotes) != 1 or quotes[0].get("result", {}).get("passed") is not True:
        raise ValueError("Review needs one verified quote")
    times = quotes[0]["result"].get("provider_times", {})
    if set(times) != {"sina", "tencent"}:
        raise ValueError("Review needs both quote-provider timestamps")
    for value in times.values():
        instant = datetime.fromisoformat(value)
        if (instant.tzinfo is None or instant > at
                or instant.astimezone(at.tzinfo).date() != at.date()):
            raise ValueError("Quote and current model must share the reviewed session")
    price = Decimal(str(quotes[0]["observed_price"]))
    if not price.is_finite() or price <= 0:
        raise ValueError("Invalid reviewed quote")
    policy, basis = model["model_policy"], model["facts"]
    cases = model["results"]
    base = next(row for row in cases if row["scenario"] == "base")
    growths = [Decimal(row["income_growth"]) for row in policy["scenarios"].values()]
    paths = []
    for case in cases:
        years = case["basis_origin_calculation"]["forecast_years"]
        explicit_end = years[policy["forecast_years"] - 1]
        paths.append({"scenario": case["scenario"],
                      "value_cny": case["conditional_value_per_current_disclosed_share_cny"],
                      "profit_at_explicit_end_cny": explicit_end["net_income_assumption_cny"],
                      "profit_at_fade_end_cny": years[-1]["net_income_assumption_cny"],
                      "fade_profit_change": str(Decimal(years[-1]["net_income_assumption_cny"])
                                                 / Decimal(explicit_end["net_income_assumption_cny"]) - 1),
                      "terminal_dividend_value_share": case["terminal_dividend_value_share"]})
    inverse = []
    for fade in sorted(set([policy["fade_years"], *policy["sensitivity"]["fade_years"]])):
        def value_at(growth):
            return Decimal(current_value(
                Decimal(basis["parent_equity_cny"]), Decimal(basis["issued_shares"]),
                Decimal(model["profit_anchor_cny"]), Decimal(base["cost_of_equity_cny_nominal"]),
                growth, Decimal(policy["payout_ratio"]), policy["forecast_years"], fade,
                Decimal(policy["terminal_growth"]), datetime.fromisoformat(policy["basis_at"]), at,
            )["conditional_value_per_current_disclosed_share_cny"])
        inverse.append({"fade_years": fade, **bounded_implied_growth(price, value_at, min(growths), max(growths))})
    return {"symbol": "600519", "review_version": "moutai-current-assumption-diagnostic-v1",
            "reviewed_as_of": at.isoformat(), "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": {"model": {"path": str(model_path.relative_to(ROOT)), "sha256": digest(model_path)},
                       "quote": {"path": str(quote_report.relative_to(ROOT)), "sha256": digest(quote_report)}},
            "quote_price_cny": str(price), "provider_trade_times": times,
            "arithmetic_reproduced": True, "profit_paths": paths, "reverse_valuation": inverse,
            "conclusion": "strong_fade_stress_scope_only_not_neutral_primary",
            "next_model_decision": "Review economically supported franchise-duration and terminal-profit assumptions; do not fit the independent model to the quote.",
            "interpretation": "A bounded inverse calculation on the archived session, not an identified market forecast. No solution means outside this conditional envelope, not proof of overvaluation. Reproduction validates arithmetic, not economic forecasts.",
            "valuation_approved": False, "simulation_eligible": False, "trade_approved": False}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--current-quote-report", type=Path)
    parser.add_argument("--model-evidence", type=Path)
    args = parser.parse_args()
    if args.model_evidence and not args.current_quote_report:
        parser.error("--model-evidence requires --current-quote-report")
    payload = (review_current(args.current_quote_report, args.model_evidence)
               if args.current_quote_report else build())
    prefix = "600519-current-assumption-diagnostic-" if args.current_quote_report else "600519-consolidated-parent-equity-assumption-review-"
    output = ROOT / "runtime/company-research" / (
        prefix + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    )
    output.mkdir(parents=True, exist_ok=False)
    evidence = output / "evidence.json"
    evidence.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({
        "inputs": payload["inputs"],
        "script_sha256": digest(Path(__file__)),
        "outputs": {"evidence.json": digest(evidence)},
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "conclusion": payload["conclusion"], "trade_approved": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
