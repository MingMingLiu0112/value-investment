import hashlib
import importlib.util
import json
from pathlib import Path
import sys

from decimal import Decimal


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "moutai_assumption_set", ROOT / "scripts" / "build_moutai_assumption_set.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_moutai_existing_assumptions_map_without_revaluation():
    payload = MODULE.build()
    assumption_set = payload["assumption_set"]
    values = {
        assumption["name"]: assumption
        for assumption in assumption_set["assumptions"]
    }

    assert payload["mapping_only"] is True
    assert payload["parameters_changed"] is False
    assert payload["valuation_recalculated"] is False
    assert payload["formal_fair_value"] is None
    assert assumption_set["status"] == "READY"
    assert set(values) == {
        "income_growth",
        "payout_ratio",
        "retention_ratio",
        "forecast_years",
        "fade_years",
        "terminal_growth",
        "cost_of_equity",
        "terminal_roe_policy",
    }
    assert values["income_growth"]["bear"] == "-0.05"
    assert values["income_growth"]["base"] == "0"
    assert values["income_growth"]["bull"] == "0.05"
    assert values["payout_ratio"]["base"] == "0.75"
    assert values["retention_ratio"]["base"] == "0.25"
    assert values["terminal_growth"]["base"] == "0.02"
    assert values["terminal_roe_policy"]["base"] == "cost_of_equity_no_permanent_excess_return"
    assert Decimal(values["cost_of_equity"]["bear"]) > Decimal(values["cost_of_equity"]["base"])
    assert Decimal(values["cost_of_equity"]["base"]) > Decimal(values["cost_of_equity"]["bull"])


def test_moutai_assumption_pointer_is_hash_bound():
    pointer = ROOT / "runtime/valuation-assumptions/600519-current-latest.json"
    pin = json.loads(pointer.read_text(encoding="utf-8"))
    evidence = ROOT / pin["path"] / "evidence.json"

    assert hashlib.sha256(evidence.read_bytes()).hexdigest() == pin["sha256"]
    assert MODULE.digest(MODULE.FORWARD) == MODULE.FORWARD_SHA256
    assert MODULE.digest(MODULE.CURRENT_MODEL) == MODULE.CURRENT_MODEL_SHA256
    assert MODULE.digest(MODULE.DISCOUNT) == MODULE.DISCOUNT_SHA256
