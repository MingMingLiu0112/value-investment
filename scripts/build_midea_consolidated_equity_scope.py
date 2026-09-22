"""Pin Midea's consolidated listed-equity scope from the retained 2025 annual report."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "runtime" / "midea-2025-official.pdf"
OUT = ROOT / "runtime" / "company-research" / "midea-consolidated-equity-scope-20260922"
POINTER = ROOT / "runtime" / "company-research" / "midea-consolidated-equity-scope-latest.json"


def page_text(reader: PdfReader, page: int) -> str:
    return reader.pages[page - 1].extract_text() or ""


def verify_source(reader: PdfReader, sha256: str) -> None:
    if hashlib.sha256(SOURCE.read_bytes()).hexdigest() != sha256:
        raise ValueError("Retained Midea annual report changed")

    checks = {
        133: ("归属于母公司股东权益合计", "少数股东权益", "223,221,305", "13,202,918"),
        135: ("归属于母公司股东的", "43,945,411"),
        136: ("基本每股收益", "5.80"),
        137: ("经营活动产生", "现金流量净额", "四(64)(h)", "53,345,930"),
        143: ("7,597,145,346"),
        185: ("存放中央银行法定准备金", "751,376"),
        246: ("美的集团财务有限公司", "金融业"),
    }
    for page, phrases in checks.items():
        text = page_text(reader, page)
        missing = [phrase for phrase in phrases if phrase not in text]
        if missing:
            raise ValueError(f"Page {page} no longer contains required phrases: {missing}")


def build_payload() -> dict:
    source_sha256 = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    reader = PdfReader(str(SOURCE))
    verify_source(reader, source_sha256)

    evidence_refs = [
        {"id": "midea_2025_official_consolidated_balance_sheet_page_133",
         "path": str(SOURCE.relative_to(ROOT)), "sha256": source_sha256, "pages": [133],
         "unit": "CNY thousands"},
        {"id": "midea_2025_official_consolidated_income_statement_pages_135_136",
         "path": str(SOURCE.relative_to(ROOT)), "sha256": source_sha256, "pages": [135, 136],
         "unit": "CNY thousands and CNY per share"},
        {"id": "midea_2025_official_consolidated_cashflow_page_137",
         "path": str(SOURCE.relative_to(ROOT)), "sha256": source_sha256, "page": 137,
         "unit": "CNY thousands"},
        {"id": "midea_2025_official_share_capital_page_143",
         "path": str(SOURCE.relative_to(ROOT)), "sha256": source_sha256, "page": 143,
         "unit": "shares"},
        {"id": "midea_2025_official_cash_note_page_185",
         "path": str(SOURCE.relative_to(ROOT)), "sha256": source_sha256, "page": 185,
         "unit": "CNY thousands"},
        {"id": "midea_2025_official_principal_subsidiaries_page_246",
         "path": str(SOURCE.relative_to(ROOT)), "sha256": source_sha256, "page": 246,
         "unit": "ownership percentages"},
    ]

    return {
        "symbol": "000333",
        "as_of_period": "2025-12-31",
        "package_version": "midea-consolidated-equity-scope-v1",
        "source_type": "issuer_annual_report_equity_scope",
        "status": "equity_facts_for_research_not_valuation_approval",
        "financial_scope_approved": False,
        "valuation_status": "VALUATION_NOT_READY",
        "consolidated_equity": {
            "total_equity_cny": "236424223000",
            "attributable_ordinary_equity_cny": "223221305000",
            "minority_equity_cny": "13202918000",
            "issued_share_capital_cny": "7597145000",
            "treasury_stock_carrying_value_cny": "8151117000",
            "issued_share_count": "7597145346",
            "treasury_share_count": None,
        },
        "consolidated_income": {
            "net_profit_cny": "44520196000",
            "attributable_ordinary_net_profit_cny": "43945411000",
            "minority_profit_cny": "574785000",
            "basic_eps_cny": "5.80",
            "diluted_eps_cny": "5.76",
            "fy2025_weighted_ordinary_shares": "7559265000",
            "fy2025_diluted_ordinary_shares": "7608132000",
        },
        "parent_company": {
            "total_equity_cny": "98052670000",
            "net_profit_cny": "29415131000",
        },
        "financial_business_visible_items": {
            "central_bank_required_reserve_cny": "751376000",
            "central_bank_excess_reserve_cny": "72751000",
            "due_from_banks_cny": "42565166000",
            "loans_and_advances_current_cny": "11779217000",
            "loans_and_advances_noncurrent_cny": "622248000",
            "absorbing_deposits_and_interbank_placements_cny": "134110000",
            "finance_company_direct_ownership_pct": "95",
            "finance_company_indirect_ownership_pct": "5",
        },
        "alternative_route_candidate": {
            "model_id": "residual_income_or_equity_value",
            "status": "CANDIDATE_NOT_REGISTERED",
            "reason": (
                "Consolidated attributable ordinary equity, attributable net income and issued A/H shares are "
                "disclosed. Forecast ROE, cost of equity, payout, franchise fade and current outstanding-share "
                "scope are not independently evidenced, so no model input is registered."
            ),
            "required_next_evidence": [
                "Historical and segment-supported ROE/cash-generation assumptions",
                "Dated cost-of-equity range with named evidence",
                "Registered payout and capital-allocation policy",
                "Current ordinary-share denominator excluding treasury shares",
            ],
        },
        "blockers": [
            "standalone_financial_business_statements_not_disclosed",
            "treasury_share_count_not_disclosed",
            "current_valuation_share_scope_not_registered",
            "financial_fact_sources_not_independently_verified",
            "equity_residual_income_assumptions_not_registered",
        ],
        "evidence_refs": evidence_refs,
        "registered_valuation_inputs": {},
        "formal_fair_value": None,
        "valuation_approved": False,
        "trade_approved": False,
        "live_eligible": False,
    }


def main() -> None:
    payload = build_payload()
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "evidence.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    evidence_sha256 = hashlib.sha256(target.read_bytes()).hexdigest()
    (OUT / "manifest.json").write_text(json.dumps({
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "evidence_sha256": evidence_sha256,
        "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
    }, indent=2) + "\n", encoding="utf-8")
    POINTER.write_text(json.dumps({
        "path": OUT.relative_to(ROOT).as_posix(), "sha256": evidence_sha256,
    }, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": target.relative_to(ROOT).as_posix(),
        "sha256": evidence_sha256,
        "status": payload["status"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
