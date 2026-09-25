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
import re

from pypdf import PdfReader


HEADINGS = ("合并资产负债表", "合并利润表", "合并现金流量表")
FACT_PATTERNS = {
    "operating_revenue": re.compile(r"营业收入\s+43\s+([-\d,]+\.\d{2})"),
    "operating_cost": re.compile(r"营业成本\s+43\s+([-\d,]+\.\d{2})"),
    "net_profit": re.compile(r"四、净利润.*?\s+([-\d,]+\.\d{2})\s+[-\d,]+\.\d{2}", re.S),
    "cash_received_from_sales": re.compile(r"销售商品、提供劳务收到的现金\s+([-\d,]+\.\d{2})"),
    "cash_and_cash_equivalents": re.compile(r"货币资金\s+1\s+([-\d,]+\.\d{2})"),
}


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
    numeric_candidates = []
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
        for field, pattern in FACT_PATTERNS.items():
            if any(item["field"] == field for item in numeric_candidates):
                continue
            match = pattern.search(text)
            if match:
                line = match.group(0).replace("\n", " ")
                numeric_candidates.append({
                    "field": field,
                    "value": match.group(1).replace(",", ""),
                    "unit": "CNY",
                    "page_number": page_number,
                    "source_line": line[:500],
                    "page_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    "verification_status": "PENDING_HUMAN_FINANCIAL_FACT_VERIFICATION",
                })
    payload = {
        "schema_version": "m5-financial-fact-candidate-extraction-v1",
        "symbol": args.symbol,
        "announcement_id": args.announcement_id,
        "published_at": args.published_at,
        "pdf": {"path": str(pdf), "sha256": digest(pdf), "page_count": len(reader.pages)},
        "matched_statement_pages": hits,
        "verification_status": "PENDING_HUMAN_FINANCIAL_FACT_VERIFICATION",
        "numeric_facts": numeric_candidates,
        "action": "no_order",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "sha256": digest(output), "statement_page_count": len(hits), "action": "no_order"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
