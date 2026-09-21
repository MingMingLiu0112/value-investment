#!/usr/bin/env python3
"""Freeze a research-only pre-2015 price-return beta candidate."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MOUTAI_DIR = ROOT / "runtime/historical-prices/20260920T074631172611Z"
BENCHMARK_DIR = ROOT / "runtime/strategy-validation/moutai-2014-sse-composite-candidate-20260920T074939Z"
CROSSCHECK_DIR = ROOT / "runtime/strategy-validation/moutai-2014-sse-composite-crosscheck-20260920T075259Z"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build() -> dict:
    manifest = json.loads((MOUTAI_DIR / "manifest.json").read_text(encoding="utf-8"))
    entry = next(item for item in manifest["requests"] if item["symbol"] == "sh600519" and item["year"] == 2014)
    raw = MOUTAI_DIR / entry["raw_file"]
    if digest(raw) != entry["sha256"]:
        raise ValueError("Moutai 2014 raw source changed")
    moutai = json.loads((MOUTAI_DIR / "sh600519-2014-bars.json").read_text(encoding="utf-8"))
    benchmark = json.loads((BENCHMARK_DIR / "sh000001-2014-bars.json").read_text(encoding="utf-8"))
    crosscheck = json.loads((CROSSCHECK_DIR / "comparison.json").read_text(encoding="utf-8"))
    if crosscheck["common_dates"] != 245 or crosscheck["ohlc_mismatch_days"] != 0:
        raise ValueError("Benchmark secondary crosscheck is not sufficient for this research candidate")
    stock = {row["date"]: Decimal(row["close"]) for row in moutai}
    index = {row["date"]: Decimal(row["close"]) for row in benchmark}
    dates = sorted(stock.keys() & index.keys())
    if len(dates) != 245 or dates[0] != "2014-01-02" or dates[-1] != "2014-12-31":
        raise ValueError("Pre-decision common-date range changed")
    returns = []
    for previous, current in zip(dates, dates[1:]):
        stock_return = stock[current] / stock[previous] - Decimal(1)
        index_return = index[current] / index[previous] - Decimal(1)
        returns.append((current, stock_return, index_return))
    if len(returns) < 120:
        raise ValueError("Frozen minimum observations not met")
    x_bar = sum(item[2] for item in returns) / len(returns)
    y_bar = sum(item[1] for item in returns) / len(returns)
    denominator = sum((item[2] - x_bar) ** 2 for item in returns)
    if denominator <= 0:
        raise ValueError("Benchmark return variance is not positive")
    beta = sum((item[2] - x_bar) * (item[1] - y_bar) for item in returns) / denominator
    return {
        "contract_version": "moutai-2015-price-return-beta-candidate-v1",
        "symbol": "600519", "decision_boundary": "2015-01-05T00:00:00+08:00",
        "method": {
            "return_type": "unadjusted_close_to_close_price_return",
            "window": [dates[0], dates[-1]], "return_observations": len(returns),
            "minimum_observations": 120, "benchmark": "SSE Composite price index", "estimator": "OLS covariance/variance",
        },
        "research_beta": str(beta),
        "inputs": {
            "moutai_raw_sha256": entry["sha256"],
            "benchmark_bars_sha256": digest(BENCHMARK_DIR / "sh000001-2014-bars.json"),
            "benchmark_crosscheck_sha256": digest(CROSSCHECK_DIR / "comparison.json"),
        },
        "formal_beta_approved": False, "cost_of_equity_approved": False,
        "historical_replay_eligible": False, "trade_approved": False,
        "limitations": [
            "This is a research price-return beta, not a total-return beta; it does not model dividends or corporate actions.",
            "The matched price inputs are later-fetched secondary data, not archived as-of the 2015 decision date.",
            "It does not provide a risk-free rate, China ERP, profit/payout/fade policy, clean-surplus bridge, fair value or strategy result.",
        ],
    }


def main() -> int:
    output = ROOT / "runtime/strategy-validation" / ("moutai-2015-price-return-beta-candidate-"
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    output.mkdir(parents=True, exist_ok=False)
    evidence = output / "evidence.json"
    evidence.write_text(json.dumps(build(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({"script_sha256": digest(Path(__file__)),
        "evidence_sha256": digest(evidence)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    data = json.loads(evidence.read_text(encoding="utf-8"))
    print(json.dumps({"output": str(output), "research_beta": data["research_beta"],
                      "formal_beta_approved": data["formal_beta_approved"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
