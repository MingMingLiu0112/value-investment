import importlib.util
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "moutai_current_capital_bridge", ROOT / "scripts" / "assess_moutai_current_capital_bridge.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_current_capital_bridge_is_bounded_and_not_a_trade_approval():
    result = MODULE.build()
    assert result["passed"] is True
    model, _ = MODULE.pinned_json(__import__("json").loads(MODULE.MODEL_POINTER.read_text(encoding="utf-8")))
    assert result["as_of"] == model["valuation_at"][:10]
    assert result["ordinary_share_basis"]["issued_shares"] == "1250081601"
    assert result["capital_event_coverage"]["coverage_reaches_as_of"] is True
    assert result["equity_treatment"]["reported_distribution_not_deducted_again"] is True
    assert result["trade_approved"] is False


def test_consecutive_windows_reject_a_gap_or_wrong_end_date():
    assert MODULE.consecutive_windows("2026-06-01~2026-09-14", "2026-09-14~2026-09-16", date(2026, 9, 16))
    assert not MODULE.consecutive_windows("2026-06-01~2026-09-13", "2026-09-14~2026-09-16", date(2026, 9, 16))
    assert not MODULE.consecutive_windows("2026-06-01~2026-09-14", "2026-09-14~2026-09-15", date(2026, 9, 16))
