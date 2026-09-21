import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "moutai_cfets_curve", ROOT / "scripts" / "inspect_moutai_historical_cfets_curve.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_pinned_cfets_probe_rejects_zero_records_as_a_rate_input():
    result = MODULE.build()
    assert result["response_status"] == "http_200_valid_request_zero_records"
    assert result["rate_input_status"] == "rejected_no_historical_curve_records"
    assert result["observed_total"] == 0
    assert result["trade_approved"] is False
