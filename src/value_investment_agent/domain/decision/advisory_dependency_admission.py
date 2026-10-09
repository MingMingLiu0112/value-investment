"""Fail-closed admission for production advisory entry and review dependencies."""
from __future__ import annotations

from datetime import date

from ...investment_decision import (
    ENTRY_TYPE_ACTUAL,
    EntryThesisSnapshot,
    InvestmentConsistencyReview,
)
from .decision_recommendation import (
    DECISION_RECOMMENDATION_SCHEMA,
    DECISION_RECOMMENDATION_V3_SCHEMA,
)


def validate_advisory_dependencies(
    *,
    symbol: str,
    decision_as_of: date,
    recommendation_schema_version: str,
    entry_thesis: EntryThesisSnapshot | None,
    investment_consistency_review: InvestmentConsistencyReview | None,
) -> None:
    """Reject D3 dependencies that cannot safely support a production action.

    The default v2 path remains byte-identical when no D3 objects are supplied.
    Supplying either D3 object explicitly opts the run into v3 semantics and
    makes the pair mandatory. The checks happen before any action is selected.
    """
    if recommendation_schema_version == DECISION_RECOMMENDATION_SCHEMA:
        if entry_thesis is not None or investment_consistency_review is not None:
            raise ValueError(
                "D3 entry/review dependencies require explicit v3 recommendation schema opt-in"
            )
        return
    if recommendation_schema_version != DECISION_RECOMMENDATION_V3_SCHEMA:
        raise ValueError(
            "recommendation_schema_version must be the default v2 or explicit v3 schema"
        )

    if entry_thesis is None and investment_consistency_review is None:
        return
    if entry_thesis is None or investment_consistency_review is None:
        raise ValueError("v3 entry and consistency review dependencies must be supplied together")
    if not isinstance(entry_thesis, EntryThesisSnapshot):
        raise TypeError("entry_thesis must be an EntryThesisSnapshot")
    if not isinstance(investment_consistency_review, InvestmentConsistencyReview):
        raise TypeError(
            "investment_consistency_review must be an InvestmentConsistencyReview"
        )

    if entry_thesis.symbol != symbol:
        raise ValueError("entry thesis symbol does not match the recommendation")
    if investment_consistency_review.symbol != symbol:
        raise ValueError("consistency review symbol does not match the recommendation")
    if entry_thesis.entry_id != investment_consistency_review.entry_id:
        raise ValueError("consistency review entry_id does not match the entry thesis")
    if entry_thesis.entry_type != ENTRY_TYPE_ACTUAL:
        raise ValueError(
            "production advisory recommendations require an actual entry thesis; "
            "simulated and reconstructed entries are not admissible"
        )
    if entry_thesis.entry_date > decision_as_of:
        raise ValueError("entry thesis date cannot follow the recommendation as-of date")
    if entry_thesis.confirmed_at.date() > decision_as_of:
        raise ValueError("entry thesis confirmation cannot follow the recommendation as-of date")
    if (
        entry_thesis.created_at is not None
        and entry_thesis.created_at.date() > decision_as_of
    ):
        raise ValueError("entry thesis creation cannot follow the recommendation as-of date")
    if investment_consistency_review.as_of > decision_as_of:
        raise ValueError("consistency review date cannot follow the recommendation as-of date")
    if investment_consistency_review.as_of < entry_thesis.entry_date:
        raise ValueError("consistency review cannot precede the original entry date")


__all__ = ["validate_advisory_dependencies"]
