import importlib.util
from pathlib import Path
import sys
import json
from decimal import Decimal


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "moutai_current_conditional_observation",
    ROOT / "scripts" / "build_moutai_current_conditional_observation.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_observation_requires_timestamps_and_never_admits_trade():
    report = ROOT / "runtime/quote-sessions/20260911T082607553737Z/report.json"
    observation = MODULE.build(report)
    assert observation["as_of"] == "2026-09-11T16:14:51+08:00"
    assert observation["research_state"] == "watch"
    assert observation["action"] == "no_order"
    assert observation["simulation_eligible"] is False
    assert observation["trade_approved"] is False
    assert observation["scenarios"] == []
    assert observation["dependencies"]["model"]["sha256"] == observation["conditional_valuation_sha256"]
    assert observation["model_version"] == "moutai-current-parent-equity-residual-income-v1"
    assert "current_model_not_same_date_as_quote_session" in observation["reason_codes"]


def test_session_verified_quote_does_not_keep_a_stale_calendar_blocker():
    report = ROOT / "runtime/quote-sessions/20260911T094557691211Z/report.json"
    observation = MODULE.build(report)
    assert observation["quote_session_verified"] is True
    assert "quote_session_not_verified" not in observation["reason_codes"]
    assert observation["valuation_approved"] is False
    assert observation["trade_approved"] is False
    assert "current_model_not_same_date_as_quote_session" in observation["reason_codes"]


def test_price_threshold_crossing_is_explained_without_crashing_or_admitting_order(tmp_path):
    source = ROOT / "runtime/quote-sessions/20260911T094557691211Z/report.json"
    report = json.loads(source.read_text(encoding="utf-8"))
    next(row for row in report["observations"] if row["symbol"] == "600519")["observed_price"] = "100"
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    observation = MODULE.build(path)
    assert observation["scenarios"] == []
    assert "current_model_not_same_date_as_quote_session" in observation["reason_codes"]
    assert "valuation_not_approved" in observation["reason_codes"]
    assert observation["action"] == "no_order"
    assert observation["simulation_eligible"] is False
