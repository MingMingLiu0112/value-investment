#!/usr/bin/env python3
"""Reconcile the 2025 audited related-party deposit schedule to the next filing.

This is a scope reconciliation only.  It establishes that the schedule's
principal and accrued-interest rows agree with the consolidated balance-sheet
opening comparator within the scanned-table rounding bound; it does not split
industrial and financial operating costs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from extract_moutai_finance_transaction_note import build_evidence


ANNUAL_COMPARATOR = ROOT / "runtime/historical-filing-index/20260909T033444358365Z/pdfs/600519-1225475868.pdf"
ANNUAL_COMPARATOR_SHA256 = "0e10aa26be46b1cf3cd03f06e834c7fb98d5dd0d661b96f8fddd4af7e846a4f6"
COMPARATOR_PAGE = 27
COMPARATOR_VALUE = Decimal("18038383776.30")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_reconciliation() -> dict:
    if digest(ANNUAL_COMPARATOR) != ANNUAL_COMPARATOR_SHA256:
        raise ValueError("2026 interim report raw file changed")
    text = PdfReader(ANNUAL_COMPARATOR).pages[COMPARATOR_PAGE - 1].extract_text().replace(" ", "").replace("\n", "")
    if "吸收存款及同业存放28" not in text or "18,038,383,776.30" not in text:
        raise ValueError("Expected annual-comparator balance-sheet cells are absent")
    extracted = build_evidence()
    included = [row for row in extracted["rows"] if row["item"] in {"吸收存款及同业存放", "应付利息"}]
    schedule_closing = sum((Decimal(row["closing"].replace(",", "")) for row in included), Decimal()) * Decimal("10000")
    difference = COMPARATOR_VALUE - schedule_closing
    # Four scanned cells are rounded to 0.01 in CNY 10,000 units.
    rounding_bound = Decimal(len(included)) * Decimal("50") + Decimal("0.005")
    if abs(difference) > rounding_bound:
        raise ValueError("2025 related-party schedule does not reconcile within disclosed rounding")
    return {
        "symbol": "600519",
        "period_end": "2025-12-31",
        "schedule": {
            "source_id": extracted["source_id"],
            "raw_file_sha256": extracted["raw_file_sha256"],
            "included_rows": [{key: row[key] for key in ("counterparty_scope", "item", "closing")} for row in included],
            "closing_cny": str(schedule_closing),
        },
        "annual_comparator": {
            "source_id": "cninfo:1225475868",
            "source_url": "https://static.cninfo.com.cn/finalpage/2026-08-15/1225475868.PDF",
            "raw_file": str(ANNUAL_COMPARATOR.relative_to(ROOT)),
            "raw_file_sha256": ANNUAL_COMPARATOR_SHA256,
            "physical_page": COMPARATOR_PAGE,
            "field": "吸收存款及同业存放",
            "opening_cny": str(COMPARATOR_VALUE),
        },
        "reconciliation": {"difference_cny": str(difference), "rounding_bound_cny": str(rounding_bound), "within_rounding": True},
        "conclusion": "The 2025 audited related-party schedule reconciles to the following interim report's 2025 opening consolidated deposit balance within table rounding.",
        "limitations": [
            "This reconciles the disclosed deposit liability balance, including accrued interest, not internal deposits held by the issuer.",
            "It does not identify consolidation eliminations or allocate financial-company shared SG&A, taxes or cash flows.",
            "The reconciled liability is not distributable cash, debt for industrial WACC, or a direct equity-value adjustment.",
        ],
        "scope_approved": False,
        "valuation_approved": False,
        "trade_approved": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = args.output_dir or ROOT / "runtime/company-research" / f"600519-finance-2025-reconciliation-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    result = build_reconciliation()
    evidence = output / "evidence.json"
    evidence.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({"outputs": {"evidence.json": digest(evidence)}}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pointer = ROOT / "runtime/company-research/600519-finance-2025-reconciliation-latest.json"
    pointer.write_text(json.dumps({"path": str(output.relative_to(ROOT)), "sha256": digest(evidence)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), **result["reconciliation"], "scope_approved": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
