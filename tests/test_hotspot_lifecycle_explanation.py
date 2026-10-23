"""TEST_ONLY native source replay verifies explanations, not strategy efficacy."""
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal

import pytest

from test_hotspot_lifecycle_bound_history import (
    CURRENT_AT, ENTRY_AT, SYMBOL, _assert_no_permission, _binding, _history, _review,
)
from value_investment_agent.application.hotspot import lifecycle_review as subject
from value_investment_agent.application.hotspot.report_text import render_hotspot_lifecycle_markdown


def _steps(result):
    return {step["check"]: step for step in result["decision_explanation"]["decision_path"]}


def test_display_only_close_never_becomes_current_pit_in_explanation(tmp_path):
    from test_hotspot_current_price_case import NOW, display_capture

    case = display_capture(tmp_path)
    result = subject.build_hotspot_lifecycle_review(root=tmp_path, symbol=case["symbol"],
        current_case_binding=_binding(case), now=NOW)
    price = result["decision_explanation"]["current_price_observation"]
    assert price["reference_price_scope"] == "LAST_COMPLETED_CLOSE_DISPLAY_ONLY"
    assert price["current_pit"] is False
    assert _steps(result)["CURRENT_DATA"]["values"]["current_pit"] is False
    text = render_hotspot_lifecycle_markdown(result)
    assert "LAST_COMPLETED_CLOSE_DISPLAY_ONLY" in text
    assert "当前 PIT 标志：否" in text
    _assert_no_permission(result)


def test_bound_recovery_explains_original_break_not_new_rolling_threshold(tmp_path):
    history = _history(tmp_path, breach=True)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    result = _review(history)
    explanation = result["decision_explanation"]
    assert explanation["basis_code"] == "ORIGINAL_PROTECTION_BREACHED"
    assert explanation["selected_review"] == "EXIT_STRUCTURE_REVIEW"
    steps = _steps(result)
    original = steps["ORIGINAL_PROTECTION"]["values"]
    assert Decimal(original["original_protection_price"]) == 11
    assert Decimal(original["current_rolling_protection_price"]) == 9
    assert Decimal(original["first_breach_close"]) == 10
    assert original["first_breach_at"] == "2026-09-22T11:30:00+08:00"
    assert steps["CURRENT_EXIT"]["outcome"] == "NOT_OBSERVED"
    assert explanation["current_price_observation"]["price"] == "12.34"
    assert explanation["current_price_observation"]["as_of"] == "2026-09-24"
    assert explanation["current_price_observation"]["available_at"] <= CURRENT_AT.isoformat()
    assert steps["ORIGINAL_PROTECTION"]["evidence_bindings"] == [
        _binding(history[3]), _binding(history[1])]
    assert "ORIGINAL_PROTECTION_BREACHED" in explanation["why_not_add"]
    assert explanation["required_external_reviews"] == result["required_external_reviews"]
    assert explanation["source_scope"] == "REFERENCE_CASES_NOT_VERIFIED_OWNERSHIP_OR_ENTRY_THESIS"
    text = render_hotspot_lifecycle_markdown(result)
    assert "ORIGINAL_PROTECTION_BREACHED" in text
    assert "2026-09-22T11:30:00+08:00" in text
    assert _binding(history[1])["sha256"] in text
    assert "NOT_PROVEN" in text and "no_order" in text
    _assert_no_permission(result)
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    original["original_protection_price"] = "0"
    assert Decimal(result["original_entry_comparison"]["original_protection_price"]) == 11


@pytest.mark.parametrize("missing_day,basis,outcome", [
    (None, "NO_STRUCTURAL_CHANGE_OBSERVED", "HOLD_STRUCTURE_OBSERVATION"),
    (23, "ENTRY_TO_CURRENT_DATA_INCOMPLETE", "UNKNOWN"),
])
def test_native_history_honestly_distinguishes_no_change_and_unknown(tmp_path, missing_day, basis, outcome):
    result = _review(_history(tmp_path, missing_day=missing_day))
    explanation = result["decision_explanation"]
    assert explanation["basis_code"] == basis
    assert explanation["selected_review"] == outcome
    assert _steps(result)["CONTINUITY_COVERAGE"]["outcome"] == (
        "COMPLETE" if missing_day is None else "INCOMPLETE")
    assert "OWNED_ENTRY_THESIS" in explanation["required_external_reviews"]
    assert "INDEPENDENT_STRATEGY_ADMISSION" in explanation["required_external_reviews"]
    assert basis in render_hotspot_lifecycle_markdown(result)
    if missing_day:
        assert basis in explanation["why_not_add"]
    _assert_no_permission(result)


def test_missing_entry_is_only_observation_not_verified_holding(tmp_path):
    _, _, _, current = _history(tmp_path)
    result = subject.build_hotspot_lifecycle_review(root=tmp_path, symbol=SYMBOL,
        current_case_binding=_binding(current), now=CURRENT_AT)
    explanation = result["decision_explanation"]
    assert explanation["basis_code"] == "ENTRY_STRUCTURE_NOT_QUALIFIED"
    steps = _steps(result)
    assert steps["ENTRY_REFERENCE"]["outcome"] == "NOT_SUPPLIED"
    assert steps["ORIGINAL_PROTECTION"]["outcome"] == "NOT_EVALUATED"
    assert steps["ENTRY_REFERENCE"]["evidence_bindings"] == []
    assert steps["CURRENT_DATA"]["values"]["blockers"] == []
    assert explanation["recomputed_rule_versions"]["entry"] is None
    _assert_no_permission(result)


