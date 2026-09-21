import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("moutai_pe_mid_contract", ROOT / "scripts" / "build_moutai_pe_mid_paper_contract.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def value_row(day, price, mid):
    return {"date": day, "status": "historical_relative_pe_research_only", "price_close_cny": price,
            "cases": [{"scenario": "mid", "conditional_value_per_share_cny": mid, "prior_pe_multiple": "20"}]}


def test_mid_pe_contract_uses_unchanged_entry_margin_and_exit_rule():
    orders, trace = MODULE.build_decisions([value_row("2020-01-02", "60", "100"), value_row("2020-01-03", "110", "100")])
    assert orders["2020-01-02"]["state"] == "proposed_entry"
    assert orders["2020-01-03"]["state"] == "proposed_reduce"
    assert trace[0]["safety_margin"] == "0.4"


def test_mid_pe_contract_keeps_missing_prior_sample_blocked():
    orders, trace = MODULE.build_decisions([{"date": "2020-01-02", "status": "blocked_insufficient_prior_pe_observations"}])
    assert orders == {}
    assert trace[0]["state"] == "blocked"
