"""Compile Midea 2014-2024 attributable equity/income/cash-return candidates.

Values stay point-in-time research candidates.  No row is registered as a
residual-income model input or an equity-value denominator.
"""
from __future__ import annotations

from decimal import Decimal, localcontext
import hashlib
import json
import logging
from pathlib import Path

from pypdf import PdfReader


logging.getLogger("pypdf").setLevel(logging.ERROR)

ROOT = Path(__file__).resolve().parents[1]
TIMELINE = ROOT / "runtime/company-research/midea-annual-share-timeline-20260912T054403745196Z/evidence.json"
TIMELINE_SHA256 = "f5687f0798cdd5898cc166d9a7831adb77e8ed68e619c9effe57c737d5815229"
OUT = ROOT / "runtime/company-research/midea-2014-2024-equity-return-candidate-20260922"
POINTER = ROOT / "runtime/company-research/midea-2014-2024-equity-return-candidate-latest.json"

ROWS = [
    {
        "year": 2014, "balance_page": 90, "income_page": 91, "dividend_pages": [36, 37],
        "equity_cny_thousands": "39,470,499.84", "parent_profit_cny_thousands": "10,502,220.26",
        "cash_dividend_cny": "4,215,808,472", "buyback_cash_cny": "0",
        "per_ten_share_cny": "10.00", "distribution_share_base": "4,215,808,472",
        "cash_payout_ratio_disclosed": "40.14%", "total_cash_ratio_disclosed": "40.14%",
    },
    {
        "year": 2015, "balance_page": 77, "income_page": 78, "dividend_pages": [36, 37],
        "equity_cny_thousands": "49,201,852", "parent_profit_cny_thousands": "12,706,725",
        "cash_dividend_cny": "5,120,869,473.60", "buyback_cash_cny": "0",
        "per_ten_share_cny": "12.00", "distribution_share_base": "4,267,391,228",
        "cash_payout_ratio_disclosed": "40.30%", "total_cash_ratio_disclosed": "40.30%",
    },
    {
        "year": 2016, "balance_page": 76, "income_page": 77, "dividend_pages": [34, 35],
        "equity_cny_thousands": "61,126,923", "parent_profit_cny_thousands": "14,684,357",
        "cash_dividend_cny": "6,465,677,368.00", "buyback_cash_cny": "0",
        "per_ten_share_cny": "10.00", "distribution_share_base": "6,465,677,368",
        "cash_payout_ratio_disclosed": "44.03%", "total_cash_ratio_disclosed": "44.03%",
    },
    {
        "year": 2017, "balance_page": 86, "income_page": 87, "dividend_pages": [39, 40],
        "equity_cny_thousands": "73,737,437", "parent_profit_cny_thousands": "17,283,689",
        "cash_dividend_cny": "7,900,827,088.80", "buyback_cash_cny": "0",
        "per_ten_share_cny": "12.00", "distribution_share_base": "6,584,022,574",
        "cash_payout_ratio_disclosed": "45.71%", "total_cash_ratio_disclosed": "45.71%",
    },
    {
        "year": 2018, "balance_page": 100, "income_page": 101, "dividend_pages": [41, 42],
        "equity_cny_thousands": "83,072,116", "parent_profit_cny_thousands": "20,230,779",
        "cash_dividend_cny": "8,561,589,853.70", "buyback_cash_cny": "4,000,000,000.00",
        "per_ten_share_cny": "13.00", "distribution_share_base": "6,585,838,349",
        "cash_payout_ratio_disclosed": "42.32%", "total_cash_ratio_disclosed": "62.09%",
    },
    {
        "year": 2019, "balance_page": 114, "income_page": 115, "dividend_pages": [47, 48],
        "equity_cny_thousands": "101,669,163", "parent_profit_cny_thousands": "24,211,222",
        "cash_dividend_cny": "11,131,489,692.80", "buyback_cash_cny": "0",
        "per_ten_share_cny": "16.00", "distribution_share_base": "6,957,181,058",
        "cash_payout_ratio_disclosed": "45.98%", "total_cash_ratio_disclosed": "45.98%",
    },
    {
        "year": 2020, "balance_page": 131, "income_page": 132, "dividend_pages": [58, 59],
        "equity_cny_thousands": "117,516,260", "parent_profit_cny_thousands": "27,222,969",
        "cash_dividend_cny": "11,066,392,174.40", "buyback_cash_cny": "2,700,000,000",
        "per_ten_share_cny": "16.00", "distribution_share_base": "6,916,495,109",
        "cash_payout_ratio_disclosed": "40.65%", "total_cash_ratio_disclosed": "50.57%",
    },
    {
        "year": 2021, "balance_page": 148, "income_page": 149, "dividend_pages": [82],
        "equity_cny_thousands": "124,868,124", "parent_profit_cny_thousands": "28,573,650",
        "cash_dividend_cny": "11,677,509,164.60", "buyback_cash_cny": "13,664,103,513.72",
        "per_ten_share_cny": "17", "distribution_share_base": "6,869,123,038",
        "cash_payout_ratio_disclosed": None, "total_cash_ratio_disclosed": None,
    },
    {
        "year": 2022, "balance_page": 152, "income_page": 153, "dividend_pages": [88],
        "equity_cny_thousands": "142,935,236", "parent_profit_cny_thousands": "29,553,507",
        "cash_dividend_cny": "17,187,651,820", "buyback_cash_cny": "2,636,704,772",
        "per_ten_share_cny": "25", "distribution_share_base": "6,875,060,728",
        "cash_payout_ratio_disclosed": None, "total_cash_ratio_disclosed": None,
    },
    {
        "year": 2023, "balance_page": 160, "income_page": 161, "dividend_pages": [87],
        "equity_cny_thousands": "162,878,825", "parent_profit_cny_thousands": "33,719,935",
        "cash_dividend_cny": "20,761,175,508", "buyback_cash_cny": "0",
        "per_ten_share_cny": "30", "distribution_share_base": "6,920,391,836",
        "cash_payout_ratio_disclosed": None, "total_cash_ratio_disclosed": None,
    },
    {
        "year": 2024, "balance_page": 157, "income_page": 158, "dividend_pages": [83, 84],
        "equity_cny_thousands": "216,750,057", "parent_profit_cny_thousands": "38,537,237",
        "cash_dividend_cny": "26,711,662,411", "buyback_cash_cny": "0",
        "per_ten_share_cny": "35", "distribution_share_base": "7,631,903,546",
        "cash_payout_ratio_disclosed": None, "total_cash_ratio_disclosed": None,
    },
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compact(value: str) -> str:
    return "".join(ch for ch in value if ch not in ", \t\r\n\u00a0")


def numeric_compact(value: str) -> str:
    raw = compact(value)
    if "%" in raw:
        return raw
    try:
        return format(Decimal(raw), "f").rstrip("0").rstrip(".")
    except Exception:
        return raw


def fixed_decimal(value: str, digits: int = 9) -> str:
    with localcontext() as context:
        context.prec = 48
        return format(Decimal(value.replace(",", "")), f".{digits}f")


def load_timeline_sources() -> dict[int, dict]:
    if sha256(TIMELINE) != TIMELINE_SHA256:
        raise ValueError("Midea annual share timeline evidence changed")
    timeline = json.loads(TIMELINE.read_text(encoding="utf-8"))
    sources: dict[int, dict] = {}
    for row in timeline["rows"]:
        source_path = (ROOT / row["source"]["source_path"]).resolve()
        if not source_path.is_relative_to(ROOT.resolve()):
            raise ValueError("Historical source path escapes project root")
        if sha256(source_path) != row["source"]["source_sha256"]:
            raise ValueError(f"Historical source hash mismatch for {row['report_year']}")
        sources[row["report_year"]] = {
            "source_id": row["source"]["source_id"],
            "source_url": row["source"]["source_url"],
            "source_path": row["source"]["source_path"],
            "source_sha256": row["source"]["source_sha256"],
            "available_at": row["available_at"],
        }
    return sources


def verify_page(reader: PdfReader, page: int, expected: tuple[str, ...], label: str) -> str:
    text = (reader.pages[page - 1].extract_text() or "").replace("\x00", " ")
    normalized = compact(text)
    missing = [value for value in expected if compact(value) not in normalized]
    if missing:
        raise ValueError(f"{label} page {page} is missing expected evidence: {missing}")
    return text


def build() -> dict:
    sources = load_timeline_sources()
    if sorted(sources) != list(range(2014, 2025)):
        raise ValueError("Unexpected Midea annual report coverage")
    readers = {
        year: PdfReader(str(ROOT / source["source_path"]))
        for year, source in sources.items()
    }
    evidence_refs = []
    series = []

    for row in ROWS:
        year = row["year"]
        source = sources[year]
        reader = readers[year]
        verify_page(
            reader, row["balance_page"],
            ("归属于母公司股东权益合计", row["equity_cny_thousands"]),
            f"{year} balance sheet",
        )
        verify_page(
            reader, row["income_page"],
            ("归属于母公司股东的", row["parent_profit_cny_thousands"]),
            f"{year} income statement",
        )

        dividend_text = "".join(
            (reader.pages[page - 1].extract_text() or "").replace("\x00", " ")
            for page in row["dividend_pages"]
        )
        normalized_dividends = compact(dividend_text)
        missing_dividend = [
            value for value in ("现金分红金额", row["cash_dividend_cny"])
            if compact(value) not in normalized_dividends
        ]
        if missing_dividend:
            raise ValueError(f"{year} dividend disclosure is missing evidence: {missing_dividend}")
        if compact(row["buyback_cash_cny"]) == "0":
            if not any(compact(label) in normalized_dividends for label in ("以其他方式", "以现金方式要约回购")):
                raise ValueError(f"{year} dividend disclosure has no other-cash-return field")
        else:
            missing = [value for value in ("以其他方式", row["buyback_cash_cny"])
                       if compact(value) not in normalized_dividends]
            if missing:
                raise ValueError(f"{year} dividend disclosure missing buyback evidence: {missing}")
        if numeric_compact(row["per_ten_share_cny"]) not in normalized_dividends:
            raise ValueError(f"{year} per-ten-share dividend amount is not pinned")
        if compact(row["distribution_share_base"]) not in normalized_dividends:
            raise ValueError(f"{year} distribution share base is not pinned")

        equity_cny = Decimal(row["equity_cny_thousands"].replace(",", "")) * 1000
        parent_profit_cny = Decimal(row["parent_profit_cny_thousands"].replace(",", "")) * 1000
        cash_dividend = Decimal(row["cash_dividend_cny"].replace(",", ""))
        buyback_cash = Decimal(row["buyback_cash_cny"].replace(",", ""))
        total_cash = cash_dividend + buyback_cash

        series.append({
            "year": year,
            "report_period_end": f"{year}-12-31",
            "source_id": source["source_id"],
            "available_at": source["available_at"],
            "audited_facts": {
                "attributable_ordinary_equity_cny": str(equity_cny.quantize(Decimal("1"))),
                "attributable_ordinary_net_profit_cny": str(parent_profit_cny.quantize(Decimal("1"))),
                "cash_dividend_proposed_cny": fixed_decimal(row["cash_dividend_cny"], 2),
                "buyback_cash_counted_as_distribution_cny": fixed_decimal(row["buyback_cash_cny"], 2),
                "total_disclosed_cash_distribution_cny": fixed_decimal(str(total_cash), 2),
                "cash_dividend_per_ten_shares_cny": fixed_decimal(row["per_ten_share_cny"], 2),
                "distribution_share_base_shares": row["distribution_share_base"].replace(",", ""),
            },
            "derived_candidates": {
                "cash_dividend_to_parent_net_profit": fixed_decimal(str(cash_dividend / parent_profit_cny)),
                "buyback_cash_to_parent_net_profit": fixed_decimal(str(buyback_cash / parent_profit_cny)),
                "total_cash_distribution_to_parent_net_profit": fixed_decimal(str(total_cash / parent_profit_cny)),
            },
            "disclosed_ratios": {
                "cash_dividend_payout_ratio_in_original_report": row["cash_payout_ratio_disclosed"],
                "total_cash_distribution_ratio_in_original_report": row["total_cash_ratio_disclosed"],
            },
            "page_refs": {
                "balance_sheet": row["balance_page"],
                "income_statement": row["income_page"],
                "dividend_disclosure": row["dividend_pages"],
            },
            "point_in_time": f"{year} original annual-report filing",
            "review_status": "candidate_series_not_reviewed_or_approved",
            "model_input": None,
        })
        evidence_refs.append({
            "id": f"midea_{year}_annual_report_equity_return_pages",
            "path": source["source_path"],
            "url": source["source_url"],
            "sha256": source["source_sha256"],
            "pages": [row["balance_page"], row["income_page"], *row["dividend_pages"]],
            "description": f"Attributable equity, attributable net profit, and cash-return disclosure for {year}",
        })

    later_comparatives = build_later_comparatives(sources, readers)
    return {
        "symbol": "000333",
        "package_version": "midea-2014-2024-equity-return-candidate-v1",
        "period_start": "2014-01-01",
        "period_end": "2024-12-31",
        "review_date": "2026-09-22",
        "source_type": "issuer_annual_report_equity_return_candidate_series",
        "engineering_status": "equity_return_candidate_series_compiled",
        "status": "equity_return_candidate_series_compiled_not_reviewed_or_registered",
        "financial_scope_approved": False,
        "valuation_status": "VALUATION_NOT_READY",
        "registered_valuation_model": None,
        "registered_valuation_inputs": {},
        "formal_fair_value": None,
        "valuation_approved": False,
        "simulation_eligible": False,
        "trade_approved": False,
        "live_eligible": False,
        "purpose": (
            "Turn each year's original audited attributable-equity, attributable-profit, cash-dividend, "
            "and buyback-style cash-return disclosures into a page-addressed point-in-time candidate series. "
            "No row is a forecast ROE, cost-of-equity, payout, or ordinary-share denominator input."
        ),
        "series": series,
        "later_comparative_observations": later_comparatives,
        "key_boundaries": [
            "Attributable ordinary equity is a consolidated accounting fact, not a valuation basis for the listed A/H equity value.",
            "Attributable net profit is audited history, not a forecast return or normalized earning power.",
            "Cash dividend is the issuer's proposed amount including tax; it is not proof of future payout policy or distributable capacity.",
            "Buyback-style cash return is only included when the issuer explicitly counts it as other cash distribution.",
            "The reported dividend share base is not a current outstanding-share denominator.",
            "Calculated payout ratios are descriptive arithmetic over two filed amounts; they are not registered model inputs.",
        ],
        "model_input_decisions": {
            "start_book_equity": "candidate_history_does_not_establish_current_ordinary_equity_basis",
            "forecast_roes": "candidate_history_does_not_establish_forward_roe_forecasts",
            "cost_of_equity": "not_derived_from_historical_equity_or_cash_return",
            "payout": "candidate_history_does_not_establish_forward_retention_or_payout",
            "ordinary_shares": "candidate_series_does_not_establish_current_treasury_adjusted_denominator",
        },
        "evidence_refs": evidence_refs,
        "blockers": [
            "financial_business_standalone_equity_and_profit_not_disclosed",
            "treasury_share_count_not_consistently_disclosed",
            "current_ordinary_share_denominator_not_registered",
            "forward_roe_and_cost_of_equity_assumptions_not_evidenced",
            "cash_return_history_is_not_a_forward_payout_commitment",
        ],
    }


def build_later_comparatives(sources: dict[int, dict], readers: dict[int, PdfReader]) -> list[dict]:
    later_comparatives = []
    if 2020 in readers:
        verify_page(
            readers[2020], 58,
            ("2019 年", "11,131,489,692.80", "24,211,222,000", "45.98%",
             "3,200,000,000", "13.22%", "14,331,489,692.80", "59.19%"),
            "2020 comparative cash-distribution table",
        )
        later_comparatives.append({
            "id": "2020_report_restates_2019_buyback_other_cash_distribution",
            "year": 2019,
            "comparative_source_id": sources[2020]["source_id"],
            "comparative_source_page": 58,
            "values": {
                "cash_dividend_cny": "11131489692.80",
                "parent_net_profit_cny": "24211222000",
                "cash_dividend_payout_ratio_disclosed": "45.98%",
                "buyback_cash_cny": "3200000000.00",
                "buyback_ratio_disclosed": "13.22%",
                "total_cash_distribution_cny": "14331489692.80",
                "total_cash_distribution_ratio_disclosed": "59.19%",
            },
            "note": "The original FY2019 report disclosed zero other-cash return at publication; the FY2020 comparative table later includes CNY 3.2 billion of buyback as other cash distribution.",
        })
    if 2024 in readers:
        verify_page(
            readers[2024], 84,
            ("2023 30 208 61.63%", "2022 25 172 58.16%", "2021 17 117 40.87%"),
            "2024 comparative cash-payout table",
        )
        later_comparatives.append({
            "id": "2024_report_comparative_cash_dividend_payout_ratios",
            "year": None,
            "comparative_source_id": sources[2024]["source_id"],
            "comparative_source_page": 84,
            "values": {
                "2021_cash_dividend_payout_ratio_disclosed": "40.87%",
                "2022_cash_dividend_payout_ratio_disclosed": "58.16%",
                "2023_cash_dividend_payout_ratio_disclosed": "61.63%",
            },
            "note": "The 2024 report's near-three-year table discloses cash-payout ratios for 2021-2023; they are comparative context, not a change to the original filing series.",
        })
    return later_comparatives


def main() -> None:
    payload = build()
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "evidence.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    evidence_hash = sha256(target)
    source_hashes = {
        source["source_id"]: source["source_sha256"]
        for source in load_timeline_sources().values()
    }
    (OUT / "manifest.json").write_text(json.dumps({
        "script_sha256": sha256(Path(__file__).resolve()),
        "evidence_sha256": evidence_hash,
        "source_sha256s": source_hashes,
    }, indent=2) + "\n", encoding="utf-8")
    POINTER.write_text(json.dumps({
        "path": OUT.relative_to(ROOT).as_posix(),
        "sha256": evidence_hash,
    }, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": target.relative_to(ROOT).as_posix(),
        "sha256": evidence_hash,
        "status": payload["status"],
        "rows": len(payload["series"]),
        "registered_inputs": payload["registered_valuation_inputs"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
