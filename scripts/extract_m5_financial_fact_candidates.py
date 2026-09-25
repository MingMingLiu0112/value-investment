"""Extract page-addressable financial-statement candidates from an archived PDF.

Text extraction is evidence navigation only.  It deliberately emits no verified
numeric facts, valuations, or investment decisions.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from pypdf import PdfReader


HEADINGS = ("合并资产负债表", "合并利润表", "合并现金流量表")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--announcement-id", required=True)
    parser.add_argument("--published-at", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    pdf = args.pdf.resolve()
    output = args.output.resolve()
    if not pdf.is_file() or output.exists():
        raise ValueError("PDF must exist and output must be new")
    reader = PdfReader(str(pdf))
    hits = []
    for page_number, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ""
        matched = tuple(item for item in HEADINGS if item in text)
        if matched:
            hits.append({
                "page_number": page_number,
                "headings": list(matched),
                "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "excerpt": text[:1200],
            })
    payload = {
        "schema_version": "m5-financial-fact-candidate-extraction-v1",
        "symbol": args.symbol,
        "announcement_id": args.announcement_id,
        "published_at": args.published_at,
        "pdf": {"path": str(pdf), "sha256": digest(pdf), "page_count": len(reader.pages)},
        "matched_statement_pages": hits,
        "verification_status": "PENDING_HUMAN_FINANCIAL_FACT_VERIFICATION",
        "numeric_facts": [],
        "action": "no_order",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "sha256": digest(output), "statement_page_count": len(hits), "action": "no_order"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
