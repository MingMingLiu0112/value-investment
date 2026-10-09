from __future__ import annotations

import pytest

from value_investment_agent.domain.decision.decision_recommendation import (
    RECOMMENDATION_ADD_CANDIDATE,
    RECOMMENDATION_BUY_CANDIDATE,
    RECOMMENDATION_HOLD,
    RECOMMENDATION_NO_ACTION,
    RECOMMENDATION_SELL_CANDIDATE,
    RECOMMENDATION_TRIM_CANDIDATE,
)
from value_investment_agent.domain.decision.recommendation_rules import (
    CONSISTENCY_BROKEN,
    CONSISTENCY_CONSISTENT,
    CONSISTENCY_WEAKENED,
    RecommendationRuleInputs,
    evaluate_recommendation_action,
)


def _inputs(**overrides: object) -> RecommendationRuleInputs:
    values: dict[str, object] = {
        "has_entry": False,
        "consistency_status": None,
        "full_buy_gate_passed": False,
        "add_evidence_present": False,
        "hold_logic_present": False,
        "trim_reason_present": False,
        "sell_reason_present": False,
        "exit_condition_present": False,
        "event_review_current": False,
        "model_validity_status": "UNKNOWN",
        "blockers": (),
    }
    values.update(overrides)
    return RecommendationRuleInputs(**values)


def test_blockers_fail_closed_before_any_positive_action() -> None:
    decision = evaluate_recommendation_action(
        _inputs(
            full_buy_gate_passed=True,
            blockers=("quote_unavailable", "quote_unavailable"),
        )
    )
    assert decision.action == RECOMMENDATION_NO_ACTION
    assert decision.blockers == ("quote_unavailable",)
    assert decision.requires_human_review is False


def test_buy_requires_full_gate_and_no_existing_entry() -> None:
    decision = evaluate_recommendation_action(
        _inputs(full_buy_gate_passed=True)
    )
    assert decision.action == RECOMMENDATION_BUY_CANDIDATE
    assert decision.requires_human_review is True


@pytest.mark.parametrize(
    "consistency_status", [CONSISTENCY_WEAKENED, CONSISTENCY_BROKEN]
)
def test_buy_fails_closed_when_inconsistent_status_is_supplied_without_entry(
    consistency_status: str,
) -> None:
    decision = evaluate_recommendation_action(
        _inputs(
            full_buy_gate_passed=True,
            consistency_status=consistency_status,
        )
    )
    assert decision.action == RECOMMENDATION_NO_ACTION
    assert "entry_consistency_not_applicable" in decision.blockers


def test_add_requires_entry_consistency_full_gate_and_incremental_evidence() -> None:
    decision = evaluate_recommendation_action(
        _inputs(
            has_entry=True,
            consistency_status=CONSISTENCY_CONSISTENT,
            full_buy_gate_passed=True,
            add_evidence_present=True,
        )
    )
    assert decision.action == RECOMMENDATION_ADD_CANDIDATE


def test_price_only_add_is_not_enough() -> None:
    decision = evaluate_recommendation_action(
        _inputs(
            has_entry=True,
            consistency_status=CONSISTENCY_CONSISTENT,
            full_buy_gate_passed=True,
            add_evidence_present=False,
        )
    )
    assert decision.action == RECOMMENDATION_NO_ACTION
    assert "hold_logic_or_current_gate_missing" in decision.blockers


def test_hold_requires_current_event_review_and_valid_model() -> None:
    decision = evaluate_recommendation_action(
        _inputs(
            has_entry=True,
            consistency_status=CONSISTENCY_CONSISTENT,
            hold_logic_present=True,
            event_review_current=True,
            model_validity_status="VALID",
        )
    )
    assert decision.action == RECOMMENDATION_HOLD


def test_hold_fails_closed_when_model_is_stale() -> None:
    decision = evaluate_recommendation_action(
        _inputs(
            has_entry=True,
            consistency_status=CONSISTENCY_CONSISTENT,
            hold_logic_present=True,
            event_review_current=True,
            model_validity_status="STALE",
        )
    )
    assert decision.action == RECOMMENDATION_NO_ACTION


def test_trim_requires_original_entry_and_weakened_thesis() -> None:
    decision = evaluate_recommendation_action(
        _inputs(
            has_entry=True,
            consistency_status=CONSISTENCY_WEAKENED,
            trim_reason_present=True,
        )
    )
    assert decision.action == RECOMMENDATION_TRIM_CANDIDATE


def test_trim_without_original_entry_is_rejected() -> None:
    decision = evaluate_recommendation_action(
        _inputs(
            consistency_status=CONSISTENCY_WEAKENED,
            trim_reason_present=True,
        )
    )
    assert decision.action == RECOMMENDATION_NO_ACTION
    assert "original_entry_missing" in decision.blockers


def test_sell_requires_broken_thesis_and_explicit_exit_condition() -> None:
    decision = evaluate_recommendation_action(
        _inputs(
            has_entry=True,
            consistency_status=CONSISTENCY_BROKEN,
            sell_reason_present=True,
            exit_condition_present=True,
            model_validity_status="UNKNOWN",
        )
    )
    assert decision.action == RECOMMENDATION_SELL_CANDIDATE


def test_sell_without_exit_condition_is_rejected_even_when_thesis_is_broken() -> None:
    decision = evaluate_recommendation_action(
        _inputs(
            has_entry=True,
            consistency_status=CONSISTENCY_BROKEN,
            sell_reason_present=True,
            exit_condition_present=False,
        )
    )
    assert decision.action == RECOMMENDATION_NO_ACTION
    assert decision.blockers == ("exit_condition_missing",)
