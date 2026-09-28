"""Capture a bounded, read-only CNINFO announcement window for a registered case."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.disclosures import (  # noqa: E402
    SEARCH_URL,
    USER_AGENT,
    _cninfo_security_id,
    _discover_security_id,
    validate_cninfo_announcement_window,
)


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--identity-index")
    parser.add_argument("--identity-index-sha256")
    args = parser.parse_args()
    if args.start > args.end:
        parser.error("start date must not be after end date")
    validate_cninfo_announcement_window([], args.start, args.end)

    column, fallback = _cninfo_security_id(args.symbol)
    organization_id = _discover_security_id(args.symbol, column, fallback, args.name)
    if bool(args.identity_index) != bool(args.identity_index_sha256):
        parser.error("identity index path and SHA-256 must be supplied together")
    identity_source: dict[str, str] | None = None
    if args.identity_index:
        identity_path = (ROOT / args.identity_index).resolve()
        if not identity_path.is_relative_to((ROOT / "runtime").resolve()):
            parser.error("identity index must be retained under runtime")
        identity_bytes = identity_path.read_bytes()
        if _hash(identity_bytes) != args.identity_index_sha256.lower():
            parser.error("identity index hash mismatch")
        identity_index = json.loads(identity_bytes)
        if (
            identity_index.get("symbol") != args.symbol
            or identity_index.get("organization_id") != organization_id
        ):
            parser.error("identity index does not bind the requested issuer and organization ID")
        identity_source = {
            "path": identity_path.relative_to(ROOT).as_posix(),
            "sha256": args.identity_index_sha256.lower(),
            "organization_id": organization_id,
        }
    base_query = {
        "pageNum": "1", "pageSize": "30", "tabName": "fulltext",
        "column": column, "stock": f"{args.symbol},{organization_id}",
        "searchkey": "", "secid": "", "plate": "", "category": "",
        "trade": "", "seDate": f"{args.start}~{args.end}",
        "sortName": "", "sortType": "", "isHLtitle": "true",
    }
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_dir = ROOT / "runtime" / f"prospective-public-event-{args.end}" / f"gapfill-{args.symbol}-{run_id}"
    run_dir.mkdir(parents=True, exist_ok=False)
    scan_started_at = datetime.now(timezone.utc)
    request_rows: list[dict] = []
    session = requests.Session()
    session.trust_env = False
    try:
        records: list[dict] = []
        raw_refs: list[dict] = []
        expected_total: int | None = None
        page = 1
        while True:
            query = dict(base_query, pageNum=str(page))
            request_started_at = datetime.now(timezone.utc)
            response = session.post(
                SEARCH_URL, data=query,
                headers={"User-Agent": USER_AGENT, "Content-Type": "application/x-www-form-urlencoded"},
                timeout=(10, 30),
            )
            response_received_at = datetime.now(timezone.utc)
            response.raise_for_status()
            raw = response.content
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError("CNINFO response must be an object")
            if "totalAnnouncement" not in payload or type(payload["totalAnnouncement"]) is not int:
                raise ValueError("CNINFO totalAnnouncement must be an integer")
            if "hasMore" not in payload or type(payload["hasMore"]) is not bool:
                raise ValueError("CNINFO hasMore must be a boolean")
            if "announcements" not in payload:
                raise ValueError("CNINFO response is missing announcements")
            total = payload["totalAnnouncement"]
            if total < 0 or (expected_total is not None and total != expected_total):
                raise ValueError("CNINFO total changed during pagination")
            expected_total = total
            batch = payload["announcements"]
            if total == 0 and batch is None:
                batch = []
            elif not isinstance(batch, list):
                raise ValueError("CNINFO announcements must be an array")
            if total > 0 and not batch:
                raise ValueError("CNINFO announcements must be a non-empty array when total is positive")
            if any(str(item.get("secCode")) != args.symbol for item in batch):
                raise ValueError("CNINFO result contains another issuer")
            raw_path = run_dir / f"{args.symbol}-page-{page}.raw.json"
            raw_path.write_bytes(raw)
            raw_refs.append({
                "page": page, "path": str(raw_path.relative_to(ROOT)).replace("\\", "/"),
                "sha256": _hash(raw), "http_status": response.status_code,
                "returned_count": len(batch), "has_more": bool(payload.get("hasMore")),
            })
            request_rows.append({
                "endpoint": SEARCH_URL,
                "http_status": response.status_code,
                "request_parameters": query,
                "request_started_at": request_started_at.isoformat(),
                "response_received_at": response_received_at.isoformat(),
                "response_bytes": len(raw),
                "response_sha256": _hash(raw),
                "returned_count": len(batch),
                "reported_total": total,
                "has_more": bool(payload.get("hasMore")),
            })
            records.extend(batch)
            if len(records) >= expected_total:
                if len(records) > expected_total:
                    raise ValueError("CNINFO returned more records than its reported total")
                if payload.get("hasMore"):
                    page += 1
                    if page > 20:
                        raise ValueError("CNINFO page bound exceeded")
                    continue
                break
            if not payload.get("hasMore") or not batch:
                raise ValueError("CNINFO pagination stopped before the reported total")
            page += 1
            if page > 20:
                raise ValueError("CNINFO page bound exceeded")
        ids = [item.get("announcementId") for item in records]
        if any(not isinstance(item_id, str) or not item_id.isdigit() for item_id in ids):
            raise ValueError("CNINFO announcementId must be a non-empty numeric string")
        if len(records) != expected_total or len(set(ids)) != len(records):
            raise ValueError("CNINFO window has missing or duplicate announcement IDs")
        if expected_total == 0 and organization_id == fallback and not identity_source:
            raise ValueError("CNINFO zero-result window cannot use the guessed organization ID fallback")
        validate_cninfo_announcement_window(records, args.start, args.end)

        retrieved_at = datetime.now(timezone.utc).isoformat()
        index = {
            "schema_version": "prospective-cninfo-window-index-v1", "provider": "cninfo",
            "url": SEARCH_URL, "symbol": args.symbol, "issuer_name": args.name,
            "organization_id": organization_id, "query": base_query,
            "scan_from": args.start, "scan_to": args.end,
            "retrieved_at": retrieved_at, "total_announcements": expected_total,
            "returned_announcements": len(records), "pages": raw_refs,
            "announcements": records, "coverage_status": "COMPLETE",
            "coverage_scope": "CNINFO exact issuer and bounded date window only",
            "action": "no_order",
        }
        index_path = run_dir / "index.json"
        index_path.write_text(json.dumps(index, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        index_ref = index_path.relative_to(ROOT).as_posix()
        index_sha256 = _hash(index_path.read_bytes())
        china_started_at = scan_started_at.astimezone(ZoneInfo("Asia/Shanghai")).isoformat()
        scan_receipt = {
            "schema_version": "cninfo-exact-issuer-single-day-receipt-v1",
            "scope": "PUBLIC_READ_ONLY_EXACT_ISSUER_SINGLE_ANNOUNCEMENT_DATE",
            "provider": "CNINFO",
            "symbol": args.symbol,
            "issuer_name": args.name,
            "organization_id": organization_id,
            "issuer_identity_status": (
                "HASH_BOUND_PREVIOUS_CNINFO_QUERY" if identity_source else "NOT_INDEPENDENTLY_BOUND"
            ),
            "identity_source": identity_source,
            "scan_date": args.start if args.start == args.end else None,
            "exact_query_date_filter": f"{args.start}~{args.end}",
            "china_local_scan_started_at": china_started_at,
            "index_path": index_ref,
            "index_sha256": index_sha256,
            "query_endpoint": SEARCH_URL,
            "requests": request_rows,
            "pagination": {
                "page_count": len(raw_refs),
                "page_refs": raw_refs,
                "returned_announcements": len(records),
                "total_announcements": expected_total,
                "terminal_has_more": raw_refs[-1]["has_more"],
            },
            "capture_status": "SNAPSHOT_CAPTURED_NOT_FULL_DAY_COMPLETENESS",
            "limitations": [
                "Query is a retrieval-time snapshot; later postings in the requested date are not covered.",
                "CNINFO exact-issuer channel only; this is not complete issuer-IR or exchange-site coverage.",
                "No event materiality conclusion is made by the scanner.",
                "This receipt does not prove strict contemporaneous PIT.",
                "This bounded query does not advance or repair a registered continuous event watermark.",
                "Request timestamps use the local process clock and are not independently timestamp-attested.",
            ],
            "action": "no_order",
        }
        receipt_path = run_dir / "scan-receipt.json"
        receipt_path.write_text(
            json.dumps(scan_receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps({
            "run_id": run_id, "directory": str(run_dir.relative_to(ROOT)).replace("\\", "/"),
            "symbol": args.symbol, "scan_from": args.start, "scan_to": args.end,
            "retrieved_at": retrieved_at, "total_announcements": expected_total,
            "returned_announcements": len(records), "coverage_status": "COMPLETE",
            "index_sha256": index_sha256,
            "scan_receipt_path": receipt_path.relative_to(ROOT).as_posix(),
            "scan_receipt_sha256": _hash(receipt_path.read_bytes()),
            "raw_pages": raw_refs,
            "announcements": [{
                "announcement_id": item.get("announcementId"),
                "title": item.get("announcementTitle"), "announcement_time_ms": item.get("announcementTime"),
                "source_url": "https://static.cninfo.com.cn/" + str(item.get("adjunctUrl", "")).lstrip("/"),
            } for item in records],
            "action": "no_order",
        }, ensure_ascii=True, indent=2))
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
