"""Original-entry continuity never authorizes a personal trade."""
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from test_hotspot_current_price_case import NOW, capture
from test_hotspot_observation_plan import binding
from value_investment_agent.application.hotspot import lifecycle_review as subject
from value_investment_agent.domain.hotspot.current_price import SESSION_TIMES
from value_investment_agent.quote_sessions import CHINA


def bars(closes):
    return [dict(time="2026-09-24 " + clock, close=str(close))
            for clock, close in zip(SESSION_TIMES["60m"], closes)]


def test_recovery_does_not_erase_original_break_and_no_same_bar_entry_exit():
    result = subject._compare_entry_bars(bars=bars([8, 9, 11, 12]),
        entry_at=datetime(2026, 9, 24, 10, 30, tzinfo=CHINA), protection="10", symbol="600519")
    assert result["breach_count"] == 1
    assert result["first_breach_at"] == "2026-09-24T11:30:00+08:00"
    assert result["coverage"] == "COMPLETE"


def test_equality_does_not_break_strict_invalidation_and_missing_bar_is_unknown():
    result = subject._compare_entry_bars(bars=bars([11, 10, 11, 12])[1:],
        entry_at=datetime(2026, 9, 24, 9, 30, tzinfo=CHINA), protection="10", symbol="600519")
    assert result["breach_count"] == 0
    assert result["coverage"] == "INCOMPLETE"
    assert result["missing_completed_bars"] == ["2026-09-24T10:30:00+08:00"]


def test_actual_loader_path_is_read_only_and_missing_entry_cannot_grant_held_actions(tmp_path):
    case = capture(tmp_path)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    result = subject.build_hotspot_lifecycle_review(root=tmp_path, symbol=case["symbol"],
        current_case_binding=binding(case), now=NOW)
    assert result["status"] == "CURRENT_STRUCTURE_ONLY"
    assert set(result["current_conditions"]) == {"OPEN", "ADD", "REDUCE", "EXIT"}
    assert result["original_entry_comparison"] is None
    assert result["personal_action"] == "NO_ACTION"
    assert result["risk_review_eligible"] is result["trade_eligible"] is False
    assert result["action"] == "no_order"
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


def test_corrupt_source_or_future_entry_cannot_produce_current_actions(tmp_path):
    case = capture(tmp_path)
    with pytest.raises(ValueError, match="known at cutoff"):
        subject.build_hotspot_lifecycle_review(root=tmp_path, symbol=case["symbol"],
            current_case_binding=binding(case), now=NOW,
            entry_case_binding=binding(case), entry_at=NOW + timedelta(days=1))
    path = tmp_path / case["source_bindings"]["60m"]["path"]
    path.write_bytes(path.read_bytes() + b" ")
    result = subject.build_hotspot_lifecycle_review(root=tmp_path, symbol=case["symbol"],
        current_case_binding=binding(case), now=NOW)
    assert result["status"] == "NOT_ASSESSABLE"
    assert result["current_conditions"] == {}


def test_latest_case_cannot_be_backdated_as_entry(tmp_path):
    case = capture(tmp_path)
    result = subject.build_hotspot_lifecycle_review(root=tmp_path, symbol=case["symbol"],
        current_case_binding=binding(case), now=NOW,
        entry_case_binding=binding(case), entry_at=NOW - timedelta(days=1))
    assert result["status"] == "NOT_ASSESSABLE"
    assert "ENTRY_CASE_NOT_VALID_AT_ENTRY" in result["blockers"]


@pytest.mark.parametrize("reduce,add,breach,expected", [
    (True, True, True, "EXIT_STRUCTURE_REVIEW"),
    (True, True, False, "REDUCE_STRUCTURE_REVIEW"),
    (False, True, False, "ADD_STRUCTURE_REVIEW"),
    (False, False, False, "HOLD_STRUCTURE_OBSERVATION"),
])
def test_review_priority_preserves_original_break(monkeypatch, reduce, add, breach, expected):
    rows = bars([11, 9 if breach else 11, 11, 12])
    case = dict(bars={"60m": rows})
    monkeypatch.setattr(subject, "inspect_current_price_case", lambda **kw:
        dict(data_status="CURRENT", case=case))
    plan = dict(model_or_rule_version="unchanged", invalidation_price="10",
        opportunity_quality=dict(structure_tier="STRUCTURE_QUALIFIED_OBSERVATION"),
        price_behavior=dict(blockers=[], observation_quality="RESEARCH_ONLY"),
        conditional_action_rules={name: dict(observed=flag) for name, flag in
            (("OPEN", True), ("ADD", add), ("REDUCE", reduce), ("EXIT", False))})
    monkeypatch.setattr(subject, "project_current_price_action_plan", lambda case: plan)
    result = subject.build_hotspot_lifecycle_review(root=Path("."), symbol="600519",
        current_case_binding=dict(path="current", sha256="a" * 64), now=NOW,
        entry_case_binding=dict(path="entry", sha256="b" * 64),
        entry_at=datetime(2026, 9, 24, 9, 30, tzinfo=CHINA))
    assert result["observed_review"] == "UNKNOWN"
    assert result["unadjusted_structural_observation"]["observed_review"] == expected
    assert result["personal_action"] == "NO_ACTION"
