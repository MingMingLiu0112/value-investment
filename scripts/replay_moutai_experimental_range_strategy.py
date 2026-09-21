#!/usr/bin/env python3
"""Replay every displayed historical research-range endpoint without cherry-picking.

This is an explicitly non-admissible research experiment.  The conditional DCF
range is not a formal fair value, and archived OHLC bars do not prove that a
real order could have been filled.  The script exists to expose the practical
consequence of that uncertainty, not to generate an investment recommendation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from replay_moutai_distributions import digest, load_inputs, write_json
from value_investment_agent.paper_sizing import size_entry_or_add
from value_investment_agent.virtual_account import VirtualAccount, dated_research_fee, replay

INPUT = ROOT / "runtime/strategy-validation/moutai-daily-research-inputs-20260909T161900156334Z/daily-inputs.json"
INPUT_HASH = "2a3e748c43f1f25371da12aed478bfd1f1c96d0fe957609720e53043207e7a9f"
VALUATION_POINTER = ROOT / "runtime/strategy-validation/moutai-historical-conditional-replay-latest.json"
ENDPOINTS = ("lower", "midpoint", "upper")
MARGINS = (Decimal("0.20"), Decimal("0.30"), Decimal("0.40"))
PERIODS = (("development", "2015-01-05", "2019-12-31"),
           ("validation", "2020-01-02", "2022-12-30"),
           ("sealed_test", "2023-01-03", "2025-12-31"))
VERSION = "moutai-historical-range-experiment-v1"


def read_pinned_ranges() -> dict[str, dict[str, Decimal | None]]:
    pointer = json.loads(VALUATION_POINTER.read_text(encoding="utf-8"))
    summary = ROOT / pointer["path"] / "summary.json"
    if digest(summary) != pointer["sha256"]:
        raise ValueError("Pinned conditional valuation summary changed")
    daily = summary.parent / "daily-experimental-valuation.json"
    result: dict[str, dict[str, Decimal | None]] = {}
    for row in json.loads(daily.read_text(encoding="utf-8")):
        low, high = row["experimental_value_low_cny"], row["experimental_value_high_cny"]
        result[row["date"]] = {
            "lower": Decimal(low) if low is not None else None,
            "midpoint": ((Decimal(low) + Decimal(high)) / 2) if low is not None and high is not None else None,
            "upper": Decimal(high) if high is not None else None,
        }
    return result


def cash_events(events: list[dict]) -> list[dict]:
    output = []
    for event in events:
        item = {
            "event_id": f"600519:{event['record_date']}",
            "record_date": event["record_date"], "ex_date": event["ex_date"],
            "payment_date": event["cash_payment_date"], "cash_per_share": event["cash_per_share"],
        }
        if event.get("bonus_shares_per_share") is not None:
            item["bonus_shares_per_share"] = event["bonus_shares_per_share"]
            item["bonus_listing_date"] = event["bonus_listing_date"]
        output.append(item)
    return output


def sessions_from_bars(bars: list[dict]) -> list[dict]:
    output = []
    for bar in bars:
        # The dated research fee component deliberately refuses early-SSE
        # fills.  Later OHLC fills remain a documented daily-bar assumption,
        # never evidence of queue position, liquidity, suspension or limits.
        executable = bar["date"] >= "2015-08-01"
        output.append({
            "date": bar["date"], "open": bar["open"], "close": bar["close"],
            "execution_ready": executable,
            "execution_reason": (
                "archived_daily_bar_research_assumption_no_queue_limit_or_liquidity_proof"
                if executable else "early_sse_fee_contract_not_available"
            ),
        })
    return output


def make_provider(values: dict[str, dict[str, Decimal | None]], endpoint: str, margin: Decimal):
    def provider(session: dict, account: dict) -> dict:
        value = values[session["date"]][endpoint]
        price = Decimal(str(session["close"]))
        shares = account["shares"]
        if value is None:
            return {"state": "watch", "action": "no_order", "reason": "range_unavailable"}
        safety_margin = (value - price) / value
        if shares == 0 and safety_margin >= margin:
            nav = Decimal(account["cash"]) + Decimal(account["receivables"]) + Decimal(shares) * price
            sizing = size_entry_or_add(nav=nav, cash=Decimal(account["cash"]), current_shares=0,
                                       price=price, tranche_index=0)
            if sizing["quantity"]:
                return {
                    "state": "proposed_entry", "action": "research_entry_experiment",
                    "decision_id": f"{endpoint}-{margin}-{session['date']}-entry",
                    "quantity": sizing["quantity"], "value_cny": str(value),
                    "safety_margin": str(safety_margin), "sizing": sizing,
                }
            return {"state": "watch", "action": "no_order", "reason": "board_lot_or_cash", "sizing": sizing}
        if shares and price > value:
            return {
                "state": "proposed_exit", "action": "research_exit_experiment",
                "decision_id": f"{endpoint}-{margin}-{session['date']}-exit",
                "value_cny": str(value), "safety_margin": str(safety_margin),
            }
        return {"state": "paper_hold" if shares else "watch", "action": "no_order",
                "value_cny": str(value), "safety_margin": str(safety_margin)}
    return provider


def summarize(journal: list[dict], account: VirtualAccount) -> dict:
    navs = [Decimal(row["nav_cny"]) for row in journal]
    peak, maximum_drawdown = navs[0], Decimal("0")
    for nav in navs:
        peak = max(peak, nav)
        maximum_drawdown = min(maximum_drawdown, (nav - peak) / peak)
    fills = [row["fill"] for row in journal if row["fill"] is not None]
    rejected = [row for row in journal if row["rejected_order_reason"]]
    return {
        "opening_nav_cny": "1000000.00", "ending_nav_cny": str(account.marked_nav()),
        "gross_research_return": str((account.marked_nav() / Decimal("1000000.00")) - 1),
        "maximum_drawdown": str(maximum_drawdown), "fills": len(fills),
        "rejected_orders": len(rejected), "ending_shares": account.shares,
        "first_fill_date": fills[0]["filled_on"] if fills else None,
        "last_fill_date": fills[-1]["filled_on"] if fills else None,
    }


def summarize_periods(journal: list[dict]) -> list[dict]:
    """Report pre-registered chronological segments without selecting a winner."""
    result = []
    for name, start, end in PERIODS:
        segment = [row for row in journal if start <= row["date"] <= end]
        if not segment:
            raise ValueError(f"Missing registered period {name}")
        first_index = journal.index(segment[0])
        opening = (Decimal("1000000.00") if first_index == 0
                   else Decimal(journal[first_index - 1]["nav_cny"]))
        navs = [opening] + [Decimal(row["nav_cny"]) for row in segment]
        peak, maximum_drawdown = navs[0], Decimal("0")
        for nav in navs:
            peak = max(peak, nav)
            maximum_drawdown = min(maximum_drawdown, (nav - peak) / peak)
        fills = [row["fill"] for row in segment if row["fill"] is not None]
        result.append({
            "period": name, "start": start, "end": end, "sessions": len(segment),
            "opening_nav_cny": str(opening), "ending_nav_cny": str(navs[-1]),
            "gross_research_return": str((navs[-1] / opening) - 1),
            "maximum_drawdown": str(maximum_drawdown), "fills": len(fills),
            "rejected_orders": sum(row["rejected_order_reason"] is not None for row in segment),
        })
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if digest(INPUT) != INPUT_HASH:
        raise ValueError("Pinned daily research inputs changed")
    ranges = read_pinned_ranges()
    bars, events, _annual, references = load_inputs(ROOT)
    if [row["date"] for row in bars] != list(ranges):
        raise ValueError("Range and price calendars differ")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output_dir or ROOT / "runtime/strategy-validation" / f"moutai-historical-range-experiment-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    config = {
        "version": VERSION, "registered_at": datetime.now(timezone.utc).isoformat(),
        "endpoints": list(ENDPOINTS), "safety_margins": [str(value) for value in MARGINS],
        "entry": "range endpoint less stated safety margin at close; earliest next archived session open",
        "exit": "close greater than same endpoint; earliest next archived session open",
        "sizing": "existing research-only P2 first tranche: 50% of an 8% NAV cap",
        "fee": "dated post-2015-08 SSE statutory components plus 0.03% commission assumption",
        "execution": "daily-bar research assumption; no order-book, limit, suspension or liquidity proof",
        "admission": "research experiment only; not formal valuation, strategy validation, simulation admission or live eligibility",
    }
    write_json(output / "config.json", config)
    results = []
    for endpoint in ENDPOINTS:
        for margin in MARGINS:
            account, journal = replay(
                sessions_from_bars(bars), {}, VirtualAccount(), cash_events=cash_events(events),
                fee_calculator=lambda side, quantity, price, day: dated_research_fee(side, quantity, price, day, exchange="SSE"),
                decision_provider=make_provider(ranges, endpoint, margin),
            )
            key = f"{endpoint}-{int(margin * 100)}pct"
            write_json(output / f"{key}-journal.json", journal)
            results.append({"scenario": key, "endpoint": endpoint, "safety_margin": str(margin),
                            **summarize(journal, account), "periods": summarize_periods(journal)})
    result = {
        "symbol": "600519", "run_type": "historical_research_range_sensitivity",
        "window": [bars[0]["date"], bars[-1]["date"]], "sessions": len(bars), "results": results,
        "formal_fair_value": None, "valuation_approved": False, "strategy_backtest_complete": False,
        "simulation_eligible": False, "trade_approved": False, "live_eligible": False,
        "interpretation": "All displayed range endpoints and registered margins are replayed together. Gross research returns are scenario diagnostics only and must not be read as a validated strategy result or investment recommendation.",
        "limitations": [
            "The range is an unresolved experimental DCF, not an approved fair value.",
            "The fee contract rejects early-SSE sessions; OHLC executions after 2015-08 remain research assumptions.",
            "Returns use gross cash distributions without final investor tax treatment or aligned total-return benchmark.",
            "The historical company, benchmark and model inputs do not meet the separate R1/R2 point-in-time admission contract.",
        ],
    }
    write_json(output / "result.json", result)
    write_json(output / "input-references.json", references + [
        {"kind": "daily_research_input", "path": str(INPUT.relative_to(ROOT)), "sha256": INPUT_HASH},
        {"kind": "range_pointer", "path": str(VALUATION_POINTER.relative_to(ROOT)), "sha256": digest(VALUATION_POINTER)},
    ])
    write_json(output / "manifest.json", {"script_sha256": digest(Path(__file__)),
               "outputs": {path.name: digest(path) for path in output.iterdir() if path.is_file()}})
    (ROOT / "runtime/strategy-validation/moutai-historical-range-experiment-latest.json").write_text(
        json.dumps({"path": str(output.relative_to(ROOT)), "sha256": digest(output / "result.json")},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "scenarios": len(results),
                      "fills": {row["scenario"]: row["fills"] for row in results},
                      "strategy_backtest_complete": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
