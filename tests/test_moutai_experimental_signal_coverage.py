import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("moutai_signal_coverage", ROOT / "scripts" / "analyze_moutai_experimental_signal_coverage.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_coverage_reports_every_range_endpoint_and_does_not_admit_trades():
    result = MODULE.analyze()
    coverage = result["range_endpoint_safety_margin_coverage"]
    assert result["sessions"] == 2674
    assert result["sessions_with_experimental_range"] == 2603
    for endpoint in ("lower", "midpoint", "upper"):
        assert coverage[endpoint]["0.20"]["sessions"] >= coverage[endpoint]["0.30"]["sessions"] >= coverage[endpoint]["0.40"]["sessions"]
    assert coverage["lower"]["0.20"]["sessions"] == 0
    assert coverage["upper"]["0.20"]["sessions"] > 0
    assert result["trade_approved"] is False


def test_relative_output_directory_is_normalized_under_project_root(monkeypatch):
    monkeypatch.chdir(ROOT)
    output = MODULE.resolve_output(Path("runtime/strategy-validation/signal-coverage-relative-output-test"))
    assert output.is_absolute()
    assert output.is_relative_to(ROOT.resolve())
