"""Review Shenhua's 2025 internal coal-power volume and fuel-cost disclosures."""
from __future__ import annotations

from decimal import Decimal, localcontext
import hashlib
import json
import logging
from pathlib import Path

from pypdf import PdfReader


logging.getLogger("pypdf").setLevel(logging.ERROR)

ROOT = Path(__file__).resolve().parents[1]
SOURCE_CN = ROOT / "runtime/shenhua-2025-official.pdf"
SOURCE_CN_URL = "https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0330/2026033004060_c.pdf"
SOURCE_CN_HASH = "460ea07ee14d3aeb2b7518a25f87b47833ea5473715d911c378c15f7425698fc"
SOURCE_CN_BYTES = 19_875_785
SOURCE_CN_PAGES = 481

SOURCE_EN = ROOT / "runtime/company-research/shenhua-2025-ifrs-annual-review-20260922/2026033003712.pdf"
SOURCE_EN_URL = "https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0330/2026033003712.pdf"
SOURCE_EN_HASH = "491E701A90B1ECE239B95CE3F3DE27053F420583F2458D81CBE5B21B4607FDC9"
SOURCE_EN_BYTES = 8_479_182
SOURCE_EN_PAGES = 373

PRIOR_POINTER = ROOT / "runtime/company-research/shenhua-2014-2025-price-cost-transport-bridge-latest.json"
OUT = ROOT / "runtime/company-research/shenhua-2025-internal-coal-power-reconciliation-20260922"
POINTER = ROOT / "runtime/company-research/shenhua-2025-internal-coal-power-reconciliation-latest.json"


def normalized_text(reader: PdfReader, page: int) -> str:
    return " ".join((reader.pages[page - 1].extract_text() or "").replace("\x00", " ").split())


def page_text(reader: PdfReader, page: int, expected: tuple[str, ...]) -> str:
    text = normalized_text(reader, page)
    missing = [value for value in expected if value not in text]
    if missing:
        raise ValueError(f"Page {page} does not contain expected evidence {missing!r}")
    return text


