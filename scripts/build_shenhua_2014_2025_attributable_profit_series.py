"""Compile a 2014-2025 Shenhua attributable-profit and tax candidate series."""
from __future__ import annotations

from decimal import Decimal, localcontext
import hashlib
import json
import logging
from pathlib import Path

from pypdf import PdfReader


logging.getLogger("pypdf").setLevel(logging.ERROR)

ROOT = Path(__file__).resolve().parents[1]
HISTORICAL_DIR = ROOT / "runtime" / "historical-filing-index" / "20260908T041326996681Z" / "pdfs"
MANIFEST = HISTORICAL_DIR / "manifest-20260908T042044684445Z.json"
SOURCE_2025 = ROOT / "runtime" / "shenhua-2025-official.pdf"
RAW_SERIES = ROOT / "runtime" / "company-research" / "shenhua-cyclical-time-series-20260921" / "evidence.json"
OUT = ROOT / "runtime" / "company-research" / "shenhua-2014-2025-attributable-profit-series-20260922"
POINTER = ROOT / "runtime" / "company-research" / "shenhua-2014-2025-attributable-profit-series-latest.json"

SOURCE_URL_2025 = "https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0330/2026033004060_c.pdf"
SOURCE_HASH_2025 = "460ea07ee14d3aeb2b7518a25f87b47833ea5473715d911c378c15f7425698fc"

