import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "moutai_p2_fixture", ROOT / "scripts" / "run_moutai_p2_settlement_fixture.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_fixture_generates_a_decision_then_settles_once_and_refuses_replay(tmp_path):
    result = MODULE.run(tmp_path / "fixture")
    assert result["created_decision_state"] == "proposed_entry"
    assert result["settlement"]["fill"]["quantity"] == result["created_quantity"]
    assert result["second_settlement_refused_without_mutation"] is True
    assert result["trade_approved"] is False
