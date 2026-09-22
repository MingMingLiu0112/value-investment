#!/usr/bin/env python3
"""Run a bounded, non-admitted residual-income scenario calculation for 600519."""
from __future__ import annotations

import hashlib
import json
import argparse
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from value_investment_agent.valuation_models.residual_income import (
    current_projection,
    current_value,
    scenario_value,
)


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "runtime/company-research/600519-consolidated-parent-equity-inputs-20260914T104011Z/evidence.json"
INPUT_SHA256 = "3ba2b4caa8584100fc41c2ec76ad04794a49dde215cc334abe5a879275dba728"
DISCOUNT = ROOT / "runtime/valuation-research/moutai-consolidated-parent-equity-discount-range-20260914T104355Z/evidence.json"
DISCOUNT_SHA256 = "d53f204548a2a97c83c046572b93e331af3963e53773f0b3f8d4962a819dd154"

SCENARIOS = {
    "bear": {
        "discount_case": "upper",
        "forecast_roe": ("0.25", "0.24", "0.23", "0.22", "0.21"),
        "terminal_roe": "0.18",
        "terminal_growth": "0.02",
    },
    "base": {
        "discount_case": "central",
        "forecast_roe": ("0.32", "0.30", "0.28", "0.26", "0.24"),
        "terminal_roe": "0.20",
        "terminal_growth": "0.025",
    },
    "bull": {
        "discount_case": "lower",
        "forecast_roe": ("0.35", "0.34", "0.33", "0.32", "0.30"),
        "terminal_roe": "0.22",
        "terminal_growth": "0.03",
    },
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path, expected: str) -> dict:
    if digest(path) != expected:
        raise ValueError(f"Pinned input changed: {path.name}")
    return json.loads(path.read_text(encoding="utf-8"))


def build() -> dict[str, object]:
    facts = load(INPUT, INPUT_SHA256)
    discount = load(DISCOUNT, DISCOUNT_SHA256)
    chain = facts.get("chain") or []
    if (facts.get("contract_version") != "moutai-consolidated-parent-equity-inputs-v2"
            or len(chain) != 12 or chain[-1].get("period_end") != "2025-12-31"):
        raise ValueError("Unexpected parent-equity fact chain")
    observed_roes = [Decimal(row["ending_equity_profit_ratio"]) for row in chain]
    latest = chain[-1]
    start_book = Decimal(latest["parent_equity_cny"])
    shares = Decimal(latest["ending_issued_shares"])
    if min(start_book, shares) <= 0:
        raise ValueError("Invalid latest parent-equity basis")
    results = []
    for name in ("bear", "base", "bull"):
        config = SCENARIOS[name]
        rate = Decimal(discount["range"][config["discount_case"]])
        result = scenario_value(start_book, shares, rate, config)
        results.append({"scenario": name, **result})
    values = [Decimal(row["conditional_value_per_2025_issued_share_cny"]) for row in results]
    if not values[0] <= values[1] <= values[2]:
        raise ValueError("Scenario ordering is not monotonic")
    return {
        "symbol": "600519",
        "model_version": "moutai-consolidated-parent-equity-residual-income-v2",
        "model_revision": "publication-and-share-provenance-correction-v1",
        "inputs": {"facts": {"path": str(INPUT.relative_to(ROOT)), "sha256": INPUT_SHA256},
                   "discount": {"path": str(DISCOUNT.relative_to(ROOT)), "sha256": DISCOUNT_SHA256}},
        "model_scope": (f"Research on the {latest['period_end']} parent-equity/share basis. "
                        f"The annual report was published on {latest['published_date']}, with conservative "
                        f"date-only availability at {latest['available_at']}, and uses later current-research "
                        "discount assumptions. This mixed-date scenario is neither a disclosure-date nor a current approved valuation."),
        "formula": "Equity value = opening parent equity + PV(explicit residual income) + PV(terminal residual income); residual income = parent profit assumption - cost of equity * opening parent equity.",
        "facts": {
            "opening_parent_equity_cny": str(start_book),
            "issued_shares_2025": str(shares),
            "report_published_date": latest["published_date"],
            "report_available_at": latest["available_at"],
            "report_source_url": latest["source_url"],
            "share_evidence": latest["share_evidence"],
            "latest_observed_ending_equity_profit_ratio": latest["ending_equity_profit_ratio"],
            "observed_2014_2025_ending_equity_profit_ratio_range": [str(min(observed_roes)), str(max(observed_roes))],
        },
        "assumption_design": {
            "roe": "Five explicit annual ROE assumptions begin inside the observed 2014-2025 ending-equity/profit range. Terminal ROE is deliberately below the observed range to represent a non-permanent premium-return fade.",
            "retention": "All five explicit years retain 30 percent of assumed income. The terminal-growth regime begins only after the explicit forecast, so it does not force an unexplained fifth-year book-growth discontinuity. This is an assumption, not a declared payout commitment.",
            "discount_rate": "Bear/base/bull use the upper/central/lower bounded listed-equity cost-of-equity research cases respectively; no single rate is selected as approved WACC.",
            "accounting": "The forecast assumes clean-surplus equity changes from income and dividends only, with fixed shares and no OCI, issuance or repurchases. Historical/current bridges still require evidence; mathematical reconciliation does not validate these assumptions.",
        },
        "arithmetic_crosscheck": "Dividend discounting under identical clean-surplus assumptions independently reconciles the residual-income sum. This checks arithmetic and timing, not forward economic evidence.",
        "results": results,
        "formal_fair_value": None,
        "safety_margin": None,
        "valuation_approved": False,
        "simulation_eligible": False,
        "trade_approved": False,
        "limitations": [
            "Forward ROE, retention, terminal growth and fade are explicit research assumptions, not issuer guidance or validated forecasts.",
            "The output uses the 2025 reporting-date share count and cannot be presented as a current per-share fair value without a separately verified post-balance share/capital-action bridge.",
            "Cost of equity remains a bounded current research range; it is not a historical point-in-time input or a formal selected rate.",
            "This model avoids an industrial/finance carveout but does not establish strategy evidence, executable historical fills, or a simulation admission.",
        ],
    }


