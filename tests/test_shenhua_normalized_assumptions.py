import hashlib
import importlib.util
import json
from pathlib import Path
import sys

from decimal import Decimal


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "shenhua_normalized_assumptions",
    ROOT / "scripts" / "build_shenhua_normalized_assumptions.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_shenhua_moves_from_facts_to_explicit_partial_assumptions():
    payload = MODULE.build()
    assumption_set = payload["assumption_set"]
    names = {assumption["name"] for assumption in assumption_set["assumptions"]}

    assert assumption_set["status"] == "PARTIAL"
    assert names == {
        "normalized_parent_operating_profit",
        "normalized_price",
        "normalized_unit_cost",
        "maintenance_capex",
        "normalized_volume",
        "resource_life",
    }
    assert payload["registered_model_inputs"] is False
    assert payload["valuation_recalculated"] is False
    assert payload["formal_fair_value"] is None
    assert payload["valuation_approved"] is False
    assert any(blocker.startswith("ASSUMPTION_MISSING:discount_rate") for blocker in assumption_set["blockers"])
    assert any(blocker.startswith("FACT_MISSING:net_cash_attributable_to_parent") for blocker in assumption_set["blockers"])

    unit_cost = next(a for a in assumption_set["assumptions"] if a["name"] == "normalized_unit_cost")
    assert unit_cost["ordering"] == "descending"
    assert Decimal(unit_cost["bear"]) > Decimal(unit_cost["base"]) > Decimal(unit_cost["bull"])


def test_shenhua_assumption_pointer_is_hash_bound():
    pointer = ROOT / "runtime/valuation-assumptions/601088-normalized-latest.json"
    pin = json.loads(pointer.read_text(encoding="utf-8"))
    evidence = ROOT / pin["path"] / "evidence.json"

    assert hashlib.sha256(evidence.read_bytes()).hexdigest() == pin["sha256"]
