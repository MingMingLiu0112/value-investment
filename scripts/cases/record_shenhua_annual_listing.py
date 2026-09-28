"""Archive the exact CNINFO annual-report query and PDF for Shenhua 2025FY."""
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
    symbol = "601088"
    column, fallback = _cninfo_security_id(symbol)
    security_id = _discover_security_id(symbol, column, fallback, "中国神华")
    query = {
        "pageNum": "1", "pageSize": "100", "tabName": "fulltext",
        "column": column, "stock": f"{symbol},{security_id}", "searchkey": "",
        "secid": "", "plate": "", "category": "category_ndbg_szsh",
        "trade": "", "seDate": "2026-03-30~2026-04-02", "sortName": "",
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
        items = json.loads(raw).get("announcements") or []
        target = [item for item in items if item.get("announcementId") == "1225064293"]
        ids = [item.get("announcementId") for item in items]
        payload = json.loads(raw)
        if (
            int(payload.get("totalAnnouncement", -1)) != 2 or len(items) != 2
            or len(set(ids)) != 2 or any(str(item.get("secCode")) != symbol for item in items)
            or len(target) != 1 or bool(payload.get("hasMore"))
        ):
            raise ValueError("bounded annual-category query is incomplete or issuer-mismatched")
        row = target[0]
        if row.get("adjunctUrl") != "finalpage/2026-03-31/1225064293.PDF":
            raise ValueError("target CNINFO annual-report URL differs from the expected listing")

        pdf_url = "https://static.cninfo.com.cn/" + row["adjunctUrl"]
        pdf_response = session.get(pdf_url, headers={"User-Agent": "Mozilla/5.0 ValueInvestmentAgent/1.0"}, timeout=(10, 60))
        pdf_response.raise_for_status()
        pdf = pdf_response.content
        if not pdf.startswith(b"%PDF-"):
            raise ValueError("official CNINFO source did not return PDF bytes")

        retrieved_at = datetime.now(timezone.utc).isoformat()
        directory = ROOT / "runtime" / "prospective-baseline-20260927" / (
            "shenhua-index-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        )
        directory.mkdir(parents=True, exist_ok=False)
        (directory / "response.raw.json").write_bytes(raw)
        source_path = directory / "shenhua-2025-annual.pdf"
        source_path.write_bytes(pdf)
        raw_hash = hashlib.sha256(raw).hexdigest()
        source_hash = hashlib.sha256(pdf).hexdigest()
        index = dict(payload) | {
            "url": SEARCH_URL, "query": query, "http_status": response.status_code,
            "content_type": response.headers.get("Content-Type"),
            "retrieved_at": retrieved_at, "raw_response_sha256": raw_hash,
        }
        (directory / "index.json").write_text(
            json.dumps(index, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        index_rel = str((directory / "index.json").relative_to(ROOT)).replace("\\", "/")
        pdf_rel = str(source_path.relative_to(ROOT)).replace("\\", "/")
        index_hash = hashlib.sha256((directory / "index.json").read_bytes()).hexdigest()
        published = datetime.fromtimestamp(row["announcementTime"] / 1000, timezone.utc).isoformat()
        scan = {
            "schema_version": "prospective-official-source-scan-v1", "symbol": symbol,
            "provider": "cninfo", "coverage_status": "COMPLETE",
            "scan_from": "2026-03-30", "scan_to": "2026-04-02",
            "retrieved_at": retrieved_at,
            "query_scope": "CNINFO annual-report category only; exact issuer and bounded date window",
            "total_announcements": 2, "returned_announcements": len(items), "has_more": False,
            "evidence_refs": [{"path": index_rel, "sha256": index_hash}],
            "announcements": [{
                "announcement_id": row["announcementId"], "published_at": published,
                "title": row["announcementTitle"], "source_url": pdf_url,
                "evidence_refs": [{"path": pdf_rel, "sha256": source_hash, "source_url": pdf_url}],
            }],
        }
        (directory / "scan-evidence.json").write_text(
            json.dumps(scan, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps({
            "directory": str(directory.relative_to(ROOT)).replace("\\", "/"),
            "query": query, "retrieved_at": retrieved_at, "http_status": response.status_code,
            "total_announcements": 2, "returned_announcements": len(items),
            "announcement_id": row["announcementId"], "title": row["announcementTitle"],
            "announcement_time_ms": row["announcementTime"], "source_url": pdf_url,
            "raw_response_sha256": raw_hash, "index_sha256": index_hash,
            "scan_evidence_sha256": hashlib.sha256((directory / "scan-evidence.json").read_bytes()).hexdigest(),
            "source_pdf_path": pdf_rel, "source_pdf_sha256": source_hash,
            "source_pdf_bytes": len(pdf), "action": "no_order",
        }, ensure_ascii=True, indent=2))
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
