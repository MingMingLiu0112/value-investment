"""Pure F2 historical conditional-price adapter; no registration or current quote.

The caller owns source-byte verification. This adapter requires path/hash bindings
and source versions, but does not claim to replay or verify external source bytes.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date
from decimal import Decimal, InvalidOperation
import re
from typing import Any, Mapping

from ...domain.decision.value_price_policy import (
    draft_value_price_policy,
    preview_draft_prices,
)
from ...valuation_models.base import ValuationResult


def draft_direct_owner_cash_price(
    *,
    plan: Mapping[str, Any],
    rule_config: Mapping[str, Any],
    as_of: date,
    valuation: ValuationResult | None = None,
) -> dict[str, Any]:
    """Return the frontend ``direct_owner_cash.conditional_price`` object.

    plan requires symbol, action=no_order, research_version,
    valuation_input_version, model_id/type/version, valuation_date (ISO date),
    source_bindings (nonempty path/sha256 rows), and bear/base/bull values.
    With valuation supplied, its identity/date/model and any retained plan values
    must agree; its scenario values are projected without recalculation.

    rule_config requires draft_id, policy_id, rule_version, profile_id, rationale,
    dividend_coverage_risk, effective_from/effective_through (ISO dates), and
    nonempty explicit rules accepted by the existing domain draft contract.
    effective_through is inclusive; as_of is an explicit evaluation day, never
    silently the historical valuation day. No default fractions are supplied.
    """
    result: dict[str, Any] = dict(
        status="REJECTED", draft_prices=None, reason_codes=[],
        currentpricecomparison=False, action="no_order",
        scope="HISTORICAL_CONDITIONAL_RESEARCH_NOT_CURRENT_BUY_PRICE",
        approved=False, registered=False,
    )
    reasons = result["reason_codes"]
    basis = deepcopy(dict(plan))
    config = deepcopy(dict(rule_config))

    def required_text(value: Any) -> bool:
        return isinstance(value, str) and bool(value.strip())

    def parse_day(value: Any, field: str) -> date | None:
        try:
            if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                raise ValueError
            return date.fromisoformat(value)
        except ValueError:
            reasons.append("INVALID_OR_MISSING_DATE:" + field)
            return None

    if type(as_of) is not date:
        reasons.append("EXPLICIT_AS_OF_DATE_REQUIRED")
    if basis.get("action") != "no_order":
        reasons.append("NO_ORDER_PLAN_REQUIRED")
    for field in ("research_version", "valuation_input_version", "model_id", "model_type", "model_version"):
        if not required_text(basis.get(field)):
            reasons.append("MISSING_SOURCE_VERSION:" + field)
    bindings = basis.get("source_bindings")
    if not isinstance(bindings, (list, tuple)) or not bindings or any(
        not isinstance(row, Mapping) or not required_text(row.get("path"))
        or not isinstance(row.get("sha256"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", row["sha256"])
        for row in bindings
    ):
        reasons.append("MISSING_OR_INVALID_SOURCE_BINDINGS")
    valuation_day = parse_day(basis.get("valuation_date"), "valuation_date")
    start = parse_day(config.get("effective_from"), "effective_from")
    expiry = parse_day(config.get("effective_through"), "effective_through")
    if expiry:
        result["expires_at"] = expiry.isoformat()
    if start and expiry and start > expiry:
        reasons.append("INVALID_VALIDITY_INTERVAL")
    if type(as_of) is date:
        if expiry and as_of > expiry:
            reasons.append("EXPIRED")
        if start and as_of < start:
            reasons.append("NOT_YET_EFFECTIVE")
        if valuation_day and valuation_day > as_of:
            reasons.append("VALUATION_DATE_IN_FUTURE")
    for field in ("draft_id", "policy_id", "rule_version", "profile_id", "rationale", "dividend_coverage_risk"):
        if not required_text(config.get(field)):
            reasons.append("MISSING_RULE_CONFIG:" + field)
    rules = config.get("rules")
    if not isinstance(rules, (list, tuple)) or not rules:
        reasons.append("EXPLICIT_RULES_REQUIRED")
    else:
        for index, rule in enumerate(rules):
            if not isinstance(rule, Mapping) or not required_text(rule.get("rationale")):
                reasons.append(f"MISSING_RULE_RATIONALE:{index}")

    if valuation is not None:
        if valuation.status == "not_ready" or valuation.blockers:
            reasons.append("VALUATION_NOT_READY_OR_BLOCKED")
        for key, value in (("symbol", valuation.symbol), ("model_type", valuation.model_type),
                           ("model_version", valuation.model_version),
                           ("valuation_date", valuation.valuation_date.isoformat())):
            if basis.get(key) != value:
                reasons.append("VALUATION_PLAN_MISMATCH:" + key)
        for name in ("bear", "base", "bull"):
            value = getattr(valuation, name + "_value")
            try:
                if basis.get(name) is not None and Decimal(str(basis[name])) != value:
                    reasons.append("VALUATION_PLAN_MISMATCH:" + name)
            except InvalidOperation:
                reasons.append("VALUATION_PLAN_MISMATCH:" + name)
            basis[name] = str(value) if value is not None else None
    if any(basis.get(name) is None for name in ("bear", "base", "bull")):
        reasons.append("SCENARIOS_UNAVAILABLE")
    if reasons:
        return result
    try:
        draft = draft_value_price_policy(
            basis, **{key: config[key] for key in (
                "draft_id", "policy_id", "rule_version", "profile_id", "rationale", "dividend_coverage_risk"
            )}, effective_from=start, effective_through=expiry, rules=rules,
        )
        prices = preview_draft_prices(draft)
    except (ValueError, TypeError, KeyError, AttributeError, InvalidOperation):
        reasons.append("INVALID_EXPLICIT_PRICE_POLICY")
        return result
    result.update(status="HISTORICAL_CONDITIONAL_DRAFT", draft_prices=prices,
                  reason_codes=["UNAPPROVED_HISTORICAL_CONDITIONAL_RESEARCH"], draft=draft)
    return result
