"""Build a source-addressed Shenhua external-price and internal-bridge package."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, localcontext
import hashlib
import json
import logging
from pathlib import Path

from pypdf import PdfReader


logging.getLogger("pypdf").setLevel(logging.ERROR)

ROOT = Path(__file__).resolve().parents[1]
HISTORICAL_DIR = ROOT / "runtime/historical-filing-index/20260908T041326996681Z/pdfs"
HISTORICAL_MANIFEST = HISTORICAL_DIR / "manifest-20260908T042044684445Z.json"
SOURCE_2025 = ROOT / "runtime/shenhua-2025-official.pdf"
SOURCE_2025_URL = "https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0330/2026033004060_c.pdf"
SOURCE_2025_HASH = "460ea07ee14d3aeb2b7518a25f87b47833ea5473715d911c378c15f7425698fc"
SCOPE = ROOT / "runtime/company-research/shenhua-cyclical-scope-20260921/evidence.json"
CANDIDATE_POINTER = ROOT / "runtime/company-research/shenhua-cyclical-candidate-inputs-latest.json"
OPERATING_AUDIT_POINTER = ROOT / "runtime/company-research/shenhua-2014-2025-operational-cycle-audit-latest.json"
ATTRIBUTABLE_POINTER = ROOT / "runtime/company-research/shenhua-2014-2025-attributable-profit-series-latest.json"
OUT = ROOT / "runtime/company-research/shenhua-2014-2025-price-cost-transport-bridge-20260922"
POINTER = ROOT / "runtime/company-research/shenhua-2014-2025-price-cost-transport-bridge-latest.json"

REVIEW_DATE = date(2026, 9, 22)

PUBLICATION_DATES = {
    2014: date(2015, 3, 20),
    2015: date(2016, 3, 24),
    2016: date(2017, 3, 17),
    2017: date(2018, 3, 23),
    2018: date(2019, 3, 22),
    2019: date(2020, 3, 27),
    2020: date(2021, 3, 26),
    2021: date(2022, 3, 25),
    2022: date(2023, 3, 24),
    2023: date(2024, 3, 22),
    2024: date(2025, 3, 21),
    2025: date(2026, 3, 30),
}

ROWS = [
    {"year": 2014, "page": 48, "benchmark": "bohai_rim_5500_kcal", "end": 525, "average": 522, "low": 478},
    {"year": 2015, "page": 42, "benchmark": "bohai_rim_5500_kcal", "end": 372, "average": 427},
    {"year": 2016, "page": 44, "benchmark": "bohai_rim_5500_kcal", "end": 593, "average": 460},
    {"year": 2017, "page": 46, "benchmark": "bohai_rim_5500_kcal", "end": 578, "average": 585.3},
    {"year": 2018, "page": None, "benchmark": None, "end": None, "average": None},
    {"year": 2019, "page": 44, "benchmark": "bohai_rim_5500_kcal", "end": None, "average": None, "range_low": 550, "range_high": 650},
    {"year": 2020, "page": 36, "benchmark": "bohai_rim_5500_kcal", "end": 585, "average": 549},
    {"year": 2021, "page": 13, "benchmark": "bohai_rim_5500_kcal", "end": 737, "average": 673},
    {"year": 2022, "page": 14, "benchmark": "bohai_rim_5500_kcal", "end": 734, "average": 737},
    {"year": 2023, "page": 14, "benchmark": "ncei_5500_kcal_long_term", "end": 710, "average": 714, "qhd_spot_average": 980},
    {"year": 2024, "page": 14, "benchmark": "ncei_5500_kcal_long_term", "end": 696, "average": 701, "qhd_spot_average": 861},
    {"year": 2025, "page": 17, "benchmark": "ncei_5500_kcal_long_term", "end": 694, "average": 680, "qhd_spot_average": 703},
]

HISTORICAL_CHECKS = {
    2014: ["价格为525元/吨", "全年环渤海动力煤指数均价522"],
    2015: ["价格为372元/吨", "全年环渤海动力煤指数均价427"],
    2016: ["价格指数为593元/吨", "全年环渤海动力煤价格指数均价460"],
    2017: ["价格指数为578元/吨", "全年指数均价585.3"],
    2019: ["550-650"],
    2020: ["价格指数为585元/吨", "全年指数均价549"],
    2021: ["价格指数为737元/吨", "全年指数均价673"],
    2022: ["综合平均价格指数为734元/吨", "全年指数均价737"],
    2023: ["中长期合同价格为710元/吨", "全年执行中长期合同价格均价约714", "成交均价约980"],
    2024: ["中长期合同执行价格为696元/吨", "全年执行中长期合同价格均价约701", "成交均价约861"],
    2025: ["中长期合同执行价格为694元/吨", "全年执行中长期合同价格均价约680", "成交均价约703"],
}

BRIDGE_CHECKS = [
    (29, "自产煤332.377.1472"),
    (29, "年度长协229.353.2455"),
    (29, "月度长协169.839.4569"),
    (29, "现货16.33.8556"),
    (29, "煤矿坑口直接销售15.53.6211"),
    (30, "对内部发电分部销售73.217.0447"),
    (30, "对内部煤化工分部销售5.01.2405"),
    (32, "自产煤156,90794,08762,82040.0"),
    (32, "自产煤单位生产成本171.6180.2(4.8)"),
    (36, "单位售电成本为334.7元/兆瓦时"),
    (37, "共耗用本集团内部销售的煤炭"),
    (37, "77.7百万吨"),
    (37, "97.7百万吨"),
    (37, "原材料、燃料及动力47,70273.1"),
    (38, "铁路分部单位运输成本为0.082元/吨公里"),
    (38, "港口分部单位运输成本为11.5元/吨"),
    (39, "航运分部单位运输成本为0.030元/吨海里"),
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compact(text: str) -> str:
    return "".join(text.split())


def decimal(value: Decimal, digits: int = 9) -> str:
    with localcontext() as context:
        context.prec = 40
        return format(value, f".{digits}f")


def page_text(reader: PdfReader, page: int, *, fragments: tuple[str, ...]) -> str:
    text = reader.pages[page].extract_text() or ""
    normalized = compact(text)
    missing = [fragment for fragment in fragments if compact(fragment) not in normalized]
    if missing:
        raise ValueError(f"Page {page} is missing expected text fragments: {missing}")
    return text


def parse_year(title: str) -> int:
    digits = "".join(ch for ch in title if ch.isdigit())
    if len(digits) < 4:
        raise ValueError(f"Cannot determine filing year from title: {title}")
    return int(digits[:4])


def load_historical_sources() -> dict[int, dict]:
    payload = json.loads(HISTORICAL_MANIFEST.read_text(encoding="utf-8"))
    sources: dict[int, dict] = {}
    for item in payload:
        if item.get("symbol") != "601088" or not item.get("path"):
            continue
        year = parse_year(item["title"])
        if year not in range(2014, 2025):
            continue
        path = ROOT / item["path"].replace("\\", "/")
        if not path.is_relative_to(ROOT.resolve()):
            raise ValueError("Historical source path escapes project root")
        actual = sha256(path)
        if actual != item["sha256"]:
            raise ValueError(f"Historical source hash mismatch for {year}")
        timestamp = datetime.fromtimestamp(item["announcement_timestamp_raw"] / 1000, timezone.utc)
        sources[year] = {
            "source_id": f"shenhua_{year}_annual_report",
            "year": year,
            "title": item["title"],
            "path": str(path.relative_to(ROOT)),
            "url": item["url"],
            "sha256": actual,
            "announcement_timestamp_raw": item["announcement_timestamp_raw"],
            "available_from_utc": timestamp.strftime("%Y-%m-%d"),
            "timestamp_precision": item["timestamp_precision"],
            "page_count": item["pages"],
        }
    if set(sources) != set(range(2014, 2025)):
        raise ValueError("Historical source years are incomplete")
    return sources


def pointer_payload(pointer: Path) -> tuple[dict, Path, str]:
    pin = json.loads(pointer.read_text(encoding="utf-8"))
    target = ROOT / pin["path"] / "evidence.json"
    if not target.is_relative_to(ROOT.resolve()):
        raise ValueError("Prior evidence pointer escapes project root")
    actual = sha256(target)
    if actual != pin["sha256"].lower():
        raise ValueError(f"Prior evidence hash mismatch: {pointer}")
    return json.loads(target.read_text(encoding="utf-8")), target, actual


def prior_ref(ref_id: str, pointer: Path, *, description: str) -> dict:
    _, target, actual = pointer_payload(pointer)
    return {
        "id": ref_id,
        "path": str(target.relative_to(ROOT)),
        "sha256": actual,
        "description": description,
    }


def source_ref(source: dict, *, description: str) -> dict:
    return {
        "id": source["source_id"],
        "path": source["path"],
        "sha256": source["sha256"],
        "description": description,
    }


def derived_candidates() -> dict[str, str]:
    with localcontext() as context:
        context.prec = 40
        self_produced_revenue_per_tonne = Decimal(156_907) / Decimal("332.3")
        self_produced_sales_cost_per_tonne = Decimal(94_087) / Decimal("332.3")
        coal_segment_cost_per_group_tonne = Decimal(154_631) / Decimal("430.9")
        power_fuel_cost_per_internal_coal_tonne = Decimal(47_702) / Decimal("77.7")
        ncei_to_company_annual_contract_gap = Decimal(680) - Decimal(455)
        qhd_to_blended_price_gap = Decimal(703) - Decimal(495)
        return {
            "self_produced_revenue_per_tonne_cny": decimal(self_produced_revenue_per_tonne),
            "self_produced_sales_cost_per_tonne_cny": decimal(self_produced_sales_cost_per_tonne),
            "coal_segment_cost_per_group_tonne_cny": decimal(coal_segment_cost_per_group_tonne),
            "power_fuel_cost_per_internal_coal_tonne_cny": decimal(power_fuel_cost_per_internal_coal_tonne),
            "ncei_average_minus_company_annual_contract_price_cny": decimal(ncei_to_company_annual_contract_gap, 0),
            "qhd_spot_average_minus_blended_realized_price_cny": decimal(qhd_to_blended_price_gap, 0),
        }


def build() -> dict:
    sources = load_historical_sources()
    if sha256(SOURCE_2025) != SOURCE_2025_HASH:
        raise ValueError("2025 annual report hash mismatch")
    sources[2025] = {
        "source_id": "shenhua_2025_annual_report",
        "year": 2025,
        "title": "中国神华能源股份有限公司 2025年度报告",
        "path": str(SOURCE_2025.relative_to(ROOT)),
        "url": SOURCE_2025_URL,
        "sha256": SOURCE_2025_HASH,
        "announcement_timestamp_raw": None,
        "available_from_utc": "2026-03-30",
        "timestamp_precision": "date_only_from_filing_url",
        "page_count": len(PdfReader(str(SOURCE_2025)).pages),
    }

    readers: dict[int, PdfReader] = {}
    for year, source in sources.items():
        readers[year] = PdfReader(str(ROOT / source["path"]))

    external_envelope = []
    for row in ROWS:
        year = row["year"]
        source = sources[year]
        page = row["page"]
        if page is not None:
            page_text(readers[year], page, fragments=tuple(HISTORICAL_CHECKS.get(year, ())))
        external_envelope.append({
            "year": year,
            "source_id": source["source_id"],
            "publication_date": PUBLICATION_DATES[year].isoformat(),
            "available_from": PUBLICATION_DATES[year].isoformat(),
            "timestamp_precision": source["timestamp_precision"],
            "source_url": source["url"],
            "page": page,
            "benchmark": row["benchmark"],
            "period_end_price_cny_per_tonne": row.get("end"),
            "annual_average_price_cny_per_tonne": row.get("average"),
            "qhd_5500_spot_annual_average_cny_per_tonne": row.get("qhd_spot_average"),
            "range_low_cny_per_tonne": row.get("range_low"),
            "range_high_cny_per_tonne": row.get("range_high"),
            "low_cny_per_tonne": row.get("low"),
            "availability": "point_value" if row.get("end") is not None else "range_or_gap",
            "model_input": None,
            "point_in_time_note": (
                "Known only from this issuer annual report, available on its filing date; "
                "not a verified index-operator daily archive."
            ),
        })

    bridge = {
        "as_of_period": "2025-12-31",
        "scope": "disclosed 2025 issuer operating metrics; pre-elimination segment results and unit costs",
        "coal": {
            "self_produced_sales_volume_million_tonnes": 332.3,
            "self_produced_average_price_cny_per_tonne": 472,
            "blended_average_price_cny_per_tonne": 495,
            "annual_long_term_volume_million_tonnes": 229.3,
            "annual_long_term_price_cny_per_tonne": 455,
            "monthly_long_term_volume_million_tonnes": 169.8,
            "monthly_long_term_price_cny_per_tonne": 569,
            "spot_volume_million_tonnes": 16.3,
            "spot_price_cny_per_tonne": 556,
            "pithead_direct_sales_volume_million_tonnes": 15.5,
            "pithead_direct_sales_price_cny_per_tonne": 211,
            "internal_power_sales_volume_million_tonnes": 73.2,
            "internal_power_sales_price_cny_per_tonne": 447,
            "internal_chemical_sales_volume_million_tonnes": 5.0,
            "internal_chemical_sales_price_cny_per_tonne": 405,
            "self_produced_revenue_cny_millions": 156_907,
            "self_produced_sales_cost_cny_millions": 94_087,
            "self_produced_gross_profit_cny_millions": 62_820,
            "external_purchased_revenue_cny_millions": 56_239,
            "external_purchased_sales_cost_cny_millions": 55_621,
            "external_purchased_gross_profit_cny_millions": 618,
            "coal_segment_revenue_cny_millions": 221_232,
            "coal_segment_cost_cny_millions": 154_631,
            "coal_segment_profit_cny_millions": 46_597,
            "unit_production_cost_cny_per_tonne": 171.6,
            "unit_production_cost_components": {
                "materials_fuel_power": 27.7,
                "labour": 51.9,
                "repairs": 8.3,
                "depreciation_amortisation": 22.2,
                "other": 61.5,
            },
        },
        "power": {
            "electricity_sold_twh": 207.00,
            "average_power_sale_price_cny_per_mwh": 386,
            "unit_sale_cost_cny_per_mwh": 334.7,
            "coal_power_fuel_and_energy_cost_cny_millions": 47_702,
            "internal_coal_consumed_million_tonnes": 77.7,
            "total_coal_consumed_million_tonnes": 97.7,
            "power_segment_revenue_cny_millions": 89_139,
            "power_segment_cost_cny_millions": 73_052,
            "power_segment_profit_cny_millions": 12_627,
        },
        "transport": {
            "railway_turnover_billion_tonne_km": 313.0,
            "railway_revenue_cny_millions": 43_710,
            "railway_cost_cny_millions": 27_158,
            "railway_profit_cny_millions": 12_901,
            "railway_unit_cost_cny_per_tonne_km": 0.082,
            "port_revenue_cny_millions": 7_020,
            "port_cost_cny_millions": 3_744,
            "port_profit_cny_millions": 2_631,
            "port_unit_cost_cny_per_tonne": 11.5,
            "shipping_revenue_cny_millions": 3_989,
            "shipping_cost_cny_millions": 3_532,
            "shipping_profit_cny_millions": 269,
            "shipping_unit_cost_cny_per_tonne_nautical_mile": 0.030,
        },
    }

    scope = json.loads(SCOPE.read_text(encoding="utf-8"))
    if scope["reported_inputs"]["coal_segment_profit_cny"] != str(bridge["coal"]["coal_segment_profit_cny_millions"] * 1_000_000):
        raise ValueError("Coal segment profit is inconsistent with reviewed scope")

    candidate_ratios = derived_candidates()
    payload = {
        "symbol": "601088",
        "review_date": REVIEW_DATE.isoformat(),
        "period_start": "2014-01-01",
        "period_end": "2025-12-31",
        "source_type": "reviewed_exchange_filed_point_in_time_external_price_and_cost_transport_bridge",
        "engineering_status": "price_cost_transport_bridge_complete",
        "status": "point_in_time_external_price_and_cost_transport_bridge_compiled_not_reviewed_or_approved",
        "financial_scope_approved": False,
        "valuation_status": "VALUATION_NOT_READY",
        "formal_fair_value": None,
        "valuation_approved": False,
        "simulation_eligible": False,
        "trade_approved": False,
        "live_eligible": False,
        "purpose": (
            "Collect each annual report's point-in-time external benchmark price and the 2025 internal "
            "coal-to-power-to-transport cost bridge. These are candidate research boundaries, not normalized "
            "bear/base/bull profit inputs."
        ),
        "external_price_envelope": external_envelope,
        "internal_cost_transport_bridge_2025": bridge,
        "derived_candidates_not_reconciled": candidate_ratios,
        "model_input_decisions": {
            "bear_normalized_parent_operating_profit": "not_derived_market_benchmark_and_pre_elimination_segments_are_not_parent_profit",
            "base_normalized_parent_operating_profit": "not_derived_market_benchmark_and_pre_elimination_segments_are_not_parent_profit",
            "bull_normalized_parent_operating_profit": "not_derived_market_benchmark_and_pre_elimination_segments_are_not_parent_profit",
            "unit_cost": "candidate_bridge_only_not_verified_all_in_route_specific_cost_curve",
            "trough_parent_operating_profit": "not_derived_low_price_year_does_not_by_itself_map_to_parent_operating_profit",
        },
        "registered_cyclical_facts_operating_inputs": [],
        "specific_findings": [
            {
                "id": "external_benchmark_definition_changes_in_2023",
                "fact": "2014-2022 use the Bohai Rim 5,500 kcal index; 2023-2025 switch to NCEI 5,500 kcal long-term price. They are not one homogeneous benchmark.",
            },
            {
                "id": "2018_external_benchmark_gap",
                "fact": "The 2018 annual report does not disclose an NCEI or Bohai Rim point value in the reviewed market section.",
            },
            {
                "id": "2019_is_range_not_point",
                "fact": "The 2019 annual report discloses a 550-650 CNY/tonne spot range and no annual average, so it cannot be treated as a verified point estimate.",
            },
            {
                "id": "ncei_and_qhd_are_different_markets",
                "fact": "NCEI long-term and Qinhuangdao spot averages cannot be averaged; their annual values are materially different in 2023, 2024 and 2025.",
            },
            {
                "id": "external_price_is_not_company_realized_price",
                "fact": "In 2025 the external NCEI average is 680 CNY/t and Qinhuangdao spot average is 703 CNY/t, while Shenhua blended and self-produced realized prices are 495 and 472 CNY/t. Calorific value, taxes, transportation, internal sales and contract mix must be reconciled before any profit mapping.",
            },
            {
                "id": "internal_power_coal_bridge_is_unreconciled",
                "fact": "The coal table records 73.2 Mt sold to the power segment at 447 CNY/t, while the power segment reports 47,702 million CNY fuel/energy cost and 77.7 Mt of internal coal consumption out of 97.7 Mt. Inventory, purchase mix, heat content and segment adjustments require an explicit reconciliation.",
            },
            {
                "id": "unit_production_cost_is_not_route_delivered_cost",
                "fact": "171.6 CNY/t is a production-scope unit cost. Rail 0.082 CNY/tonne-km, port 11.5 CNY/t and shipping 0.030 CNY/tonne-nautical-mile require route-specific tonne-kilometres and volumes before an all-in delivered cost can be formed.",
            },
            {
                "id": "segments_do_not_add_to_group_profit_without_reconciliation",
                "fact": "Pre-elimination segment profit lines cannot be summed into group parent operating profit without intersegment elimination, tax, minority and unallocated-item reconciliation.",
            },
        ],
        "point_in_time_policy": [
            "Each benchmark observation is available only on or after its annual-report filing date.",
            "Issuer annual-report market commentary is secondary provenance for an index; a valuation decision should also retain the index-operator daily archive.",
            "A year with a range or missing observation is a gap, not a zero or interpolated point.",
            "Benchmark definition changes must be treated as separate instruments.",
        ],
        "forbidden_calculations": [
            "external benchmark price - disclosed unit production cost = company operating profit",
            "NCEI or Qinhuangdao average * self-produced volume = company revenue or parent profit",
            "internal coal volume * internal transfer price = power fuel cost without reconciliation",
            "sum of pre-elimination segment profit = parent operating profit",
            "minimum descriptive annual price = verified trough model input",
        ],
        "evidence_refs": [
            *[source_ref(source, description=f"{source['year']} annual report source used for point-in-time market facts") for source in sources.values()],
            prior_ref("shenhua_cyclical_scope", CANDIDATE_POINTER, description="Previously reviewed cyclical candidate input package"),
            prior_ref("shenhua_operational_cycle_audit", OPERATING_AUDIT_POINTER, description="Previously audited 2014-2025 operating period facts"),
            prior_ref("shenhua_attributable_profit_series", ATTRIBUTABLE_POINTER, description="Previously compiled parent-attributable profit and tax candidate series"),
        ],
        "blockers": [
            "external_price_series_has_benchmark_definition_break_and_disclosure_gaps",
            "issuer_market_commentary_is_not_index_operator_primary_provenance",
            "market_benchmark_is_not_company_realized_price",
            "internal_power_coal_transfer_bridge_is_unreconciled",
            "unit_production_cost_is_not_route_specific_all_in_cost",
            "segment_profit_is_not_parent_operating_profit",
            "mid_cycle_and_trough_profit_still_not_derived",
        ],
    }
    return payload


def main() -> None:
    payload = build()
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "evidence.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    digest = sha256(target)
    script_digest = sha256(Path(__file__).resolve())
    source_hashes = {source["source_id"]: source["sha256"] for source in load_historical_sources().values()}
    source_hashes["shenhua_2025_annual_report"] = SOURCE_2025_HASH
    prior_hashes = {
        "cyclical_candidate_inputs": json.loads(CANDIDATE_POINTER.read_text(encoding="utf-8"))["sha256"],
        "operational_cycle_audit": json.loads(OPERATING_AUDIT_POINTER.read_text(encoding="utf-8"))["sha256"],
        "attributable_profit_series": json.loads(ATTRIBUTABLE_POINTER.read_text(encoding="utf-8"))["sha256"],
    }
    manifest = {
        "script_sha256": script_digest,
        "evidence_sha256": digest,
        "source_sha256s": source_hashes,
        "prior_evidence_sha256s": prior_hashes,
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    POINTER.write_text(json.dumps({
        "path": OUT.relative_to(ROOT).as_posix(),
        "sha256": digest,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(target),
        "sha256": digest,
        "status": payload["status"],
        "registered_inputs": payload["registered_cyclical_facts_operating_inputs"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
