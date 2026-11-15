"""Native provider transport tests; no model calls or economic admission."""
from copy import deepcopy
import json

import pytest

from test_operating_horizon_split_v8 import _annual
from value_investment_agent.application.research.agent_review import operating_horizon_native_transport_v1 as native


def native_response(scenario="bear"):
    path = json.loads(_annual())["years"]["2027"]["operating_paths"][scenario]
    driver_ids = {
        "volume_change": "revenue_activity_volume",
        "realization_mix_change": "realization_mix_change",
        "unit_cost_change": "unit_cost_change",
        "fixed_cogs_share": "fixed_cogs_share",
        "opex_change": "opex_change",
        "surcharge_ratio": "surcharge_ratio",
        "other_pretax_cny": "other_pretax_cny",
    }
    drivers = []
    for name, value in path["drivers"].items():
        drivers.append(dict(driver_id=driver_ids[name], value=dict(type="range",
            lower=float(value["lower"]), upper=float(value["upper"]),
            unit="CNY" if name == "other_pretax_cny" else "ratio"),
            baseline_anchor_ids=value["evidence_ids"], rationale=value["rationale"]))
    capital_ids = {"investment": "capital_investment", "funding_access": "funding_access",
                   "terminal": "terminal"}
    capital = []
    for row in path["capital_assumptions"]:
        capital.append(dict(assumption_id=capital_ids[row["dimension"]],
            value=dict(type="unknown" if row["classification"] == "UNKNOWN" else "range",
                       lower=row["lower"], upper=row["upper"], unit=row["unit"]),
            baseline_anchor_ids=row["evidence_ids"], rationale=row["rationale"]))
    case = path["unit_cost_case"]
    return dict(scenario=scenario, drivers=drivers, capital_assumptions=capital,
                unit_cost_mechanism="INPUT_PRICE",
                unit_cost_case=dict(conditional_mechanism=case["mechanism"],
                                    mechanism_source_ids=case["source_anchor_ids"],
                                    contrary_evidence_ids=case["contrary_evidence_ids"]),
                counter_evidence=["Historical ratio is contrary evidence."],
                reopen_condition=case["reopen_condition"])


def test_native_shape_maps_without_altering_bounds_or_citations():
    raw = native_response()
    result = native.normalize_scenario(json.dumps(raw), "bear",
        period_start="2027-01-01", period_end="2027-12-31")
    assert result["drivers"]["volume_change"]["lower"] == str(raw["drivers"][0]["value"]["lower"])
    assert result["drivers"]["other_pretax_cny"]["evidence_ids"] == raw["drivers"][-1]["baseline_anchor_ids"]
    assert result["capital_assumptions"][0]["classification"] == "UNKNOWN"
    assert result["capital_assumptions"][0]["lower"] is None
    assert result["unit_cost_case"]["source_anchor_ids"] == raw["unit_cost_case"]["mechanism_source_ids"]


@pytest.mark.parametrize("mutate,code", [
    (lambda row: row["drivers"].pop(), "SEVEN_DRIVERS"),
    (lambda row: row["drivers"][0].update(driver_id="made_up"), "DRIVER_ID"),
    (lambda row: row["drivers"][0]["value"].update(unit="CNY"), "DRIVER_UNIT"),
    (lambda row: row["capital_assumptions"][0]["value"].update(lower=0), "UNKNOWN_BOUNDS"),
    (lambda row: row["unit_cost_case"].update(extra="x"), "Exact"),
])
def test_native_shape_rejects_ambiguous_or_invalid_fields(mutate, code):
    raw = native_response()
    mutate(raw)
    with pytest.raises(ValueError, match=code):
        native.normalize_scenario(json.dumps(raw), "bear",
            period_start="2027-01-01", period_end="2027-12-31")
