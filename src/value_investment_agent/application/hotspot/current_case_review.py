"""Separate current-data expiry from source integrity and strategy admission."""
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path

from ...infrastructure.hotspot.current_price_case import load_current_price_case
from .event_replay import _availability, _bound_bytes


def is_stale_current_price_error(error: Exception) -> bool:
    message = str(error)
    return message in {
        "B1 current close rejected: stale_quote",
        "Display close is not calendar-bound latest completed session: stale_quote",
    }


def inspect_current_price_case(*, root: Path, symbol: str, case_binding: dict,
                               now: datetime) -> dict:
    """Reverify bytes at now; expired evidence is reverified at its acquisition.

    A historical verification never grants current PIT. Only the two explicit
    stale-quote failures may enter that fallback; corruption remains INVALID.
    """
    if now.utcoffset() is None:
        raise ValueError("Current case review requires a timezone-aware clock")
    root = root.resolve()
    result = dict(schema_version="hotspot-current-case-review-v1", symbol=symbol,
        case_binding=deepcopy(case_binding), evaluated_at=now.isoformat(),
        data_status="INVALID", source_integrity="NOT_VERIFIED", case=None,
        source_verified_at=None, current_pit=False, formal_eligibility=False,
        strategy_validation="NOT_EVALUATED", action="no_order")
    try:
        # Bind the exact case before reading any timestamps for historical use.
        case = json.loads(_bound_bytes(root, case_binding))
        kwargs = dict(root=root, symbol=symbol, case_path=Path(case_binding["path"]),
                      expected_sha256=case_binding["sha256"])
        try:
            verified = load_current_price_case(**kwargs, now=now)
            result.update(data_status="CURRENT", reason=None, diagnostic=None)
        except ValueError as error:
            if not is_stale_current_price_error(error):
                raise
            quote = case["current_reference_close"]
            bundle = json.loads(_bound_bytes(root,
                dict(path=quote["bundle_path"], sha256=quote["bundle_sha256"])))
            acquired = datetime.fromisoformat(_availability(case, bundle))
            if acquired.utcoffset() is None or acquired > now:
                raise ValueError("Historical source unavailable at evaluation cutoff")
            verified = load_current_price_case(**kwargs, now=acquired)
            result.update(data_status="STALE", reason="CURRENT_MARKET_DATA_STALE",
                          diagnostic=str(error))
        result.update(source_integrity="VERIFIED", case=verified,
            source_verified_at=verified["verified_available_at"],
            current_pit=(result["data_status"] == "CURRENT"
                         and verified.get("observation_scope") != "LAST_COMPLETED_CLOSE_DISPLAY_ONLY"))
    except (ValueError, OSError, KeyError, TypeError, ArithmeticError) as error:
        result.update(data_status="INVALID", reason="CURRENT_CASE_EVIDENCE_INVALID",
                      diagnostic=str(error), case=None)
    return result


def expire_price_action_plan(plan: dict, *, review: dict) -> dict:
    """Keep verified old conditions only in an explicitly historical object."""
    if review.get("data_status") != "STALE" or review.get("source_integrity") != "VERIFIED":
        raise ValueError("Only verified expired evidence can be retained as history")
    output = deepcopy(plan)
    history = deepcopy(plan)
    history.update(reference_price_scope="HISTORICAL_CLOSE_NOT_CURRENT_QUOTE",
        observation_scope="HISTORICAL_OBSERVATION_ONLY", current_pit=False,
        formal_eligibility=False, risk_review_eligible=False, action_eligibility=False,
        action_intent="WATCH", action="no_order")
    output.update(historical_observation=history, signal_state="STALE", action_intent="WATCH",
        current_data_status="STALE", current_pit=False, source_integrity="VERIFIED",
        reference_price_scope="UNAVAILABLE_CURRENT_QUOTE", observation_scope="HISTORICAL_OBSERVATION_ONLY",
        formal_eligibility=False, risk_review_eligible=False, action_eligibility=False,
        portfolio_eligibility=None, position_guidance=None, trade_eligible=False,
        explanation="行情已过期；已复核的旧结构仅供历史观察，当前价位等待下一份完整交易日证据。",
        blockers=list(dict.fromkeys([*plan.get("blockers", []), "CURRENT_MARKET_DATA_STALE"])),
        action="no_order")
    return suppress_current_price_conditions(output)


def suppress_current_price_conditions(plan: dict) -> dict:
    """No stale/invalid condition may remain an actionable current field."""
    output = deepcopy(plan)
    for key in ("current_reference_price", "current_reference_close", "entry_trigger_price",
                "add_trigger_price", "reduce_trigger_price", "exit_trigger_price", "invalidation_price",
                "entry_condition", "add_condition", "reduce_condition", "exit_condition",
                "invalidation_condition", "price_behavior", "opportunity_quality", "risk_reward_ratio",
                "security_risk_trigger", "next_completed_eligible_session", "next_session_date",
                "operational_conditions"):
        output[key] = None
    output.update(levels=None if plan.get("levels") is None else {},
        period_structure={}, conditional_action_rules={}, trend_state="NOT_ASSESSED",
        action_intent="WATCH", current_pit=False, risk_review_eligible=False,
        reference_price_scope="UNAVAILABLE_CURRENT_QUOTE")
    return output
