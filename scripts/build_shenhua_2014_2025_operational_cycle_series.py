"""Build an evidence-only 2014-2025 Shenhua operating-cycle series."""
from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path

from pypdf import PdfReader


logging.getLogger("pypdf").setLevel(logging.ERROR)

ROOT = Path(__file__).resolve().parents[1]
HISTORICAL_DIR = ROOT / "runtime" / "historical-filing-index" / "20260908T041326996681Z" / "pdfs"
MANIFEST = HISTORICAL_DIR / "manifest-20260908T042044684445Z.json"
SOURCE_2025 = ROOT / "runtime" / "shenhua-2025-official.pdf"
SOURCE_URL_2025 = "https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0330/2026033004060_c.pdf"
SOURCE_HASH_2025 = "460ea07ee14d3aeb2b7518a25f87b47833ea5473715d911c378c15f7425698fc"
OUT = ROOT / "runtime" / "company-research" / "shenhua-2014-2025-operational-cycle-series-20260922"
POINTER = ROOT / "runtime" / "company-research" / "shenhua-2014-2025-operational-cycle-series-latest.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize(value: str) -> str:
    return re.sub(r"\s+", "", value)


def load_sources() -> dict[str, dict]:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    sources = {}
    for item in payload:
        if item.get("symbol") != "601088":
            continue
        year = int("".join(ch for ch in item["title"] if ch.isdigit())[:4])
        path = ROOT / item["path"]
        if sha256(path) != item["sha256"]:
            raise ValueError(f"Historical source hash mismatch for {year}")
        source_id = f"shenhua_{year}_annual_report"
        sources[source_id] = {
            "source_id": source_id,
            "year": year,
            "title": item["title"],
            "path": path.relative_to(ROOT).as_posix(),
            "url": item["url"],
            "sha256": item["sha256"],
        }
    if sha256(SOURCE_2025) != SOURCE_HASH_2025:
        raise ValueError("2025 Shenhua source hash mismatch")
    sources["shenhua_2025_annual_report"] = {
        "source_id": "shenhua_2025_annual_report",
        "year": 2025,
        "title": "中国神华能源股份有限公司 2025年度报告",
        "path": SOURCE_2025.relative_to(ROOT).as_posix(),
        "url": SOURCE_URL_2025,
        "sha256": SOURCE_HASH_2025,
    }
    return sources


EXPECTED = {
    "shenhua_2014_annual_report": {
        23: ("加权平均煤炭销售价格351.4元/吨", "煤炭销售量451.1百万吨"),
        27: ("自产煤单位生产成本为127.6元/吨",),
        10: ("总售电量十亿千瓦时199.44",),
        29: ("平均售电电价为355元/兆瓦时",),
    },
    "shenhua_2015_annual_report": {
        18: ("煤炭平均销售价格292.6元/吨", "售电量210.45十亿千瓦时", "平均售电电价334元/兆瓦时"),
        28: ("自产煤单位生产成本119.5",),
    },
    "shenhua_2016_annual_report": {
        18: ("煤炭平均销售价格317元/吨", "售电量220.57十亿千瓦时", "平均售电电价307元/兆瓦时"),
        19: ("其中：自产煤百万吨285.5289.3(1.3)298.7",),
        29: ("自产煤单位生产成本108.9",),
    },
    "shenhua_2017_annual_report": {
        19: ("煤炭销售量443.8百万吨", "煤炭平均销售价格425元/吨（不含税）"),
        31: ("自产煤单位生产成本108.5",),
        33: ("合计/加权平均262.87236.0411.4246.25220.5711.63123071.6",),
    },
    "shenhua_2018_annual_report": {
        19: ("其中：自产煤百万吨300.7301.0(0.1)285.5",),
        26: ("销售量合计/平均价格(不含税)460.9100.0429443.8100.04250.9",),
        29: ("自产煤单位生产成本113.4",),
        30: ("合计285.32262.878.5267.59246.258.73183121.9",),
    },
    "shenhua_2019_annual_report": {
        25: ("煤炭销售量447.1百万吨", "煤炭平均销售价格为426元/吨"),
        28: ("自产煤单位生产成本118.8",),
        11: ("总售电量144.04十亿千瓦时",),
    },
    "shenhua_2020_annual_report": {
        15: ("其中：自产煤百万吨296.0284.83.9300.7",),
        22: ("煤炭销售量446.4百万吨", "煤炭平均销售价格为410元/吨"),
        25: ("自产煤单位生产成本119.2", "总售电量127.65十亿千瓦时"),
    },
    "shenhua_2021_annual_report": {
        18: ("其中：自产煤百万吨312.7296.05.6284.8",),
        24: ("煤炭销售量482.3百万吨", "煤炭销售平均价格为588元/吨"),
        28: ("自产煤单位生产成本155.5",),
        29: ("合计166.45136.3322.1156.13127.6522.33483344.2",),
    },
    "shenhua_2022_annual_report": {
        18: ("其中：自产煤百万吨316.2312.71.1296.0",),
        26: ("煤炭销售量417.8百万吨", "煤炭销售平均价格为644元/吨"),
        27: ("一、自产煤316.275.7597",),
        30: ("自产煤单位生产成本176.3",),
        31: ("总售电量179.81十亿千瓦时", "平均售电价格418元/兆瓦时"),
    },
    "shenhua_2023_annual_report": {
        18: ("其中：自产煤百万吨325.4316.22.9312.7",),
        26: ("煤炭销售量450.0百万吨", "煤炭销售平均价格（不含税）为584元/吨"),
        27: ("自产煤325.472.3548",),
        30: ("自产煤单位生产成本179.0",),
        31: ("总售电量199.75十亿千瓦时", "平均售电价格414元/兆瓦时"),
    },
    "shenhua_2024_annual_report": {
        26: ("煤炭销售量459.3百万吨", "煤炭销售平均价格（不含税）为564元/吨"),
        27: ("自产煤327.071.2527",),
        30: ("自产煤单位生产成本179.0",),
        31: ("总售电量210.28十亿千瓦时", "平均售电价格403元/兆瓦时"),
    },
    "shenhua_2025_annual_report": {
        22: ("其中：自产煤百万吨332.3337.6(1.6)339.0", "总售电量十亿千瓦时207.00215.41(3.9)205.17"),
        29: ("煤炭销售量430.9百万吨", "煤炭销售平均价格（不含税）为495元/吨"),
        30: ("自产煤332.377.1472", "销售量合计/平均价格(不含税)430.9100.0495460.2100.0563(6.4)(12.1)"),
        33: ("自产煤单位生产成本171.6180.2(4.8)",),
        34: ("总售电量207.00十亿千瓦时", "平均售电价格386元/兆瓦时"),
        35: ("合计220.20228.89(3.8)207.00215.41(3.9)386402(4.0)",),
    },
}


