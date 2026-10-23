"""Read-only structural continuity for integration behind owned-entry review.

The caller supplies a reference case from its verified Entry Thesis. This module
rechecks public case bytes; it does not establish ownership or sellable shares.
"""
from datetime import datetime, time, timedelta
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

from .current_case_review import inspect_current_price_case
from .corporate_action_coverage import inspect_official_action_coverage
from .independent_price_conditions import INDEPENDENT_OPEN_RULE
from .price_action_case import project_current_price_action_plan
from ...domain.execution.exchange_calendar import is_exchange_session
from ...domain.hotspot.current_price import SESSION_TIMES
from ...infrastructure.hotspot.price_comparability import inspect_price_comparability
from ...quote_sessions import CHINA


VERSION = "hotspot-entry-structure-continuity-v2"


def _stamp(value):
    stamp = datetime.fromisoformat(value)
    return stamp.replace(tzinfo=CHINA) if stamp.utcoffset() is None else stamp


def _compare_entry_bars(*, bars, entry_at, protection, symbol):
    """Keep the original level and every observed breach, including recoveries."""
    points = [(_stamp(row["time"]), row) for row in bars]
    after = [(stamp, row) for stamp, row in points if stamp > entry_at]
    breached = [(stamp, row) for stamp, row in after
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
        first_breach_at=breached[0][0].isoformat() if breached else None,
        first_breach_close=breached[0][1]["close"] if breached else None,
        breach_count=len(breached), inspected_bar_count=len(after),
        missing_completed_bars=[stamp.isoformat() for stamp in missing],
        coverage="COMPLETE" if expected and not missing else "INCOMPLETE",
        comparison_scope="UNADJUSTED_PRICE_STRUCTURE_REQUIRES_CORPORATE_ACTION_REVIEW")


def _explain(result, basis, *, plan=None, entry_plan=None, case=None):
    """Describe already evaluated rules, without granting a personal permission."""
    current_refs = [result["current_case_binding"]] if plan else []
    entry_refs = [result["entry_case_binding"]] if entry_plan else []
    path = [dict(check="CURRENT_DATA", outcome=result["current_data_status"],
        values=dict(blockers=[result["current_data_reason"]] if result["current_data_reason"] else [],
            current_pit=result["current_pit"],
            source_integrity=result["source_integrity"]), evidence_bindings=current_refs)]
    path.append(dict(check="ENTRY_REFERENCE", outcome="VERIFIED_REFERENCE_ONLY" if entry_plan
        else "UNVERIFIED" if result["entry_case_binding"] else "NOT_SUPPLIED",
        values=dict(entry_at=result["entry_at"], blockers=["ENTRY_CASE_NOT_VALID_AT_ENTRY"]
            if basis == "ENTRY_EVIDENCE_UNAVAILABLE" else []), evidence_bindings=entry_refs))
    versions = dict(current=plan.get("model_or_rule_version") if plan else None,
        entry=entry_plan.get("model_or_rule_version") if entry_plan else None)
    path.append(dict(check="ENTRY_RULE_COMPATIBILITY", outcome=(
        "MATCH" if versions["current"] == versions["entry"] else "MISMATCH")
        if entry_plan else "NOT_EVALUATED", values=versions,
        evidence_bindings=current_refs + entry_refs))
    comparability = result["price_comparability"]
    path.append(dict(check="PRICE_COMPARABILITY", outcome=comparability["status"]
        if comparability else "NOT_EVALUATED", values=comparability or {},
        evidence_bindings=comparability["evidence_bindings"] if comparability else []))
    comparison = result["original_entry_comparison"]
    path.append(dict(check="ORIGINAL_PROTECTION", outcome=("BREACHED"
        if comparison["first_breach_at"] else "NO_OBSERVED_BREACH")
        if comparison else "NOT_EVALUATED", values=comparison or {},
        evidence_bindings=current_refs + entry_refs if comparison else []))
    path.append(dict(check="CONTINUITY_COVERAGE", outcome=comparison["coverage"]
        if comparison else "NOT_EVALUATED", values=dict(missing_completed_bars=
        comparison["missing_completed_bars"]) if comparison else {},
        evidence_bindings=current_refs + entry_refs if comparison else []))
    for intent in ("EXIT", "REDUCE", "ADD", "OPEN"):
        condition = result["current_conditions"].get(intent)
        path.append(dict(check="CURRENT_" + intent, outcome=("OBSERVED"
            if condition["observed"] else "NOT_OBSERVED") if condition else "NOT_EVALUATED",
            values=condition or {}, evidence_bindings=current_refs))
    path.append(dict(check="STRUCTURE_QUALITY", outcome=plan["price_behavior"].get(
        "observation_quality", "UNKNOWN") if plan else "NOT_EVALUATED",
        values={key: plan["price_behavior"].get(key) for key in (
            "rule_version", "observation_quality", "daily_trend", "risk_reward_ratio",
            "risk_reward_scope", "risk_reward_blocker", "blockers")} if plan else {},
        evidence_bindings=current_refs))
    path.append(dict(check="OPPORTUNITY_QUALITY", outcome=plan["opportunity_quality"]["structure_tier"]
        if plan else "NOT_EVALUATED", values=result.get("opportunity_quality", {}),
        evidence_bindings=current_refs))
    why_not_add = []
    if basis not in {"CURRENT_ADD_CONDITION_OBSERVED", "NO_STRUCTURAL_CHANGE_OBSERVED"}:
        why_not_add.append(basis)
    if plan:
        if not result["current_conditions"]["ADD"]["observed"]:
            why_not_add.append("ADD_CONDITION_NOT_OBSERVED")
        if plan["price_behavior"].get("observation_quality") != "RESEARCH_ONLY":
            why_not_add.append("ADD_STRUCTURE_QUALITY_NOT_USABLE")
    price = None
    if case is not None:
        price = dict(price=case.get("current_reference_price"),
            as_of=case.get("market_trade_date"), available_at=plan.get("data_available_at"),
            reference_price_scope=plan.get("reference_price_scope"), current_pit=result["current_pit"])
    result["decision_explanation"] = deepcopy(dict(
        schema_version="hotspot-lifecycle-explanation-v1", selected_review=result["observed_review"],
        basis_code=basis, decision_path=path, why_not_add=why_not_add,
        required_external_reviews=result["required_external_reviews"],
        current_price_observation=price, recomputed_rule_versions=versions if plan else None,
        source_scope="REFERENCE_CASES_NOT_VERIFIED_OWNERSHIP_OR_ENTRY_THESIS", action="no_order"))
    return result


