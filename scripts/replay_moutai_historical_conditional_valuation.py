#!/usr/bin/env python3
"""Replay a frozen, experimental historical DCF range for 600519.

This is a research experiment, not an approved fair-value model or a trading
backtest.  It uses only annual inputs whose ``available_at`` precedes each
session, keeps unresolved denominator cases blocked, and never emits an order.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "runtime/strategy-validation/moutai-daily-research-inputs-20260909T161900156334Z/daily-inputs.json"
INPUT_HASH = "2a3e748c43f1f25371da12aed478bfd1f1c96d0fe957609720e53043207e7a9f"
VERSION = "moutai-historical-conditional-dcf-v2-shared-cost-only"
TAX_RATES = (Decimal("0.15"), Decimal("0.25"))
WACCS = (Decimal("0.08"), Decimal("0.10"), Decimal("0.12"))
TERMINAL_GROWTHS = (Decimal("0.02"), Decimal("0.03"), Decimal("0.04"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def decimal(value: object) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def read_cases() -> list[dict]:
    pointer = json.loads((ROOT / "runtime/strategy-validation/moutai-historical-conditional-inputs-latest.json").read_text(encoding="utf-8"))
    evidence = ROOT / pointer["path"] / "evidence.json"
    if digest(evidence) != pointer["sha256"]:
        raise ValueError("Pinned conditional-input evidence changed")
    package = json.loads(evidence.read_text(encoding="utf-8"))
    if package["trade_approved"] or package["formal_fair_value"] is not None:
        raise ValueError("Research-only input package unexpectedly approved")
    return package["input_cases"]


def conditional_values(case: dict, previous: dict | None) -> tuple[list[dict], list[str]]:
    """Return finite experimental values; first annual case lacks delta-NWC."""
    if previous is None:
        return [], ["prior_annual_operating_nwc_not_available"]
    results = []
    current_fact = case["facts"]
    prior_fact = previous["facts"]
    direct_profit = decimal(current_fact.get("direct_revenue_less_cost_cny"))
    shared_cost = decimal(current_fact.get("shared_cost_proxy_cny"))
    capex_less_da = decimal(current_fact["cash_capex_less_da_cny"])
    if direct_profit is None or shared_cost is None or capex_less_da is None:
        return [], ["required_shared_cost_proxy_missing"]
    prior_nwc = {f"{row['prepayments']}|{row['unclassified_payables']}": decimal(row["conditional_operating_nwc_cny"])
                 for row in previous["sensitivity_dimensions"]["operating_nwc"]}
    for nwc in case["sensitivity_dimensions"]["operating_nwc"]:
        key = f"{nwc['prepayments']}|{nwc['unclassified_payables']}"
        if key not in prior_nwc:
            continue
        delta_nwc = decimal(nwc["conditional_operating_nwc_cny"]) - prior_nwc[key]
        for cost in case["sensitivity_dimensions"]["shared_cost"]:
            industrial_share = Decimal(cost["industrial_share"])
            # The unresolved allocation applies to residual shared costs only;
            # multiplying the entire operating subtotal would also scale direct
            # product profit and was economically incoherent.
            ebit_proxy = direct_profit - shared_cost * industrial_share
            for tax_rate in TAX_RATES:
                fcff_proxy = ebit_proxy * (Decimal("1") - tax_rate) - capex_less_da - delta_nwc
                for wacc in WACCS:
                    for growth in TERMINAL_GROWTHS:
                        if wacc <= growth:
                            continue
                        enterprise_value = fcff_proxy * (Decimal("1") + growth) / (wacc - growth)
                        for denominator in case["sensitivity_dimensions"]["share_denominator"]:
                            if denominator["shares"] is None:
                                results.append({"nwc": key, "industrial_share": str(industrial_share), "tax_rate": str(tax_rate),
                                                "wacc": str(wacc), "terminal_growth": str(growth), "direct_profit_cny": str(direct_profit),
                                                "shared_cost_proxy_cny": str(shared_cost), "fcff_proxy_cny": str(fcff_proxy),
                                                "per_share_value_cny": None, "status": denominator["status"]})
                            else:
                                per_share = enterprise_value / Decimal(denominator["shares"])
                                results.append({"nwc": key, "industrial_share": str(industrial_share), "tax_rate": str(tax_rate),
                                                "wacc": str(wacc), "terminal_growth": str(growth), "direct_profit_cny": str(direct_profit),
                                                "shared_cost_proxy_cny": str(shared_cost), "fcff_proxy_cny": str(fcff_proxy),
                                                "per_share_value_cny": str(per_share.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)),
                                                "status": "experimental_source_backed_issued_share_denominator"})
    return results, []


def replay(rows: list[dict], cases: list[dict]) -> list[dict]:
    by_source = {case["source"]["source_id"]: case for case in cases}
    ordered = sorted(cases, key=lambda row: row["available_at"])
    experiments = {}
    for index, case in enumerate(ordered):
        experiments[case["source"]["source_id"]] = conditional_values(case, ordered[index - 1] if index else None)
    output = []
    for row in rows:
        case = by_source.get(row["annual_source_id"])
        if case is None or case["available_at"] > row["decision_at"]:
            raise ValueError("Future or missing annual input used in experimental replay")
        values, blockers = experiments[row["annual_source_id"]]
        approved = [Decimal(value["per_share_value_cny"]) for value in values if value["per_share_value_cny"] is not None]
        output.append({"date": row["date"], "decision_at": row["decision_at"], "annual_source_id": row["annual_source_id"],
                       "input_available_at": case["available_at"], "experimental_case_count": len(approved),
                       "experimental_value_low_cny": str(min(approved)) if approved else None,
                       "experimental_value_high_cny": str(max(approved)) if approved else None,
                       "formal_fair_value": None, "valuation_approved": False, "trade_approved": False,
                       "blockers": list(dict.fromkeys(case["blockers"] + blockers + ["experimental_historical_value_not_formal_or_tradeable"]))})
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if digest(INPUT) != INPUT_HASH:
        raise ValueError("Pinned daily inputs changed")
    rows = json.loads(INPUT.read_text(encoding="utf-8"))
    replay_rows = replay(rows, read_cases())
    if any(row["trade_approved"] or row["formal_fair_value"] is not None for row in replay_rows):
        raise ValueError("Experimental replay must never create approved values or trades")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output_dir or ROOT / "runtime/strategy-validation" / f"moutai-historical-conditional-replay-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    evidence = output / "daily-experimental-valuation.json"
    evidence.write_text(json.dumps(replay_rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {"symbol": "600519", "rule_version": VERSION, "sessions": len(replay_rows),
               "sessions_with_experimental_range": sum(row["experimental_case_count"] > 0 for row in replay_rows),
               "formal_fair_value": None, "valuation_approved": False, "trade_approved": False,
               "strategy_backtest_complete": False,
               "interpretation": "A finite, point-in-time research DCF range is replayed. It is deliberately excluded from formal value, trade admission and strategy performance."}
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {"input": str(INPUT.relative_to(ROOT)), "input_sha256": INPUT_HASH, "script_sha256": digest(Path(__file__)),
                "outputs": {path.name: digest(path) for path in output.iterdir() if path.is_file()}}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (ROOT / "runtime/strategy-validation/moutai-historical-conditional-replay-latest.json").write_text(
        json.dumps({"path": str(output.relative_to(ROOT)), "sha256": digest(output / "summary.json")}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), **summary}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
