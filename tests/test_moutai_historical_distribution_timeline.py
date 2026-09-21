import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "moutai_distribution_timeline", ROOT / "scripts" / "build_moutai_historical_distribution_timeline.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def row(day, source="annual", eps="10"):
    return {"date": day, "decision_at": f"{day}T15:00:00+08:00",
            "annual_available_at": "2020-03-01T00:00:00+08:00", "annual_source_id": source,
            "annual_profit_per_bonus_adjusted_share": eps, "report_period": "2019-12-31"}


def event(payment, *, bonus=None):
    return {"record_date": payment, "ex_date": payment, "cash_payment_date": payment,
            "cash_per_share": "5", "evidence": [], "tax_treatment_verified": False,
            "bonus_shares_per_share": bonus}


def test_special_distribution_is_not_presented_as_annual_payout_ratio():
    observations, timeline = MODULE.build([row("2020-06-01"), row("2020-12-20")], [event("2020-12-20")])
    assert observations[0]["status"] == "special_distribution_not_annual_payout_ratio"
    assert observations[0]["cash_to_prior_annual_eps_ratio"] is None
    assert timeline[-1]["status"] == "no_prior_annual_cycle_cash_observation"


def test_bonus_share_event_blocks_ratio_and_later_annual_cash_observation_is_available():
    rows = [row("2020-06-01"), row("2020-07-01"), row("2021-06-01", source="annual-2", eps="20")]
    observations, timeline = MODULE.build(rows, [event("2020-07-01", bonus="0.1"), event("2021-06-01")])
    assert observations[0]["status"] == "blocked_bonus_share_denominator_ambiguous"
    assert observations[1]["status"] == "annual_cycle_cash_to_available_annual_eps"
    assert observations[1]["cash_to_prior_annual_eps_ratio"] == "0.25"
    assert timeline[-1]["latest_annual_cycle_distribution_event_id"] == "600519:2021-06-01"
    assert timeline[-1]["status"] == "prior_annual_cycle_cash_observation_available"
