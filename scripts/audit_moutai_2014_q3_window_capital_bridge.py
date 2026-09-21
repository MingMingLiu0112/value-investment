#!/usr/bin/env python3
"""Audit disclosed capital-event coverage after 600519's 2014 Q3 report.

The result is intentionally narrower than a clean-surplus equity rollforward:
it only establishes the archived CNINFO index/document coverage and whether an
explicit capital-action term was found in the reviewed documents.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pypdf import PdfReader
import pypdfium2 as pdfium


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "runtime/historical-filing-index/20260920-2014q3-bridge/cninfo-index.json"
INDEX_SHA256 = "a8aca6ec26cd74c429568c6f8925accf4edc903a2e7ebb3aa3f55df5185f10fa"
Q3 = ROOT / "runtime/strategy-validation/moutai-2014-q3-parent-equity-20260920T044648Z/evidence.json"
DOCS = {
    "1200409385": "77fd155a4226d22a954ff306986cd5b872882350fc300ca788b9b6a9d34f7e7c",
    "1200453935": "04a5ee0d449ccb065c6a2d1a772f02af4197c9bc262272328c1439ee24625968",
    "1200474284": "34d1cf3020f213da5f9d1eaf740d4a636cfe918f10a2015183f07b7bb7f95eae",
    "1200474283": "6e8abe20dace1ec1dd2ee060217257ea3d342e46bb1ec5d1cd1c83f28bd504dd",
}
DOC_DIR = ROOT / "evidence-archive/cninfo/600519/2014-q3-window-announcements"
FIRST_DECISION_AT = "2015-01-05T15:00:00+08:00"
CAPITAL_TERMS = (
    "\u80a1\u672c", "\u5229\u6da6\u5206\u914d", "\u56de\u8d2d", "\u589e\u53d1",
    "\u914d\u80a1", "\u80a1\u4efd\u53d8\u52a8", "\u9001\u80a1", "\u8f6c\u589e",
    "\u80a1\u6743\u6fc0\u52b1",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(path: Path) -> str:
    return str(path.relative_to(ROOT))


def decode_document(path: Path) -> tuple[str, str]:
    primary = "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    secondary_pages = []
    with pdfium.PdfDocument(path) as document:
        for page in document:
            textpage = page.get_textpage()
            try:
                secondary_pages.append(textpage.get_text_range())
            finally:
                textpage.close()
                page.close()
    secondary = "\n".join(secondary_pages)
    if min(len(primary), len(secondary)) < 100:
        raise ValueError("Document text extraction is insufficient for term review")
    return primary, secondary


def build() -> dict:
    if digest(INDEX) != INDEX_SHA256:
        raise ValueError("CNINFO bridge index changed")
    q3 = json.loads(Q3.read_text(encoding="utf-8"))
    if q3["available_at"] > FIRST_DECISION_AT:
        raise ValueError("Q3 fact is unavailable before registered window")
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    announcements = index["announcements"]
    if index["totalAnnouncement"] != 12 or len(announcements) != 12:
        raise ValueError("Bridge index is incomplete")
    dates = []
    by_id = {}
    for row in announcements:
        if row["secCode"] != "600519" or str(row["announcementId"]) in by_id:
            raise ValueError("Bridge index has wrong issuer or duplicate announcement")
        date = datetime.fromtimestamp(row["announcementTime"] / 1000, timezone(timedelta(hours=8))).date().isoformat()
        if not "2014-10-31" <= date < "2015-01-05":
            raise ValueError("Bridge index returned an announcement outside the expected period")
        dates.append(date)
        by_id[str(row["announcementId"])] = {"published_date": date, "title": row["announcementTitle"]}
    if not set(DOCS).issubset(by_id):
        raise ValueError("Reviewed document IDs are absent from bridge index")
    reviewed_documents = []
    for announcement_id, expected_hash in DOCS.items():
        path = DOC_DIR / f"600519-{announcement_id}.pdf"
        if digest(path) != expected_hash:
            raise ValueError("Reviewed bridge document changed: " + announcement_id)
        primary, secondary = decode_document(path)
        primary_hits = [term for term in CAPITAL_TERMS if term in primary]
        secondary_hits = [term for term in CAPITAL_TERMS if term in secondary]
        if primary_hits or secondary_hits:
            raise ValueError("Potential capital-action term requires manual source classification: " + announcement_id)
        reviewed_documents.append({
            "announcement_id": announcement_id,
            "published_date": by_id[announcement_id]["published_date"],
            "title": by_id[announcement_id]["title"],
            "source_path": relative(path),
            "raw_file_hash": expected_hash,
            "pypdf_text_characters": len(primary),
            "pdfium_text_characters": len(secondary),
            "capital_term_hits": {"pypdf": primary_hits, "pdfium": secondary_hits},
        })
    title_hits = [
        {"announcement_id": item["announcementId"], "title": item["announcementTitle"]}
        for item in announcements if any(term in item["announcementTitle"] for term in CAPITAL_TERMS)
    ]
    if title_hits:
        raise ValueError("Bridge index contains an explicit capital-action title")
    return {
        "audit_version": "moutai-2014-q3-window-capital-bridge-v1",
        "symbol": "600519",
        "status": "announcements_covered_no_explicit_capital_action_detected_clean_surplus_unresolved",
        "window": {"after_report_date": "2014-10-31", "before_first_decision_at": FIRST_DECISION_AT},
        "index_coverage": {
            "announcement_count": len(announcements),
            "first_published_date": min(dates),
            "last_published_date": max(dates),
            "title_capital_term_hits": title_hits,
        },
        "reviewed_documents": reviewed_documents,
        "conclusion": "No explicit capital-action term was found in the complete index titles or the four decision/meeting documents selected for content review. This supports continuity of the reported Q3 share count only within the stated disclosure coverage.",
        "limitations": [
            "No-term detection is not a complete clean-surplus equity rollforward and does not establish unannounced accounting changes, OCI, or all balance-sheet movements.",
            "The audit does not produce a decision-date parent equity amount, historical fair value, or executable trade rule.",
        ],
        "formal_fair_value": None,
        "valuation_approved": False,
        "historical_trade_backtest_complete": False,
        "simulation_eligible": False,
        "trade_approved": False,
        "live_eligible": False,
        "inputs": {
            relative(INDEX): digest(INDEX),
            relative(Q3): digest(Q3),
            **{relative(DOC_DIR / f"600519-{key}.pdf"): value for key, value in DOCS.items()},
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    result = build()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output_dir or ROOT / "runtime/strategy-validation" / f"moutai-2014-q3-window-capital-bridge-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    evidence = output / "evidence.json"
    evidence.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({
        "script": relative(Path(__file__)),
        "script_sha256": digest(Path(__file__)),
        "evidence_sha256": digest(evidence),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "status": result["status"], "reviewed_documents": len(result["reviewed_documents"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
