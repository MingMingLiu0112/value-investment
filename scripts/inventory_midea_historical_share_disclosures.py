#!/usr/bin/env python3
"""Index Midea annual-report share disclosures without deriving a share series."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from pypdf import PdfReader

from value_investment_agent.pdf_text import extract_pages

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "runtime/historical-filing-index/20260908T041326996681Z/000333-1-2588aae8bfff792ac1ec05c32baea97e7a9a9121ed73d04a491a51d0874c0dc2.json"
PDFS = ROOT / "runtime/historical-filing-index/20260908T041326996681Z/pdfs"
TERMS = ("\u80a1\u4efd\u603b\u6570", "\u603b\u80a1\u672c", "\u5e93\u5b58\u80a1", "\u80a1\u672c\u7ed3\u6784", "\u80a1\u672c")
PAGE_LIMIT = 160


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def annual_reports() -> list[dict]:
    payload = json.loads(INDEX.read_text(encoding="utf-8"))
    rows = []
    for row in payload["response"]["announcements"]:
        title = row.get("announcementTitle", "")
        match = re.fullmatch(r"(20\d{2})\u5e74\u5e74\u5ea6\u62a5\u544a", title)
        if not match:
            continue
        report_year = int(match.group(1))
        filename = f"000333-{row['announcementId']}.pdf"
        path = PDFS / filename
        if not path.exists():
            raise ValueError(f"Archived annual report missing: {filename}")
        rows.append({"report_year": report_year, "announcement_id": row["announcementId"],
                     "publication_date": datetime.fromtimestamp(row["announcementTime"] / 1000,
                                                                  tz=timezone.utc).date().isoformat(),
                     "url": "https://static.cninfo.com.cn/" + row["adjunctUrl"],
                         "path": path})
    # The bounded index response retained the 2014 English edition but omitted
    # this already hash-pinned Chinese original used by existing Midea evidence.
    # It is recorded explicitly rather than inferred from a later comparative.
    legacy_path = PDFS / "000333-1200767542.pdf"
    if not legacy_path.exists():
        raise ValueError("Archived 2014 Midea annual report missing")
    rows.append({"report_year": 2014, "announcement_id": "1200767542",
                 "publication_date": "2015-03-31",
                 "url": "https://static.cninfo.com.cn/finalpage/2015-03-31/1200767542.PDF",
                 "path": legacy_path})
    rows.sort(key=lambda row: row["report_year"])
    if [row["report_year"] for row in rows] != list(range(2014, 2025)):
        raise ValueError("Unexpected Midea annual-report coverage")
    return rows


def candidates(pages: list[str]) -> list[dict]:
    found = []
    for number, page in enumerate(pages, start=1):
        normalized = re.sub(r"\s+", " ", page)
        for term in TERMS:
            start = 0
            while True:
                position = normalized.find(term, start)
                if position < 0:
                    break
                found.append({"page": number, "term": term,
                              "excerpt": normalized[max(0, position - 100): position + len(term) + 220]})
                start = position + len(term)
    return found


def build_inventory() -> dict:
    reports = []
    for report in annual_reports():
        raw_hash = digest(report["path"])
        pdfium = candidates(extract_pages(report["path"], limit=PAGE_LIMIT))
        candidate_pages = {row["page"] for row in pdfium}
        reader = PdfReader(report["path"])
        pypdf_pages = ["" for _ in range(min(len(reader.pages), PAGE_LIMIT))]
        for page_number in candidate_pages:
            pypdf_pages[page_number - 1] = reader.pages[page_number - 1].extract_text() or ""
        pypdf = candidates(pypdf_pages)
        # Exact text can vary by decoder; a page/term multiset establishes only
        # that both located the same disclosure neighborhood.
        pdfium_keys = {(row["page"], row["term"]) for row in pdfium}
        pypdf_keys = {(row["page"], row["term"]) for row in pypdf}
        reports.append({"report_year": report["report_year"], "announcement_id": report["announcement_id"],
                        "publication_date": report["publication_date"], "url": report["url"],
                        "path": str(report["path"].relative_to(ROOT)), "sha256": raw_hash,
                        "pdfium_candidates": pdfium, "pypdf_candidates": pypdf,
                        "shared_page_term_candidates": sorted(({"page": page, "term": term}
                                                                  for page, term in pdfium_keys & pypdf_keys),
                                                                 key=lambda row: (row["page"], row["term"]))})
    return {"symbol": "000333", "inventory_version": "midea-annual-share-disclosure-inventory-v1",
            "input_scope": "2014_to_2024_CNINFO_annual_reports_first_160_pages", "reports": reports,
            "interpretation": "Candidate excerpts only. A share-capital currency amount, weighted EPS denominator, or later comparative figure is not an approved period-end ordinary-share count.",
            "limitations": ["First 160 physical PDF pages per report only", "Two decoders locate candidate neighborhoods but do not independently verify financial facts"],
            "share_timeline_approved": False, "valuation_approved": False, "trade_approved": False}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output_dir or ROOT / "runtime/company-research" / f"midea-annual-share-disclosure-inventory-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    inventory = build_inventory()
    data = output / "inventory.json"
    data.write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {"symbol": inventory["symbol"], "reports": len(inventory["reports"]),
               "pdfium_candidates": sum(len(row["pdfium_candidates"]) for row in inventory["reports"]),
               "pypdf_candidates": sum(len(row["pypdf_candidates"]) for row in inventory["reports"]),
               "shared_page_term_candidates": sum(len(row["shared_page_term_candidates"]) for row in inventory["reports"]),
               "share_timeline_approved": False, "inventory_sha256": digest(data)}
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({"script_sha256": digest(Path(__file__)), "outputs": {path.name: digest(path) for path in output.iterdir()}}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), **summary}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
