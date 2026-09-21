#!/usr/bin/env python3
"""Locate 2025 parent-equity and share disclosures in the archived issuer PDF."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pypdfium2 as pdfium
from pypdf import PdfReader
from build_moutai_consolidated_equity_inputs import annual_report_metadata


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "runtime/historical-filing-index/20260909T033444358365Z/pdfs/600519-1225114741.pdf"
REPORT_SHA256 = "474905deeaf0f875fc0a1b097a626c0c7852c427faadc5d7fc7816cbf45ea288"
LABELS = ("归属于上市公司股东的净资产", "归属于母公司所有者权益合计", "总股本", "股本")


def compact(value: str) -> str:
    return "".join(value.split())


def excerpt(value: str, label: str) -> str:
    index = value.find(label)
    if index < 0:
        return ""
    return value[max(0, index - 160):index + 420]


def main() -> int:
    metadata = annual_report_metadata()
    if hashlib.sha256(REPORT.read_bytes()).hexdigest() != REPORT_SHA256:
        raise ValueError("Pinned 2025 annual report changed")
    reader = PdfReader(str(REPORT))
    candidates: list[dict[str, object]] = []
    with pdfium.PdfDocument(str(REPORT)) as document:
        if len(reader.pages) != len(document):
            raise ValueError("PDF decoders disagree on page count")
        for index, page in enumerate(reader.pages):
            pypdf_text = compact(page.extract_text() or "")
            pdfium_page = document[index]
            text_page = pdfium_page.get_textpage()
            try:
                pdfium_text = compact(text_page.get_text_range())
            finally:
                text_page.close()
                pdfium_page.close()
            for label in LABELS:
                if label in pypdf_text or label in pdfium_text:
                    candidates.append({
                        "physical_page": index + 1,
                        "label": label,
                        "pypdf_found": label in pypdf_text,
                        "pdfium_found": label in pdfium_text,
                        "pypdf_excerpt": excerpt(pypdf_text, label),
                        "pdfium_excerpt": excerpt(pdfium_text, label),
                    })
    if not candidates:
        raise ValueError("No required labels found in the pinned annual report")
    output = ROOT / "runtime/company-research" / (
        "600519-2025-parent-equity-probe-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    )
    output.mkdir(parents=True, exist_ok=False)
    evidence = {
        "symbol": "600519",
        "report_period": "2025-12-31",
        "source": {
            **metadata,
            "path": str(REPORT.relative_to(ROOT)),
            "sha256": REPORT_SHA256,
        },
        "probe_scope": "dual-decoder label and excerpt location only; no value promotion or valuation",
        "candidates": candidates,
        "valuation_approved": False,
        "trade_approved": False,
    }
    path = output / "evidence.json"
    path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "outputs": {"evidence.json": hashlib.sha256(path.read_bytes()).hexdigest()},
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "candidates": len(candidates)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