def verify_sources(sources: dict[str, dict]) -> None:
    for source_id, source in sources.items():
        reader = PdfReader(str(ROOT / source["path"]), strict=False)
        for page, values in EXPECTED.get(source_id, {}).items():
            text = normalize(reader.pages[page - 1].extract_text() or "")
            missing = [value for value in values if normalize(value) not in text]
            if missing:
                raise ValueError(f"{source_id} page {page} missing evidence: {missing}")


def source_ref(source: dict, page: int, metric: str) -> dict:
    return {
        "source_id": source["source_id"],
        "path": source["path"],
        "url": source["url"],
        "sha256": source["sha256"],
        "page": page,
        "metric": metric,
    }


# (year, source, coal volume Mt, coal price, coal pages, self volume Mt, self source,
#  self pages, self price, self price pages, unit cost, unit pages, electricity TWh,
#  electricity pages, power price, power price pages, power price note)
ROW_SPECS = [
    (2014, "shenhua_2014_annual_report", 451.1, 351.4, [23], 298.7, "shenhua_2016_annual_report", [19], None, [], 127.6, [27], 199.44, [10], 355.0, [29], None),
    (2015, "shenhua_2015_annual_report", 370.5, 292.6, [18], 289.3, "shenhua_2016_annual_report", [19], None, [], 119.5, [28], 210.45, [18], 334.0, [18], None),
    (2016, "shenhua_2016_annual_report", 394.9, 317.0, [18], 285.5, "shenhua_2016_annual_report", [19], None, [], 108.9, [29], 220.57, [18], 307.0, [18], None),
    (2017, "shenhua_2017_annual_report", 443.8, 425.0, [19], 301.0, "shenhua_2018_annual_report", [19], None, [], 108.5, [31], 246.25, [19], 312.0, [33], None),
    (2018, "shenhua_2018_annual_report", 460.9, 429.0, [26], 300.7, "shenhua_2018_annual_report", [19], None, [], 113.4, [29], 267.59, [30], 318.0, [30], None),
    (2019, "shenhua_2019_annual_report", 447.1, 426.0, [25], 284.8, "shenhua_2020_annual_report", [15], None, [], 118.8, [28], 144.04, [11], None, [], "January 2019 power reorganization removed assets; no comparable group average power price was identified."),
    (2020, "shenhua_2020_annual_report", 446.4, 410.0, [22], 296.0, "shenhua_2020_annual_report", [15], None, [], 119.2, [25], 127.65, [25], None, [], "The filing discloses retail-sales-company prices only, not a group average power-sale price."),
    (2021, "shenhua_2021_annual_report", 482.3, 588.0, [24], 312.7, "shenhua_2021_annual_report", [18], None, [], 155.5, [28], 156.13, [29], 348.0, [29], None),
    (2022, "shenhua_2022_annual_report", 417.8, 644.0, [26], 316.2, "shenhua_2022_annual_report", [18], 597.0, [27], 176.3, [30], 179.81, [31], 418.0, [31], None),
    (2023, "shenhua_2023_annual_report", 450.0, 584.0, [26], 325.4, "shenhua_2023_annual_report", [18], 548.0, [27], 179.0, [30], 199.75, [31], 414.0, [31], None),
    (2024, "shenhua_2024_annual_report", 459.3, 564.0, [26], 327.0, "shenhua_2024_annual_report", [27], 527.0, [27], 179.0, [30], 210.28, [31], 403.0, [31], None),
    (2025, "shenhua_2025_annual_report", 430.9, 495.0, [29], 332.3, "shenhua_2025_annual_report", [22, 30], 472.0, [30], 171.6, [33], 207.00, [34], 386.0, [34], None),
]


