"""Read-only structural continuity for integration behind owned-entry review.

The caller supplies a reference case from its verified Entry Thesis. This module
rechecks public case bytes; it does not establish ownership or sellable shares.
"""
from datetime import datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

from .current_case_review import inspect_current_price_case
from .independent_price_conditions import INDEPENDENT_OPEN_RULE
from .price_action_case import project_current_price_action_plan
from ...domain.execution.exchange_calendar import is_exchange_session
from ...domain.hotspot.current_price import SESSION_TIMES
from ...quote_sessions import CHINA


VERSION = "hotspot-entry-structure-continuity-v1"


def _stamp(value):
    stamp = datetime.fromisoformat(value)
    return stamp.replace(tzinfo=CHINA) if stamp.utcoffset() is None else stamp


def _compare_entry_bars(*, bars, entry_at, protection, symbol):
    """Keep the original level and every observed breach, including recoveries."""
    points = [(_stamp(row["time"]), row) for row in bars]
    after = [(stamp, row) for stamp, row in points if stamp > entry_at]
    breached = [stamp.isoformat() for stamp, row in after
                if Decimal(row["close"]) < Decimal(protection)]
    expected = set()
    venue = "SSE" if symbol.startswith("6") else "SZSE"
    last = points[-1][0]
    day = entry_at.astimezone(CHINA).date()
    while day <= last.astimezone(CHINA).date():
        if is_exchange_session(venue, day):
            for clock in SESSION_TIMES["60m"]:
                stamp = datetime.combine(day, time.fromisoformat(clock), CHINA)
                if entry_at < stamp <= last:
                    expected.add(stamp)
        day += timedelta(days=1)
    observed = {stamp for stamp, _ in after}
    missing = sorted(expected - observed)
    return dict(original_protection_price=protection,
        first_breach_at=breached[0] if breached else None,
        breach_count=len(breached), inspected_bar_count=len(after),
        missing_completed_bars=[stamp.isoformat() for stamp in missing],
        coverage="COMPLETE" if expected and not missing else "INCOMPLETE",
        comparison_scope="UNADJUSTED_PRICE_STRUCTURE_REQUIRES_CORPORATE_ACTION_REVIEW")


def build_hotspot_lifecycle_review(*, root: Path, symbol: str,
        current_case_binding: dict, now: datetime,
        entry_case_binding: dict | None = None,
        entry_at: datetime | None = None) -> dict:
    """Source-bound explanations, never a personal action or approved strategy.

    Missing entry means no held review. The current entry observation remains
    visible for an independently confirmed flat account. A prior break is not
    erased by a later rally or a lower rolling-window invalidation level.
    """
    if now.utcoffset() is None:
        raise ValueError("Timezone-aware cutoff required")
    if (entry_case_binding is None) != (entry_at is None):
        raise ValueError("Entry reference and confirmation time must be supplied together")
    if entry_at is not None and (entry_at.utcoffset() is None or entry_at > now):
        raise ValueError("Entry confirmation must be known at cutoff")
    result = dict(schema_version=VERSION, symbol=symbol, action="no_order",
        evaluated_at=now.isoformat(), status="NOT_ASSESSABLE", observed_review="UNKNOWN",
        original_entry_comparison=None, current_conditions={}, blockers=[],
        current_case_binding=dict(current_case_binding),
        entry_case_binding=dict(entry_case_binding) if entry_case_binding else None,
        entry_at=entry_at.isoformat() if entry_at else None,
        holding_ownership="NOT_VERIFIED_HERE", position_guidance=None,
        personal_action="NO_ACTION", formal_eligibility=False, trade_eligible=False,
        risk_review_eligible=False, strategy_validation="NOT_PROVEN",
        required_external_reviews=["OWNED_ENTRY_THESIS", "CORPORATE_ACTION_COMPARABILITY",
            "INDEPENDENT_STRATEGY_ADMISSION", "EVENT_RISK", "PORTFOLIO_CAPACITY",
            "SELLABLE_QUANTITY_T_PLUS_ONE_AND_EXECUTION"])
    current = inspect_current_price_case(root=root, symbol=symbol,
        case_binding=current_case_binding, now=now)
    result["current_data_status"] = current["data_status"]
    if current["data_status"] != "CURRENT":
        result["blockers"] = [current["reason"]]
        return result
    plan = project_current_price_action_plan(current["case"])
    result["current_conditions"] = plan["conditional_action_rules"]
    result["current_conditions"]["OPEN"]["rule"] = INDEPENDENT_OPEN_RULE
    result["blockers"] = list(plan["price_behavior"]["blockers"])
    result["current_open_observed"] = plan["conditional_action_rules"]["OPEN"]["observed"]
    result["opportunity_quality"] = plan["opportunity_quality"]
    if entry_case_binding is None:
        result.update(status="CURRENT_STRUCTURE_ONLY", observed_review="ENTRY_OBSERVATION"
            if result["current_open_observed"] and plan["opportunity_quality"]["structure_tier"]
                == "STRUCTURE_QUALIFIED_OBSERVATION" else "WATCH")
        result["blockers"].append("OWNED_ENTRY_REQUIRED_FOR_HELD_REVIEW")
        return result
    original = inspect_current_price_case(root=root, symbol=symbol,
        case_binding=entry_case_binding, now=entry_at)
    if original["data_status"] != "CURRENT":
        result["blockers"].append("ENTRY_CASE_NOT_VALID_AT_ENTRY")
        return result
    entry_plan = project_current_price_action_plan(original["case"])
    if entry_plan["model_or_rule_version"] != plan["model_or_rule_version"]:
        result["blockers"].append("ENTRY_CURRENT_RULE_MISMATCH")
        return result
    comparison = _compare_entry_bars(bars=current["case"]["bars"]["60m"],
        entry_at=entry_at, protection=entry_plan["invalidation_price"], symbol=symbol)
    comparison["current_rolling_protection_price"] = plan["invalidation_price"]
    result["original_entry_comparison"] = comparison
    rules = result["current_conditions"]
    if comparison["first_breach_at"] or rules["EXIT"]["observed"]:
        observed = "EXIT_STRUCTURE_REVIEW"
    elif comparison["coverage"] != "COMPLETE":
        result["blockers"].append("ENTRY_TO_CURRENT_BAR_COVERAGE_INCOMPLETE")
        return result
    elif rules["REDUCE"]["observed"]:
        observed = "REDUCE_STRUCTURE_REVIEW"
    elif rules["ADD"]["observed"] and plan["price_behavior"]["observation_quality"] == "RESEARCH_ONLY":
        observed = "ADD_STRUCTURE_REVIEW"
    else:
        observed = "HOLD_STRUCTURE_OBSERVATION"
    result.update(status="STRUCTURAL_COMPARISON_ONLY", observed_review=observed)
    result["blockers"].append("STRUCTURAL_OBSERVATION_IS_NOT_PERSONAL_ACTION")
    return result
