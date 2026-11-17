"""Explicit draft economics; preparation and user confirmation are separate."""
from copy import deepcopy
from datetime import date
from decimal import Decimal, localcontext
import hashlib
import json

from .value_action_plan import ACTIONS, ValuePriceRule

DRAFT_SCHEMA = "value-price-policy-draft-v1"
PREPARED_SCHEMA = "value-price-policy-prepared-v1"


def payload_hash(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def policy_basis(plan):
    return deepcopy({key: plan.get(key) for key in (
        "symbol", "research_version", "valuation_input_version", "model_id", "model_type",
        "model_version", "valuation_date", "bear", "base", "bull")})


def validate_draft(draft):
    if draft.get("schema_version") != DRAFT_SCHEMA or draft.get("status") != "DRAFT":
        raise ValueError("Expected an unapproved policy draft")
    if draft.get("action") != "no_order" or draft.get("registered") is not False:
        raise ValueError("Draft cannot authorize or register a policy")
    for field in ("draft_id", "policy_id", "rule_version", "profile_id", "rationale",
                  "dividend_coverage_risk"):
        if not isinstance(draft.get(field), str) or not draft[field].strip():
            raise ValueError("Explicit draft field required: " + field)
    if date.fromisoformat(draft["effective_through"]) < date.fromisoformat(draft["effective_from"]):
        raise ValueError("Invalid policy validity interval")
    if draft.get("currency") != "CNY" or draft.get("share_basis") != "ordinary_share_unadjusted":
        raise ValueError("Unsupported policy price basis")
    basis = draft.get("basis") or {}
    symbol = basis.get("symbol")
    if not isinstance(symbol, str) or len(symbol) != 6 or not symbol.isdigit():
        raise ValueError("Explicit security identity required")
    rules = tuple(ValuePriceRule(action=row["action"], scenario=row["scenario"],
        value_fraction=Decimal(row["value_fraction"]), comparison=row["comparison"],
        rationale=row["rationale"]) for row in draft["rules"])
    if len({rule.action for rule in rules}) != len(rules):
        raise ValueError("Duplicate action policy")
    return rules


def draft_value_price_policy(plan, *, draft_id, policy_id, rule_version, profile_id,
                             effective_from, effective_through, rationale,
                             dividend_coverage_risk, rules=(), thesis_reviews=()):
    """No default fraction: empty rules produce no action prices."""
    if plan.get("action") != "no_order":
        raise ValueError("Policy draft requires a no-order plan")
    draft = dict(schema_version=DRAFT_SCHEMA, status="DRAFT", draft_id=draft_id,
        policy_id=policy_id, rule_version=rule_version, profile_id=profile_id,
        effective_from=effective_from.isoformat(), effective_through=effective_through.isoformat(),
        rationale=rationale, dividend_coverage_risk=dividend_coverage_risk,
        basis=policy_basis(plan), rules=deepcopy(list(rules)),
        thesis_reviews=deepcopy(list(thesis_reviews)), source_bindings=deepcopy(plan.get("source_bindings", [])),
        currency="CNY", share_basis="ordinary_share_unadjusted", registered=False, action="no_order")
    validate_draft(draft)
    return draft


def preview_draft_prices(draft):
    """Arithmetic preview only; not the registered plan's action prices."""
    prices = dict.fromkeys(ACTIONS)
    for rule in validate_draft(draft):
        value = draft["basis"].get(rule.scenario)
        if value is None:
            continue
        value = Decimal(value)
        if not value.is_finite() or value <= 0:
            raise ValueError("Invalid retained scenario")
        with localcontext() as context:
            context.prec = max(50, len(value.as_tuple().digits) + len(rule.value_fraction.as_tuple().digits) + 4)
            prices[rule.action] = str(value * rule.value_fraction)
    return prices
