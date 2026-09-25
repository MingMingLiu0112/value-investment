import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "moutai_historical_range_strategy", ROOT / "scripts" / "replay_moutai_experimental_range_strategy.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_range_provider_keeps_a_missing_value_non_actionable():
    provider = MODULE.make_provider({"2020-01-01": {"lower": None}}, "lower", MODULE.Decimal("0.30"))
    decision = provider({"date": "2020-01-01", "close": "100"}, {"shares": 0, "cash": "1000000", "receivables": "0"})
    assert decision["state"] == "watch"
    assert decision["action"] == "no_order"


def test_range_provider_uses_explicit_margin_and_board_lot_sizing():
    provider = MODULE.make_provider({"2020-01-01": {"upper": MODULE.Decimal("200")}}, "upper", MODULE.Decimal("0.30"))
    decision = provider({"date": "2020-01-01", "close": "100"}, {"shares": 0, "cash": "1000000", "receivables": "0"})
    assert decision["state"] == "proposed_entry"
    assert decision["quantity"] % 100 == 0
    assert decision["safety_margin"] == "0.5"


def test_registered_periods_are_chronological_and_non_overlapping():
    periods = MODULE.PERIODS
    assert [row[0] for row in periods] == ["development", "validation", "sealed_test"]
    assert periods[0][2] < periods[1][1] < periods[1][2] < periods[2][1]


def test_range_result_keeps_the_retrospective_experiment_out_of_strategy_validation():
    source = (ROOT / "scripts" / "replay_moutai_experimental_range_strategy.py").read_text(encoding="utf-8")
    assert '"validation_classification": NOT_PIT_SAFE' in source
    assert '"approved_value_model_sessions": 0' in source
    assert '"strategy_backtest_complete": False' in source
