#!/usr/bin/env python3
"""Archive 2012 comparative balance rows disclosed in the 2013 600519 annual report.

This is a source-extraction step only. It never treats a blank balance-sheet
row as zero and never approves an operating-NWC convention, valuation or trade.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pypdfium2 as pdfium
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "runtime/historical-filing-index/20260909T061926130764Z/pdfs/600519-63720184.pdf"
PDF_SHA256 = "26524de9281264e149c23bdc618a32820678c8d07c5dc7c88cbc7e19b3df0bff"
CAPITAL = ROOT / "runtime/strategy-validation/moutai-historical-capital-20260909T153535637673Z/evidence.json"
CAPITAL_SHA256 = "9e1e49492b4877f47627c6a4575a77abe306d659880536bc213f3198a17923c8"
AMOUNT = re.compile(r"(?<![\d.])-?(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}(?!\d)")
FIELDS = {
    "accounts_receivable": "应收账款",
    "notes_receivable": "应收票据",
    "inventory": "存货",
    "prepayments": "预付款项",
    "accounts_payable": "应付账款",
    "notes_payable": "应付票据",
    "advance_receipts": "预收款项",
    "payroll_payable": "应付职工薪酬",
    "other_payables": "其他应付款",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def extract_pair(text: str, label: str) -> tuple[str, str] | None:
    """Read the two adjacent balance-sheet amounts after an exact row label."""
    match = re.search(r"\s*".join(re.escape(char) for char in label) + r".{0,140}", normalized(text))
    if match is None:
        return None
    amounts = AMOUNT.findall(match.group())
    if len(amounts) < 2:
        return None
    return tuple(amount.replace(",", "") for amount in amounts[:2])


def pdfium_pages(path: Path, pages: tuple[int, ...]) -> str:
    document = pdfium.PdfDocument(path)
    try:
        result = []
        for page_number in pages:
            page = document[page_number - 1]
            try:
                text_page = page.get_textpage()
                try:
                    result.append(text_page.get_text_range())
                finally:
                    text_page.close()
            finally:
                page.close()
        return "\n".join(result)
    finally:
        document.close()


def build() -> dict:
    if digest(PDF) != PDF_SHA256 or digest(CAPITAL) != CAPITAL_SHA256:
        raise ValueError("Pinned annual filing or capital evidence changed")
    capital = json.loads(CAPITAL.read_text(encoding="utf-8"))
    row = next(item for item in capital["rows"] if item["source_id"] == "cninfo:63720184")
    pages = tuple(row["statement_pages"])
    primary = "\n".join(PdfReader(PDF).pages[page_number - 1].extract_text() for page_number in pages)
    secondary = pdfium_pages(PDF, pages)
    extracted = {}
    for field, label in FIELDS.items():
        first, second = extract_pair(primary, label), extract_pair(secondary, label)
        current = row["facts"][field]["value_cny"]
        # A current-year blank was already position-checked by the capital
        # extractor. Never let a following row's amounts fill it by proximity.
        if current is None or first is None or second is None:
            extracted[field] = {
                "label": label,
                "current_cny": current,
                "comparative_2012_cny": None,
                "status": "blank_or_unparseable_comparative_is_unknown",
            }
            continue
        if first != second:
            raise ValueError(f"Decoder disagreement for {field}")
        current_from_row, comparative = first
        if current is None or Decimal(current_from_row) != Decimal(current):
            raise ValueError(f"Current-column crosscheck failed for {field}")
        extracted[field] = {
            "label": label,
            "current_cny": current_from_row,
            "comparative_2012_cny": comparative,
            "status": "dual_decoder_and_current_column_crosschecked",
        }
    unresolved = [field for field, item in extracted.items() if item["comparative_2012_cny"] is None]
    return {
        "symbol": "600519",
        "source_id": "cninfo:63720184",
        "report_period": "2013-12-31",
        "comparative_period": "2012-12-31",
        "source_url": "https://static.cninfo.com.cn/finalpage/2014-03-25/63720184.PDF",
        "source_path": str(PDF.relative_to(ROOT)),
        "source_sha256": PDF_SHA256,
        "statement_pages": list(pages),
        "fields": extracted,
        "unresolved_fields": unresolved,
        "comparative_nwc_input_complete": not unresolved,
        "operating_nwc_approved": False,
        "formal_fair_value": None,
        "trade_approved": False,
        "limitations": [
            "Comparative figures are disclosed within the 2013 annual report and were available with that report; they are not a separately archived 2012 filing.",
            "The selected rows have not been classified as operating versus financial assets or liabilities.",
            "A blank or unparseable row remains unknown and cannot be silently used as zero.",
            "This receipt does not select a cash-tax scope, share denominator, cost of capital, execution policy or benchmark.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    result = build()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output_dir or ROOT / "runtime/strategy-validation" / f"moutai-2012-comparative-nwc-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    evidence = output / "evidence.json"
    evidence.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({
        "script_sha256": digest(Path(__file__)),
        "evidence_sha256": digest(evidence),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "complete": result["comparative_nwc_input_complete"],
                      "unresolved": result["unresolved_fields"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
