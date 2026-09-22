"""Audit whether Shenhua disclosures support a route-specific delivered coal cost."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, localcontext
import hashlib
import json
import logging
import re
from pathlib import Path

from pypdf import PdfReader


logging.getLogger("pypdf").setLevel(logging.ERROR)

ROOT = Path(__file__).resolve().parents[1]
HISTORICAL_DIR = ROOT / "runtime/historical-filing-index/20260908T041326996681Z/pdfs"
HISTORICAL_MANIFEST = HISTORICAL_DIR / "manifest-20260908T042044684445Z.json"

SOURCE_CN = ROOT / "runtime/shenhua-2025-official.pdf"
SOURCE_CN_URL = "https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0330/2026033004060_c.pdf"
SOURCE_CN_HASH = "460ea07ee14d3aeb2b7518a25f87b47833ea5473715d911c378c15f7425698fc"
SOURCE_CN_PAGES = 481

SOURCE_EN = ROOT / "runtime/company-research/shenhua-2025-ifrs-annual-review-20260922/2026033003712.pdf"
SOURCE_EN_URL = "https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0330/2026033003712.pdf"
SOURCE_EN_HASH = "491E701A90B1ECE239B95CE3F3DE27053F420583F2458D81CBE5B21B4607FDC9"
SOURCE_EN_PAGES = 373

PRIOR_POINTER = ROOT / "runtime/company-research/shenhua-2014-2025-price-cost-transport-bridge-latest.json"
OUT = ROOT / "runtime/company-research/shenhua-2014-2025-route-delivered-cost-audit-20260922"
POINTER = ROOT / "runtime/company-research/shenhua-2014-2025-route-delivered-cost-audit-latest.json"

REVIEW_DATE = date(2026, 9, 22)

ROUTE_NAMES = (
    "朔黄",
    "神朔",
    "包神",
    "新朔",
    "大准",
    "准池",
    "巴准",
    "甘泉",
    "黄万",
    "黄大",
    "塔韩",
)
ROUTE_METRIC_TERMS = (
    "运输周转量",
    "货运量",
    "货物运输量",
    "装船量",
    "单位运输成本",
    "运输成本",
    "货物周转量",
)
ROUTE_SPECIFIC_PHRASES = tuple(
    phrase
    for route in ROUTE_NAMES
    for phrase in (
        f"{route}铁路运输周转量",
        f"{route}线运输周转量",
        f"{route}铁路货运量",
        f"{route}线货运量",
        f"{route}铁路货物运输量",
        f"{route}线货物运输量",
        f"{route}铁路单位运输成本",
        f"{route}线单位运输成本",
        f"{route}铁路运输成本",
        f"{route}线运输成本",
    )
)
ALLOCATION_TERMS = (
    "分线路",
    "各线路",
    "分路线",
    "线路分配",
    "运输线路分配",
    "分线运输周转量",
    "分线运输成本",
    "路线分配矩阵",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized_text(reader: PdfReader, page: int) -> str:
    return " ".join((reader.pages[page - 1].extract_text() or "").replace("\x00", " ").split())


def page_text(reader: PdfReader, page: int, expected: tuple[str, ...]) -> str:
    text = normalized_text(reader, page)
    missing = [value for value in expected if value not in text]
    if missing:
        raise ValueError(f"Page {page} does not contain expected evidence {missing!r}")
    return text


def decimal_ratio(numerator: Decimal, denominator: Decimal) -> str:
    with localcontext() as context:
        context.prec = 40
        return format(numerator / denominator, ".12f")


def load_sources() -> dict[str, dict]:
    manifest = json.loads(HISTORICAL_MANIFEST.read_text(encoding="utf-8"))
    sources: dict[str, dict] = {}
    for item in manifest:
        if item.get("symbol") != "601088":
            continue
        digits = "".join(ch for ch in item["title"] if ch.isdigit())
        if not digits:
            continue
        year = int(digits[:4])
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
            "pages": item["pages"],
            "language": "zh",
        }

    if sha256(SOURCE_CN) != SOURCE_CN_HASH:
        raise ValueError("2025 Shenhua Chinese annual-report hash mismatch")
    sources["shenhua_2025_annual_report"] = {
        "source_id": "shenhua_2025_annual_report",
        "year": 2025,
        "title": "中国神华能源股份有限公司 2025年度报告",
        "path": SOURCE_CN.relative_to(ROOT).as_posix(),
        "url": SOURCE_CN_URL,
        "sha256": SOURCE_CN_HASH,
        "pages": SOURCE_CN_PAGES,
        "language": "zh",
    }

    if sha256(SOURCE_EN).upper() != SOURCE_EN_HASH:
        raise ValueError("2025 Shenhua English annual-report hash mismatch")
    sources["shenhua_2025_english_annual_report"] = {
        "source_id": "shenhua_2025_english_annual_report",
        "year": 2025,
        "title": "China Shenhua Energy Company Limited 2025 Annual Report",
        "path": SOURCE_EN.relative_to(ROOT).as_posix(),
        "url": SOURCE_EN_URL,
        "sha256": SOURCE_EN_HASH,
        "pages": SOURCE_EN_PAGES,
        "language": "en",
    }
    return sources


def search_source(path: Path, expected_pages: int, language: str) -> dict:
    reader = PdfReader(str(path))
    if len(reader.pages) != expected_pages:
        raise ValueError(f"{path.name} page count mismatch: {len(reader.pages)} != {expected_pages}")

    page_texts = {index: normalized_text(reader, index) for index in range(1, expected_pages + 1)}
    route_name_pages = {
        route: [index for index, text in page_texts.items() if route in text]
        for route in ROUTE_NAMES
    }
    route_specific_pages = {
        phrase: [index for index, text in page_texts.items() if phrase in text]
        for phrase in ROUTE_SPECIFIC_PHRASES
    }
    allocation_pages = {
        term: [index for index, text in page_texts.items() if term in text]
        for term in ALLOCATION_TERMS
    }
    route_metric_cooccurrences = {
        route: [
            index
            for index in route_name_pages[route]
            if any(term in page_texts[index] for term in ROUTE_METRIC_TERMS)
        ]
        for route in ROUTE_NAMES
    }
    return {
        "language": language,
        "route_name_pages": route_name_pages,
        "route_specific_metric_phrase_pages": {
            phrase: pages for phrase, pages in route_specific_pages.items() if pages
        },
        "explicit_allocation_term_pages": {
            term: pages for term, pages in allocation_pages.items() if pages
        },
        "route_and_generic_metric_same_page": {
            route: pages for route, pages in route_metric_cooccurrences.items() if pages
        },
    }


def source_ref(ref_id: str, page: int, unit: str, description: str, quoted_facts: list[str]) -> dict:
    return {
        "id": ref_id,
        "path": SOURCE_CN.relative_to(ROOT).as_posix(),
        "url": SOURCE_CN_URL,
        "sha256": SOURCE_CN_HASH,
        "page": page,
        "unit": unit,
        "description": description,
        "quoted_facts": quoted_facts,
    }


def prior_ref(ref_id: str, pointer: Path, description: str) -> dict:
    pointer_payload = json.loads(pointer.read_text(encoding="utf-8"))
    target = ROOT / pointer_payload["path"] / "evidence.json"
    return {
        "id": ref_id,
        "path": target.relative_to(ROOT).as_posix(),
        "sha256": pointer_payload["sha256"],
        "page": None,
        "unit": None,
        "description": description,
        "quoted_facts": [],
    }


def build() -> dict:
    sources = load_sources()
    cn_reader = PdfReader(str(SOURCE_CN))
    en_reader = PdfReader(str(SOURCE_EN))

    page_text(cn_reader, 22, ("自有铁路运输周转量", "313.0", "黄骅港装船量", "217.0", "航运周转量", "114.9"))
    page_text(cn_reader, 24, ("铁路", "43,710", "27,158", "港口", "7,020", "3,744", "航运", "3,989", "3,532"))
    page_text(cn_reader, 30, ("自产煤", "332.3", "472", "外购煤", "98.6", "570"))
    page_text(cn_reader, 33, ("自产煤单位生产成本", "171.6", "折旧及摊销", "22.2"))
    page_text(cn_reader, 39, ("铁路分部单位运输成本", "0.082", "吨公里", "营业成本", "27,158"))
    page_text(cn_reader, 39, ("港口分部单位运输成本", "11.5", "元/吨", "黄骅港完成装船量", "217.0", "天津煤码头完成装船量", "44.6"))
    page_text(cn_reader, 40, ("航运分部单位运输成本", "0.030", "吨海里", "完成航运货运量", "111.3", "完成航运周转量", "114.9"))
    page_text(en_reader, 57, ("77.7 million tonnes", "97.7 million tonnes", "47,702"))
    page_text(en_reader, 59, ("0.082", "tonne km"))
    page_text(en_reader, 60, ("unit transportation cost", "Huanghua Port"))
    page_text(en_reader, 61, ("0.030", "tonne nautical mile"))

    source_searches = []
    total_pages = 0
    for source in sorted(sources.values(), key=lambda item: (item["year"], item["language"])):
        source_path = ROOT / source["path"]
        search = search_source(source_path, source["pages"], source["language"])
        total_pages += source["pages"]
        source_searches.append({
            "source_id": source["source_id"],
            "year": source["year"],
            "language": source["language"],
            "pages": source["pages"],
            **search,
        })

    route_specific_hits = {
        phrase: {
            "sources": [
                item["source_id"]
                for item in source_searches
                if phrase in item["route_specific_metric_phrase_pages"]
            ],
            "pages": [
                {"source_id": item["source_id"], "pages": item["route_specific_metric_phrase_pages"][phrase]}
                for item in source_searches
                if phrase in item["route_specific_metric_phrase_pages"]
            ],
        }
        for phrase in ROUTE_SPECIFIC_PHRASES
        if any(phrase in item["route_specific_metric_phrase_pages"] for item in source_searches)
    }
    allocation_hits = {
        term: [
            {"source_id": item["source_id"], "pages": item["explicit_allocation_term_pages"][term]}
            for item in source_searches
            if term in item["explicit_allocation_term_pages"]
        ]
        for term in ALLOCATION_TERMS
        if any(term in item["explicit_allocation_term_pages"] for item in source_searches)
    }

    rail_cost_per_group_sale = Decimal("27158") / Decimal("430.9")
    reported_port_loading = Decimal("217.0") + Decimal("44.6")
    port_segment_cost_per_reported_loading = Decimal("3744") / reported_port_loading
    shipping_cost_per_freight_volume = Decimal("3532") / Decimal("111.3")
    production_plus_transport_segment_proxies = (
        Decimal("171.6")
        + rail_cost_per_group_sale
        + port_segment_cost_per_reported_loading
        + shipping_cost_per_freight_volume
    )

    payload = {
        "symbol": "601088",
        "review_date": REVIEW_DATE.isoformat(),
        "period_start": "2014-01-01",
        "period_end": "2025-12-31",
        "source_type": "reviewed_exchange_filed_route_specific_delivered_cost_disclosure_audit",
        "engineering_status": "route_specific_delivered_cost_disclosure_audit_complete",
        "status": "route_specific_delivered_cost_not_disclosed_or_approved",
        "financial_scope_approved": False,
        "valuation_status": "VALUATION_NOT_READY",
        "formal_fair_value": None,
        "valuation_approved": False,
        "simulation_eligible": False,
        "trade_approved": False,
        "live_eligible": False,
        "purpose": (
            "Audit all retained 2014-2025 exchange filings for route-specific railway tonne-kilometres, "
            "port tonnage, shipping nautical-mile equivalents and the route allocation required to form an "
            "all-in mine-to-customer delivered cost. Aggregate transport facts are retained; no proxy is approved."
        ),
        "search_scope": {
            "years": list(range(2014, 2026)),
            "source_count": len(sources),
            "pages_scanned": total_pages,
            "route_names": list(ROUTE_NAMES),
            "route_metric_terms": list(ROUTE_METRIC_TERMS),
            "route_specific_phrase_count": len(ROUTE_SPECIFIC_PHRASES),
            "allocation_terms": list(ALLOCATION_TERMS),
            "disclosure_criterion": (
                "A route-specific delivered cost requires per-route turnover or volume and per-route cost, "
                "or an explicit allocation matrix linking mine output, transport mode and customer destination."
            ),
        },
        "search_results_by_source": source_searches,
        "route_specific_metric_phrase_hits": route_specific_hits,
        "explicit_allocation_term_hits": allocation_hits,
        "aggregate_transport_facts_2025": {
            "coal": {
                "group_sales_volume_million_tonnes": 430.9,
                "self_produced_sales_volume_million_tonnes": 332.3,
                "self_produced_average_price_cny_per_tonne": 472,
                "self_produced_unit_production_cost_cny_per_tonne": 171.6,
                "production_cost_scope": "production scope; excludes rail, port, shipping and customer delivery",
            },
            "railway": {
                "turnover_billion_tonne_km": 313.0,
                "segment_revenue_cny_millions": 43_710,
                "segment_cost_cny_millions": 27_158,
                "disclosed_unit_cost_cny_per_tonne_km": 0.082,
                "includes_non_coal_and_external_customers": True,
            },
            "ports": {
                "huanghua_loading_million_tonnes": 217.0,
                "tianjin_coal_terminal_loading_million_tonnes": 44.6,
                "segment_revenue_cny_millions": 7_020,
                "segment_cost_cny_millions": 3_744,
                "disclosed_unit_cost_cny_per_tonne": 11.5,
                "route_and_customer_allocation_disclosed": False,
            },
            "shipping": {
                "freight_volume_million_tonnes": 111.3,
                "turnover_billion_tonne_nautical_miles": 114.9,
                "segment_revenue_cny_millions": 3_989,
                "segment_cost_cny_millions": 3_532,
                "disclosed_unit_cost_cny_per_tonne_nautical_mile": 0.030,
                "route_and_customer_allocation_disclosed": False,
            },
        },
        "derived_proxies_forbidden_not_approved": {
            "railway_segment_cost_per_group_coal_sale_tonne_cny": decimal_ratio(
                rail_cost_per_group_sale, Decimal("1")
            ),
            "port_segment_cost_per_reported_huanghua_tianjin_loading_tonne_cny": decimal_ratio(
                port_segment_cost_per_reported_loading, Decimal("1")
            ),
            "shipping_segment_cost_per_shipping_freight_tonne_cny": decimal_ratio(
                shipping_cost_per_freight_volume, Decimal("1")
            ),
            "production_plus_transport_segment_proxy_sum_cny_per_tonne": decimal_ratio(
                production_plus_transport_segment_proxies, Decimal("1")
            ),
            "why_forbidden": (
                "The rail denominator is all coal sales, not rail-carried coal tonne-kilometres. The port "
                "denominator omits other port activities and cannot identify mine routes. The shipping "
                "denominator is distance-dependent tonnage, not nautical miles. Summing the three proxies "
                "double counts internal transfers and treats every tonne as using every transport mode."
            ),
        },
        "specific_findings": [
            {
                "id": "production_cost_is_not_delivered_cost",
                "fact": "171.6 CNY/t is a disclosed production-scope unit cost. It excludes rail, port, shipping, handling and customer delivery.",
            },
            {
                "id": "aggregate_transport_costs_require_unallocated_distance_units",
                "fact": "Railway 0.082 CNY/t-km, port 11.5 CNY/t and shipping 0.030 CNY/t-nautical-mile are mode-level averages, not mine-route or customer-route costs.",
            },
            {
                "id": "no_route_specific_metric_phrases_found",
                "fact": "No retained report contains a route-specific turnover, freight volume or unit-cost disclosure matching the searched route phrases.",
            },
            {
                "id": "no_explicit_transport_allocation_matrix_found",
                "fact": "No retained report presents a route/customer allocation matrix that maps self-produced or purchased coal from mines through railway, port and shipping legs.",
            },
            {
                "id": "route_names_in_narrative_are_not_throughput_disclosures",
                "fact": "Route names appear in operations, project and subsidiary narrative, but do not supply the required route tonne-kilometres or route costs.",
            },
            {
                "id": "segment_costs_mix_internal_and_external_work",
                "fact": "Rail, port and shipping segment cost lines include internal services, external customers, non-coal freight and non-transport activities, so simple tonnage division is not an auditable delivered cost.",
            },
        ],
        "forbidden_calculations": [
            "171.6 + railway segment cost / group coal volume + port segment cost / port loading + shipping segment cost / shipping volume = delivered cost",
            "railway segment cost / 430.9 Mt = rail cost per delivered tonne",
            "port segment cost / (217.0 + 44.6) Mt = port cost per delivered tonne",
            "shipping segment cost / 111.3 Mt = shipping cost per delivered tonne",
            "assume a generic railway distance, port leg and nautical-mile leg without a source-addressed route allocation",
        ],
        "missing_route_facts": [
            "route_specific_railway_tonne_km",
            "route_specific_railway_cost",
            "mine_to_port_volume_allocation",
            "port_volume_by_origin_route",
            "shipping_nautical_mile_by_origin_route",
            "route_specific_shipping_cost",
            "internal_versus_external_transport_allocation",
            "self_produced_versus_purchased_coal_transport_allocation",
            "all_in_delivered_cost_by_route",
        ],
        "model_input_decisions": {
            "unit_cost": {
                "status": "not_derived_route_specific_all_in_cost",
                "model_input": None,
                "reason": (
                    "A production unit cost plus aggregate transport costs does not identify a verified "
                    "mine-to-customer delivered-cost curve without route-specific distances and volumes."
                ),
            },
            "normalized_mid_cycle_coal_price": {
                "status": "not_derived_from_transport_audit",
                "model_input": None,
                "reason": "Transport-cost provenance does not establish a point-in-time external-price envelope.",
            },
            "trough_parent_operating_profit": {
                "status": "not_derived",
                "model_input": None,
                "reason": "The audit does not supply verified route margins, tax, minority or corporate allocation.",
            },
        },
        "registered_cyclical_facts_operating_inputs": [],
        "point_in_time_policy": [
            "Every page and quoted fact is retained with source, URL and SHA-256.",
            "Annual-report publication dates bound the earliest availability of issuer narrative.",
            "Absence in a retained annual report is a disclosure gap for that filing, not proof that no separate route report exists elsewhere.",
            "Restated operating comparatives remain separate from original point-in-time disclosures.",
        ],
        "evidence_refs": [
            *[
                {
                    "id": source["source_id"],
                    "path": source["path"],
                    "url": source["url"],
                    "sha256": source["sha256"],
                    "page": None,
                    "unit": None,
                    "description": f"{source['title']} searched for route-specific delivered-cost disclosures",
                    "quoted_facts": [],
                }
                for source in sorted(sources.values(), key=lambda item: (item["year"], item["language"]))
            ],
            source_ref(
                "shenhua_2025_aggregate_transport_indicators_page_22",
                22,
                "billion tonne-km, million tonnes, billion tonne-nautical miles",
                "Aggregate railway, port and shipping operating indicators",
                ["自有铁路运输周转量 313.0十亿吨公里", "黄骅港装船量 217.0百万吨", "天津煤码头装船量 44.6百万吨", "航运周转量 114.9十亿吨海里"],
            ),
            source_ref(
                "shenhua_2025_segment_results_page_24",
                24,
                "CNY millions",
                "Pre-elimination railway, port and shipping revenue and cost",
                ["铁路 43,710 / 27,158", "港口 7,020 / 3,744", "航运 3,989 / 3,532"],
            ),
            source_ref(
                "shenhua_2025_coal_sales_page_30",
                30,
                "million tonnes and CNY/tonne",
                "Self-produced and purchased coal sales volume and price",
                ["自产煤 332.3百万吨 472元/吨", "外购煤 98.6百万吨 570元/吨", "合计 430.9百万吨 495元/吨"],
            ),
            source_ref(
                "shenhua_2025_production_cost_page_33",
                33,
                "CNY/tonne",
                "Production-scope self-produced coal unit cost and components",
                ["自产煤单位生产成本 171.6元/吨", "折旧及摊销 22.2元/吨"],
            ),
            source_ref(
                "shenhua_2025_railway_port_unit_costs_page_39",
                39,
                "CNY/t-km and CNY/t",
                "Disclosed railway and port unit costs",
                ["铁路 0.082元/吨公里", "港口 11.5元/吨"],
            ),
            source_ref(
                "shenhua_2025_shipping_unit_cost_page_40",
                40,
                "CNY/t-nautical-mile",
                "Disclosed shipping unit cost",
                ["航运 0.030元/吨海里"],
            ),
            prior_ref(
                "shenhua_price_cost_transport_bridge",
                PRIOR_POINTER,
                "Previously compiled external-price and 2025 internal cost-transport bridge",
            ),
        ],
        "blockers": [
            "route_specific_transport_volume_and_cost_not_disclosed",
            "mine_to_customer_route_allocation_matrix_not_disclosed",
            "production_cost_excludes_delivery_and_transport",
            "aggregate_transport_costs_mix_internal_external_and_non_coal_work",
            "all_in_delivered_cost_cannot_be_audited_from_retained_filings",
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
    source_hashes = {
        source_id: source["sha256"]
        for source_id, source in load_sources().items()
    }
    prior_payload = json.loads(PRIOR_POINTER.read_text(encoding="utf-8"))
    manifest = {
        "script_sha256": script_digest,
        "evidence_sha256": digest,
        "source_sha256s": source_hashes,
        "prior_evidence_sha256s": {
            "price_cost_transport_bridge": prior_payload["sha256"],
        },
    }
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    POINTER.write_text(
        json.dumps({
            "path": OUT.relative_to(ROOT).as_posix(),
            "sha256": digest,
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "output": target.relative_to(ROOT).as_posix(),
        "sha256": digest,
        "status": payload["status"],
        "pages_scanned": payload["search_scope"]["pages_scanned"],
        "route_specific_metric_hits": len(payload["route_specific_metric_phrase_hits"]),
        "explicit_allocation_hits": len(payload["explicit_allocation_term_hits"]),
        "registered_inputs": payload["registered_cyclical_facts_operating_inputs"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
