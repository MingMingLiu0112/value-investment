import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "moutai_2014_q3_parent_equity", ROOT / "scripts" / "build_moutai_2014_q3_parent_equity.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_q3_fact_is_available_before_window_but_not_silently_substituted():
    result = module.build()
    assert result["source_id"] == "cninfo:1200354286"
    assert result["report_period"] == "2014-09-30"
    assert result["available_at"] <= "2015-01-05T15:00:00+08:00"
    assert result["facts"]["parent_equity_cny"] == "48740550040.56"
    assert result["facts"]["parent_profit_ytd_cny"] == "10693329220.86"
    assert result["facts"]["issued_shares_cny_par_value"] == "1141998000.00"
    assert result["relationship_to_registered_window"]["replaces_registered_annual_source"] is False
    assert result["formal_fair_value"] is None
    assert result["trade_approved"] is False
