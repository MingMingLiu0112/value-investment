"""Audit Shenhua's operating series into period facts versus model inputs."""
from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERIES_POINTER = ROOT / "runtime/company-research/shenhua-2014-2025-operational-cycle-series-latest.json"
RAW_SERIES = ROOT / "runtime/company-research/shenhua-cyclical-time-series-20260921/evidence.json"
SCOPE = ROOT / "runtime/company-research/shenhua-cyclical-scope-20260921/evidence.json"
CANDIDATE_POINTER = ROOT / "runtime/company-research/shenhua-cyclical-candidate-inputs-latest.json"
OUT = ROOT / "runtime/company-research/shenhua-2014-2025-operational-cycle-audit-20260922"
POINTER = ROOT / "runtime/company-research/shenhua-2014-2025-operational-cycle-audit-latest.json"

REVIEW_DATE = date(2026, 9, 22)

FIELDS = (
    "coal_sales_volume_million_tonnes",
    "blended_average_coal_price_cny_per_tonne",
    "self_produced_coal_sales_volume_million_tonnes",
    "self_produced_coal_average_price_cny_per_tonne",
    "self_produced_coal_unit_production_cost_cny_per_tonne",
    "electricity_sold_twh",
    "average_power_sale_price_cny_per_mwh",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pinned_evidence(pointer: Path) -> tuple[dict, Path, str]:
    pin = json.loads(pointer.read_text(encoding="utf-8"))
    target = ROOT / pin["path"] / "evidence.json"
    if not target.is_relative_to(ROOT.resolve()):
        raise ValueError("Evidence pointer escapes project root")
    actual = sha256(target)
    if actual != pin["sha256"].lower():
        raise ValueError("Pinned evidence hash mismatch")
    return json.loads(target.read_text(encoding="utf-8")), target, actual


def ref(ref_id: str, path: Path, *, description: str) -> dict:
    return {
        "id": ref_id,
        "path": str(path.relative_to(ROOT)),
        "sha256": sha256(path),
        "description": description,
    }


def non_null(values: list[object]) -> int:
    return sum(value is not None for value in values)


def build() -> dict:
    payload, series_path, series_hash = pinned_evidence(SERIES_POINTER)
    manifest = json.loads((series_path.parent / "manifest.json").read_text(encoding="utf-8"))
    if manifest["evidence_sha256"] != series_hash:
        raise ValueError("Operational series manifest does not match evidence")

    sources = {item["source_id"]: item for item in payload["sources"]}
    if set(manifest["source_sha256s"]) != set(sources):
        raise ValueError("Operational series manifest source set mismatch")
    for source_id, source in sources.items():
        path = ROOT / source["path"]
        if sha256(path) != source["sha256"]:
            raise ValueError(f"Source hash mismatch: {source_id}")
        if manifest["source_sha256s"][source_id] != source["sha256"]:
            raise ValueError(f"Manifest source hash mismatch: {source_id}")

    rows = payload["series"]
    if [row["year"] for row in rows] != list(range(2014, 2026)):
        raise ValueError("Operational series years are incomplete")
    by_year = {row["year"]: row for row in rows}

    later_year_volume_years = sorted(
        row["year"] for row in rows
        if row["page_refs"]["self_produced_coal_sales_volume"]["source_id"] != f"shenhua_{row['year']}_annual_report"
    )
    comparable_power_price_years = sorted(
        row["year"] for row in rows
        if row["average_power_sale_price_cny_per_mwh"] is not None
    )
    scope = json.loads(SCOPE.read_text(encoding="utf-8"))
    production_2025 = float(scope["reported_inputs"]["self_produced_coal_million_tonnes"])
    sales_2025 = by_year[2025]["self_produced_coal_sales_volume_million_tonnes"]
    if production_2025 == sales_2025:
        raise ValueError("2025 production and self-produced sales volumes must not be conflated")

    field_decisions = {
        "coal_sales_volume_million_tonnes": {
            "decision": "approved_as_period_fact_only",
            "coverage": f"{non_null([row['coal_sales_volume_million_tonnes'] for row in rows])}/12",
            "scope": "group total coal sales volume",
            "model_input": None,
            "reason": "A disclosed annual operating volume is source-addressed period evidence, not a normalized profit input.",
        },
        "blended_average_coal_price_cny_per_tonne": {
            "decision": "approved_as_period_fact_only",
            "coverage": f"{non_null([row['blended_average_coal_price_cny_per_tonne'] for row in rows])}/12",
            "scope": "group blended coal average price",
            "model_input": None,
            "reason": "The blended group price cannot be paired with self-produced unit production cost to infer a unit margin.",
        },
        "self_produced_coal_sales_volume_million_tonnes": {
            "decision": "approved_as_period_fact_only",
            "coverage": "12/12",
            "scope": "self-produced coal sales volume",
            "later_year_comparative_years": later_year_volume_years,
            "model_input": None,
            "reason": "Volumes carried from a later year's comparative table are available only at that later filing date.",
        },
        "self_produced_coal_average_price_cny_per_tonne": {
            "decision": "approved_as_period_fact_only",
            "coverage": f"{non_null([row['self_produced_coal_average_price_cny_per_tonne'] for row in rows])}/12",
            "scope": "self-produced coal average price, 2022-2025 only",
            "model_input": None,
            "reason": "A disclosed price is not a mine-to-parent contribution because transport, tax, inter-segment and elimination effects remain.",
        },
        "self_produced_coal_unit_production_cost_cny_per_tonne": {
            "decision": "approved_as_period_fact_only",
            "coverage": f"{non_null([row['self_produced_coal_unit_production_cost_cny_per_tonne'] for row in rows])}/12",
            "scope": "absolute self-produced coal unit production cost",
            "model_input": None,
            "reason": "This is a historical production-cost series, not a total delivered cost, all-in cash cost or independently verified competitive cost curve.",
        },
        "electricity_sold_twh": {
            "decision": "approved_as_period_fact_only",
            "coverage": f"{non_null([row['electricity_sold_twh'] for row in rows])}/12",
            "scope": "group electricity sold, with 2019 power reorganization and restatement boundaries",
            "model_input": None,
            "reason": "Electricity volume is period evidence; it does not establish normalized power profit or price.",
        },
        "average_power_sale_price_cny_per_mwh": {
            "decision": "approved_as_period_fact_only_with_scope_boundaries",
            "coverage": f"{non_null([row['average_power_sale_price_cny_per_mwh'] for row in rows])}/12",
            "comparable_years": comparable_power_price_years,
            "excluded_years": [2019, 2020],
            "model_input": None,
            "reason": "2019/2020 group power-price values are not established or comparable because of the January 2019 power joint-venture reorganization.",
        },
    }

    model_input_decisions = {
        "bear_normalized_parent_operating_profit": "cannot_derive_from_operating_series",
        "base_normalized_parent_operating_profit": "cannot_derive_from_operating_series",
        "bull_normalized_parent_operating_profit": "cannot_derive_from_operating_series",
        "cash_tax_rate": "not_present",
        "maintenance_capex": "not_present",
        "normalized_working_capital_change": "not_present",
        "discount_rate": "not_present",
        "long_term_growth": "not_present",
        "resource_life_years": "not_present",
        "net_cash_attributable_to_parent": "not_present",
        "ordinary_shares": "separate_point_in_time_denominator_approved_but_not_registered",
        "trough_parent_operating_profit": "not_established_by_descriptive_series",
        "unit_cost": "rejected_as_direct_model_input_historical_production_cost_only",
    }

    return {
        "symbol": "601088",
        "period_start": "2014-01-01",
        "period_end": "2025-12-31",
        "review_date": REVIEW_DATE.isoformat(),
        "source_type": "independent_audit_of_pinned_shenhua_operating_cycle_series",
        "engineering_status": "operational_cycle_audit_complete",
        "status": "operational_cycle_series_audited_as_period_evidence_only",
        "financial_scope_approved": False,
        "valuation_status": "VALUATION_NOT_READY",
        "formal_fair_value": None,
        "valuation_approved": False,
        "simulation_eligible": False,
        "trade_approved": False,
        "live_eligible": False,
        "purpose": (
            "Classify each source-addressed operational observation as period evidence or a verified "
            "cyclical model input. No value in this audit is registered in CyclicalFacts.operating_inputs."
        ),
        "audit_conclusion": (
            "All seven operational fields are retained as point-in-time period facts. None is approved as "
            "a direct model input. The series improves cost and price research provenance but does not yet "
            "establish normalized parent operating profit, an all-in cost curve, trough solvency or valuation."
        ),
        "field_decisions": field_decisions,
        "model_input_decisions": model_input_decisions,
        "registered_cyclical_facts_operating_inputs": [],
        "specific_findings": [
            {
                "id": "production_is_not_sales_2025",
                "fact": f"2025 self-produced production is {production_2025} Mt while self-produced sales volume is {sales_2025} Mt.",
                "use": "period_fact",
                "model_input": None,
            },
            {
                "id": "later_year_comparative_volume_provenance",
                "years": later_year_volume_years,
                "fact": "Self-produced sales volume for these years comes from a later annual report's comparative table, not the fiscal year's own filing.",
                "use": "period_fact_available_at_later_filing_date",
                "model_input": None,
            },
            {
                "id": "blended_price_unit_cost_pairing_forbidden",
                "fact": "Blended group average coal price and self-produced unit production cost measure different economic scopes and must not be subtracted.",
                "use": "research_boundary",
                "model_input": None,
            },
            {
                "id": "power_price_scope_break",
                "years": [2019, 2020],
                "fact": "The 2019 power joint-venture reorganization prevents a single comparable group power-price series across all twelve years.",
                "use": "research_boundary",
                "model_input": None,
            },
        ],
        "point_in_time_policy": [
            "Original fiscal-year filings are point-in-time facts as of their own publication dates.",
            "Values carried forward in a later filing's comparative table are point-in-time only as of the later filing.",
            "Restated comparatives are separate versions and do not make the original filing incorrect when first published.",
            "A historical simulation dated before the later filing must not use that later filing's comparative value.",
        ],
        "forbidden_calculations": [
            "blended_average_coal_price - self_produced_unit_production_cost = unit margin",
            "operating_quantity * disclosed_price = attributable operating profit without tax, minority, inter-segment and elimination reconciliation",
            "descriptive minimum or maximum = verified mid-cycle or trough model input",
        ],
        "evidence_refs": [
            ref("shenhua_operating_cycle_series", series_path, description="2014-2025 operational cycle series under audit"),
            ref("shenhua_cyclical_raw_time_series", RAW_SERIES, description="2014-2025 reviewed raw financial time series"),
            ref("shenhua_cyclical_scope", SCOPE, description="2025 annual report cyclical scope audit"),
            ref("shenhua_cyclical_candidate_inputs", ROOT / json.loads(CANDIDATE_POINTER.read_text(encoding="utf-8"))["path"] / "evidence.json", description="Reviewed cyclical input candidate package"),
        ],
        "blockers": [
            "period_evidence_only_no_cyclical_model_inputs_approved",
            "blended_group_coal_price_cannot_be_paired_with_unit_production_cost",
            "later_year_comparative_volumes_are_not_contemporaneous_for_2014_2015_2017_2019",
            "2019_2020_power_price_scope_is_not_comparable",
            "unit_production_cost_is_not_an_all_in_cost_curve",
            "normalized_profit_and_other_required_cyclical_inputs_still_missing",
        ],
    }


def main() -> None:
    payload = build()
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "evidence.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    digest = sha256(target)
    script_digest = sha256(Path(__file__).resolve())
    input_manifest = json.loads(
        (ROOT / json.loads(SERIES_POINTER.read_text(encoding="utf-8"))["path"] / "manifest.json").read_text(encoding="utf-8")
    )
    source_hashes = input_manifest["source_sha256s"]
    manifest = {
        "script_sha256": script_digest,
        "evidence_sha256": digest,
        "operating_series_sha256": json.loads(SERIES_POINTER.read_text(encoding="utf-8"))["sha256"],
        "source_sha256s": source_hashes,
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
