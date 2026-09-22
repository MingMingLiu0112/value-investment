"""Review Shenhua's 2025 IFRS annual report for subsidiary-level pre-tax and tax facts."""
from __future__ import annotations

from decimal import Decimal, localcontext
import hashlib
import json
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "runtime/company-research/shenhua-2025-ifrs-annual-review-20260922/2026033003712.pdf"
SOURCE_URL = "https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0330/2026033003712.pdf"
SOURCE_HASH = "491E701A90B1ECE239B95CE3F3DE27053F420583F2458D81CBE5B21B4607FDC9"
SOURCE_BYTES = 8_479_182
SOURCE_PAGES = 373
OUT = ROOT / "runtime/company-research/shenhua-2025-ifrs-subsidiary-tax-review-20260922"


def source_ref(ref_id: str, page: int, description: str, quoted_facts: list[str]) -> dict:
    return {
        "id": ref_id,
        "path": SOURCE.relative_to(ROOT).as_posix(),
        "url": SOURCE_URL,
        "sha256": SOURCE_HASH,
        "page": page,
        "unit": "CNY millions",
        "description": description,
        "quoted_facts": quoted_facts,
    }


def page_text(reader: PdfReader, page: int, expected: tuple[str, ...]) -> str:
    text = (reader.pages[page - 1].extract_text() or "").replace("\x00", " ").replace("\u200a", " ")
    missing = [value for value in expected if value not in text]
    if missing:
        raise ValueError(f"Page {page} does not contain expected evidence {missing!r}")
    return text


def normalized_text(reader: PdfReader, page: int) -> str:
    return " ".join((reader.pages[page - 1].extract_text() or "").replace("\x00", " ").split())


