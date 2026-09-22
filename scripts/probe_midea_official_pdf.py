"""Locate FCFF-relevant pages in the retained official Midea filing without deriving values."""
from __future__ import annotations

import hashlib
import json
import argparse
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "runtime" / "midea-2025-official.pdf"
TERMS = ("现金流量表", "购建固定资产", "折旧", "财务费用", "所得税费用", "资产负债表", "股本")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pages", nargs="*", type=int,
                        help="One-based pages to emit after the keyword index.")
    args = parser.parse_args()
    reader = PdfReader(str(SOURCE))
    hits: dict[str, list[int]] = {term: [] for term in TERMS}
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        for term in TERMS:
            if term in text:
                hits[term].append(index)
    payload = {
        "source": str(SOURCE.relative_to(ROOT)),
        "sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "pages": len(reader.pages),
        "keyword_pages": hits,
    }
    if args.pages:
        payload["page_text"] = {
            str(page): reader.pages[page - 1].extract_text() or ""
            for page in args.pages
            if 1 <= page <= len(reader.pages)
        }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
