#!/usr/bin/env python3
"""Archive official SSE 600519 suspension-query responses for the replay period.

An empty SSE response is evidence that the queried official status service
returned no listed stop/resume event. It is not evidence of an executable
order: daily order-book, queue and auction conditions remain unknown.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
QUERY_URL = "https://query.sse.com.cn/commonSoaQuery.do"
REFERER = "https://www.sse.com.cn/disclosure/dealinstruc/suspension/stock/"
SQL_ID = "GW_PL_JYTS_TFPXX"
WINDOWS = (
    ("20150101", "20171231"),
    ("20180101", "20201231"),
    ("20210101", "20231231"),
    ("20240101", "20251231"),
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_jsonp(raw: bytes) -> dict:
    text = raw.decode("utf-8")
    prefix, suffix = "callback(", ")"
    if not text.startswith(prefix) or not text.rstrip().endswith(suffix):
        raise ValueError("Unexpected SSE JSONP envelope")
    return json.loads(text[len(prefix):text.rfind(suffix)])


def request_params(start: str, end: str) -> dict[str, str | int | bool]:
    return {
        "jsonCallBack": "callback", "isPagination": "true", "sqlId": SQL_ID,
        "pageHelp.pageSize": 100, "pageHelp.pageNo": 1, "pageHelp.beginPage": 1,
        "productCode": "600519", "keyWords": "", "startStopDate": start,
        "endStopDate": end,
    }


def validate_response(payload: dict) -> list[dict]:
    if payload.get("sqlId") != SQL_ID or not isinstance(payload.get("result"), list):
        raise ValueError("Unexpected SSE suspension response payload")
    total = payload.get("pageHelp", {}).get("total")
    if total is not None and total != len(payload["result"]):
        raise ValueError("SSE suspension pagination is incomplete")
    return payload["result"]


def main() -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = ROOT / "runtime/exchange-suspension-probes" / f"moutai-sse-suspension-audit-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    records, queries = [], []
    with requests.Session() as session:
        session.trust_env = False
        for start, end in WINDOWS:
            response = session.post(QUERY_URL, data=request_params(start, end), headers={"Referer": REFERER, "User-Agent": "Mozilla/5.0"}, timeout=(10, 25))
            response.raise_for_status()
            raw_path = output / f"{start}-{end}.jsonp"
            raw_path.write_bytes(response.content)
            rows = validate_response(parse_jsonp(response.content))
            records.extend(rows)
            queries.append({"start": start, "end": end, "url": response.url, "path": raw_path.name, "sha256": sha256(raw_path), "records": len(rows)})
    evidence = {
        "symbol": "600519", "period": "2015-01-01..2025-12-31",
        "source": {"url": QUERY_URL, "referer": REFERER, "sql_id": SQL_ID, "interface_limit": "SSE page validates date windows no longer than three years"},
        "queries": queries, "official_returned_records": records,
        "official_returned_record_count": len(records),
        "suspension_status_evidence": "no_official_listed_stop_resume_records_returned" if not records else "official_records_returned_review_required",
        "calendar_or_execution_approved": False,
        "limitation": "An official empty response is not proof of intraday order-book liquidity, auction participation, queue priority, costs, or any fill. It also does not replace the separately pinned official SSE trading-calendar audit.",
    }
    evidence_path = output / "evidence.json"
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({"script_sha256": sha256(Path(__file__)), "evidence_sha256": sha256(evidence_path), "raw_responses": {row["path"]: row["sha256"] for row in queries}}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "records": len(records), "status": evidence["suspension_status_evidence"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
