import importlib.util
from decimal import Decimal
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("moutai_pe_crosscheck", ROOT / "scripts" / "build_moutai_historical_pe_crosscheck.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def row(day, price, eps="10"):
    return {"date": day, "decision_at": day + "T15:00:00+08:00", "annual_available_at": day + "T00:00:00+08:00",
            "annual_source_id": "source", "report_period": "2019-12-31", "close": price,
            "annual_profit_per_bonus_adjusted_share": eps}


def test_current_close_is_not_used_in_its_own_percentile_range(monkeypatch):
    monkeypatch.setattr(MODULE, "MIN_PRIOR_SESSIONS", 2)
    values = MODULE.build([row("2020-01-01", "100"), row("2020-01-02", "200"), row("2020-01-03", "1000")])
    assert values[1]["status"] == "blocked_insufficient_prior_pe_observations"
    third = values[2]
    assert third["status"] == "historical_relative_pe_research_only"
    assert Decimal(third["cases"][0]["prior_pe_multiple"]) == Decimal("12")
    assert Decimal(third["cases"][2]["prior_pe_multiple"]) == Decimal("18")
    assert third["valuation_approved"] is False


def test_real_crosscheck_remains_research_only():
    values = MODULE.build(__import__("json").loads(MODULE.INPUT.read_text(encoding="utf-8")))
    assert len(values) == 2674
    assert any(row["status"] == "historical_relative_pe_research_only" for row in values)
    assert all(row["trade_approved"] is False for row in values)
