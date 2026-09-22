"""Build a reviewed 2014-2025 Shenhua raw annual time-series package."""
from __future__ import annotations

import hashlib
import json
import statistics
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
HISTORICAL_DIR = ROOT / "runtime" / "historical-filing-index" / "20260908T041326996681Z" / "pdfs"
MANIFEST = HISTORICAL_DIR / "manifest-20260908T042044684445Z.json"
SOURCE_2025 = ROOT / "runtime" / "shenhua-2025-official.pdf"
SOURCE_URL_2025 = "https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0330/2026033004060_c.pdf"
OUT = ROOT / "runtime" / "company-research" / "shenhua-cyclical-time-series-20260921"


ROWS = [
    {"year": 2014, "income_page": 121, "revenue_page": 121, "cash_flow_page": 123,
     "capex_page": 123, "revenue": "248,360", "pretax_profit": "59,233",
     "parent_profit": "36,807", "operating_cash_flow": "67,511", "cash_capex": "44,539"},
    {"year": 2015, "income_page": 102, "revenue_page": 102, "cash_flow_page": 104,
     "capex_page": 104, "revenue": "177,069", "pretax_profit": "33,082",
     "parent_profit": "16,144", "operating_cash_flow": "55,406", "cash_capex": "29,876"},
    {"year": 2016, "income_page": 113, "revenue_page": 113, "cash_flow_page": 115,
     "capex_page": 115, "revenue": "183,127", "pretax_profit": "38,896",
     "parent_profit": "22,712", "operating_cash_flow": "81,883", "cash_capex": "29,058"},
    {"year": 2017, "income_page": 117, "revenue_page": 117, "cash_flow_page": 119,
     "capex_page": 119, "revenue": "248,746", "pretax_profit": "70,333",
     "parent_profit": "45,037", "operating_cash_flow": "95,152", "cash_capex": "20,268"},
    {"year": 2018, "income_page": 122, "revenue_page": 122, "cash_flow_page": 124,
     "capex_page": 124, "revenue": "264,101", "pretax_profit": "70,069",
     "parent_profit": "43,867", "operating_cash_flow": "88,248", "cash_capex": "20,935"},
    {"year": 2019, "income_page": 136, "revenue_page": 135, "cash_flow_page": 140,
     "capex_page": 141, "revenue": "241,871", "pretax_profit": "66,724",
     "parent_profit": "43,250", "operating_cash_flow": "63,106", "cash_capex": "19,009"},
    {"year": 2020, "income_page": 125, "revenue_page": 124, "cash_flow_page": 129,
     "capex_page": 130, "revenue": "233,263", "pretax_profit": "62,662",
     "parent_profit": "39,170", "operating_cash_flow": "81,289", "cash_capex": "20,673"},
    {"year": 2021, "income_page": 126, "revenue_page": 125, "cash_flow_page": 130,
     "capex_page": 131, "revenue": "335,216", "pretax_profit": "77,375",
     "parent_profit": "50,269", "operating_cash_flow": "94,575", "cash_capex": "23,863"},
    {"year": 2022, "income_page": 138, "revenue_page": 137, "cash_flow_page": 142,
     "capex_page": 143, "revenue": "344,533", "pretax_profit": "96,247",
     "parent_profit": "69,626", "operating_cash_flow": "109,734", "cash_capex": "28,684"},
    {"year": 2023, "income_page": 138, "revenue_page": 137, "cash_flow_page": 142,
     "capex_page": 143, "revenue": "343,074", "pretax_profit": "87,176",
     "parent_profit": "59,694", "operating_cash_flow": "89,687", "cash_capex": "37,084"},
    {"year": 2024, "income_page": 143, "revenue_page": 142, "cash_flow_page": 147,
     "capex_page": 148, "revenue": "338,375", "pretax_profit": "85,793",
     "parent_profit": "58,671", "operating_cash_flow": "93,348", "cash_capex": "37,032"},
    {"year": 2025, "income_page": 157, "revenue_page": 156, "cash_flow_page": 161,
     "capex_page": 162, "revenue": "294,916", "pretax_profit": "79,339",
     "parent_profit": "52,849", "operating_cash_flow": "75,059", "cash_capex": "48,398"},
]


def number(value: str) -> int:
    return int(value.replace(",", ""))