ROWS = [
    {"year": 2014, "income_page": 121, "net_page": None, "cash_tax_page": 123,
     "operating_profit": 58_999, "pretax_profit": 59_233, "income_tax": 12_860,
     "parent_profit": 36_807, "minority_profit": 9_566, "cash_taxes_paid": 43_826},
    {"year": 2015, "income_page": 102, "net_page": None, "cash_tax_page": 104,
     "operating_profit": 32_088, "pretax_profit": 33_082, "income_tax": 9_818,
     "parent_profit": 16_144, "minority_profit": 7_120, "cash_taxes_paid": 37_480},
    {"year": 2016, "income_page": 113, "net_page": None, "cash_tax_page": 115,
     "operating_profit": 39_332, "pretax_profit": 38_896, "income_tax": 9_360,
     "parent_profit": 22_712, "minority_profit": 6_824, "cash_taxes_paid": 32_730},
    {"year": 2017, "income_page": 117, "net_page": None, "cash_tax_page": 119,
     "operating_profit": 71_102, "pretax_profit": 70_333, "income_tax": 16_283,
     "parent_profit": 45_037, "minority_profit": 9_013, "cash_taxes_paid": 48_693},
    {"year": 2018, "income_page": 122, "net_page": None, "cash_tax_page": 124,
     "operating_profit": 73_146, "pretax_profit": 70_069, "income_tax": 16_028,
     "parent_profit": 43_867, "minority_profit": 10_174, "cash_taxes_paid": 53_182},
    {"year": 2019, "income_page": 135, "net_page": 136, "cash_tax_page": 140,
     "operating_profit": 66_629, "pretax_profit": 66_724, "income_tax": 15_184,
     "parent_profit": 43_250, "minority_profit": 8_290, "cash_taxes_paid": 45_091},
    {"year": 2020, "income_page": 124, "net_page": 125, "cash_tax_page": 129,
     "operating_profit": 63_490, "pretax_profit": 62_662, "income_tax": 15_397,
     "parent_profit": 39_170, "minority_profit": 8_095, "cash_taxes_paid": 39_915},
    {"year": 2021, "income_page": 125, "net_page": 126, "cash_tax_page": 130,
     "operating_profit": 78_242, "pretax_profit": 77_375, "income_tax": 18_016,
     "parent_profit": 50_269, "minority_profit": 9_090, "cash_taxes_paid": 29_153},
    {"year": 2022, "income_page": 137, "net_page": 138, "cash_tax_page": 142,
     "operating_profit": 98_138, "pretax_profit": 96_247, "income_tax": 14_592,
     "parent_profit": 69_626, "minority_profit": 12_029, "cash_taxes_paid": 39_123},
    {"year": 2023, "income_page": 137, "net_page": 138, "cash_tax_page": 142,
     "operating_profit": 91_367, "pretax_profit": 87_176, "income_tax": 17_578,
     "parent_profit": 59_694, "minority_profit": 9_904, "cash_taxes_paid": 37_419},
    {"year": 2024, "income_page": 142, "net_page": 143, "cash_tax_page": 147,
     "operating_profit": 88_362, "pretax_profit": 85_793, "income_tax": 16_928,
     "parent_profit": 58_671, "minority_profit": 10_194, "cash_taxes_paid": 39_502},
    {"year": 2025, "income_page": 337, "net_page": 338, "cash_tax_page": 161,
     "operating_profit": 75_532, "pretax_profit": 79_339, "income_tax": 16_556,
     "parent_profit": 52_849, "minority_profit": 9_934, "cash_taxes_paid": 37_637},
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def number(value: int) -> str:
    return f"{value:,}"


def decimal(value: Decimal, digits: int = 9) -> str:
    with localcontext() as context:
        context.prec = 40
        return format(value, f".{digits}f")


def load_sources() -> dict[int, dict]:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    sources = {}
    for item in payload:
        if item.get("symbol") != "601088":
            continue
        year = int("".join(ch for ch in item["title"] if ch.isdigit())[:4])
        path = ROOT / item["path"]
        if sha256(path) != item["sha256"]:
            raise ValueError(f"Historical source hash mismatch for {year}")
        sources[year] = {
            "source_id": f"shenhua_{year}_annual_report",
            "year": year,
            "title": item["title"],
            "path": path.relative_to(ROOT).as_posix(),
            "url": item["url"],
            "sha256": item["sha256"],
        }
    if sha256(SOURCE_2025) != SOURCE_HASH_2025:
        raise ValueError("2025 Shenhua source hash mismatch")
    sources[2025] = {
        "source_id": "shenhua_2025_annual_report",
        "year": 2025,
        "title": "中国神华能源股份有限公司 2025年度报告",
        "path": SOURCE_2025.relative_to(ROOT).as_posix(),
        "url": SOURCE_URL_2025,
        "sha256": SOURCE_HASH_2025,
    }
    return sources


def verified_text(reader: PdfReader, page: int, expected: tuple[str, ...], label: str) -> str:
    text = (reader.pages[page - 1].extract_text() or "").replace("\x00", " ")
    missing = [value for value in expected if value not in text]
    if missing:
        raise ValueError(f"{label} page {page} does not contain expected evidence {missing!r}")
    return text


def build() -> dict:
    sources = load_sources()
    raw = json.loads(RAW_SERIES.read_text(encoding="utf-8"))
    raw_by_year = {row["year"]: row for row in raw["series"]}
    readers = {year: PdfReader(str(ROOT / source["path"])) for year, source in sources.items()}
    evidence_refs = []
    series = []

    for row in ROWS:
        year = row["year"]
        source = sources[year]
        reader = readers[year]
        verified_text(
            reader, row["income_page"],
            ("营业利润", number(row["operating_profit"]), "利润总额", number(row["pretax_profit"]),
             "所得税费用", number(row["income_tax"])),
            f"{year} income statement",
        )
        verified_text(
            reader, row["net_page"] or row["income_page"],
            ("归属于母公司", number(row["parent_profit"]), "少数股东损益", number(row["minority_profit"])),
            f"{year} profit allocation",
        )
        verified_text(
            reader, row["cash_tax_page"],
            ("支付的各项税费", number(row["cash_taxes_paid"])),
            f"{year} cash-flow tax payment",
        )

        parent_net = Decimal(row["parent_profit"])
        minority_net = Decimal(row["minority_profit"])
        operating = Decimal(row["operating_profit"])
        pretax = Decimal(row["pretax_profit"])
        income_tax = Decimal(row["income_tax"])
        cash_taxes = Decimal(row["cash_taxes_paid"])
        consolidated_net = parent_net + minority_net
        parent_share = parent_net / consolidated_net

        non_operating_net = pretax - operating
        uniform_pro_forma = operating * parent_share
        no_tax_assumption_lower = parent_net - max(Decimal(0), non_operating_net)
        no_tax_assumption_upper = operating
        if not no_tax_assumption_lower <= uniform_pro_forma <= no_tax_assumption_upper:
            raise ValueError(f"Pro forma outside no-tax-allocation bounds for {year}")

        if raw_by_year[year]["parent_attributable_profit_cny"] != row["parent_profit"] * 1_000_000:
            raise ValueError(f"Raw-series parent-profit cross-check failed for {year}")
        if raw_by_year[year]["pretax_profit_cny"] != row["pretax_profit"] * 1_000_000:
            raise ValueError(f"Raw-series pre-tax cross-check failed for {year}")

        series.append({
            "year": year,
            "audited_facts": {
                "consolidated_operating_profit_cny_millions": row["operating_profit"],
                "consolidated_pretax_profit_cny_millions": row["pretax_profit"],
                "income_tax_expense_cny_millions": row["income_tax"],
                "parent_attributable_net_profit_cny_millions": row["parent_profit"],
                "minority_net_profit_cny_millions": row["minority_profit"],
                "cash_taxes_paid_cny_millions": row["cash_taxes_paid"],
                "non_operating_net_cny_millions": row["pretax_profit"] - row["operating_profit"],
            },
            "derived_candidates": {
                "parent_attributable_pretax_operating_profit_uniform_share_pro_forma_cny_millions": decimal(uniform_pro_forma, 3),
                "parent_attributable_pretax_operating_profit_no_tax_assumption_lower_cny_millions": decimal(no_tax_assumption_lower, 3),
                "parent_attributable_pretax_operating_profit_no_tax_assumption_upper_cny_millions": decimal(no_tax_assumption_upper, 3),
                "income_tax_expense_rate": decimal(income_tax / pretax),
                "cash_taxes_paid_to_pretax_profit_rate": decimal(cash_taxes / pretax),
                "cash_taxes_paid_to_operating_profit_rate": decimal(cash_taxes / operating),
            },
            "model_input": None,
            "review_status": "candidate_series_not_reviewed_or_approved",
            "point_in_time": f"{year} original annual-report filing",
            "source_id": source["source_id"],
            "page_refs": {
                "income_statement": row["income_page"],
                "profit_allocation": row["net_page"] or row["income_page"],
                "cash_flow_tax_payment": row["cash_tax_page"],
            },
        })
        evidence_refs.append({
            "id": f"shenhua_{year}_income_and_cash_tax_pages",
            "path": source["path"],
            "url": source["url"],
            "sha256": source["sha256"],
            "pages": sorted({row["income_page"], row["net_page"] or row["income_page"], row["cash_tax_page"]}),
            "metric": "attributable_profit_and_cash_tax_candidates",
        })

    restatement_observations = [
        {
            "id": "2015_report_restated_2014",
            "values": {
                "2014_operating_profit_original": 58_999,
                "2014_operating_profit_restated_in_2015": 59_913,
                "2014_parent_profit_original": 36_807,
                "2014_parent_profit_restated_in_2015": 37_419,
                "2014_minority_profit_original": 9_566,
                "2014_minority_profit_restated_in_2015": 9_634,
            },
            "note": "The 2015 report presents 2014 on a restated basis after same-control acquisitions.",
        },
        {
            "id": "2023_report_restated_2022",
            "values": {
                "2022_income_tax_original": 14_592,
                "2022_income_tax_restated_in_2023": 14_551,
                "2022_parent_profit_original": 69_626,
                "2022_parent_profit_restated_in_2023": 69_648,
                "2022_minority_profit_original": 12_029,
                "2022_minority_profit_restated_in_2023": 12_048,
            },
            "note": "The 2023 report makes a small retrospective tax and ownership adjustment to 2022.",
        },
        {
            "id": "2025_report_restated_2024",
            "values": {
                "2024_operating_profit_original": 88_362,
                "2024_operating_profit_restated_in_2025": 87_082,
                "2024_pretax_profit_original": 85_793,
                "2024_pretax_profit_restated_in_2025": 82_928,
                "2024_income_tax_original": 16_928,
                "2024_income_tax_restated_in_2025": 16_929,
                "2024_parent_profit_original": 58_671,
                "2024_parent_profit_restated_in_2025": 55_805,
                "2024_minority_profit_original": 10_194,
                "2024_minority_profit_restated_in_2025": 10_194,
            },
            "note": "The 2025 report restates 2024 after the same-control acquisition of Hangjin Energy.",
        },
    ]

    return {
        "symbol": "601088",
        "period_start": "2014-01-01",
        "period_end": "2025-12-31",
        "review_date": "2026-09-22",
        "source_type": "reviewed_exchange_filed_attributable_profit_and_tax_candidate_series",
        "engineering_status": "attributable_profit_tax_candidate_series_complete",
        "status": "attributable_profit_and_tax_candidate_series_compiled_not_reviewed_or_approved",
        "financial_scope_approved": False,
        "valuation_status": "VALUATION_NOT_READY",
        "formal_fair_value": None,
        "valuation_approved": False,
        "simulation_eligible": False,
        "trade_approved": False,
        "live_eligible": False,
        "purpose": (
            "Turn each year's audited consolidated income statement and cash-flow tax payment into a "
            "source-addressed candidate series for parent-attributable operating profit and tax burden. "
            "No value is registered as a normalized model input."
        ),
        "series": series,
        "restatement_observations": restatement_observations,
        "key_boundaries": [
            "The exact parent-attributable pre-tax operating profit is not a disclosed statutory line item.",
            "The uniform parent-net-share pro forma assumes a uniform tax and ownership ratio across the group.",
            "The no-tax-allocation bounds use only nonnegative tax and nonnegative segment operating-profit assumptions; they are wide by design.",
            "Cash-flow '支付的各项税费' includes resource tax and other taxes, not only income tax, so it is a conservative upper-bound cash-tax-burden ratio.",
            "Original point-in-time filings and later restated comparatives are separate versions.",
        ],
        "model_input_decisions": {
            "bear_normalized_parent_operating_profit": "not_derived_series_must_be_reviewed_as_cycle_envelope",
            "base_normalized_parent_operating_profit": "not_derived_series_must_be_reviewed_as_cycle_envelope",
            "bull_normalized_parent_operating_profit": "not_derived_series_must_be_reviewed_as_cycle_envelope",
            "cash_tax_rate": "candidate_upper_bound_only_cash_taxes_paid_includes_all_taxes",
            "trough_parent_operating_profit": "descriptive_series_does_not_by_itself_establish_trough",
        },
        "registered_cyclical_facts_operating_inputs": [],
        "evidence_refs": evidence_refs,
        "blockers": [
            "parent_operating_profit_is_a_pro_forma_not_a_disclosed_statutory_line",
            "uniform_tax_and_ownership_allocation_not_independently_verified",
            "cash_tax_payment_line_mixes_income_tax_with_resource_and_other_taxes",
            "non_operating_and_special_items_not_normalized",
            "mid_cycle_and_trough_scenarios_not_yet_derived",
        ],
    }


def main() -> None:
    payload = build()
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "evidence.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    digest = sha256(target)
    script_digest = sha256(Path(__file__).resolve())
    source_hashes = {source["source_id"]: source["sha256"] for source in load_sources().values()}
    (OUT / "manifest.json").write_text(json.dumps({
        "script_sha256": script_digest,
        "evidence_sha256": digest,
        "source_sha256s": source_hashes,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    POINTER.write_text(json.dumps({
        "path": OUT.relative_to(ROOT).as_posix(),
        "sha256": digest,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(target),
        "sha256": digest,
        "status": payload["status"],
        "rows": len(series) if (series := payload["series"]) else 0,
        "registered_inputs": payload["registered_cyclical_facts_operating_inputs"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
