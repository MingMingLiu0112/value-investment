#!/usr/bin/env python3
"""Verify scope and arithmetic of the 2026 daily-related-transactions notice."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "runtime/company-research/600519-daily-related-transactions-20260911T074452Z"
PDF_SHA256 = "bb56bf63969359a55f5dbca20f5164b174029221ad6fbc4959ceacfd54527784"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_evidence() -> dict:
    pdf = SOURCE / "600519-1225114727.pdf"
    pages = json.loads((SOURCE / "extracted-pages.json").read_text(encoding="utf-8"))
    if digest(pdf) != PDF_SHA256 or len(pages) != 5:
        raise ValueError("Related-transactions source changed")
    text = {row["physical_page"]: row["text"] for row in pages}
    scope = "不含本公司及控股子公司、分公司"
    if scope not in text[1]:
        raise ValueError("Notice scope exclusion is absent")
    expected = {
        "production_and_trade": ["19.65", "4.28", "1.45", "0.49", "0.15", "59.63"],
        "employee_and_service": ["0.86", "0.01", "0.01", "0.74", "0.09"],
        "culture_promotion": ["2.20", "1.40", "1.10"],
    }
    for value in [item for values in expected.values() for item in values]:
        if value not in text[2] + text[3]:
            raise ValueError(f"Expected non-tax forecast amount missing: {value}")
    totals = {name: str(sum((Decimal(value) for value in values), Decimal())) for name, values in expected.items()}
    total = sum((Decimal(value) for value in totals.values()), Decimal())
    if total != Decimal("92.06"):
        raise ValueError("Expected related-transaction total changed")
    return {
        "symbol": "600519", "source_id": "cninfo:1225114727",
        "source_url": "https://static.cninfo.com.cn/finalpage/2026-04-17/1225114727.PDF",
        "raw_file_sha256": PDF_SHA256, "period": "2026 annual forecast", "unit": "CNY 100 million, tax-exclusive",
        "counterparty_scope": "Moutai Group and controlled subsidiaries, excluding issuer and its controlled subsidiaries/branches",
        "scope_exclusion_verbatim": scope,
        "category_totals_cny_100million": totals, "total_cny_100million": str(total),
        "pricing": "government price/guidance, comparable independent market or transaction price, otherwise reasonable cost plus reasonable profit",
        "limitations": [
            "Amounts are 2026 expected transaction caps, not actual expenses, cash flows or segment allocations.",
            "The notice excludes the issuer and its controlled subsidiaries, so it does not provide a financial-company controlled-subsidiary cost allocation.",
            "Expected sales and purchases cannot be directly netted into industrial FCFF or used as a fair-value adjustment.",
        ],
        "scope_approved": False, "valuation_approved": False, "trade_approved": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    output = args.output_dir or ROOT / "runtime/company-research" / f"600519-daily-related-transactions-scope-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    output.mkdir(parents=True, exist_ok=False)
    result = build_evidence()
    evidence = output / "evidence.json"
    evidence.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({"outputs": {"evidence.json": digest(evidence)}}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "total_cny_100million": result["total_cny_100million"], "scope_approved": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
