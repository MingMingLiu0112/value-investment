import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "moutai_historical_window_benchmark", ROOT / "scripts" / "build_moutai_historical_window_benchmark_contract.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_narrow_window_has_pinned_official_tri_coverage_without_benchmark_acceptance():
    result = MODULE.build()
    assert result["coverage_verified"] is True
    assert result["historical_version_verified"] is False
    assert result["same_period_benchmark_accepted"] is False
    assert result["trade_approved"] is False
    assert result["dates"][0] == "2015-01-05"
    assert result["dates"][-1] == "2015-01-30"
    assert len(result["dates"]) == 20
    for code in ("H00300", "H00932"):
        assert list(result["series"][code]["levels"]) == result["dates"]
        assert result["series"][code]["official_name_en"].endswith("Total Return Index")