def build_current(policy_path: Path, as_of: datetime | None = None) -> dict:
    policy_path = policy_path.resolve()
    if not policy_path.is_relative_to(ROOT):
        raise ValueError("Current policy must be under the project root")
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    if (policy.get("policy_version") != "moutai-current-equity-policy-v1" or policy.get("symbol") != "600519"
            or policy.get("earnings_anchor") != "lower_of_reported_and_issuer_ex_nonrecurring_ttm"
            or policy.get("terminal_roe_policy") != "cost_of_equity_no_permanent_excess_return"
            or Decimal(policy["post_basis_distributions_cny"]) != 0):
        raise ValueError("Unsupported current policy scope or unhandled capital distributions")
    sources = {}
    for name, ref in policy["sources"].items():
        path = (ROOT / ref["path"]).resolve()
        if not path.is_relative_to(ROOT) or digest(path) != ref["sha256"]:
            raise ValueError("Current policy source changed: " + name)
        if path.suffix == ".json":
            sources[name] = json.loads(path.read_text(encoding="utf-8"))
    facts, discount, capital = (sources[name] for name in ("facts", "discount", "capital_review"))
    refresh = sources.get("capital_refresh")
    basis = facts["current_disclosed_basis"]
    as_of = as_of or datetime.now(timezone(timedelta(hours=8)))
    if as_of.tzinfo is None or as_of > datetime.now(timezone.utc):
        raise ValueError("Valuation time must be known and timezone-aware")
    as_of = as_of.astimezone(timezone(timedelta(hours=8)))
    registered_at = datetime.fromisoformat(policy["registered_at"])
    assessment_at = datetime.fromisoformat(basis["assessment_available_at"])
    basis_at = datetime.fromisoformat(policy["basis_at"])
    if (registered_at.tzinfo is None or as_of < max(registered_at, assessment_at)
            or basis_at.date().isoformat() != basis["period_end"]
            or as_of.date().isoformat() != policy["event_coverage_date"]):
        raise ValueError("Policy or event evidence is unavailable/expired at the valuation time")
    if refresh is None:
        if basis["event_query"]["window"].split("~")[-1] != policy["event_coverage_date"]:
            raise ValueError("Base capital-event coverage is expired")
    elif (refresh.get("query_window") != "2026-09-14~" + policy["event_coverage_date"]
          or refresh.get("complete") is not True or refresh.get("new_or_changed_announcements") != 0):
        raise ValueError("Capital refresh does not support the policy date")
    elif datetime.fromisoformat(refresh["fetched_at"]) > as_of:
        raise ValueError("Capital refresh was not available at the valuation time")
    capital_ref = basis["inputs"]["capital_review"]
    if (capital_ref != policy["sources"]["capital_review"] or basis["event_query"]["complete"] is not True
            or basis["event_query"]["new_or_changed_announcements"] != 0
            or basis["raw_file_hash"] != policy["sources"]["interim_pdf"]["sha256"]
            or str(capital["disclosure_supported_ordinary_share_assumption"]) != basis["issued_shares"]
            or capital["distribution"]["deduct_again_from_june_book_equity"] is not False):
        raise ValueError("Current capital basis does not match the reviewed policy sources")
    for ref in [basis["event_query"], *basis["inputs"].values()]:
        path = (ROOT / ref["path"]).resolve()
        if not path.is_relative_to(ROOT) or digest(path) != ref["sha256"]:
            raise ValueError("Current-basis dependency changed")
    book, shares = Decimal(basis["parent_equity_cny"]), Decimal(basis["issued_shares"])
    profit = min(Decimal(basis["ttm_parent_profit_cny"]), Decimal(basis["ttm_ex_nonrecurring_parent_profit_cny"]))
    payout, terminal_growth = Decimal(policy["payout_ratio"]), Decimal(policy["terminal_growth"])
    results = []
    def calculate(case: dict, *, payout_override=None, fade_override=None, extra_cost=Decimal(0)):
        return current_value(book, shares, profit, Decimal(discount["range"][case["discount_case"]]) + extra_cost,
                             Decimal(case["income_growth"]), payout if payout_override is None else payout_override,
                             policy["forecast_years"], policy["fade_years"] if fade_override is None else fade_override,
                             terminal_growth, basis_at, as_of)
    for name in ("bear", "base", "bull"):
        results.append({"scenario": name, **calculate(policy["scenarios"][name])})
    values = [Decimal(row["conditional_value_per_current_disclosed_share_cny"]) for row in results]
    if not values[0] <= values[1] <= values[2]:
        raise ValueError("Current scenarios are not ordered")
    sensitivity = []
    for ratio in policy["sensitivity"]["payout_ratios"]:
        sensitivity.append({"case": "base_payout_" + ratio,
                            **calculate(policy["scenarios"]["base"], payout_override=Decimal(ratio))})
    for years in policy["sensitivity"]["fade_years"]:
        sensitivity.append({"case": "base_fade_" + str(years),
                            **calculate(policy["scenarios"]["base"], fade_override=years)})
    sensitivity.append({"case": "base_higher_equity_cost", **calculate(policy["scenarios"]["base"],
        extra_cost=Decimal(policy["sensitivity"]["extra_cost_of_equity"]))})
    return {
        "symbol": "600519", "model_version": "moutai-current-parent-equity-residual-income-v1",
        "valuation_at": as_of.isoformat(), "information_available_at": max(registered_at, assessment_at).isoformat(),
        "policy": {"path": str(policy_path.relative_to(ROOT)), "sha256": digest(policy_path)},
        "inputs": policy["sources"], "facts": basis,
        "profit_anchor_cny": str(profit), "model_policy": policy,
        "model_scope": "Current-dated forward scenario on the latest disclosed consolidated parent equity and ordinary shares; origin-date book equity is not observed current net assets.",
        "results": results, "sensitivity": sensitivity,
        "extreme_loss_scenario": {"value_per_share_cny": "0", "interpretation": policy["sensitivity"]["no_franchise_tail"]},
        "checks": {"dated_facts_and_capital_inventory": True, "forecast_separate_from_book_compounding": True,
                   "no_permanent_excess_roe": all(Decimal(row["basis_origin_calculation"]["terminal_residual_income_cny"]) == 0 for row in results),
                   "dividend_current_date_reconciliation": all(abs(Decimal(row["current_dividend_crosscheck_difference_cny"])) < Decimal("0.01") for row in results + sensitivity)},
        "review_status": "current_model_and_sensitivity_ready_for_scope_review",
        "formal_fair_value": None, "valuation_approved": False, "simulation_eligible": False, "trade_approved": False,
        "limitations": ["Registered assumptions and exact reconciliation are not future earnings or strategy-effectiveness proof.",
                        "Payout/remittance, growth and fade remain economic assumptions; the full-loss stress is not a probability estimate.",
                        "This current package needs P1 scope review and compatible daily/account/export consumers before simulation admission.",
                        "Event coverage is limited to the stated valuation date; later sessions require event and data-freshness assessment.",
                        "No paid June distribution or repurchase is subtracted again; no daily net assets or future actual dividends are claimed."],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--current-policy", type=Path)
    parser.add_argument("--as-of")
    args = parser.parse_args()
    as_of = datetime.fromisoformat(args.as_of) if args.as_of else None
    payload = build_current(args.current_policy, as_of) if args.current_policy else build()
    package_name = "600519-consolidated-parent-equity-residual-income" + ("-current" if args.current_policy else "")
    output = ROOT / "runtime/company-research" / (
        package_name + "-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    )
    output.mkdir(parents=True, exist_ok=False)
    evidence = output / "evidence.json"
    evidence.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({
        "inputs": ({**{ref["path"]: ref["sha256"] for ref in payload["inputs"].values()},
                    payload["policy"]["path"]: payload["policy"]["sha256"]} if args.current_policy
                   else {str(INPUT.relative_to(ROOT)): INPUT_SHA256, str(DISCOUNT.relative_to(ROOT)): DISCOUNT_SHA256}),
        "script_sha256": digest(Path(__file__)),
        "outputs": {"evidence.json": digest(evidence)},
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pointer = ROOT / "runtime/company-research" / (package_name + "-latest.json")
    pointer.write_text(json.dumps({"path": str(output.relative_to(ROOT)), "sha256": digest(evidence)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    value_key = "conditional_value_per_current_disclosed_share_cny" if args.current_policy else "conditional_value_per_2025_issued_share_cny"
    print(json.dumps({"output": str(output), "values": [row[value_key] for row in payload["results"]], "valuation_approved": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
