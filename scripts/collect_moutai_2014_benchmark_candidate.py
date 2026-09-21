#!/usr/bin/env python3
"""Archive a research-only 2014 SSE Composite price-return candidate."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

try:
    from scripts.collect_historical_prices import parse_bars
except ModuleNotFoundError:
    from collect_historical_prices import parse_bars


ROOT = Path(__file__).resolve().parents[1]
URL = "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get"
SYMBOL = "sh000001"


def main() -> int:
    output = ROOT / "runtime/strategy-validation" / ("moutai-2014-sse-composite-candidate-"
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    output.mkdir(parents=True, exist_ok=False)
    with requests.Session() as session:
        session.trust_env = False
        response = session.get(URL, params={"param": f"{SYMBOL},day,2014-01-01,2014-12-31,640,"},
                               timeout=(10, 25))
        response.raise_for_status()
    raw = response.content
    raw_path = output / "sh000001-2014.raw.json"
    raw_path.write_bytes(raw)
    raw_hash = hashlib.sha256(raw).hexdigest()
    bars = parse_bars(raw, SYMBOL, 2014)
    if len(bars) < 200 or bars[0]["date"] != "2014-01-02" or bars[-1]["date"] != "2014-12-31":
        raise ValueError("Unexpected 2014 SSE Composite candidate coverage")
    bars_path = output / "sh000001-2014-bars.json"
    bars_path.write_text(json.dumps(bars, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    evidence = {
        "symbol": "000001", "instrument": "SSE Composite Index", "provider": "Tencent secondary market data",
        "adjustment": "unadjusted price index", "year": 2014, "sessions": len(bars),
        "first_date": bars[0]["date"], "last_date": bars[-1]["date"],
        "source_url": response.url, "raw_path": str(raw_path.relative_to(ROOT)), "raw_sha256": raw_hash,
        "research_only": True, "cross_verified": False, "point_in_time_version_verified": False,
        "beta_estimated": False, "historical_replay_eligible": False, "trade_approved": False,
        "limitations": [
            "This is a secondary provider response fetched after the decision period.",
            "It must be independently cross-checked and aligned to an exchange calendar before any beta research calculation.",
            "It is not a dated official benchmark archive and cannot release historical replay or trading gates.",
        ],
    }
    evidence_path = output / "evidence.json"
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "raw_sha256": raw_hash, "bars_sha256": hashlib.sha256(bars_path.read_bytes()).hexdigest(),
        "evidence_sha256": hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "sessions": len(bars), "research_only": True}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
