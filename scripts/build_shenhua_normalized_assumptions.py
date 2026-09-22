"""Register Shenhua's first normalised cyclical assumptions as candidates.

This script consumes only the existing 2014-2025 operational and attributable-
profit packages. The resulting set is PARTIAL: historical candidates become
explicit assumption objects, but are not approved model inputs and no valuation
arithmetic is run.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from value_investment_agent.valuation_assumptions import (
    ValuationAssumption,
    build_valuation_assumption_set,
)


ROOT = Path(__file__).resolve().parents[1]

OPERATIONAL_POINTER = ROOT / "runtime/company-research/shenhua-2014-2025-operational-cycle-series-latest.json"
ATTRIBUTABLE_POINTER = ROOT / "runtime/company-research/shenhua-2014-2025-attributable-profit-series-latest.json"
CANDIDATE_POINTER = ROOT / "runtime/company-research/shenhua-cyclical-candidate-inputs-latest.json"
OUT = ROOT / "runtime/valuation-assumptions/shenhua-normalized-candidates-20260922"
POINTER = ROOT / "runtime/valuation-assumptions/601088-normalized-latest.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_pinned_pointer(pointer: Path) -> tuple[dict, str]:
    pin = json.loads(pointer.read_text(encoding="utf-8"))
    target = (ROOT / pin["path"] / "evidence.json").resolve()
    if not target.is_relative_to(ROOT.resolve()):
        raise ValueError(f"Pinned path escapes project root: {pointer.name}")
    if digest(target) != pin["sha256"]:
        raise ValueError(f"Pinned evidence changed: {pointer.name}")
    return json.loads(target.read_text(encoding="utf-8")), pin["sha256"]


def _median(values: list[Decimal]) -> Decimal:
    if not values:
        raise ValueError("Cannot calculate a median from an empty list")
    if len(values) % 2:
        return sorted(values)[len(values) // 2]
    ordered = sorted(values)
    return (ordered[len(values) // 2 - 1] + ordered[len(values) // 2]) / Decimal("2")


def _range(values: list[Decimal]) -> tuple[Decimal, Decimal, Decimal]:
    return min(values), _median(values), max(values)


def build() -> dict:
    operational, operational_hash = load_pinned_pointer(OPERATIONAL_POINTER)
    attributable, attributable_hash = load_pinned_pointer(ATTRIBUTABLE_POINTER)
    candidates, candidate_hash = load_pinned_pointer(CANDIDATE_POINTER)
    if (
        operational.get("symbol") != "601088"
        or operational.get("status")
        != "multi_year_operational_cycle_series_collected_not_approved_as_model_inputs"
        or attributable.get("symbol") != "601088"
        or candidates.get("symbol") != "601088"
    ):
        raise ValueError("Shenhua assumption source packages changed their contracts")

    price_values = [
        Decimal(str(row["blended_average_coal_price_cny_per_tonne"]))
        for row in operational["series"]
        if row.get("blended_average_coal_price_cny_per_tonne") is not None
    ]
    volume_values = [
        Decimal(str(row["self_produced_coal_sales_volume_million_tonnes"]))
        for row in operational["series"]
        if row.get("self_produced_coal_sales_volume_million_tonnes") is not None
    ]
    cost_values = [
        Decimal(str(row["self_produced_coal_unit_production_cost_cny_per_tonne"]))
        for row in operational["series"]
        if row.get("self_produced_coal_unit_production_cost_cny_per_tonne") is not None
    ]
    profit_values = [
        Decimal(str(row["derived_candidates"][
            "parent_attributable_pretax_operating_profit_uniform_share_pro_forma_cny_millions"
        ]))
        for row in attributable["series"]
    ]
    maintenance = candidates["candidate_derivations"]["maintenance_capex"]
    maintenance_low = Decimal(str(maintenance["candidate_values"]["accounting_depreciation_proxy_cny"]))
    maintenance_high = Decimal(str(maintenance["candidate_values"]["cash_capex_upper_bound_cny"]))
    resource = candidates["candidate_derivations"]["resource_life_years"]
    resource_low = Decimal(str(resource["candidate_values"]["jorc_over_current_output_years"]))
    resource_high = Decimal(str(resource["candidate_values"]["china_recoverable_over_current_output_years"]))

    price_bear, price_base, price_bull = _range(price_values)
    volume_bear, volume_base, volume_bull = _range(volume_values)
    _, cost_base, cost_bear = _range(cost_values)
    cost_bull = min(cost_values)
    profit_bear, profit_base, profit_bull = _range(profit_values)
    resource_base = (resource_low + resource_high) / Decimal("2")

    as_of = date(2026, 9, 22)
    assumptions = [
        ValuationAssumption(
            name="normalized_parent_operating_profit",
            unit="CNY millions/year",
            bear=profit_bear,
            base=profit_base,
            bull=profit_bull,
            basis="2014-2025 uniform-share pro-forma parent pre-tax operating-profit candidates from the retained annual reports",
            rationale="The uniform-share pro-forma series is a bounded research candidate, not a disclosed statutory line",
            as_of=as_of,
            confidence="low",
            sensitivity="high",
            evidence_refs=[{"id": "shenhua_attributable_profit_series"}],
            blockers=["parent_operating_profit_is_a_pro_forma_not_a_disclosed_statutory_line"],
        ),
        ValuationAssumption(
            name="normalized_price",
            unit="CNY/tonne",
            bear=price_bear,
            base=price_base,
            bull=price_bull,
            basis="2014-2025 group blended average coal price observations",
            rationale="The historical envelope is a candidate range; the blended group price is not a mine-to-parent contribution",
            as_of=as_of,
            confidence="low",
            sensitivity="high",
            evidence_refs=[{"id": "shenhua_operational_cycle_series"}],
            blockers=["blended_group_coal_price_cannot_be_paired_with_unit_production_cost"],
        ),
        ValuationAssumption(
            name="normalized_unit_cost",
            unit="CNY/tonne",
            bear=cost_bear,
            base=cost_base,
            bull=cost_bull,
            basis="2014-2025 absolute self-produced coal unit production cost observations",
            rationale="High cost is used in the bear scenario and low cost in the bull scenario; this is an all-in-cost candidate, not a verified curve",
            as_of=as_of,
            confidence="low",
            sensitivity="high",
            evidence_refs=[{"id": "shenhua_operational_cycle_series"}],
            blockers=["unit_production_cost_is_not_an_all_in_cost_curve"],
            ordering="descending",
        ),
        ValuationAssumption(
            name="maintenance_capex",
            unit="CNY/year",
            bear=maintenance_high,
            base=(maintenance_low + maintenance_high) / Decimal("2"),
            bull=maintenance_low,
            basis="2025 segment depreciation proxy and cash capex upper bound from the retained annual report",
            rationale="Maintenance and growth capital expenditure are not separately disclosed; the candidate uses accounting depreciation as a lower bound",
            as_of=as_of,
            confidence="low",
            sensitivity="high",
            evidence_refs=[{"id": "shenhua_cyclical_candidate_inputs"}],
            blockers=["maintenance_and_growth_capex_split_not_disclosed"],
            ordering="descending",
        ),
        ValuationAssumption(
            name="normalized_volume",
            unit="million tonnes/year",
            bear=volume_bear,
            base=volume_base,
            bull=volume_bull,
            basis="2014-2025 self-produced coal sales volume observations",
            rationale="Volume uses the historical envelope while retaining the later-year comparative-source boundary",
            as_of=as_of,
            confidence="medium",
            sensitivity="medium",
            evidence_refs=[{"id": "shenhua_operational_cycle_series"}],
            blockers=["later_year_comparative_volumes_are_not_contemporaneous_for_2014_2015_2017_2019"],
        ),
        ValuationAssumption(
            name="resource_life",
            unit="years",
            bear=resource_low,
            base=resource_base,
            bull=resource_high,
            basis="JORC and China recoverable reserve-to-2025-output candidate ratios",
            rationale="A static reserve/output ratio is a candidate for research sensitivity, not a reviewed mine service life",
            as_of=as_of,
            confidence="low",
            sensitivity="medium",
            evidence_refs=[{"id": "shenhua_cyclical_candidate_inputs"}],
            blockers=["resource_life_is_a_static_ratio_not_a_reviewed_life"],
        ),
    ]
    set_blockers = [
        "ASSUMPTION_MISSING:discount_rate",
        "ASSUMPTION_MISSING:long_term_growth",
        "FACT_MISSING:net_cash_attributable_to_parent",
        "FACT_MISSING:current_ordinary_share_denominator",
        "ASSUMPTION_LOW_CONFIDENCE:normalized_parent_operating_profit",
        "ASSUMPTION_LOW_CONFIDENCE:normalized_price",
        "ASSUMPTION_LOW_CONFIDENCE:normalized_unit_cost",
    ]
    evidence_refs = [
        {
            "id": "shenhua_operational_cycle_series",
            "path": str((ROOT / json.loads(OPERATIONAL_POINTER.read_text(encoding="utf-8"))["path"] / "evidence.json").relative_to(ROOT)),
            "sha256": operational_hash,
            "description": "2014-2025 Shenhua operational cycle series",
        },
        {
            "id": "shenhua_attributable_profit_series",
            "path": str((ROOT / json.loads(ATTRIBUTABLE_POINTER.read_text(encoding="utf-8"))["path"] / "evidence.json").relative_to(ROOT)),
            "sha256": attributable_hash,
            "description": "2014-2025 Shenhua attributable profit and tax candidate series",
        },
        {
            "id": "shenhua_cyclical_candidate_inputs",
            "path": str((ROOT / json.loads(CANDIDATE_POINTER.read_text(encoding="utf-8"))["path"] / "evidence.json").relative_to(ROOT)),
            "sha256": candidate_hash,
            "description": "Reviewed Shenhua cyclical input candidates",
        },
    ]
    assumption_set = build_valuation_assumption_set(
        symbol="601088",
        profile_id="cyclical_cash_return",
        model_type="cyclical_normalized",
        as_of=as_of,
        assumptions=assumptions,
        blockers=set_blockers,
        evidence_refs=evidence_refs,
    )
    return {
        "package_version": "shenhua-normalized-assumption-candidates-v1",
        "symbol": "601088",
        "assumption_set": assumption_set.as_policy(),
        "registered_model_inputs": False,
        "valuation_recalculated": False,
        "formal_fair_value": None,
        "valuation_approved": False,
        "trade_approved": False,
        "live_eligible": False,
    }


def main() -> None:
    payload = build()
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "evidence.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_digest = digest(target)
    (OUT / "manifest.json").write_text(
        json.dumps(
            {
                "script_sha256": digest(Path(__file__).resolve()),
                "evidence_sha256": output_digest,
                "operational_series_sha256": load_pinned_pointer(OPERATIONAL_POINTER)[1],
                "attributable_series_sha256": load_pinned_pointer(ATTRIBUTABLE_POINTER)[1],
                "candidate_inputs_sha256": load_pinned_pointer(CANDIDATE_POINTER)[1],
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    POINTER.write_text(
        json.dumps(
            {"path": OUT.relative_to(ROOT).as_posix(), "sha256": output_digest},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": target.relative_to(ROOT).as_posix(),
                "sha256": output_digest,
                "assumption_status": payload["assumption_set"]["status"],
                "registered_model_inputs": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