RESTATED_2024 = {
    "coal_sales_volume_million_tonnes": 460.2,
    "blended_average_coal_price_cny_per_tonne": 563.0,
    "self_produced_coal_sales_volume_million_tonnes": 337.6,
    "self_produced_coal_average_price_cny_per_tonne": 521.0,
    "self_produced_coal_unit_production_cost_cny_per_tonne": 180.2,
    "electricity_sold_twh": 215.41,
    "average_power_sale_price_cny_per_mwh": 402.0,
    "source_id": "shenhua_2025_annual_report",
    "pages": [22, 30, 33, 35],
    "reason": "The 2025 report retroactively adjusted 2024 for the same-control acquisition of Hangjin Energy.",
}


def build_series() -> dict:
    sources = load_sources()
    verify_sources(sources)

    series = []
    evidence_refs = []
    for spec in ROW_SPECS:
        (year, source_id, coal_volume, coal_price, coal_pages, self_volume, self_source_id,
         self_pages, self_price, self_price_pages, unit_cost, unit_pages, electricity,
         electricity_pages, power_price, power_price_pages, power_note) = spec
        source = sources[source_id]
        row = {
            "year": year,
            "coal_sales_volume_million_tonnes": coal_volume,
            "blended_average_coal_price_cny_per_tonne": coal_price,
            "self_produced_coal_sales_volume_million_tonnes": self_volume,
            "self_produced_coal_average_price_cny_per_tonne": self_price,
            "self_produced_coal_unit_production_cost_cny_per_tonne": unit_cost,
            "electricity_sold_twh": electricity,
            "average_power_sale_price_cny_per_mwh": power_price,
            "source_id": source_id,
            "source_title": source["title"],
            "source_url": source["url"],
            "source_sha256": source["sha256"],
            "page_refs": {
                "coal_volume_and_blended_price": {"source_id": source_id, "pages": coal_pages},
                "self_produced_coal_sales_volume": {"source_id": self_source_id, "pages": self_pages},
                "self_produced_coal_average_price": {"source_id": source_id if self_price_pages else None, "pages": self_price_pages},
                "self_produced_coal_unit_production_cost": {"source_id": source_id, "pages": unit_pages},
                "electricity_sold": {"source_id": source_id, "pages": electricity_pages},
                "average_power_sale_price": {"source_id": source_id if power_price_pages else None, "pages": power_price_pages, "scope_note": power_note},
            },
        }
        if year == 2024:
            row["restated_2025"] = RESTATED_2024
        series.append(row)

        page_specs = [
            (source, coal_pages, "coal_volume_and_blended_price"),
            (sources[self_source_id], self_pages, "self_produced_coal_sales_volume"),
            (source, self_price_pages, "self_produced_coal_average_price"),
            (source, unit_pages, "self_produced_coal_unit_production_cost"),
            (source, electricity_pages, "electricity_sold"),
            (source, power_price_pages, "average_power_sale_price"),
        ]
        for ref_source, pages, metric in page_specs:
            for page in pages:
                evidence_refs.append(source_ref(ref_source, page, metric))
        if year == 2024:
            for page in RESTATED_2024["pages"]:
                evidence_refs.append(source_ref(sources["shenhua_2025_annual_report"], page, "restated_2024"))

    payload = {
        "symbol": "601088",
        "period_start": "2014-01-01",
        "period_end": "2025-12-31",
        "source_type": "reviewed_exchange_filed_annual_report_operating_cycle_series",
        "status": "multi_year_operational_cycle_series_collected_not_approved_as_model_inputs",
        "financial_scope_approved": False,
        "valuation_status": "VALUATION_NOT_READY",
        "formal_fair_value": None,
        "valuation_approved": False,
        "simulation_eligible": False,
        "trade_approved": False,
        "live_eligible": False,
        "purpose": "Raw, source-addressed operational observations for cycle research only; they are not normalized model inputs.",
        "sources": sorted(sources.values(), key=lambda item: item["year"]),
        "series": series,
        "restatement_observations": [
            {
                "id": "2015_report_restated_2014",
                "values": {
                    "2014_blended_coal_price_original": 351.4,
                    "2014_blended_coal_price_restated_in_2015": 351.0,
                    "2014_electricity_sold_twh_original": 199.44,
                    "2014_electricity_sold_twh_restated_in_2015": 218.42,
                    "2014_average_power_price_original": 355.0,
                    "2014_average_power_price_restated_in_2015": 354.0,
                },
                "note": "The 2015 report presents 2014 on a restated basis after same-control acquisitions.",
            },
            {
                "id": "2021_report_restated_2020_unit_cost",
                "values": {"2020_unit_cost_original": 119.2, "2020_unit_cost_restated_in_2021": 128.6},
                "note": "The 2021 report uses a restated 2020 unit-cost basis; the original filing remains point-in-time evidence.",
            },
            {
                "id": "2025_report_restated_2024_and_2023_for_hangjin",
                "values": {
                    "2024_coal_sales_volume_original": 459.3,
                    "2024_coal_sales_volume_restated": 460.2,
                    "2024_blended_coal_price_original": 564.0,
                    "2024_blended_coal_price_restated": 563.0,
                    "2024_self_produced_volume_original": 327.0,
                    "2024_self_produced_volume_restated": 337.6,
                    "2024_self_produced_price_original": 527.0,
                    "2024_self_produced_price_restated": 521.0,
                    "2024_unit_cost_original": 179.0,
                    "2024_unit_cost_restated": 180.2,
                    "2024_electricity_sold_twh_original": 210.28,
                    "2024_electricity_sold_twh_restated": 215.41,
                    "2024_average_power_price_original": 403.0,
                    "2024_average_power_price_restated": 402.0,
                    "2023_coal_sales_volume_original": 450.0,
                    "2023_coal_sales_volume_restated": 454.6,
                    "2023_self_produced_volume_original": 325.4,
                    "2023_self_produced_volume_restated": 339.0,
                    "2023_electricity_sold_twh_original": 199.75,
                    "2023_electricity_sold_twh_restated": 205.17,
                },
                "note": "The 2025 report restates comparatives after the same-control acquisition of Hangjin Energy.",
            },
        ],
        "accounting_scope_warnings": [
            "2014-2024 blended group coal average price is not the same as self-produced coal price and must not be paired with self-produced unit production cost to infer a unit margin.",
            "2022-2025 self-produced average price still does not by itself establish mine-to-margin contribution because transportation, tax, inter-segment and elimination effects remain.",
            "2019 and 2020 group average power-sale prices are not directly comparable with earlier years because of the 2019 power joint-venture reorganization.",
            "Absolute unit production cost is not a total delivered-cost or all-in cash-cost metric.",
            "Restated comparatives are disclosure adjustments, not evidence that original point-in-time values were incorrect when first published.",
        ],
        "missing_model_links": {
            "normalized_parent_operating_profit": "The series contains operating quantities and prices, not a reconciled normalized profit series.",
            "cash_tax_rate": "Not derived from this series.",
            "maintenance_capex": "Not derived from this series.",
            "normalized_working_capital_change": "Not derived from this series.",
            "discount_rate": "Not present.",
            "long_term_growth": "Not present.",
            "resource_life_years": "Not present.",
            "net_cash_attributable_to_parent": "Not present.",
            "ordinary_shares": "Not present.",
            "trough_parent_operating_profit": "Descriptive ranges do not establish a trough.",
            "unit_cost_curve": "This is a disclosed historical series, not an independently verified competitive cost curve.",
        },
        "evidence_refs": evidence_refs,
    }
    return payload


def main() -> None:
    payload = build_series()
    OUT.mkdir(parents=True, exist_ok=True)
    evidence_path = OUT / "evidence.json"
    evidence_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    evidence_hash = sha256(evidence_path)
    manifest = {
        "script_sha256": sha256(Path(__file__).resolve()),
        "evidence_sha256": evidence_hash,
        "source_sha256s": {source_id: source["sha256"] for source_id, source in load_sources().items()},
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    POINTER.write_text(json.dumps({"path": str(OUT.relative_to(ROOT)), "sha256": evidence_hash}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(evidence_path), "sha256": evidence_hash}, ensure_ascii=False))


if __name__ == "__main__":
    main()
