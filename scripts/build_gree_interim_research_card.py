#!/usr/bin/env python3
"""Build a hash-bound, R0 research card from Gree's 2026 H1 CNINFO filing.

This deliberately records issuer-disclosed facts and review boundaries only.
It is a shallow research-priority output, not a valuation model or trade signal.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "runtime/company-research/000651-official-interim-20260917/1225515004.pdf"
PDF_SHA256 = "50da2e03fddbe9dd424d8fe7881f47fb34efa5d38c96aa9449c12e445c3b2dec"
SOURCE_URL = "https://static.cninfo.com.cn/finalpage/2026-08-27/1225515004.PDF"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build() -> dict:
    if not PDF.is_file() or digest(PDF) != PDF_SHA256:
        raise ValueError("Pinned CNINFO interim report is missing or changed")
    return {
        "symbol": "000651",
        "company_name": "珠海格力电器股份有限公司",
        "assessment_version": "gree-interim-r0-research-card-v1",
        "research_status": "priority_for_shallow_research",
        "assessment_scope": "issuer H1 fact review only; no valuation, portfolio sizing, or trade recommendation",
        "issuer_filing": {
            "source_id": "cninfo:1225515004",
            "source_url": SOURCE_URL,
            "published_date": "2026-08-27",
            "period_end": "2026-06-30",
            "raw_file_path": str(PDF.relative_to(ROOT)),
            "raw_file_hash": PDF_SHA256,
            "report_pages": {"key_metrics": 7, "asset_liability_summary": 25,
                             "balance_sheet": [52, 53], "cash_note": 109,
                             "contract_liability_note": 138, "interest_bearing_debt": 167},
        },
        "issuer_disclosed_facts_cny": {
            "h1_revenue": "89397522501.21",
            "h1_parent_net_profit": "13277590882.57",
            "h1_parent_ex_nonrecurring_profit": "12706672720.90",
            "h1_operating_cash_flow": "18808832392.46",
            "gross_cash": "128248277441.37",
            "cash_and_cash_equivalents": "35699553592.36",
            "restricted_cash": "13963044908.63",
            "short_term_borrowings": "79719240399.52",
            "current_portion_noncurrent_liabilities": "1134773411.03",
            "long_term_borrowings": "2128656424.92",
            "issuer_disclosed_interest_bearing_liabilities": "84635545410.92",
            "contract_liabilities": "8474270795.66",
            "prior_year_end_contract_liabilities": "15206576385.44",
        },
        "issuer_disclosed_changes": {
            "h1_revenue_yoy_percent": "-8.15",
            "h1_parent_net_profit_yoy_percent": "-7.87",
            "h1_parent_ex_nonrecurring_profit_yoy_percent": "-8.89",
            "h1_operating_cash_flow_yoy_percent": "-33.60",
            "weighted_average_roe_percent": "8.68",
            "contract_liabilities_change_percent": "-44.23",
        },
        "interpretation_boundaries": [
            "Gross cash is not distributable cash: the filing separately identifies restricted cash, non-cash-equivalent deposits and finance-related balances.",
            "Interest-bearing-liability aggregation is the issuer's disclosure and is not a net-debt calculation; financial subsidiary balances and liquidity structure require a dedicated scope review.",
            "The decline in contract liabilities is a working-capital and channel-demand question, not by itself evidence of a permanent business deterioration.",
            "H1 financial statements are unaudited, as disclosed by the issuer.",
        ],
        "review_risks": [
            "Revenue, parent profit, ex-nonrecurring profit and operating cash flow all declined year on year.",
            "Overseas revenue and the consumer HVAC market were described by the issuer as under pressure.",
            "Large financial assets, restricted cash and interest-bearing liabilities make a simplistic net-cash valuation unreliable.",
        ],
        "next_verification_events": [
            "Obtain the next statutory financial disclosure and reconcile revenue, margin, operating cash flow and contract-liability movement.",
            "Map financial-subsidiary assets/liabilities, restricted cash, debt and maturities before any enterprise or equity value bridge.",
            "Review capital allocation, related-party disclosures, dividends and share changes from primary documents.",
        ],
        "formal_fair_value": None,
        "valuation_approved": False,
        "simulation_eligible": False,
        "trade_approved": False,
        "live_eligible": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = build()
    output = args.output or ROOT / "runtime/company-research" / (
        "000651-r0-research-card-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    output.mkdir(parents=True, exist_ok=False)
    evidence = output / "evidence.json"
    evidence.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps({
        "script_sha256": digest(Path(__file__)), "evidence_sha256": digest(evidence),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    pointer = ROOT / "runtime/company-research/000651-r0-research-card-latest.json"
    pointer.write_text(json.dumps({"path": str(output.relative_to(ROOT)), "sha256": digest(evidence)},
                                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "research_status": result["research_status"],
                      "trade_approved": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
