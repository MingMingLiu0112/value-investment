#!/usr/bin/env python3
"""Cross-check the research-only 2014 Moutai Tencent bars against Sina."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import requests

try:
    from scripts.collect_historical_prices import parse_bars
    from scripts.crosscheck_historical_prices import compare, normalize_sina, sina_payload
except ModuleNotFoundError:
    from collect_historical_prices import parse_bars
    from crosscheck_historical_prices import compare, normalize_sina, sina_payload


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "runtime/historical-prices/20260920T074631172611Z"
SYMBOL = "sh600519"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    manifest = json.loads((SOURCE / "manifest.json").read_text(encoding="utf-8"))
    entry = next((row for row in manifest["requests"] if row["symbol"] == SYMBOL and row["year"] == 2014), None)
    if entry is None:
        raise ValueError("Pinned 2014 Moutai Tencent request is missing")
    raw = SOURCE / entry["raw_file"]
    if digest(raw) != entry["sha256"]:
        raise ValueError("Pinned Tencent evidence changed")
    left = {row["date"]: row for row in parse_bars(raw.read_bytes(), SYMBOL, 2014)}
    if len(left) != 245 or min(left) != "2014-01-02" or max(left) != "2014-12-31":
        raise ValueError("Unexpected 2014 Moutai Tencent coverage")

    from akshare.stock.stock_zh_a_sina import hk_js_decode, py_mini_racer, zh_sina_a_stock_hist_url
    url = zh_sina_a_stock_hist_url.format(SYMBOL)
    with requests.Session() as session:
        session.trust_env = False
        response = session.get(url, timeout=(10, 30))
        response.raise_for_status()
    sina_raw = response.content
    decoder = py_mini_racer.MiniRacer()
    decoder.eval(hk_js_decode)
    right = normalize_sina(decoder.call("d", sina_payload(sina_raw, SYMBOL)), start_year=2014, end_year=2014)
    output = ROOT / "runtime/strategy-validation" / ("moutai-2014-price-crosscheck-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    output.mkdir(parents=True, exist_ok=False)
    sina_path = output / "sh600519-sina.js"
    sina_path.write_bytes(sina_raw)
    result = {
        "symbol": "600519", "year": 2014, "tencent_candidate": str(SOURCE.relative_to(ROOT)),
        "tencent_raw_sha256": entry["sha256"], "sina_url": response.url,
        "sina_raw_sha256": digest(sina_path),
        **compare(left, right, tolerance=Decimal("0.01")),
        "crosscheck_scope": "secondary_vs_secondary_research_only",
        "formal_beta_approved": False, "historical_replay_eligible": False, "trade_approved": False,
    }
    evidence = output / "comparison.json"
    evidence.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({"script_sha256": digest(Path(__file__)), "comparison_sha256": digest(evidence)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("common_dates", "ohlc_mismatch_days", "backtest_ready")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
