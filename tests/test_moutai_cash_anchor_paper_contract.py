import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("cash_anchor_paper_contract", ROOT / "scripts" / "build_moutai_cash_anchor_paper_contract.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def value_row(price, value):
    return {"date": "2020-01-02", "status": "cash_distribution_anchored_research_only", "price_close_cny": price,
            "cases": [{"scenario": "bear", "conditional_value_per_share_cny": value}]}


def test_contract_uses_bear_endpoint_and_existing_entry_threshold():
    orders, trace = MODULE.build_decisions([value_row("70", "100")])
    assert orders["2020-01-02"]["quantity"] == 100
    assert trace[0]["state"] == "proposed_entry"


def test_contract_keeps_pre_cash_observation_dates_blocked():
    orders, trace = MODULE.build_decisions([{"date": "2015-01-05", "status": "blocked_no_prior_implemented_annual_cycle_cash_observation"}])
    assert orders == {}
    assert trace[0]["state"] == "blocked"


def test_relative_output_directory_is_normalized_under_project_root(monkeypatch):
    monkeypatch.chdir(ROOT)
    output = MODULE.resolve_output(Path("runtime/strategy-validation/cash-anchor-relative-output-test"))
    assert output.is_absolute()
    assert output.is_relative_to(ROOT.resolve())
