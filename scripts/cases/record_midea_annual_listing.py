"""Archive the exact CNINFO annual-report index query for Midea 2025FY."""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from value_investment_agent.disclosures import (  # noqa: E402
    SEARCH_URL,
    _cninfo_security_id,
    _discover_security_id,
)


def main() -> int:
    column, fallback = _cninfo_security_id("000333")
    security_id = _discover_security_id("000333", column, fallback, "美的集团")
    query = {
        "pageNum": "1", "pageSize": "100", "tabName": "fulltext",
        "column": column, "stock": f"000333,{security_id}", "searchkey": "",
        "secid": "", "plate": "", "category": "category_ndbg_szsh",
        "trade": "", "seDate": "2026-03-31~2026-03-31", "sortName": "",
        "sortType": "", "isHLtitle": "true",
    }
    session = requests.Session()
    session.trust_env = False
    try:
        response = session.post(
            SEARCH_URL, data=query,
            headers={"User-Agent": "Mozilla/5.0 ValueInvestmentAgent/1.0",
                     "Content-Type": "application/x-www-form-urlencoded"},
            timeout=(10, 30),
        )
        response.raise_for_status()
        raw = response.content
    finally:
        session.close()

    payload = json.loads(raw)
    items = payload.get("announcements") or []
    target = [item for item in items if item.get("announcementId") == "1225065145"]
    ids = [item.get("announcementId") for item in items]
    if (
        int(payload.get("totalAnnouncement", -1)) != 2 or len(items) != 2
        or len(set(ids)) != 2 or any(str(item.get("secCode")) != "000333" for item in items)
        or len(target) != 1
    ):
        raise ValueError("exact annual-category query did not return the complete expected issuer index")
    row = target[0]
    if row.get("adjunctUrl") != "finalpage/2026-03-31/1225065145.PDF":
        raise ValueError("target CNINFO listing URL differs from the expected official annual report")
    source = ROOT / "runtime" / "midea-2025-official.pdf"
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    if source_hash != "16f95f70527db59dcf2736f276a9479cf7ee917e5f71e4f6cbbe83acbad9f4b6":
        raise ValueError("retained Midea annual-report PDF hash differs from the reviewed original")

    retrieved_at = datetime.now(timezone.utc).isoformat()
    directory = ROOT / "runtime" / "prospective-baseline-20260927" / (
        "midea-index-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    )
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "response.raw.json").write_bytes(raw)
    index = dict(payload) | {
        "url": SEARCH_URL, "query": query, "http_status": response.status_code,
        "content_type": response.headers.get("Content-Type"),
        "retrieved_at": retrieved_at,
        "raw_response_sha256": hashlib.sha256(raw).hexdigest(),
    }
    (directory / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    index_hash = hashlib.sha256((directory / "index.json").read_bytes()).hexdigest()
    scan = {
        "schema_version": "prospective-official-source-scan-v1", "symbol": "000333",
        "provider": "cninfo", "coverage_status": "COMPLETE",
        "scan_from": "2026-03-31", "scan_to": "2026-03-31",
        "retrieved_at": retrieved_at,
        "query_scope": "CNINFO annual-report category only; exact issuer and disclosure date",
        "total_announcements": 2, "returned_announcements": len(items),
        "has_more": bool(payload.get("hasMore")),
        "evidence_refs": [{"path": str((directory / "index.json").relative_to(ROOT)).replace("\\", "/"),
                           "sha256": index_hash}],
        "announcements": [{
            "announcement_id": row["announcementId"],
            "published_at": datetime.fromtimestamp(row["announcementTime"] / 1000, timezone.utc).isoformat(),
            "title": row["announcementTitle"],
            "source_url": "https://static.cninfo.com.cn/" + row["adjunctUrl"],
            "evidence_refs": [{"path": "runtime/midea-2025-official.pdf",
                               "sha256": source_hash,
                               "source_url": "https://static.cninfo.com.cn/" + row["adjunctUrl"]}],
        }],
    }
    (directory / "scan-evidence.json").write_text(
        json.dumps(scan, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    result = {
        "directory": str(directory.relative_to(ROOT)).replace("\\", "/"),
        "retrieved_at": retrieved_at, "query": query,
        "http_status": response.status_code, "total_announcements": 2,
        "returned_announcements": len(items), "target_announcement_id": row["announcementId"],
        "target_title": row["announcementTitle"],
        "target_announcement_time_ms": row["announcementTime"],
        "official_pdf_url": scan["announcements"][0]["source_url"],
        "raw_response_sha256": hashlib.sha256(raw).hexdigest(),
        "index_sha256": index_hash, "scan_evidence_sha256": hashlib.sha256(
            (directory / "scan-evidence.json").read_bytes()
        ).hexdigest(), "source_pdf_sha256": source_hash,
        "action": "no_order",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
