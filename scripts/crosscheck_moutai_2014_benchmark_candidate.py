#!/usr/bin/env python3
"""Cross-check the research-only 2014 SSE Composite candidate against Sina."""
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
SOURCE = ROOT / "runtime/strategy-validation/moutai-2014-sse-composite-candidate-20260920T074939Z"


def main() -> int:
    evidence = json.loads((SOURCE / "evidence.json").read_text(encoding="utf-8"))
    raw = SOURCE / "sh000001-2014.raw.json"
    if hashlib.sha256(raw.read_bytes()).hexdigest() != evidence["raw_sha256"]:
        raise ValueError("Tencent benchmark candidate changed")
    left = {row["date"]: row for row in parse_bars(raw.read_bytes(), "sh000001", 2014)}
    from akshare.stock.stock_zh_a_sina import hk_js_decode, py_mini_racer, zh_sina_a_stock_hist_url
    url = zh_sina_a_stock_hist_url.format("sh000001")
    with requests.Session() as session:
        session.trust_env = False
        response = session.get(url, timeout=(10, 30))
        response.raise_for_status()
    sina_raw = response.content
    decoder = py_mini_racer.MiniRacer()
    decoder.eval(hk_js_decode)
    right = normalize_sina(decoder.call("d", sina_payload(sina_raw, "sh000001")), start_year=2014, end_year=2014)
    output = ROOT / "runtime/strategy-validation" / ("moutai-2014-sse-composite-crosscheck-"
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    output.mkdir(parents=True, exist_ok=False)
    sina_path = output / "sh000001-sina.js"
    sina_path.write_bytes(sina_raw)
    result = {
        "symbol": "000001", "year": 2014, "tencent_candidate": str(SOURCE.relative_to(ROOT)),
        "sina_url": response.url, "sina_raw_sha256": hashlib.sha256(sina_raw).hexdigest(),
        **compare(left, right, tolerance=Decimal("0.01")),
        "crosscheck_scope": "secondary_vs_secondary_research_only",
        "beta_estimated": False, "historical_replay_eligible": False, "trade_approved": False,
    }
    report = output / "comparison.json"
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "comparison_sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("common_dates", "ohlc_mismatch_days", "backtest_ready")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
