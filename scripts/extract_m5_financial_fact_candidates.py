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
SECTION_HEADINGS = (*HEADINGS, "母公司资产负债表", "母公司利润表", "母公司现金流量表")
FACT_PATTERNS = {
    "consolidated_balance_sheet": {
        "monetary_funds": re.compile(r"(?m)^货币资金\s+1\s+([-\d,]+\.\d{2})\s+[-\d,]+\.\d{2}"),
    },
    "consolidated_income_statement": {
        "operating_revenue": re.compile(r"(?m)^其中：营业收入\s+43\s+([-\d,]+\.\d{2})\s+[-\d,]+\.\d{2}"),
        "operating_cost": re.compile(r"(?m)^其中：营业成本\s+43\s+([-\d,]+\.\d{2})\s+[-\d,]+\.\d{2}"),
        "net_profit": re.compile(r"五、净利润[^\n]{0,45}\n[^\n]{0,8}\s+([-\d,]+\.\d{2})\s+[-\d,]+\.\d{2}"),
    },
    "consolidated_cash_flow_statement": {
        "cash_received_from_sales": re.compile(r"(?m)^销售商品、提供劳务收到的现金\s+([-\d,]+\.\d{2})\s+[-\d,]+\.\d{2}"),
    },
}
SECTION_BY_HEADING = dict(zip(HEADINGS, FACT_PATTERNS))


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
    section = None
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
        boundaries = sorted(
            (match.start(), match.group(0))
            for heading in SECTION_HEADINGS
            for match in re.finditer(r"(?m)^" + re.escape(heading) + r"$", text)
        )
        starts = [(0, section), *[(position, SECTION_BY_HEADING.get(heading)) for position, heading in boundaries]]
        for index, (start, active_section) in enumerate(starts):
            end = starts[index + 1][0] if index + 1 < len(starts) else len(text)
            if active_section is None:
                continue
            segment = text[start:end]
            for field, pattern in FACT_PATTERNS[active_section].items():
                if any(item["field"] == field for item in numeric_candidates):
                    continue
                match = pattern.search(segment)
                if match:
                    numeric_candidates.append({
                        "field": field,
                        "value": match.group(1).replace(",", ""),
                        "unit": "CNY",
                        "unit_basis": "yuan",
                        "statement_scope": "consolidated",
                        "statement_type": active_section,
                        "column_basis": "current_period_first_column",
                        "page_number": page_number,
                        "source_line": match.group(0).replace("\n", " ")[:500],
                        "page_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                        "verification_status": "PENDING_HUMAN_FINANCIAL_FACT_VERIFICATION",
                    })
        if boundaries:
            section = SECTION_BY_HEADING.get(boundaries[-1][1])
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
