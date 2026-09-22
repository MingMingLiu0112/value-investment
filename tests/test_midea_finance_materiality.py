import hashlib
import importlib.util
import json
from pathlib import Path
import sys

from decimal import Decimal


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "midea_finance_materiality", ROOT / "scripts" / "build_midea_finance_materiality.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_midea_finance_scope_is_quantified_low_and_fail_closed_for_fcff():
    payload = MODULE.build()
    assessment = payload["assessment"]
    effect = payload["applicability_effect"]

    assert payload["symbol"] == "000333"
    assert assessment["materiality"] == "LOW"
    assert assessment["treatment"] == "MODEL_AS_RANGE"
    assert Decimal(assessment["estimated_exposure_ratio"]) == Decimal("0.00934178")
    assert Decimal(assessment["downside_impact"]) == Decimal("-0.03520539")
    assert Decimal(assessment["upside_impact"]) == Decimal("0.03520539")
    assert payload["industrial_fcff_carve_out"] == "MODEL_NOT_APPLICABLE"
    assert effect["applicability_status_before"] == "MODEL_NOT_APPLICABLE"
    assert effect["applicability_status_after"] == "MODEL_NOT_APPLICABLE"
    assert effect["model_unlocked"] is False
    assert payload["registered_valuation_model"] is None
    assert payload["formal_fair_value"] is None
    assert payload["valuation_approved"] is False
    assert payload["trade_approved"] is False


def test_midea_materiality_pointer_is_hash_bound():
    pointer = ROOT / "runtime/company-research/000333-finance-materiality-latest.json"
    pin = json.loads(pointer.read_text(encoding="utf-8"))
    evidence = ROOT / pin["path"] / "evidence.json"

    assert hashlib.sha256(evidence.read_bytes()).hexdigest() == pin["sha256"]