def build() -> dict:
    if hashlib.sha256(SOURCE.read_bytes()).hexdigest().upper() != SOURCE_HASH:
        raise ValueError("Shenhua 2025 IFRS annual report hash mismatch")
    if SOURCE.stat().st_size != SOURCE_BYTES:
        raise ValueError("Shenhua 2025 IFRS annual report size mismatch")
    reader = PdfReader(str(SOURCE))
    if len(reader.pages) != SOURCE_PAGES:
        raise ValueError("Shenhua 2025 IFRS annual report page count mismatch")

    page_text(reader, 240, ("Profit before income tax", "81,062", "Income tax expense", "(16,559)", "Profit for the year", "64,503"))
    page_text(reader, 294, ("10. INCOME TAX EXPENSE", "Current tax, mainly PRC enterprise income tax", "16,511", "Deferred tax", "(6)", "different tax rates of branches and subsidiaries", "(4,228)"))
    page_text(reader, 295, ("The applicable tax rates of the Group", "Indonesia", "22.0", "Hong Kong, China", "8.25/16.5"))
    page_text(reader, 358, ("44. SUBSIDIARIES (CONTINUED)", "Details of non-wholly owned subsidiaries", "before intragroup eliminations", "Zhunge", "Profit allocated to", "Individually immaterial subsidiaries", "72,891"))
    page_text(reader, 359, ("Revenue", "Expenses", "Profit and total comprehensive", "Zhunge", "Baorixile", "Dingzhou"))
    page_text(reader, 360, ("Revenue", "Expenses", "Profit and total comprehensive", "Shuohuang", "Yuanhai", "Huanghua"))
    page_text(reader, 361, ("Revenue", "Expenses", "Profit and total comprehensive", "Beidian Shengli Company"))
    page_text(reader, 67, ("In 2025, the revenue of Shendong Coal was RMB67,918 million and the operating profit was", "RMB9,253 million", "RMB9,073 million", "RMB7,822 million"))
    page_text(reader, 371, ("CONSOLIDATED STATEMENT OF PROFIT OR LOSS AND", "Profit before income tax", "81,062", "Income tax expenses", "(16,559)", "Non-controlling interests", "10,285"))

    subsidiary_pages = [358, 359, 360, 361]
    absent_terms = ("Profit before income tax", "Income tax expense", "Profit before tax")
    unexpected = []
    for page in subsidiary_pages:
        text = normalized_text(reader, page)
        for term in absent_terms:
            if term in text:
                unexpected.append({"page": page, "term": term})
    if unexpected:
        raise ValueError(f"Unexpected subsidiary-level tax lines found: {unexpected!r}")

    subsidiaries = [
        {
            "name": "Zhunge'er Energy",
            "nci_holding_pct": 42,
            "profit_allocated_to_nci_cny_millions": 2_870,
            "accumulated_nci_cny_millions": 8_682,
            "revenue_cny_millions": 13_016,
            "expenses_cny_millions": 9_129,
            "profit_and_total_comprehensive_income_cny_millions": 6_675,
        },
        {
            "name": "China Energy Baorixile Energy Industrial Co., Ltd.",
            "nci_holding_pct": 43,
            "profit_allocated_to_nci_cny_millions": 1_311,
            "accumulated_nci_cny_millions": 5_240,
            "revenue_cny_millions": 8_183,
            "expenses_cny_millions": 4_311,
            "profit_and_total_comprehensive_income_cny_millions": 2_938,
        },
        {
            "name": "Dingzhou Power",
            "nci_holding_pct": 59,
            "profit_allocated_to_nci_cny_millions": 436,
            "accumulated_nci_cny_millions": 1_897,
            "revenue_cny_millions": 4_423,
            "expenses_cny_millions": 3_474,
            "profit_and_total_comprehensive_income_cny_millions": 733,
        },
        {
            "name": "China Energy Shuohuang Railway Development Co., Ltd.",
            "nci_holding_pct": 47,
            "profit_allocated_to_nci_cny_millions": 3_105,
            "accumulated_nci_cny_millions": 18_589,
            "revenue_cny_millions": 23_061,
            "expenses_cny_millions": 13_920,
            "profit_and_total_comprehensive_income_cny_millions": 6_594,
        },
        {
            "name": "China Energy Yuanhai Shipping Co., Ltd.",
            "nci_holding_pct": 49,
            "profit_allocated_to_nci_cny_millions": 100,
            "accumulated_nci_cny_millions": 3_358,
            "revenue_cny_millions": 3_989,
            "expenses_cny_millions": 3_731,
            "profit_and_total_comprehensive_income_cny_millions": 205,
        },
        {
            "name": "China Energy Huanghua Harbour Administration Co., Ltd.",
            "nci_holding_pct": 30,
            "profit_allocated_to_nci_cny_millions": 522,
            "accumulated_nci_cny_millions": 3_940,
            "revenue_cny_millions": 5_388,
            "expenses_cny_millions": 3_040,
            "profit_and_total_comprehensive_income_cny_millions": 1_711,
        },
        {
            "name": "Beidian Shengli Company",
            "nci_holding_pct": 37,
            "profit_allocated_to_nci_cny_millions": 750,
            "accumulated_nci_cny_millions": 4_568,
            "revenue_cny_millions": 6_677,
            "expenses_cny_millions": 4_244,
            "profit_and_total_comprehensive_income_cny_millions": 2_005,
        },
    ]
    named_nci_profit = sum(item["profit_allocated_to_nci_cny_millions"] for item in subsidiaries)
    named_accumulated_nci = sum(item["accumulated_nci_cny_millions"] for item in subsidiaries)
    consolidated_minority_profit = 10_285
    consolidated_minority_equity = 72_891

    with localcontext() as context:
        context.prec = 30
        effective_tax_rate_pct = format(Decimal(16_559) / Decimal(81_062) * 100, ".9f")

    payload = {
        "symbol": "601088",
        "as_of_period": "2025-12-31",
        "source_type": "hkex_ifrs_annual_report_subsidiary_tax_disclosure_review",
        "source_url": SOURCE_URL,
        "package_version": "shenhua-ifrs-subsidiary-tax-review-v1",
        "status": "ifrs_12_sub_company_summary_reviewed_no_verified_pretax_tax_allocation",
        "valuation_status": "VALUATION_NOT_READY",
        "purpose": (
            "Review the English IFRS annual report against the specific question of whether it "
            "discloses audited pre-tax profit and income tax for each subsidiary. The report gives "
            "summarized IFRS 12 information, but still does not allocate pre-tax profit, tax, and "
            "minority interests entity by entity, so the package leaves the normalized parent "
            "operating-profit model input null."
        ),
        "key_findings": [
            "IFRS Note 44 provides summarized revenue, expenses, and profit and total comprehensive income for each material non-wholly-owned subsidiary, but no separate Profit before income tax or Income tax expense line for any subsidiary.",
            "The summarized information is explicitly before intragroup eliminations, so it cannot be treated as the post-elimination group parent-attributable operating profit.",
            "The consolidated tax reconciliation shows RMB(4,228) million from different tax rates of branches and subsidiaries; uniform-rate or ownership-proportion allocation of tax would ignore this disclosed heterogeneity.",
            "The Directors' Report gives operating profit notes for only Shendong Coal, Shuohuang Railway and Zhunge'er Energy, not a complete subsidiary-by-subsidiary pre-tax/tax/minority allocation for the group.",
        ],
        "consolidated_ifrs_2025_facts": {
            "profit_before_income_tax_cny_millions": 81_062,
            "income_tax_expense_cny_millions": 16_559,
            "profit_for_year_cny_millions": 64_503,
            "minority_profit_cny_millions": consolidated_minority_profit,
            "minority_equity_cny_millions": consolidated_minority_equity,
            "effective_tax_rate_pct": effective_tax_rate_pct,
        },
        "tax_reconciliation_observations": {
            "current_tax_cny_millions": 16_511,
            "deferred_tax_cny_millions": -6,
            "different_tax_rates_effect_cny_millions": -4_228,
            "preferential_rates_noted": "Western-region PRC subsidiaries 15%; overseas rates vary and are disclosed only in aggregate.",
            "conclusion": "The filing proves tax rates differ materially across entities, but does not disclose each entity's pre-tax profit and tax expense.",
        },
        "named_subsidiaries_ifrs_12_2025": subsidiaries,
        "named_subsidiary_reconciliation": {
            "named_profit_allocated_to_nci_cny_millions": named_nci_profit,
            "consolidated_minority_profit_cny_millions": consolidated_minority_profit,
            "profit_residual_cny_millions": consolidated_minority_profit - named_nci_profit,
            "named_accumulated_nci_cny_millions": named_accumulated_nci,
            "consolidated_minority_equity_cny_millions": consolidated_minority_equity,
            "equity_residual_cny_millions": consolidated_minority_equity - named_accumulated_nci,
            "note": "The equity residual equals the disclosed individually immaterial subsidiaries amount, but the profit residual is not allocated by the filing.",
        },
        "partial_major_subsidiary_operating_profit": {
            "disclosure_page": 67,
            "entries": [
                {"name": "Shendong Coal", "revenue_cny_millions": 67_918, "operating_profit_cny_millions": 9_253},
                {"name": "Shuohuang Railway", "revenue_cny_millions": 23_061, "operating_profit_cny_millions": 9_073},
                {"name": "Zhunge'er Energy", "revenue_cny_millions": 13_016, "operating_profit_cny_millions": 7_822},
            ],
            "limitations": [
                "Only three subsidiaries receive operating-profit notes.",
                "The notes give no tax or non-controlling-interest allocation.",
                "Subsidiary operating profit before group elimination is not a substitute for group parent-attributable pre-tax operating profit.",
            ],
        },
        "absence_check": {
            "pages": subsidiary_pages,
            "absent_line_items": list(absent_terms),
            "conclusion": "No subsidiary-level pre-tax or tax line item is disclosed in the IFRS 12 summarized tables.",
        },
        "model_derivations": {
            "normalized_parent_operating_profit": {
                "status": "cannot_derive_from_ifrs_12_or_partial_major_subsidiary_disclosure",
                "candidate_values": {},
                "model_input": None,
                "review_requirement": (
                    "Obtain an audited statutory allocation of pre-tax profit, income tax, and minority "
                    "interests for every relevant subsidiary plus post-elimination parent attribution, or an "
                    "audited group parent-attributable pre-tax operating-profit line. IFRS 12 summarized "
                    "tables and three operating-profit notes are not sufficient."
                ),
            },
            "attributable_net_cash": {
                "status": "outside_this_evidence_package",
                "candidate_values": {},
                "model_input": None,
                "note": "The IFRS subsidiary tables do not allocate cash, restricted deposits or debt to the parent common-equity claim.",
            },
        },
        "evidence_refs": [
            source_ref("shenhua_ifrs_consolidated_profit_page_240", 240, "IFRS consolidated statement of profit or loss and other comprehensive income", ["Profit before income tax 81,062", "Income tax expense (16,559)", "Profit for the year 64,503"]),
            source_ref("shenhua_ifrs_income_tax_note_page_294", 294, "IFRS income tax expense and consolidated tax reconciliation", ["Current tax 16,511", "Deferred tax (6)", "Different tax rates of branches and subsidiaries (4,228)"]),
            source_ref("shenhua_ifrs_overseas_tax_rates_page_295", 295, "IFRS disclosure of overseas subsidiary tax rates", ["Indonesia 22.0", "Hong Kong, China 8.25/16.5"]),
            source_ref("shenhua_ifrs_nci_summary_page_358", 358, "IFRS Note 44 material non-wholly-owned subsidiary NCI summary", ["Amounts before intragroup eliminations", "Profit allocated to non-controlling interests", "Individually immaterial subsidiaries 26,617"]),
            source_ref("shenhua_ifrs_subsidiary_summary_page_359", 359, "IFRS Note 44 summarized subsidiaries: Zhunge'er, Baorixile, Dingzhou", ["Revenue", "Expenses", "Profit and total comprehensive income for the year"]),
            source_ref("shenhua_ifrs_subsidiary_summary_page_360", 360, "IFRS Note 44 summarized subsidiaries: Shuohuang, Yuanhai, Huanghua", ["Revenue", "Expenses", "Profit and total comprehensive income for the year"]),
            source_ref("shenhua_ifrs_subsidiary_summary_page_361", 361, "IFRS Note 44 summarized subsidiary: Beidian Shengli", ["Revenue", "Expenses", "Profit and total comprehensive income for the year"]),
            source_ref("shenhua_ifrs_major_subsidiary_notes_page_67", 67, "IFRS Directors' Report partial major-subsidiary operating-profit notes", ["Shendong Coal operating profit RMB9,253 million", "Shuohuang Railway operating profit RMB9,073 million", "Zhunge'er Energy operating profit RMB7,822 million"]),
            source_ref("shenhua_ifrs_five_year_summary_page_371", 371, "IFRS five-year consolidated profit and loss summary", ["Profit before income tax 81,062", "Income tax expenses (16,559)", "Non-controlling interests 10,285"]),
        ],
        "linked_evidence": [],
        "formal_fair_value": None,
        "valuation_approved": False,
        "simulation_eligible": False,
        "trade_approved": False,
        "live_eligible": False,
    }
    return payload


def main() -> int:
    payload = build()
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "evidence.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    evidence_sha256 = hashlib.sha256(target.read_bytes()).hexdigest().upper()
    manifest = {
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest().upper(),
        "evidence_sha256": evidence_sha256,
        "source_sha256": SOURCE_HASH,
        "source_bytes": SOURCE_BYTES,
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    pointer = ROOT / "runtime/company-research/shenhua-2025-ifrs-subsidiary-tax-review-latest.json"
    pointer.write_text(json.dumps({
        "path": OUT.relative_to(ROOT).as_posix(),
        "sha256": evidence_sha256,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(target),
        "sha256": evidence_sha256,
        "status": payload["status"],
        "named_nci_profit": payload["named_subsidiary_reconciliation"]["named_profit_allocated_to_nci_cny_millions"],
        "profit_residual": payload["named_subsidiary_reconciliation"]["profit_residual_cny_millions"],
        "model_input": payload["model_derivations"]["normalized_parent_operating_profit"]["model_input"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
