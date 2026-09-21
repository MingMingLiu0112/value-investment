import importlib.util
from decimal import Decimal
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("moutai_distributable_earnings", ROOT / "scripts" / "build_moutai_historical_distributable_earnings_range.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_value_uses_explicit_payout_and_return_assumptions():
    assert MODULE.value_per_share(Decimal("10"), Decimal("1"), Decimal("0.5"), Decimal("0.1"), Decimal("0")) == Decimal("50")


def test_only_bonus_share_event_blocks_the_per_share_comparison():
    input_row = {"date": "2020-01-01", "decision_at": "2020-01-01T15:00:00+08:00", "annual_available_at": "2019-01-01T00:00:00+08:00", "distributions_since_report": "2020-01-01", "annual_source_id": "source", "annual_profit_per_bonus_adjusted_share": "10", "report_period": "2018-12-31", "close": "50"}
    blocked = MODULE.build([input_row], {"2020-01-01": {"source_id": "source", "post_report_bonus_events": "1"}})
    allowed = MODULE.build([input_row], {"2020-01-01": {"source_id": "source", "post_report_bonus_events": "0"}})
    assert blocked[0]["status"] == "blocked_post_report_bonus_share_basis_missing"
    assert allowed[0]["status"] == "conditional_research_only"
    assert allowed[0]["cash_distributions_since_report"] == "2020-01-01"
