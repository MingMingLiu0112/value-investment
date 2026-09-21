import importlib.util
from decimal import Decimal
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "moutai_cash_anchor_equity", ROOT / "scripts" / "build_moutai_historical_cash_anchor_equity_range.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_cash_anchor_value_requires_explicit_return_and_growth():
    assert MODULE.value_per_share(Decimal("10"), Decimal("0.5"), Decimal("0.1"), Decimal("0")) == Decimal("50")


def test_build_blocks_dates_before_first_implemented_annual_cash_observation():
    rows = [{"date": "2020-01-01", "decision_at": "2020-01-01T15:00:00+08:00", "annual_source_id": "annual",
             "annual_profit_per_bonus_adjusted_share": "10", "report_period": "2019-12-31", "annual_available_at": "2019-03-01T00:00:00+08:00", "close": "50"}]
    timeline = [{"date": "2020-01-01", "latest_annual_cycle_distribution_event_id": None}]
    assert MODULE.build(rows, [], timeline)[0]["status"] == "blocked_no_prior_implemented_annual_cycle_cash_observation"


def test_build_uses_only_prior_implemented_cash_observations():
    rows = [{"date": "2021-07-01", "decision_at": "2021-07-01T15:00:00+08:00", "annual_source_id": "annual",
             "annual_profit_per_bonus_adjusted_share": "10", "report_period": "2020-12-31", "annual_available_at": "2021-03-01T00:00:00+08:00", "close": "50"}]
    observations = [{"event_id": "600519:2021-06-25", "status": "annual_cycle_cash_to_available_annual_eps",
                     "available_for_research_at": "2021-06-25T00:00:00+08:00", "cash_to_prior_annual_eps_ratio": "0.5"},
                    {"event_id": "600519:2022-06-30", "status": "annual_cycle_cash_to_available_annual_eps",
                     "available_for_research_at": "2022-06-30T00:00:00+08:00", "cash_to_prior_annual_eps_ratio": "0.9"}]
    timeline = [{"date": "2021-07-01", "latest_annual_cycle_distribution_event_id": "600519:2021-06-25"}]
    result = MODULE.build(rows, observations, timeline)[0]
    assert result["status"] == "cash_distribution_anchored_research_only"
    assert {item["payout_ratio_assumption"] for item in result["cases"]} == {"0.5"}
