"""Index retained official filing text without deriving financial values."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TERMS = ("营业收入", "净利润", "经营活动产生的现金流量净额", "现金流量表", "资产负债表", "股本")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, help="PDF path, relative to repository root or absolute")
    parser.add_argument("--term", action="append", dest="terms", help="Keyword to index; repeatable")
    parser.add_argument("--pages", nargs="*", type=int, help="One-based pages to emit after the keyword index")
    args = parser.parse_args()
    source = args.source if args.source.is_absolute() else ROOT / args.source
    source = source.resolve()
    reader = PdfReader(str(source))
    terms = tuple(args.terms or DEFAULT_TERMS)
    hits: dict[str, list[int]] = {term: [] for term in terms}
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        for term in terms:
            if term in text:
                hits[term].append(index)
    payload: dict[str, object] = {
        "source": str(source.relative_to(ROOT)),
        "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
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
