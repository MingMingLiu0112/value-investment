"""Separate dated activity ranking from completed price structure evidence."""

RULE_VERSION = "hotspot-opportunity-quality-v1"


def classify_structure(behavior: dict, structures: dict, *, signal_state: str,
                       trade_date: str, expires_after_session: str) -> dict:
    if behavior.get("action") != "no_order" or set(structures) != {"daily", "60m", "15m"}:
        raise ValueError("Incomplete research-only structure evidence")
    reasons = []
    if signal_state in {"TRIGGER_REJECTED", "INVALIDATED"} or behavior.get("structural_invalidation"):
        reasons.append("PRIMARY_STRUCTURE_INVALIDATED")
    if behavior.get("daily_trend") == "DOWNTREND":
        reasons.append("DAILY_DOWNTREND_CONFLICT")
    if behavior.get("observation_quality") == "INSUFFICIENT_UPPER_SPACE":
        reasons.append("INSUFFICIENT_UPPER_SPACE")
    if structures["60m"] == "INVALIDATED":
        reasons.append("PRIMARY_STRUCTURE_INVALIDATED")
    if structures["daily"] == "INVALIDATED" or structures["15m"] == "INVALIDATED":
        reasons.append("SUPPORTING_STRUCTURE_INVALIDATED")
    if reasons:
        tier = "CONFLICT_OR_REJECTED"
    elif (behavior.get("daily_trend") in {"UPTREND", "RANGE"}
          and behavior.get("observation_quality") == "RESEARCH_ONLY"
          and structures["60m"] == "BREAKOUT"
          and (behavior.get("breakout", {}).get("confirmed_on_next_completed_bar") is True
               or behavior.get("pullback_recovery", {}).get("observed") is True)):
        tier = "STRUCTURE_QUALIFIED_OBSERVATION"
        reasons = ["DAILY_AND_PRIMARY_STRUCTURE_CONFIRMED"]
    else:
        tier = "ACTIVE_ONLY"
        reasons = ["STRUCTURE_CONFIRMATION_PENDING"]
    return dict(rule_version=RULE_VERSION, activity_tier="ACTIVE_OBSERVATION",
                structure_tier=tier, structure_reasons=list(dict.fromkeys(reasons)),
                assessed_trade_date=trade_date, expires_after_session=expires_after_session,
                expiry_rule="Refresh after next completed exchange session",
                formal_eligibility=False, action="no_order")