def load_historical_sources() -> dict[int, dict]:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    sources = {}
    for item in payload:
        if item.get("symbol") != "601088":
            continue
        year = int("".join(ch for ch in item["title"] if ch.isdigit())[:4])
        path = ROOT / item["path"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError(f"Historical source hash mismatch: {year}")
        sources[year] = {"path": path, "sha256": item["sha256"], "url": item["url"], "title": item["title"]}
    return sources


def verified_text(reader: PdfReader, page: int, expected: tuple[str, ...]) -> str:
    text = reader.pages[page - 1].extract_text() or ""
    for value in expected:
        if value not in text:
            raise ValueError(f"Page {page} does not contain expected evidence {value!r}")
    return text


def build_series() -> dict:
    historical = load_historical_sources()
    if hashlib.sha256(SOURCE_2025.read_bytes()).hexdigest() != "460ea07ee14d3aeb2b7518a25f87b47833ea5473715d911c378c15f7425698fc":
        raise ValueError("2025 Shenhua source hash mismatch")
    readers = {year: PdfReader(str(source["path"])) for year, source in historical.items()}
    readers[2025] = PdfReader(str(SOURCE_2025))

    rows = []
    evidence_refs = []
    for row in ROWS:
        year = row["year"]
        source = historical.get(year)
        if source is None:
            source = {"path": SOURCE_2025, "sha256": hashlib.sha256(SOURCE_2025.read_bytes()).hexdigest(),
                      "url": SOURCE_URL_2025, "title": "2025年年度报告"}
        reader = readers[year]
        verified_text(reader, row["income_page"], ("归属于母公司", row["parent_profit"]))
        verified_text(reader, row["revenue_page"], ("营业收入", row["revenue"], row["pretax_profit"]))
        verified_text(reader, row["cash_flow_page"], ("经营活动产生的现金流量净额", row["operating_cash_flow"]))
        verified_text(reader, row["capex_page"], ("购建固定资产", row["cash_capex"]))

        record = {
            "year": year,
            "revenue_cny": number(row["revenue"]) * 1000000,
            "pretax_profit_cny": number(row["pretax_profit"]) * 1000000,
            "parent_attributable_profit_cny": number(row["parent_profit"]) * 1000000,
            "operating_cash_flow_cny": number(row["operating_cash_flow"]) * 1000000,
            "cash_paid_for_long_term_assets_cny": number(row["cash_capex"]) * 1000000,
            "source_title": source["title"],
            "source_url": source["url"],
            "source_sha256": source["sha256"],
            "page_refs": {
                "income_statement": row["income_page"],
                "revenue_statement": row["revenue_page"],
                "cash_flow_statement": row["cash_flow_page"],
                "capex_cash_flow": row["capex_page"],
            },
        }
        rows.append(record)
        evidence_refs.append({
            "id": f"shenhua_{year}_annual_report_pages",
            "path": str(source["path"].relative_to(ROOT)) if source["path"] != SOURCE_2025 else "runtime/shenhua-2025-official.pdf",
            "sha256": source["sha256"],
            "pages": [row["income_page"], row["revenue_page"], row["cash_flow_page"], row["capex_page"]],
            "url": source["url"],
        })

    profits = [row["parent_attributable_profit_cny"] for row in rows]
    cash_flows = [row["operating_cash_flow_cny"] for row in rows]
    capex = [row["cash_paid_for_long_term_assets_cny"] for row in rows]
    payload = {
        "symbol": "601088",
        "period_start": "2014-01-01",
        "period_end": "2025-12-31",
        "source_type": "reviewed_exchange_filed_annual_report_raw_time_series",
        "status": "multi_year_raw_series_collected_but_not_approved_as_normalized_inputs",
        "financial_scope_approved": False,
        "valuation_status": "VALUATION_NOT_READY",
        "purpose": (
            "Raw reviewed observations for cycle research. Mean, median, minimum and maximum are descriptive only; "
            "they do not establish normalized profit, mid-cycle cash flow, resource life, cost position or a valuation."
        ),
        "series": rows,
        "descriptive_stats": {
            "parent_attributable_profit_cny": {
                "minimum": min(profits), "maximum": max(profits), "mean": round(statistics.mean(profits), 2), "median": statistics.median(profits),
            },
            "operating_cash_flow_cny": {
                "minimum": min(cash_flows), "maximum": max(cash_flows), "mean": round(statistics.mean(cash_flows), 2), "median": statistics.median(cash_flows),
            },
            "cash_paid_for_long_term_assets_cny": {
                "minimum": min(capex), "maximum": max(capex), "mean": round(statistics.mean(capex), 2), "median": statistics.median(capex),
            },
        },
        "restatement_observations": [
            {
                "year_originally_reported": 2024,
                "latest_restated_source": "2025 annual report",
                "originally_reported_parent_profit_cny": 58671000000,
                "restated_parent_profit_cny": 55805000000,
                "originally_reported_operating_cash_flow_cny": 93348000000,
                "restated_operating_cash_flow_cny": 91086000000,
                "originally_reported_cash_capex_cny": 37032000000,
                "restated_cash_capex_cny": 37708000000,
            }
        ],
        "blockers": [
            "raw_series_has_unreconciled_restatement_and_scope_boundaries",
            "consolidated_operating_cash_flow_is_not_parent_distributable_cash",
            "maintenance_and_growth_capex_not_separated",
            "mid_cycle_commodity_price_and_unit_cost_envelope_not_verified",
            "resource_life_in_years_and_trough_solvency_not_established",
            "attributable_net_cash_and_ordinary_share_bridge_not_completed",
        ],
        "evidence_refs": evidence_refs,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "evidence.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    payload = build_series()
    target = OUT / "evidence.json"
    print(json.dumps({"output": str(target), "rows": len(payload["series"]),
                      "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