@pytest.mark.parametrize("invalid", ["current_hash", "entry_hash", "stale_current"])
def test_invalid_evidence_is_not_presented_as_verified(tmp_path, invalid):
    _, entry, _, current = _history(tmp_path)
    current_binding, entry_binding = _binding(current), _binding(entry)
    if invalid == "current_hash":
        current_binding["sha256"] = "0" * 64
    if invalid == "entry_hash":
        entry_binding["sha256"] = "0" * 64
    result = subject.build_hotspot_lifecycle_review(root=tmp_path, symbol=SYMBOL,
        current_case_binding=current_binding, entry_case_binding=entry_binding,
        entry_at=ENTRY_AT, now=CURRENT_AT + timedelta(days=4) if invalid == "stale_current" else CURRENT_AT)
    explanation = result["decision_explanation"]
    assert explanation["selected_review"] == "UNKNOWN"
    if invalid == "entry_hash":
        assert explanation["basis_code"] == "ENTRY_EVIDENCE_UNAVAILABLE"
        assert _steps(result)["ENTRY_REFERENCE"]["evidence_bindings"] == []
        assert _steps(result)["ENTRY_REFERENCE"]["values"]["blockers"] == ["ENTRY_CASE_NOT_VALID_AT_ENTRY"]
        assert _steps(result)["CURRENT_DATA"]["values"]["blockers"] == []
        assert explanation["current_price_observation"] is not None
    else:
        assert explanation["basis_code"] == "CURRENT_DATA_UNAVAILABLE"
        assert explanation["current_price_observation"] is None
        assert all(not step["evidence_bindings"] for step in explanation["decision_path"])
    _assert_no_permission(result)


@pytest.mark.parametrize("exit_seen,reduce_seen,add_seen,quality,basis", [
    (True, True, True, "RESEARCH_ONLY", "CURRENT_PROTECTION_BREACHED"),
    (False, True, True, "RESEARCH_ONLY", "CURRENT_REDUCTION_CONDITION_OBSERVED"),
    (False, False, True, "RESEARCH_ONLY", "CURRENT_ADD_CONDITION_OBSERVED"),
    (False, False, True, "UNFAVORABLE_DAILY_TREND", "NO_STRUCTURAL_CHANGE_OBSERVED"),
])
def test_explanation_uses_same_priority_as_existing_conditions(tmp_path, monkeypatch,
        exit_seen, reduce_seen, add_seen, quality, basis):
    history = _history(tmp_path)
    native = subject.project_current_price_action_plan

    def project(case):
        plan = deepcopy(native(case))
        for intent, observed in (("EXIT", exit_seen), ("REDUCE", reduce_seen), ("ADD", add_seen)):
            plan["conditional_action_rules"][intent]["observed"] = observed
        plan["price_behavior"]["observation_quality"] = quality
        return plan

    monkeypatch.setattr(subject, "project_current_price_action_plan", project)
    result = _review(history)
    explanation = result["decision_explanation"]
    assert explanation["basis_code"] == basis
    assert explanation["selected_review"] == result["observed_review"]
    if quality != "RESEARCH_ONLY":
        assert "ADD_STRUCTURE_QUALITY_NOT_USABLE" in explanation["why_not_add"]
    if basis == "CURRENT_ADD_CONDITION_OBSERVED":
        assert explanation["why_not_add"] == []
        assert explanation["required_external_reviews"]
    _assert_no_permission(result)


def test_recomputed_rule_mismatch_explained_without_claiming_original_thesis(tmp_path, monkeypatch):
    history = _history(tmp_path)
    native = subject.project_current_price_action_plan

    def project(case):
        plan = native(case)
        plan["model_or_rule_version"] = case["market_trade_date"]
        return plan

    monkeypatch.setattr(subject, "project_current_price_action_plan", project)
    result = _review(history)
    explanation = result["decision_explanation"]
    assert explanation["basis_code"] == "ENTRY_CURRENT_RULE_MISMATCH"
    assert explanation["recomputed_rule_versions"] == dict(current="2026-09-24", entry="2026-09-21")
    assert _steps(result)["ENTRY_RULE_COMPATIBILITY"]["outcome"] == "MISMATCH"
    assert _steps(result)["ORIGINAL_PROTECTION"]["outcome"] == "NOT_EVALUATED"
    _assert_no_permission(result)


def test_behavior_quality_and_opportunity_tier_remain_separate(tmp_path, monkeypatch):
    history = _history(tmp_path)
    native = subject.project_current_price_action_plan

    def project(case):
        plan = native(case)
        plan["price_behavior"]["observation_quality"] = "RESEARCH_ONLY"
        plan["opportunity_quality"].update(structure_tier="CONFLICT_OR_REJECTED",
            structure_reasons=["SUPPORTING_STRUCTURE_INVALIDATED"])
        return plan

    monkeypatch.setattr(subject, "project_current_price_action_plan", project)
    result = _review(history)
    steps = _steps(result)
    behavior, opportunity = steps["STRUCTURE_QUALITY"], steps["OPPORTUNITY_QUALITY"]
    assert behavior["outcome"] == behavior["values"]["observation_quality"] == "RESEARCH_ONLY"
    assert opportunity["outcome"] == opportunity["values"]["structure_tier"] == "CONFLICT_OR_REJECTED"
    assert opportunity["values"]["structure_reasons"] == ["SUPPORTING_STRUCTURE_INVALIDATED"]
    assert behavior["values"]["rule_version"] != opportunity["values"]["rule_version"]
    assert "OPPORTUNITY_QUALITY" in render_hotspot_lifecycle_markdown(result)
    _assert_no_permission(result)
