#!/usr/bin/env python3
"""Probe public historical price coverage for a no-look-ahead beta policy."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import akshare as ak
import requests


ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    # Eastmoney's public historical endpoint is reachable directly on this host;
    # do not inherit a stale local proxy into this evidence-only probe.
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        os.environ.pop(key, None)
    direct_session = requests.Session()
    direct_session.trust_env = False
    requests.get = direct_session.get
    output = ROOT / "runtime/strategy-validation" / ("moutai-pre2015-market-history-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    output.mkdir(parents=True, exist_ok=False)
    stock = ak.stock_zh_a_hist(symbol="600519", period="daily", start_date="20100101", end_date="20141231", adjust="qfq")
    index = ak.stock_zh_index_daily_em(symbol="sh000300")
    stock_path, index_path = output / "600519-qfq.csv", output / "sh000300.csv"
    stock.to_csv(stock_path, index=False, encoding="utf-8")
    index.to_csv(index_path, index=False, encoding="utf-8")
    result = {
        "symbol": "600519", "benchmark": "sh000300", "provider": "akshare",
        "request": {"stock_start": "20100101", "stock_end": "20141231", "stock_adjust": "qfq"},
        "stock_rows": len(stock), "index_rows": len(index),
        "stock_columns": list(stock.columns), "index_columns": list(index.columns),
        "stock_first": stock.iloc[0].to_dict() if len(stock) else None,
        "stock_last": stock.iloc[-1].to_dict() if len(stock) else None,
        "files": {str(stock_path.relative_to(ROOT)): digest(stock_path), str(index_path.relative_to(ROOT)): digest(index_path)},
        "beta_input_status": "coverage_probe_only_not_admitted",
        "limitations": ["Provider is a public-data adapter, not an official exchange historical total-return source.", "Adjusted-price treatment, benchmark identity and corporate-action methodology require separate validation before beta estimation."],
    }
    (output / "evidence.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "stock_rows": len(stock), "index_rows": len(index)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