def build_hotspot_lifecycle_review(*, root: Path, symbol: str,
        current_case_binding: dict, now: datetime,
        entry_case_binding: dict | None = None,
        entry_at: datetime | None = None,
        corporate_action_registry_binding: dict | None = None,
        official_event_observation_binding: dict | None = None) -> dict:
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
        original_entry_comparison=None, price_comparability=None,
        unadjusted_structural_observation=None, current_conditions={}, blockers=[],
        current_conditions_scope="RAW_UNADJUSTED_NOT_PERSONAL_ACTION",
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
    result["current_data_reason"] = current.get("reason")
    result["current_pit"] = current.get("current_pit", False)
    result["source_integrity"] = current.get("source_integrity", "NOT_VERIFIED")
    if current["data_status"] != "CURRENT":
        result["blockers"] = [current["reason"]]
        return _explain(result, "CURRENT_DATA_UNAVAILABLE")
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
        return _explain(result, "ENTRY_STRUCTURE_OBSERVED"
            if result["observed_review"] == "ENTRY_OBSERVATION" else "ENTRY_STRUCTURE_NOT_QUALIFIED",
            plan=plan, case=current["case"])
    original = inspect_current_price_case(root=root, symbol=symbol,
        case_binding=entry_case_binding, now=entry_at)
    if original["data_status"] != "CURRENT":
        result["blockers"].append("ENTRY_CASE_NOT_VALID_AT_ENTRY")
        return _explain(result, "ENTRY_EVIDENCE_UNAVAILABLE", plan=plan, case=current["case"])
    entry_plan = project_current_price_action_plan(original["case"])
    if entry_plan["model_or_rule_version"] != plan["model_or_rule_version"]:
        result["blockers"].append("ENTRY_CURRENT_RULE_MISMATCH")
        return _explain(result, "ENTRY_CURRENT_RULE_MISMATCH", plan=plan,
            entry_plan=entry_plan, case=current["case"])
    comparison = _compare_entry_bars(bars=current["case"]["bars"]["60m"],
        entry_at=entry_at, protection=entry_plan["invalidation_price"], symbol=symbol)
    comparison["current_rolling_protection_price"] = plan["invalidation_price"]
    result["original_entry_comparison"] = comparison
    start = min(_stamp(row["time"]).date() for case in (original["case"], current["case"])
        for rows in case["bars"].values() for row in rows)
    end = _stamp(current["case"]["bars"]["60m"][-1]["time"]).date()
    comparability = inspect_price_comparability(root=root, symbol=symbol, start=start, end=end,
        now=now, registry_binding=corporate_action_registry_binding)
    comparability["official_disclosure_coverage"] = inspect_official_action_coverage(
        root=root, symbol=symbol, start=start, end=end, now=now,
        observation_binding=official_event_observation_binding)
    result["price_comparability"] = comparability
    rules = result["current_conditions"]
    if comparison["first_breach_at"] or rules["EXIT"]["observed"]:
        observed = "EXIT_STRUCTURE_REVIEW"
        basis = "ORIGINAL_PROTECTION_BREACHED" if comparison["first_breach_at"] else "CURRENT_PROTECTION_BREACHED"
    elif comparison["coverage"] != "COMPLETE":
        result["blockers"].append("ENTRY_TO_CURRENT_BAR_COVERAGE_INCOMPLETE")
        return _explain(result, "ENTRY_TO_CURRENT_DATA_INCOMPLETE", plan=plan,
            entry_plan=entry_plan, case=current["case"])
    elif rules["REDUCE"]["observed"]:
        observed = "REDUCE_STRUCTURE_REVIEW"
        basis = "CURRENT_REDUCTION_CONDITION_OBSERVED"
    elif rules["ADD"]["observed"] and plan["price_behavior"]["observation_quality"] == "RESEARCH_ONLY":
        observed = "ADD_STRUCTURE_REVIEW"
        basis = "CURRENT_ADD_CONDITION_OBSERVED"
    else:
        observed = "HOLD_STRUCTURE_OBSERVATION"
        basis = "NO_STRUCTURAL_CHANGE_OBSERVED"
    result["unadjusted_structural_observation"] = dict(observed_review=observed, basis_code=basis,
        scope="RAW_UNADJUSTED_NOT_COMPARABILITY_ADMITTED", action="no_order")
    if comparability["status"] != "CONFIRMED":
        result["blockers"].append("PRICE_BASIS_" + comparability["status"])
        return _explain(result, "PRICE_BASIS_" + comparability["status"], plan=plan,
            entry_plan=entry_plan, case=current["case"])
    result.update(status="STRUCTURAL_COMPARISON_ONLY", observed_review=observed)
    result["blockers"].append("STRUCTURAL_OBSERVATION_IS_NOT_PERSONAL_ACTION")
    return _explain(result, basis, plan=plan, entry_plan=entry_plan, case=current["case"])
