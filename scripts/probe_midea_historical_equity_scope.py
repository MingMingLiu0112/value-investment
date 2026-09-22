"""Locate historical Midea equity/profit/dividend evidence without deriving values."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
HISTORICAL_DIR = ROOT / "runtime" / "historical-filing-index" / "20260908T041326996681Z" / "pdfs"
TERMS = (
    "归属于母公司股东权益",
    "归属于母公司股东的",
    "净利润",
    "基本每股收益",
    "利润分配",
    "现金分红",
    "现金红利",
    "每股派发现金",
)


def main() -> None:
    rows = []
    for path in sorted(HISTORICAL_DIR.glob("000333-*.pdf")):
        reader = PdfReader(str(path))
        hits = {term: [] for term in TERMS}
        for index, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            for term in TERMS:
                if term in text:
                    hits[term].append(index)
        row = {
            "file": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "pages": len(reader.pages),
            "hits": hits,
        }
        if "--emit-context" in sys.argv:
            balance_pages = hits.get("归属于母公司股东权益", [])
            parent_pages = hits.get("归属于母公司股东的", [])
            dividend_pages = hits.get("现金分红", [])
            chosen = sorted(set(balance_pages[:1] + parent_pages[:1] + dividend_pages[:3]))
            row["contexts"] = {
                str(page): (reader.pages[page - 1].extract_text() or "")
                for page in chosen
            }
        rows.append(row)
    print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
