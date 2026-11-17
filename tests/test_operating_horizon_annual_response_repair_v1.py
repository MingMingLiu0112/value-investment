"""Direct offline checks for the exact annual response field relocation."""

from copy import deepcopy
import hashlib
import json

import pytest

from test_operating_horizon_annual_v3 import paired, _response, NOW
from test_operating_horizon_draft_v2 import context
from value_investment_agent.application.research.agent_review import operating_horizon_annual_response_repair_v1 as mod


def misplaced():
    value = _response()
    row = value["years"]["2026"]
    for field in mod.FIELDS:
        row["operating_paths"][field] = row.pop(field)
    return value


def test_exact_relocation_preserves_values_and_hashes(paired):
    value = misplaced()
    original = deepcopy(value)
    raw = json.dumps(value, ensure_ascii=False)
    out = mod.normalize_response(raw, paired, [2026], NOW)
    assert value == original
    assert out["version"] == mod.VERSION
    assert out["raw_sha256"] == hashlib.sha256(raw.encode()).hexdigest()
    assert out["derived_sha256"] != out["raw_sha256"]
    assert out["relocations"] == [
        {"from": f"/years/2026/operating_paths/{field}", "to": f"/years/2026/{field}"}
        for field in mod.FIELDS]
    assert out["validated_result"]["action"] == "no_order"
    assert out["validated_result"]["response_sha256"] == out["derived_sha256"]


@pytest.mark.parametrize("change", ["partial", "conflict", "extra_path", "extra_year", "duplicate", "citation", "economic", "already_valid"])
def test_all_other_faults_fail_closed(paired, change):
    value = misplaced()
    row = value["years"]["2026"]
    if change == "partial":
        row["operating_paths"].pop("reopen_condition")
    elif change == "conflict":
        row["counter_evidence"] = "conflicting declaration"
    elif change == "extra_path":
        row["operating_paths"]["other"] = {}
    elif change == "extra_year":
        row["other"] = "unexpected"
    elif change == "citation":
        row["operating_paths"]["bull"]["unit_cost_case"]["contrary_evidence_ids"] = ["unknown"]
    elif change == "economic":
        row["operating_paths"]["bull"].pop("drivers")
    elif change == "already_valid":
        for field in mod.FIELDS:
            row[field] = row["operating_paths"].pop(field)
    raw = json.dumps(value, ensure_ascii=False)
    if change == "duplicate":
        raw = raw.replace('"years":', '"years": {}, "years":', 1)
    with pytest.raises((ValueError, KeyError, TypeError)):
        mod.normalize_response(raw, paired, [2026], NOW)