def source_ref(
    ref_id: str,
    report: str,
    page: int,
    unit: str,
    description: str,
    quoted_facts: list[str],
) -> dict:
    if report == "cn":
        path = SOURCE_CN
        url = SOURCE_CN_URL
        digest = SOURCE_CN_HASH
    elif report == "en":
        path = SOURCE_EN
        url = SOURCE_EN_URL
        digest = SOURCE_EN_HASH
    else:
        raise ValueError(f"Unknown report {report!r}")
    return {
        "id": ref_id,
        "path": path.relative_to(ROOT).as_posix(),
        "url": url,
        "sha256": digest,
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


def term_pages(reader: PdfReader, terms: tuple[str, ...]) -> dict[str, list[int]]:
    hits: dict[str, list[int]] = {}
    for index, page in enumerate(reader.pages, start=1):
        text = normalized_text(reader, index)
        for term in terms:
            if term in text:
                hits.setdefault(term, []).append(index)
    return hits


def build() -> dict:
    if hashlib.sha256(SOURCE_CN.read_bytes()).hexdigest() != SOURCE_CN_HASH:
        raise ValueError("Shenhua Chinese annual report hash mismatch")
    if SOURCE_CN.stat().st_size != SOURCE_CN_BYTES:
        raise ValueError("Shenhua Chinese annual report size mismatch")
    cn_reader = PdfReader(str(SOURCE_CN))
    if len(cn_reader.pages) != SOURCE_CN_PAGES:
        raise ValueError("Shenhua Chinese annual report page count mismatch")

    if hashlib.sha256(SOURCE_EN.read_bytes()).hexdigest().upper() != SOURCE_EN_HASH:
        raise ValueError("Shenhua English annual report hash mismatch")
    if SOURCE_EN.stat().st_size != SOURCE_EN_BYTES:
        raise ValueError("Shenhua English annual report size mismatch")
    en_reader = PdfReader(str(SOURCE_EN))
    if len(en_reader.pages) != SOURCE_EN_PAGES:
        raise ValueError("Shenhua English annual report page count mismatch")

    page_text(cn_reader, 30, ("自产煤", "332.3", "472", "外购煤", "98.6", "570", "430.9", "495"))
    page_text(cn_reader, 31, ("对外部客户销售", "352.7", "对内部发电分部销售", "73.2", "447", "对内部煤化工分部销售", "5.0", "405"))
    page_text(cn_reader, 38, ("77.7", "97.7", "79.5", "原材料、燃料及动力", "47,702"))
    page_text(cn_reader, 24, ("煤炭", "430.9", "23.4", "(2.5)"))
    page_text(cn_reader, 41, ("煤化工分部共耗用煤炭", "5.1", "全部为本集团内部销售的煤炭"))
    page_text(cn_reader, 459, ("从煤炭业务分部和外部供应商采购煤炭", "以煤炭发电"))

    page_text(en_reader, 45, ("Self-produced coal", "332.3", "Purchased coal", "98.6", "430.9", "495"))
    page_text(en_reader, 46, ("Sales to internal power", "73.2", "447", "Sales to internal coal", "5.0", "405"))
    page_text(en_reader, 57, ("77.7 million tonnes", "97.7 million", "Raw material, fuel and power", "47,702"))
    page_text(en_reader, 34, ("Inventory at", "23.4", "(2.5)"))
    page_text(en_reader, 287, ("use coal from the coal operations segment and external suppliers", "power operations segment"))

    cn_term_hits = term_pages(cn_reader, ("73.2", "77.7", "内部销售", "库存", "期初库存", "期末库存量", "煤炭耗用"))
    en_term_hits = term_pages(en_reader, ("73.2", "77.7", "Inventory at", "internal power segment", "coal sold within the Group"))

    with localcontext() as ctx:
        ctx.prec = 12
        volume_difference = Decimal("77.7") - Decimal("73.2")
        external_consumption = Decimal("97.7") - Decimal("77.7")
        fuel_cost_per_internal_tonne = Decimal(47_702) / Decimal("77.7")

    payload: dict[str, object] = {
        "symbol": "601088",
        "as_of_period": "2025-12-31",
        "source_type": "annual_report_internal_coal_power_reconciliation_review",
        "package_version": "shenhua-internal-coal-power-reconciliation-v1",
        "engineering_status": "internal_coal_power_reconciliation_evidence_boundary_complete",
        "status": "sales_and_consumption_basis_documented_no_explicit_volume_bridge_found",
        "valuation_status": "VALUATION_NOT_READY",
        "purpose": (
            "Pin the 2025 coal-segment internal power sales volume, power-segment internal coal "
            "consumption, fuel cost, inventory and segment-sourcing disclosures, and determine "
            "whether the retained reports explicitly reconcile the 4.5 million tonne difference."
        ),
        "key_findings": [
            "The coal table records 73.2 Mt sold to the internal power segment at 447 CNY/t.",
            "The power table records 77.7 Mt of coal sold within the Group consumed by power, out of 97.7 Mt total consumption.",
            "The reports do not disclose a table or note that reconciles the 4.5 Mt difference.",
            "The two measures use different operational bases: sales volume versus coal consumed.",
            "Power operations are disclosed as purchasing coal from both the coal operations segment and external suppliers.",
            "Group coal inventory at period end is 23.4 Mt and inventory is reported 2.5% below the beginning of the period; no power-plant fuel inventory volume bridge is disclosed.",
            "47,702 million CNY raw-material, fuel and power cost cannot be converted into an internal transfer price by dividing by 77.7 Mt because it includes external coal, quality and heat differences, transport, inventory timing and other energy inputs.",
        ],
        "coal_segment_internal_sales_2025": {
            "basis": "coal sales volume",
            "internal_power_sales_million_tonnes": 73.2,
            "internal_power_sales_price_cny_per_tonne": 447,
            "internal_coal_chemical_sales_million_tonnes": 5.0,
            "internal_coal_chemical_sales_price_cny_per_tonne": 405,
            "total_sales_million_tonnes": 430.9,
            "total_average_sales_price_cny_per_tonne": 495,
            "self_produced_sales_million_tonnes": 332.3,
            "purchased_coal_sales_million_tonnes": 98.6,
        },
        "power_segment_consumption_2025": {
            "basis": "coal consumed by power segment",
            "internal_group_coal_consumed_million_tonnes": 77.7,
            "total_coal_consumed_million_tonnes": 97.7,
            "internal_share_pct": 79.5,
            "coal_power_raw_material_fuel_power_cost_cny_millions": 47_702,
            "source_scope": "coal sold within the Group, including self-produced coal and purchased coal of the Group",
        },
        "volume_reconciliation": {
            "coal_segment_internal_power_sales_million_tonnes": "73.2",
            "power_segment_internal_coal_consumed_million_tonnes": "77.7",
            "difference_million_tonnes": str(volume_difference),
            "derived_external_power_coal_million_tonnes": str(external_consumption),
            "explicit_reconciliation_disclosed": False,
            "reconciliation_status": "not_reconciled_by_disclosed_data",
            "basis_conflict": (
                "One value is a sales-volume classification and the other is a consumption-volume "
                "measure. Equality is not required by the disclosures and cannot be assumed."
            ),
        },
        "inventory_boundary": {
            "group_coal_inventory_end_million_tonnes": 23.4,
            "inventory_versus_beginning_pct": -2.5,
            "power_plant_fuel_inventory_volume_bridge_disclosed": False,
            "note": (
                "This is group-level coal product inventory. It does not allocate opening or closing "
                "fuel stock at power plants and therefore cannot independently explain the 4.5 Mt difference."
            ),
        },
        "fuel_cost_boundary": {
            "raw_material_fuel_power_cost_cny_millions": 47_702,
            "simple_division_by_77_7_mt_cny_per_tonne": str(fuel_cost_per_internal_tonne),
            "is_internal_transfer_price": False,
            "reason": (
                "The cost line is not stated as internal coal tonnage multiplied by one price. It can "
                "include external coal, heat and quality differences, transport, inventory timing and "
                "non-coal energy inputs."
            ),
        },
        "candidate_explanations": [
            {
                "id": "sales_volume_versus_consumption_volume",
                "status": "definitional_basis_difference",
                "supported_by_disclosure": True,
                "explanation": "The coal table describes sales while the power table describes consumption.",
            },
            {
                "id": "power_plant_inventory_movement",
                "status": "plausible_but_not_disclosed",
                "supported_by_disclosure": False,
                "explanation": "Timing differences between delivery and burn can create a gap, but no power fuel inventory volume bridge is disclosed.",
            },
            {
                "id": "direct_external_power_purchases_counted_as_internal",
                "status": "contradicted_by_disclosure_label",
                "supported_by_disclosure": False,
                "explanation": "The 77.7 Mt is explicitly described as coal sold within the Group; direct external purchases belong to the 20.0 Mt external residual.",
            },
            {
                "id": "heat_quality_and_moisture_measurement_difference",
                "status": "plausible_but_not_disclosed",
                "supported_by_disclosure": False,
                "explanation": "Mine calorific ranges are disclosed, but no adjustment converts sales tonnage to as-consumed tonnage.",
            },
        ],
        "search_scope": {
            "method": "targeted text search of retained Chinese and English annual-report PDFs",
            "chinese_term_pages": cn_term_hits,
            "english_term_pages": en_term_hits,
            "no_page_contains_both_73_2_and_77_7": {
                "chinese": not set(cn_term_hits.get("73.2", [])).intersection(cn_term_hits.get("77.7", [])),
                "english": not set(en_term_hits.get("73.2", [])).intersection(en_term_hits.get("77.7", [])),
            },
            "absence_note": (
                "Absence in these reports is evidence that the reconciliation is not presented in the "
                "director-report tables, not proof that a reconciliation could not exist elsewhere."
            ),
        },
        "model_input_decisions": {
            "normalized_mid_cycle_coal_price": {
                "status": "cannot_derive_from_internal_sales_or_consumption",
                "model_input": None,
                "reason": "447 CNY/t is an internal accounting transfer price, not a market mid-cycle price.",
            },
            "normalized_power_fuel_unit_cost": {
                "status": "cannot_derive_without_complete_fuel_bridge",
                "model_input": None,
                "reason": "47,702 million CNY must be separated into internal coal, external coal, quality, transport and other energy inputs.",
            },
            "normalized_self_produced_unit_cost": {
                "status": "outside_this_evidence_package",
                "model_input": None,
                "reason": "The 171.6 CNY/t production-scope cost remains separate from delivered fuel cost.",
            },
        },
        "registered_cyclical_facts_operating_inputs": [],
        "forbidden_calculations": [
            "73.2 Mt * 447 CNY/t = power raw-material fuel cost",
            "47,702 million CNY / 77.7 Mt = verified internal transfer price",
            "73.2 Mt and 77.7 Mt are an arithmetic error requiring forced equality",
            "group coal inventory delta fully explains the 4.5 Mt internal-volume difference",
        ],
        "evidence_refs": [
            source_ref("shenhua_cn_coal_source_page_30", "cn", 30, "CNY/t and Mt", "Chinese annual-report coal source sales table", ["Self-produced coal 332.3 Mt at 472 CNY/t", "Purchased coal 98.6 Mt at 570 CNY/t", "Total sales 430.9 Mt at 495 CNY/t"]),
            source_ref("shenhua_cn_internal_external_customer_page_31", "cn", 31, "CNY/t and Mt", "Chinese annual-report internal and external customer table", ["Sales to internal power segment 73.2 Mt at 447 CNY/t", "Sales to internal coal chemical segment 5.0 Mt at 405 CNY/t"]),
            source_ref("shenhua_cn_power_consumption_page_38", "cn", 38, "CNY millions and Mt", "Chinese annual-report power consumption and coal-fired cost table", ["77.7 Mt consumed within the Group", "Total coal consumption 97.7 Mt", "Raw materials, fuel and power 47,702 million CNY"]),
            source_ref("shenhua_cn_inventory_page_24", "cn", 24, "Mt", "Chinese annual-report major-product inventory", ["Coal inventory at end of period 23.4 Mt", "Inventory 2.5% below beginning"]),
            source_ref("shenhua_cn_coal_chemical_page_41", "cn", 41, "Mt", "Chinese annual-report coal chemical consumption", ["5.1 Mt coal consumed", "All coal sold within the Group"]),
            source_ref("shenhua_cn_segment_policy_page_459", "cn", 459, "text", "Chinese annual-report segment product and service descriptions", ["Power operations purchase coal from coal operations and external suppliers"]),
            source_ref("shenhua_en_internal_external_customer_page_46", "en", 46, "CNY/t and Mt", "English annual-report internal and external customer table", ["Sales to internal power segment 73.2 Mt at 447 CNY/t", "Sales to internal coal chemical segment 5.0 Mt at 405 CNY/t"]),
            source_ref("shenhua_en_power_consumption_page_57", "en", 57, "CNY millions and Mt", "English annual-report power consumption and coal-fired cost table", ["77.7 million tonnes consumed within the Group", "Total consumption 97.7 million tonnes", "Raw material, fuel and power 47,702 million CNY"]),
            source_ref("shenhua_en_inventory_page_34", "en", 34, "Mt", "English annual-report major-product inventory", ["Coal inventory at end of period 23.4 Mt", "Inventory 2.5% below beginning"]),
            source_ref("shenhua_en_segment_policy_page_287", "en", 287, "text", "English annual-report segment product and service descriptions", ["Power operations use coal from the coal operations segment and external suppliers"]),
            prior_ref("shenhua_price_cost_transport_bridge", PRIOR_POINTER, "Previously compiled external-price and 2025 internal cost-transport bridge"),
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
    prior_payload = json.loads(PRIOR_POINTER.read_text(encoding="utf-8"))
    manifest = {
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest().upper(),
        "evidence_sha256": evidence_sha256,
        "source_sha256s": {
            "shenhua_2025_chinese_annual_report": SOURCE_CN_HASH,
            "shenhua_2025_english_annual_report": SOURCE_EN_HASH,
        },
        "source_bytes": {
            "shenhua_2025_chinese_annual_report": SOURCE_CN_BYTES,
            "shenhua_2025_english_annual_report": SOURCE_EN_BYTES,
        },
        "prior_evidence_sha256s": {
            "price_cost_transport_bridge": prior_payload["sha256"],
        },
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    POINTER.write_text(json.dumps({
        "path": OUT.relative_to(ROOT).as_posix(),
        "sha256": evidence_sha256,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(target),
        "sha256": evidence_sha256,
        "status": payload["status"],
        "volume_difference_million_tonnes": payload["volume_reconciliation"]["difference_million_tonnes"],
        "explicit_reconciliation_disclosed": payload["volume_reconciliation"]["explicit_reconciliation_disclosed"],
        "registered_inputs": payload["registered_cyclical_facts_operating_inputs"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
