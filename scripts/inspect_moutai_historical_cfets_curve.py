#!/usr/bin/env python3
"""Classify one pinned CFETS historical-curve probe without admitting a rate."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "runtime/strategy-validation/moutai-historical-cfets-rate-probe-20260920T070000Z"
RAW = DIRECTORY / "response.raw"
URL = ("https://www.chinamoney.com.cn/ags/ms/cm-u-bk-currency/ClsYldCurvHis?lang=CN&reference=1,2,3"
       "&bondType=CYCC000&startDate=2014-12-31&endDate=2014-12-31&termId=1&pageNum=1&pageSize=50")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build() -> dict:
    value = json.loads(RAW.read_text(encoding="utf-8"))
    data, records = value.get("data") or {}, value.get("records") or []
    valid_identity = (value.get("head", {}).get("rep_code") == "200"
                      and data.get("firstBondType") == "CYCC000"
                      and data.get("startDateCN") == "2014-12-31"
                      and data.get("endDateCN") == "2014-12-31")
    if not valid_identity:
        raise ValueError("CFETS response does not match the requested government-curve date")
    if records or data.get("total") != 0 or data.get("pageTotal") != 0:
        raise ValueError("This inspector only records the observed zero-record response")
    return {
        "source_id": "cfets:ClsYldCurvHis:CYCC000",
        "source_url": URL,
        "requested_date": "2014-12-31",
        "curve_id": "CYCC000",
        "raw_response": str(RAW.relative_to(ROOT)),
        "raw_response_sha256": digest(RAW),
        "response_status": "http_200_valid_request_zero_records",
        "rate_input_status": "rejected_no_historical_curve_records",
        "observed_total": 0,
        "observed_page_total": 0,
        "valuation_approved": False,
        "trade_approved": False,
        "limitations": [
            "An HTTP 200 response and accepted date parameter do not establish a yield observation.",
            "Zero returned records are not a zero percent rate and must not enter a model.",
            "The 2015 historical parent-equity assumption contract remains missing a dated risk-free proxy.",
        ],
    }


def main() -> int:
    result = build()
    output = DIRECTORY / "inspection.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (DIRECTORY / "manifest.json").write_text(json.dumps({
        "script_sha256": digest(Path(__file__)), "raw_response_sha256": digest(RAW),
        "inspection_sha256": digest(output), "inspected_at": datetime.now(timezone.utc).isoformat(),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "rate_input_status": result["rate_input_status"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
