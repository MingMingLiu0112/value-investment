#!/usr/bin/env python3
"""Archive a reproducible manual extraction from the 2025 finance transaction note.

The report table is a scanned page.  Values below are transcribed from the
rendered page with fixed source/page coordinates and are deliberately kept out
of the valuation engine: it is not a complete consolidation-elimination or
shared-cost allocation schedule.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "runtime/company-research/600519-finance-transaction-note-20260911/600519-1225114715.pdf"
PAGE = ROOT / "runtime/company-research/600519-finance-transaction-note-20260911/page4.png"
SOURCE_SHA256 = "e6d6e55688a8b140128d54459140a58b0c509c8a1065eceb1c403c61539106df"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def amount(value: str) -> Decimal:
    return Decimal(value.replace(",", ""))


def build_evidence() -> dict:
    if digest(SOURCE) != SOURCE_SHA256:
        raise ValueError("Finance transaction note raw file changed")
    if not PAGE.is_file():
        raise FileNotFoundError(PAGE)
    # PDF page 3 is rendered to the locally named page4.png image.  The image
    # is retained to make this scanned-table transcription independently checkable.
    rows = [
        {"counterparty_scope": "中国贵州茅台酒厂（集团）有限责任公司及下属子集团",
         "item": "吸收存款及同业存放", "opening": "1447827.77", "increase": "9807831.33",
         "decrease": "10422755.86", "closing": "832903.24"},
        {"counterparty_scope": "茅台集团", "item": "应付利息", "opening": "183.71", "increase": "7431.06",
         "decrease": "7448.18", "closing": "166.59"},
        {"counterparty_scope": "茅台集团子公司", "item": "吸收存款及同业存放", "opening": "859153.28", "increase": "4461162.77",
         "decrease": "4356165.44", "closing": "964150.61"},
        {"counterparty_scope": "茅台集团子公司", "item": "应付利息", "opening": "3121.12", "increase": "10146.43",
         "decrease": "6649.62", "closing": "6617.93"},
        {"counterparty_scope": "茅台集团子公司", "item": "发放贷款和垫款", "opening": "4276.00", "increase": "0.00",
         "decrease": "1528.00", "closing": "2748.00"},
        {"counterparty_scope": "茅台集团子公司", "item": "应收利息", "opening": "4.77", "increase": "135.27",
         "decrease": "136.98", "closing": "3.06"},
    ]
    for row in rows:
        if amount(row["opening"]) + amount(row["increase"]) - amount(row["decrease"]) != amount(row["closing"]):
            raise ValueError(f"Table arithmetic failed: {row['counterparty_scope']} {row['item']}")
    deposit_closing = sum((amount(row["closing"]) for row in rows if row["item"] == "吸收存款及同业存放"), Decimal())
    return {
        "symbol": "600519",
        "reporting_year": 2025,
        "source_id": "cninfo:1225114715",
        "source_url": "https://static.cninfo.com.cn/finalpage/2026-04-17/1225114715.PDF",
        "raw_file": str(SOURCE.relative_to(ROOT)),
        "raw_file_sha256": SOURCE_SHA256,
        "visual_source": {"path": str(PAGE.relative_to(ROOT)), "pdf_page": 3, "table_title": "关联方交易、存款、贷款等金融业务情况表", "unit": "CNY 10,000"},
        "extraction_method": "manual_visual_transcription_v1",
        "rows": rows,
        "derived": {"related_party_deposit_closing_cny": str(deposit_closing * Decimal("10000"))},
        "valuation_use": "scope_evidence_only",
        "not_used_for_valuation": True,
        "limitations": [
            "The table is limited to the named related-party scopes and does not establish all group internal deposits.",
            "It does not provide consolidation eliminations, financial-company shared SG&A/taxes, or a cost allocation basis.",
            "The closing balance cannot replace issuer-only or consolidated deposit disclosures without a separately evidenced scope bridge.",
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
    output = args.output_dir or ROOT / "runtime/company-research" / f"600519-finance-transaction-extract-{stamp}"
    output.mkdir(parents=True, exist_ok=False)
    evidence = build_evidence()
    path = output / "evidence.json"
    path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({"outputs": {"evidence.json": digest(path)}}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pointer = ROOT / "runtime/company-research/600519-finance-transaction-extract-latest.json"
    pointer.write_text(json.dumps({"path": str(output.relative_to(ROOT)), "sha256": digest(path)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "related_party_deposit_closing_cny": evidence["derived"]["related_party_deposit_closing_cny"], "scope_approved": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
