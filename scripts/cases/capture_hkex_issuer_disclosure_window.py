"""Capture a bounded, read-only HKEX issuer disclosure window.

The command pins the issuer identity, the exchange-side record list and, when
requested, the original disclosure files. It records hashes and request
metadata so a later review can re-verify the bytes. It makes no materiality,
PIT or valuation conclusion and never admits evidence into a model.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parents[2]

PREFIX_URL = "https://www1.hkexnews.hk/search/prefix.do"
SEARCH_URL = "https://www1.hkexnews.hk/search/titleSearchServlet.do"
FILE_BASE_URL = "https://www1.hkexnews.hk"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) value-investment-research/1.0"
)
MAX_ROW_RANGE = 100
CODE_PATTERN = re.compile(r"^[0-9]{5}$")
LINK_PATTERN = re.compile(r"^/listedco/listconews/[A-Za-z0-9/_.-]+$")


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _iso_china(value: str) -> str:
    """Convert an HKEX ``dd/mm/yyyy HH:MM`` stamp into an ISO China-time string."""

    parsed = datetime.strptime(value, "%d/%m/%Y %H:%M")
    return parsed.replace(tzinfo=ZoneInfo("Asia/Shanghai")).isoformat()


def _resolve_stock_id(session: requests.Session, code: str, lang: str) -> tuple[str, bytes]:
    response = session.get(
        PREFIX_URL,
        params={"callback": "cb", "lang": lang.upper(), "type": "A", "name": code, "market": "SEHK"},
        headers={"User-Agent": USER_AGENT},
        timeout=(10, 30),
    )
    response.raise_for_status()
    raw = response.content
    text = raw.decode("utf-8")
    match = re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*\((.*)\);?\s*", text, flags=re.S)
    if match is None:
        raise ValueError("HKEX prefix response is not a JSONP payload")
    payload = json.loads(match.group(1))
    matches = [item for item in payload.get("stockInfo", []) if item.get("code") == code]
    if len(matches) != 1:
        raise ValueError(f"HKEX prefix lookup must identify exactly one issuer for {code}")
    stock_id = matches[0].get("stockId")
    if not isinstance(stock_id, int):
        raise ValueError("HKEX prefix lookup is missing a numeric stockId")
    return str(stock_id), raw


def _query_window(
    session: requests.Session,
    stock_id: str,
    start: date,
    end: date,
    lang: str,
    row_range: int,
) -> tuple[bytes, dict]:
    parameters = {
        "sortDir": "0",
        "sortByOptions": "DateTime",
        "category": "0",
        "market": "SEHK",
        "stockId": stock_id,
        "documentType": "-1",
        "fromDate": start.strftime("%Y%m%d"),
        "toDate": end.strftime("%Y%m%d"),
        "title": "",
        "searchType": "1",
        "t1code": "-2",
        "t2Gcode": "-2",
        "t2code": "-2",
        "rowRange": str(row_range),
        "lang": lang,
    }
    response = session.get(
        SEARCH_URL,
        params=parameters,
        headers={"User-Agent": USER_AGENT},
        timeout=(10, 30),
    )
    response.raise_for_status()
    raw = response.content
    envelope = json.loads(raw)
    if not isinstance(envelope, dict) or not isinstance(envelope.get("result"), str):
        raise ValueError("HKEX window response is missing a result payload")
    records = json.loads(envelope["result"])
    if not isinstance(records, list):
        raise ValueError("HKEX result payload must be a record array")
    if envelope.get("hasNextRow"):
        raise ValueError("HKEX window exceeds the bounded row range; narrow the date window")
    reported = envelope.get("recordCnt")
    loaded = envelope.get("loadedRecord")
    if not isinstance(reported, int) or not isinstance(loaded, int):
        raise ValueError("HKEX response counts must be integers")
    if reported != loaded or loaded != len(records):
        raise ValueError("HKEX response counts do not reconcile with the returned records")
    return raw, {"parameters": parameters, "records": records, "record_count": reported}


def _normalize_records(records: list, code: str, start: date, end: date) -> list[dict]:
    normalized: list[dict] = []
    seen: set[str] = set()
    for item in records:
        news_id = item.get("NEWS_ID")
        link = item.get("FILE_LINK")
        stamp = item.get("DATE_TIME")
        title = item.get("TITLE")
        if not isinstance(news_id, str) or not news_id.isdigit():
            raise ValueError("HKEX record is missing a numeric NEWS_ID")
        if news_id in seen:
            raise ValueError("HKEX window contains a duplicate NEWS_ID")
        seen.add(news_id)
        if item.get("STOCK_CODE") != code:
            raise ValueError("HKEX window returned another issuer")
        if not isinstance(link, str) or LINK_PATTERN.fullmatch(link) is None:
            raise ValueError("HKEX record FILE_LINK is outside the listed-company path")
        if not isinstance(stamp, str):
            raise ValueError("HKEX record is missing a DATE_TIME stamp")
        released_at = _iso_china(stamp)
        released_date = date.fromisoformat(released_at[:10])
        if not start <= released_date <= end:
            raise ValueError("HKEX record falls outside the requested window")
        if not isinstance(title, str) or not title.strip():
            raise ValueError("HKEX record is missing a title")
        normalized.append({
            "news_id": news_id,
            "released_at": released_at,
            "released_at_raw": stamp,
            "title": title.strip(),
            "long_text": item.get("LONG_TEXT"),
            "file_type": item.get("FILE_TYPE"),
            "file_link": link,
            "source_url": FILE_BASE_URL + link,
        })
    normalized.sort(key=lambda entry: (entry["released_at"], int(entry["news_id"])))
    return normalized


def _download_originals(
    session: requests.Session, records: list[dict], target_dir: Path,
) -> list[dict]:
    target_dir.mkdir(parents=True, exist_ok=True)
    originals: list[dict] = []
    for entry in records:
        name = Path(entry["file_link"]).name
        target = target_dir / f"{entry['news_id']}-{name}"
        response = session.get(
            entry["source_url"], headers={"User-Agent": USER_AGENT}, timeout=(10, 90),
        )
        response.raise_for_status()
        payload = response.content
        if not payload:
            raise ValueError(f"HKEX download for {entry['news_id']} returned no bytes")
        target.write_bytes(payload)
        originals.append({
            "news_id": entry["news_id"],
            "path": str(target.relative_to(ROOT)).replace("\\", "/"),
            "bytes": len(payload),
            "sha256": _hash(payload),
            "http_status": response.status_code,
        })
    return originals


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--code", required=True, help="HKEX five-digit stock code, e.g. 00300")
    parser.add_argument("--start", required=True, help="window start (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="window end (YYYY-MM-DD)")
    parser.add_argument("--output-dir", required=True, help="new directory under runtime/")
    parser.add_argument("--lang", default="zh")
    parser.add_argument("--row-range", type=int, default=MAX_ROW_RANGE)
    parser.add_argument("--expect-name", help="optional exact STOCK_NAME assertion")
    parser.add_argument("--download", action="store_true", help="also retain original PDFs")
    args = parser.parse_args()

    if CODE_PATTERN.fullmatch(args.code) is None:
        parser.error("code must be exactly five digits")
    if not 1 <= args.row_range <= MAX_ROW_RANGE:
        parser.error(f"row range must be 1..{MAX_ROW_RANGE}")
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    if start > end:
        parser.error("start date must not be after end date")
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    if end > today:
        parser.error("end date must not be in the future")
    if args.lang not in {"zh", "en"}:
        parser.error("lang must be zh or en")

    run_dir = (ROOT / args.output_dir).resolve()
    if not run_dir.is_relative_to((ROOT / "runtime").resolve()):
        parser.error("output directory must remain under runtime/")
    if run_dir.exists():
        parser.error("output directory already exists; refuse to overwrite evidence")
    run_dir.mkdir(parents=True)

    started_at = datetime.now(timezone.utc)
    session = requests.Session()
    session.trust_env = False
    try:
        stock_id, prefix_raw = _resolve_stock_id(session, args.code, args.lang)
        prefix_path = run_dir / "stock-id.raw.json"
        prefix_path.write_bytes(prefix_raw)
        window_raw, window = _query_window(
            session, stock_id, start, end, args.lang, args.row_range,
        )
        window_path = run_dir / "window.raw.json"
        window_path.write_bytes(window_raw)
        records = _normalize_records(window["records"], args.code, start, end)
        if args.expect_name is not None:
            names = {item.get("STOCK_NAME") for item in window["records"]}
            if names != {args.expect_name}:
                raise ValueError(f"HKEX issuer name mismatch: {sorted(names)}")
        originals = _download_originals(session, records, run_dir / "originals") if args.download else []
        retrieved_at = datetime.now(timezone.utc).isoformat()
    finally:
        session.close()

    index = {
        "schema_version": "hkex-issuer-window-index-v1",
        "provider": "HKEXNEWS",
        "code": args.code,
        "stock_id": stock_id,
        "query_endpoint": SEARCH_URL,
        "query_parameters": window["parameters"],
        "query_string": urlencode(window["parameters"]),
        "scan_from": args.start,
        "scan_to": args.end,
        "retrieved_at": retrieved_at,
        "total_records": window["record_count"],
        "records": records,
        "raw_responses": [
            {
                "path": prefix_path.relative_to(ROOT).as_posix(),
                "sha256": _hash(prefix_raw),
                "purpose": "issuer identity prefix lookup",
            },
            {
                "path": window_path.relative_to(ROOT).as_posix(),
                "sha256": _hash(window_raw),
                "purpose": "bounded issuer window result",
            },
        ],
        "originals": originals,
        "coverage_status": "COMPLETE",
        "coverage_scope": "HKEX issuer disclosure channel and bounded date window only",
        "action": "no_order",
    }
    index_path = run_dir / "window-index.json"
    index_path.write_text(
        json.dumps(index, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    receipt = {
        "schema_version": "hkex-issuer-disclosure-window-receipt-v1",
        "scope": "PUBLIC_READ_ONLY_EXACT_ISSUER_BOUNDED_DISCLOSURE_WINDOW",
        "provider": "HKEXNEWS",
        "code": args.code,
        "stock_id": stock_id,
        "exact_query_date_filter": f"{args.start}~{args.end}",
        "run_started_at": started_at.isoformat(),
        "retrieved_at": retrieved_at,
        "index_path": index_path.relative_to(ROOT).as_posix(),
        "index_sha256": _hash(index_path.read_bytes()),
        "record_count": window["record_count"],
        "downloaded_originals": len(originals),
        "capture_status": "SNAPSHOT_CAPTURED_NOT_FULL_DAY_COMPLETENESS",
        "limitations": [
            "Query is a retrieval-time snapshot; later postings in the requested window are not covered.",
            "HKEX issuer disclosure channel only; this is not complete issuer-IR or CNINFO coverage.",
            "No event materiality conclusion is made by the capture.",
            "This receipt does not prove strict contemporaneous PIT.",
            "This bounded query does not advance or repair a registered continuous event watermark.",
            "Request timestamps use the local process clock and are not independently timestamp-attested.",
        ],
        "action": "no_order",
    }
    receipt_path = run_dir / "capture-receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "directory": run_dir.relative_to(ROOT).as_posix(),
        "code": args.code,
        "stock_id": stock_id,
        "scan_from": args.start,
        "scan_to": args.end,
        "record_count": window["record_count"],
        "index_sha256": receipt["index_sha256"],
        "receipt_path": receipt_path.relative_to(ROOT).as_posix(),
        "receipt_sha256": _hash(receipt_path.read_bytes()),
        "records": [
            {
                "news_id": entry["news_id"],
                "released_at": entry["released_at"],
                "title": entry["title"],
                "source_url": entry["source_url"],
            }
            for entry in records
        ],
        "action": "no_order",
    }, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
