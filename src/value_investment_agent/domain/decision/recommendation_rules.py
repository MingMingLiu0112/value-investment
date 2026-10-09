"""Pure, fail-closed action selection for the D3 advisory contract."""
from __future__ import annotations

from dataclasses import dataclass

from .decision_recommendation import (
    RECOMMENDATION_ADD_CANDIDATE,
    RECOMMENDATION_BUY_CANDIDATE,
    RECOMMENDATION_HOLD,
    RECOMMENDATION_NO_ACTION,
    RECOMMENDATION_SELL_CANDIDATE,
    RECOMMENDATION_TRIM_CANDIDATE,
)


CONSISTENCY_CONSISTENT = "CONSISTENT"
CONSISTENCY_FULFILLED = "FULFILLED"
CONSISTENCY_WEAKENED = "WEAKENED"
CONSISTENCY_BROKEN = "BROKEN"
CONSISTENCY_STATUSES = frozenset(
    {
        CONSISTENCY_CONSISTENT,
        CONSISTENCY_FULFILLED,
        CONSISTENCY_WEAKENED,
        CONSISTENCY_BROKEN,
    }
)


@dataclass(frozen=True)
class RecommendationRuleInputs:
    """Already-evaluated facts consumed by the action selector.

    This object deliberately contains no market price or portfolio amount.
    Buy/add gates are supplied by the existing evidence pipeline; risk-reduction
    actions depend on the original entry thesis and consistency review instead.
    """

    has_entry: bool
    consistency_status: str | None = None
    full_buy_gate_passed: bool = False
    add_evidence_present: bool = False
    hold_logic_present: bool = False
    trim_reason_present: bool = False
    sell_reason_present: bool = False
    exit_condition_present: bool = False
    event_review_current: bool = False
    model_validity_status: str = "UNKNOWN"
    blockers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.consistency_status is not None and self.consistency_status not in CONSISTENCY_STATUSES:
            raise ValueError("Unknown thesis consistency status")
        if self.model_validity_status not in {"VALID", "STALE", "INVALID", "UNKNOWN"}:
            raise ValueError("Unknown model validity status")
        object.__setattr__(self, "blockers", tuple(dict.fromkeys(self.blockers)))


@dataclass(frozen=True)
class RecommendationRuleDecision:
    action: str
    reason_codes: tuple[str, ...]
    blockers: tuple[str, ...]
    rule_version: str = "recommendation-rules-v1"
    requires_human_review: bool = True


def _decision(
    action: str,
    *reason_codes: str,
    blockers: tuple[str, ...] = (),
) -> RecommendationRuleDecision:
    return RecommendationRuleDecision(
        action=action,
        reason_codes=tuple(dict.fromkeys(reason_codes)),
        blockers=tuple(dict.fromkeys(blockers)),
        requires_human_review=action != RECOMMENDATION_NO_ACTION,
    )


def evaluate_recommendation_action(
    inputs: RecommendationRuleInputs,
) -> RecommendationRuleDecision:
    """Select one advisory action without ever creating an execution order."""
    if inputs.blockers:
        return _decision(
            RECOMMENDATION_NO_ACTION,
            "blockers_present",
            blockers=inputs.blockers,
        )

    if inputs.sell_reason_present:
        missing: list[str] = []
        if not inputs.has_entry:
            missing.append("original_entry_missing")
        if inputs.consistency_status != CONSISTENCY_BROKEN:
            missing.append("thesis_not_broken")
        if not inputs.exit_condition_present:
            missing.append("exit_condition_missing")
        if missing:
            return _decision(
                RECOMMENDATION_NO_ACTION,
                "sell_review_incomplete",
                blockers=tuple(missing),
            )
        return _decision(
            RECOMMENDATION_SELL_CANDIDATE,
            "thesis_broken",
            "exit_condition_present",
        )

    if inputs.trim_reason_present:
        missing = []
        if not inputs.has_entry:
            missing.append("original_entry_missing")
        if inputs.consistency_status != CONSISTENCY_WEAKENED:
            missing.append("thesis_not_weakened")
        if missing:
            return _decision(
                RECOMMENDATION_NO_ACTION,
                "trim_review_incomplete",
                blockers=tuple(missing),
            )
        return _decision(
            RECOMMENDATION_TRIM_CANDIDATE,
            "thesis_weakened",
            "risk_reduction_reason_present",
        )

    if inputs.has_entry:
        if inputs.consistency_status not in {
            CONSISTENCY_CONSISTENT,
            CONSISTENCY_FULFILLED,
        }:
            return _decision(
                RECOMMENDATION_NO_ACTION,
                "entry_consistency_not_supportive",
                blockers=("entry_thesis_not_consistent",),
            )
        if inputs.full_buy_gate_passed and inputs.add_evidence_present:
            return _decision(
                RECOMMENDATION_ADD_CANDIDATE,
                "full_buy_gate_passed",
                "incremental_evidence_present",
            )
        if (
            inputs.hold_logic_present
            and inputs.event_review_current
            and inputs.model_validity_status == "VALID"
        ):
            return _decision(
                RECOMMENDATION_HOLD,
                "entry_thesis_intact",
                "hold_logic_present",
                "event_review_current",
                "model_validity_valid",
            )
        return _decision(
            RECOMMENDATION_NO_ACTION,
            "hold_support_incomplete",
            blockers=("hold_logic_or_current_gate_missing",),
        )

    if inputs.consistency_status not in {
        None,
        CONSISTENCY_CONSISTENT,
        CONSISTENCY_FULFILLED,
    }:
        return _decision(
            RECOMMENDATION_NO_ACTION,
            "entry_consistency_without_entry",
            blockers=("entry_consistency_not_applicable",),
        )

    if inputs.full_buy_gate_passed:
        return _decision(
            RECOMMENDATION_BUY_CANDIDATE,
            "full_buy_gate_passed",
            "no_existing_entry",
        )
    return _decision(
        RECOMMENDATION_NO_ACTION,
        "no_positive_gate_combination",
    )


__all__ = [
    "CONSISTENCY_BROKEN",
    "CONSISTENCY_CONSISTENT",
    "CONSISTENCY_FULFILLED",
    "CONSISTENCY_STATUSES",
    "CONSISTENCY_WEAKENED",
    "RecommendationRuleDecision",
    "RecommendationRuleInputs",
    "evaluate_recommendation_action",
]
