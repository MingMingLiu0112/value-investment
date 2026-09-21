#!/usr/bin/env python3
"""Archive the official SSE stop/resume query for one current 600519 window."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from audit_moutai_sse_suspension_status import (QUERY_URL, REFERER, parse_jsonp,
                                                 request_params, validate_response)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True, help="YYYYMMDD")
    parser.add_argument("--end", required=True, help="YYYYMMDD")
    args = parser.parse_args()
    if not (args.start.isdigit() and args.end.isdigit() and len(args.start) == len(args.end) == 8
            and args.start <= args.end):
        raise ValueError("An ordered YYYYMMDD window is required")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = ROOT / "runtime/exchange-suspension-probes" / f"moutai-current-suspension-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    with requests.Session() as session:
        session.trust_env = False
        response = session.post(QUERY_URL, data=request_params(args.start, args.end),
                                headers={"Referer": REFERER, "User-Agent": "Mozilla/5.0"},
                                timeout=(10, 25))
        response.raise_for_status()
        raw = output / f"{args.start}-{args.end}.jsonp"
        raw.write_bytes(response.content)
    records = validate_response(parse_jsonp(raw.read_bytes()))
    evidence = {
        "symbol": "600519", "window": f"{args.start}..{args.end}",
        "source": {"url": QUERY_URL, "referer": REFERER, "sql_id": "GW_PL_JYTS_TFPXX"},
        "raw_response": {"path": raw.name, "sha256": digest(raw)},
        "official_returned_records": records,
        "official_returned_record_count": len(records),
        "suspension_status": "no_official_listed_stop_resume_records_returned" if not records else "official_records_returned_review_required",
        "execution_ready": False,
        "limitations": [
            "An empty official stop/resume result is not proof of normal intraday trading or order-book liquidity.",
            "This check does not establish price-limit status, order validity, slippage, or a broker fill.",
        ],
        "trade_approved": False, "live_eligible": False,
    }
    path = output / "evidence.json"
    path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({"script_sha256": digest(Path(__file__)), "evidence_sha256": digest(path)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "records": len(records), "status": evidence["suspension_status"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
