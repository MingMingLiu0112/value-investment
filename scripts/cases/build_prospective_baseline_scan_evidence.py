"""Bind a fresh complete CNINFO query to one official filing PDF."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.disclosures import validate_cninfo_announcement_window


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inside(path: str | Path) -> Path:
    resolved = (ROOT / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
    if not resolved.is_relative_to(ROOT.resolve()):
        raise ValueError("evidence paths must remain inside the repository")
    return resolved


def build(
    index_path: Path, symbol: str, document_id: str, source_path: Path,
    output_path: Path, *, expected_start: str, expected_end: str,
) -> dict:
    index_path, source_path, output_path = map(inside, (index_path, source_path, output_path))
    if output_path.exists():
        raise FileExistsError(output_path)
    index_bytes = index_path.read_bytes()
    index = json.loads(index_bytes)
    if (
        index.get("coverage_status") != "COMPLETE"
        or index.get("coverage_scope") != "CNINFO exact issuer and bounded date window only"
        or index.get("symbol") != symbol
    ):
        raise ValueError("a complete exact-issuer CNINFO index is required")
    query = index.get("query") or {}
    scan_from, scan_to = index.get("scan_from"), index.get("scan_to")
    if (
        not isinstance(scan_from, str) or not isinstance(scan_to, str)
        or scan_from != expected_start or scan_to != expected_end
    ):
        raise ValueError("index scan dates differ from the independently supplied expected window")
    expected_query = {
        "pageNum": "1", "pageSize": "30", "tabName": "fulltext",
        "column": "sse" if symbol.startswith("6") else "szse",
        "stock": f"{symbol},{index.get('organization_id')}",
        "searchkey": "", "secid": "", "plate": "", "category": "",
        "trade": "", "seDate": f"{expected_start}~{expected_end}",
        "sortName": "", "sortType": "", "isHLtitle": "true",
    }
    if query != expected_query:
        raise ValueError("CNINFO query filters differ from the complete exact-issuer window contract")

    page_refs = index.get("pages")
    if not isinstance(page_refs, list) or not page_refs:
        raise ValueError("index must retain all raw response pages")
    pages: list[dict] = []
    page_evidence: list[dict] = []
    total: int | None = None
    for expected_page, ref in enumerate(page_refs, start=1):
        if ref.get("page") != expected_page:
            raise ValueError("raw response pages are not contiguous")
        raw_path = inside(ref["path"])
        raw_bytes = raw_path.read_bytes()
        if sha256(raw_path) != ref.get("sha256"):
            raise ValueError("raw CNINFO response hash mismatch")
        payload = json.loads(raw_bytes)
        reported = int(payload.get("totalAnnouncement", -1))
        if reported < 0 or (total is not None and reported != total):
            raise ValueError("CNINFO total changed across pages")
        total = reported
        announcements = payload.get("announcements") or []
        if len(announcements) != ref.get("returned_count"):
            raise ValueError("raw response count differs from the archived index")
        if any(str(item.get("secCode")) != symbol for item in announcements):
            raise ValueError("raw CNINFO response contains another issuer")
        expected_has_more = expected_page < len(page_refs)
        if bool(payload.get("hasMore")) != expected_has_more:
            raise ValueError("raw CNINFO pagination flags do not support complete coverage")
        pages.extend(announcements)
        page_evidence.append({
            "path": str(raw_path.relative_to(ROOT)).replace("\\", "/"),
            "sha256": ref["sha256"],
        })
    indexed = index.get("announcements") or []
    validate_cninfo_announcement_window(pages, scan_from, scan_to)
    ids = [str(item.get("announcementId")) for item in pages]
    if (
        total != index.get("total_announcements")
        or total != index.get("returned_announcements")
        or total != len(indexed)
        or ids != [str(item.get("announcementId")) for item in indexed]
        or pages != indexed
        or len(set(ids)) != len(ids)
    ):
        raise ValueError("raw CNINFO pages do not reconcile to the complete index")

    matches = [item for item in indexed if str(item.get("announcementId")) == document_id]
    if len(matches) != 1 or str(matches[0].get("secCode")) != symbol:
        raise ValueError("target filing is not uniquely present for the registered issuer")
    announcement = matches[0]
    source_url = "https://static.cninfo.com.cn/" + str(announcement.get("adjunctUrl", "")).lstrip("/")
    source_bytes = source_path.read_bytes()
    if not source_bytes.startswith(b"%PDF-"):
        raise ValueError("bound official source is not a PDF")
    retrieved_at = index["retrieved_at"]
    published_at = datetime.fromtimestamp(
        int(announcement["announcementTime"]) / 1000, timezone.utc
    ).isoformat()
    index_ref = {
        "path": str(index_path.relative_to(ROOT)).replace("\\", "/"),
        "sha256": sha256(index_path),
    }
    source_ref = {
        "path": str(source_path.relative_to(ROOT)).replace("\\", "/"),
        "sha256": hashlib.sha256(source_bytes).hexdigest(),
        "source_url": source_url,
    }
    result = {
        "schema_version": "prospective-official-source-scan-v1",
        "symbol": symbol,
        "provider": "cninfo",
        "coverage_status": "COMPLETE",
        "scan_from": index["scan_from"],
        "scan_to": index["scan_to"],
        "retrieved_at": retrieved_at,
        "query_scope": index["coverage_scope"],
        "total_announcements": total,
        "returned_announcements": len(indexed),
        "has_more": False,
        "evidence_refs": [index_ref, *page_evidence],
        "announcements": [{
            "announcement_id": document_id,
            "published_at": published_at,
            "title": announcement.get("announcementTitle"),
            "source_url": source_url,
            "evidence_refs": [index_ref, source_ref],
        }],
        "action": "no_order",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return {"output_path": str(output_path.relative_to(ROOT)).replace("\\", "/"), "sha256": sha256(output_path), "action": "no_order"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--source-pdf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-start", required=True)
    parser.add_argument("--expected-end", required=True)
    args = parser.parse_args()
    print(json.dumps(build(
        args.index, args.symbol, args.document_id, args.source_pdf, args.output,
        expected_start=args.expected_start, expected_end=args.expected_end,
    ), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
