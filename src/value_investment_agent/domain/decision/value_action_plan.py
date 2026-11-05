"""Policy-bound value conditions over existing research; never value or order."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, localcontext
import re
from typing import Any, Mapping
from ...pre_decision_eligibility import PreDecisionEligibility, STATUS_ELIGIBLE

SCHEMA_VERSION = "value-action-plan-v1"
RULE_VERSION = "value-action-plan-projection-v4"
ACTIONS = ("entry", "add", "reduce", "exit")
ACTION_INTENTS = ("OPEN", "ADD", "HOLD", "REDUCE", "EXIT")


@dataclass(frozen=True)
class ValuePriceRule:
    action: str
    scenario: str
    value_fraction: Decimal
    comparison: str
    rationale: str

    def __post_init__(self):
        if self.action not in ACTIONS or self.scenario not in {"bear", "base", "bull"}:
            raise ValueError("Unsupported value policy action or scenario")
        if (not isinstance(self.value_fraction, Decimal) or not self.value_fraction.is_finite()
                or self.value_fraction <= 0 or not self.rationale.strip()):
            raise ValueError("Policy fraction and rationale are required")
        expected = "LTE" if self.action in {"entry", "add"} else "GTE"
        if self.comparison != expected:
            raise ValueError("Policy comparison conflicts with action")


@dataclass(frozen=True)
class RegisteredValueActionPolicy:
    """A caller-verified registration, distinct from G3 or an order approval."""
    policy_id: str
    rule_version: str
    symbol: str
    profile_id: str
    model_id: str
    model_version: str
    effective_from: date
    effective_through: date
    registered_at: datetime
    rules: tuple[ValuePriceRule, ...]
    source_binding: Mapping[str, str]
    currency: str = "CNY"
    share_basis: str = "ordinary_share_unadjusted"

    def __post_init__(self):
        if not re.fullmatch(r"\d{6}", self.symbol):
            raise ValueError("Policy security identity required")
        if not all(isinstance(value, str) and value.strip() for value in (
                self.policy_id, self.rule_version, self.profile_id, self.model_id, self.model_version)):
            raise ValueError("Policy registration identity required")
        if self.registered_at.utcoffset() is None or self.effective_through < self.effective_from:
            raise ValueError("Policy registration dates invalid")
        if self.currency != "CNY" or self.share_basis != "ordinary_share_unadjusted":
            raise ValueError("Unsupported policy currency or share basis")
        if (set(self.source_binding) != {"path", "sha256"}
                or not self.source_binding["path"]
                or not re.fullmatch(r"[0-9a-f]{64}", self.source_binding["sha256"])):
            raise ValueError("Policy must carry its verified registration binding")
        if not self.rules or len({rule.action for rule in self.rules}) != len(self.rules):
            raise ValueError("Policy rules must be nonempty and unique by action")


@dataclass(frozen=True)
class ValueActionPlan:
    """Public plan snapshot. Personal sizing and human approval stay external."""
    payload: Mapping[str, Any]

    def __post_init__(self):
        if (self.payload.get("schema_version") != SCHEMA_VERSION
                or self.payload.get("action") != "no_order"
                or type(self.payload.get("formal_eligibility")) is not bool
                or (self.payload.get("portfolio_eligibility") is not None
                    and type(self.payload.get("portfolio_eligibility")) is not bool)
                or self.payload.get("position_guidance") is not None):
            raise ValueError("ValueActionPlan cannot authorize human decisions or positions")
        if self.payload["formal_eligibility"] and (
                self.payload.get("formal_eligibility_blockers")
                or self.payload.get("security_review_eligible") is not True):
            raise ValueError("Formal auxiliary eligibility requires admitted security review")
        object.__setattr__(self, "payload", deepcopy(dict(self.payload)))

    def as_policy(self) -> dict[str, Any]:
        return deepcopy(dict(self.payload))


def build_value_action_plan(*, explanation: Mapping[str, Any],
                           policy: RegisteredValueActionPolicy | None = None,
                           reference_quote: Mapping[str, Any] | None = None,
                           source_bindings: tuple[dict, ...] = (),
                           repository_replayed: bool = False,
                           verified_predecision: PreDecisionEligibility | None = None,
                           decision_as_of: date | None = None) -> ValueActionPlan:
    """Project source-verified inputs; thresholds have no implicit defaults.

    The application owns verification. The existing v3 recommendation owns
    thesis action selection and predecision owns price admission. This function
    only applies an explicitly registered scenario fraction, never recomputes
    valuation or reinterprets a research value band as an investment policy.
    """
    symbol = explanation["symbol"]
    if not re.fullmatch(r"\d{6}", symbol) or explanation.get("action") != "no_order":
        raise ValueError("Value plan requires a no-order security explanation")
    research_day = date.fromisoformat(explanation.get("research_as_of") or explanation["decision_as_of"])
    decision_day = decision_as_of or date.fromisoformat(explanation["decision_as_of"])
    if research_day > decision_day or date.fromisoformat(explanation["decision_as_of"]) > decision_day:
        raise ValueError("Research available after plan date")
    valuation = explanation.get("valuation") or {}
    values = {key: valuation.get(key + "_value") for key in ("bear", "base", "bull")}
    for value in values.values():
        if value is not None and (not Decimal(value).is_finite() or Decimal(value) <= 0):
            raise ValueError("Invalid retained scenario value")
    if all(value is not None for value in values.values()) and not (
            Decimal(values["bear"]) <= Decimal(values["base"]) <= Decimal(values["bull"])):
        raise ValueError("Retained scenarios are not ordered")
    if valuation and (valuation.get("symbol") != symbol
                      or date.fromisoformat(valuation["valuation_date"]) > decision_day):
        raise ValueError("Valuation identity or availability mismatch")
    price_context = explanation.get("price_context") or {}
    bridge = price_context.get("price_bridge") or {}
    quote = dict(reference_quote or {})
    if reference_quote is None and bridge.get("current_price") is not None:
        quote = dict(symbol=symbol, price=bridge["current_price"], quote_date=bridge.get("quote_date"),
                     status=bridge.get("quote_status"), comparison_eligible=True)
    if quote and (quote.get("symbol") != symbol or quote.get("quote_date") is None
                  or date.fromisoformat(quote["quote_date"]) > decision_day
                  or not Decimal(quote["price"]).is_finite() or Decimal(quote["price"]) <= 0):
        raise ValueError("Reference quote identity/availability invalid")
    positive_review = price_context.get("positive_price_review_eligible") is True
    comparable = (positive_review and bridge.get("bridge_status") == "READY"
                  and quote.get("comparison_eligible") is True
                  and quote.get("status") == "verified_close"
                  and quote.get("quote_date") == bridge.get("quote_date")
                  and Decimal(quote["price"]) == Decimal(bridge["current_price"]))
    blockers = list(explanation.get("blockers") or [])
    validity = explanation.get("model_validity") or {}
    validity_status = validity.get("status", "UNKNOWN")
    if bridge and bridge.get("symbol") != symbol:
        raise ValueError("PriceBridge belongs to another security")
    if quote.get("quote_date") and validity_status == "VALID":
        checked = validity.get("last_material_event_check")
        if checked is None or checked < quote["quote_date"]:
            comparable = False
            blockers.append("VALUE_MODEL_EVENT_SCAN_DOES_NOT_COVER_QUOTE")
    scenario_ready = (all(value is not None for value in values.values())
                      and valuation.get("status") != "not_ready")
    if not comparable:
        blockers.append("VALUE_PRICE_COMPARISON_NOT_ELIGIBLE")
    conditions = {action: None for action in ACTIONS}
    policy_view = None
    policy_usable = False
    if policy is not None:
        if not isinstance(policy, RegisteredValueActionPolicy):
            raise ValueError("Value policy must be a verified registration")
        profile_id = (price_context.get("price_attractiveness") or {}).get("profile_id")
        model_id = explanation.get("model_id") or validity.get("model_id")
        if (policy.symbol != symbol or policy.model_id != model_id
                or policy.model_version != valuation.get("model_version")
                or policy.profile_id != profile_id):
            blockers.append("VALUE_POLICY_NOT_APPLICABLE")
        elif not (policy.effective_from <= decision_day <= policy.effective_through
                  and policy.registered_at.date() <= decision_day):
            blockers.append("VALUE_POLICY_NOT_CURRENT_OR_NOT_YET_REGISTERED")
        elif (not scenario_ready or validity_status != "VALID" or bridge.get("bridge_status") != "READY"
              or not quote or quote.get("status") != "verified_close"
              or validity.get("last_material_event_check", "") < quote.get("quote_date", "")):
            blockers.append("VALUE_POLICY_MODEL_OR_PRICE_BASIS_NOT_READY")
        else:
            policy_usable = True
            policy_view = dict(policy_id=policy.policy_id, rule_version=policy.rule_version,
                               source_binding=dict(policy.source_binding), currency=policy.currency,
                               share_basis=policy.share_basis)
            for rule in policy.rules:
                # Do not let a caller's Decimal context change published levels.
                with localcontext() as context:
                    context.prec = max(50, len(Decimal(values[rule.scenario]).as_tuple().digits)
                                       + len(rule.value_fraction.as_tuple().digits) + 4)
                    price = Decimal(values[rule.scenario]) * rule.value_fraction
                triggered = None
                if comparable:
                    close = Decimal(quote["price"])
                    triggered = close <= price if rule.comparison == "LTE" else close >= price
                conditions[rule.action] = dict(kind="POLICY_PRICE_REVIEW", price=str(price),
                    comparison=rule.comparison, scenario=rule.scenario,
                    scenario_value=values[rule.scenario], value_fraction=str(rule.value_fraction),
                    rationale=rule.rationale, triggered=triggered, rule_version=policy.rule_version,
                    policy_id=policy.policy_id, source_binding=dict(policy.source_binding),
                    qualification="CONDITIONAL_REVIEW_NOT_ORDER")
    for action in ACTIONS:
        if conditions[action] is None:
            blockers.append(f"VALUE_{action.upper()}_PRICE_POLICY_MISSING_OR_INAPPLICABLE")
    kind = explanation.get("candidate_action", "NO_ACTION")
    entry = explanation.get("entry_thesis") or {}
    for action, reasons_key, observed_kind in (
            ("reduce", "reasons_to_reduce", "TRIM_CANDIDATE"),
            ("exit", "reasons_to_exit", "SELL_CANDIDATE")):
        reasons = entry.get(reasons_key) or []
        if reasons:
            thesis_condition = dict(kind="THESIS_REVIEW", price=None, reasons=deepcopy(reasons),
                triggered=kind == observed_kind, rule_version="recommendation-rules-v1",
                entry_id=explanation.get("entry_id"),
                consistency_status=explanation.get("thesis_consistency_status"),
                qualification="INDEPENDENT_THESIS_REVIEW_NOT_PRICE_OR_SELL_AUTHORIZATION")
            if conditions[action] is None:
                conditions[action] = thesis_condition
            else:
                conditions[action]["thesis_review"] = thesis_condition
    hold_logic = entry.get("hold_logic")
    if kind == "HOLD" and isinstance(hold_logic, str) and hold_logic.strip():
        conditions["hold"] = dict(kind="HOLD_THESIS", price=None,
            reasoning=hold_logic.strip(), triggered=True,
            rule_version="recommendation-rules-v1", entry_id=explanation.get("entry_id"),
            consistency_status=explanation.get("thesis_consistency_status"),
            qualification="EXISTING_THESIS_HOLD_REVIEW_NOT_TRADE_AUTHORIZATION")
    intent = {"BUY_CANDIDATE": "OPEN", "ADD_CANDIDATE": "ADD", "HOLD": "HOLD",
              "TRIM_CANDIDATE": "REDUCE", "SELL_CANDIDATE": "EXIT"}.get(kind)
    review_eligible = (repository_replayed and kind in {
        "BUY_CANDIDATE", "ADD_CANDIDATE", "HOLD", "TRIM_CANDIDATE", "SELL_CANDIDATE"})
    protected = intent in ACTION_INTENTS
    if protected:
        blockers.append("VALUE_DECISION_REQUIRES_HUMAN_CONFIRMATION")
    formal_blockers = []
    if not repository_replayed:
        formal_blockers.append("VALUE_FRESH_REPOSITORY_REPLAY_REQUIRED")
    if intent in {"OPEN", "ADD"}:
        if not isinstance(verified_predecision, PreDecisionEligibility):
            formal_blockers.append("VALUE_VERIFIED_PREDECISION_REQUIRED")
        else:
            admission = verified_predecision
            if admission.symbol != symbol or admission.decision_as_of != decision_day:
                formal_blockers.append("VALUE_PREDECISION_IDENTITY_OR_DATE_MISMATCH")
            if admission.status != STATUS_ELIGIBLE or admission.blockers:
                formal_blockers.extend(admission.blockers)
                formal_blockers.append("VALUE_PREDECISION_G3_EVENT_MODEL_PRICE_GATE_NOT_PASSED")
            if not admission.positive_price_review_eligible:
                formal_blockers.append("VALUE_POSITIVE_PRICE_ADMISSION_REQUIRED")
        if (explanation.get("rule_evidence") or {}).get("full_buy_gate_passed") is not True:
            formal_blockers.append("VALUE_EXISTING_FULL_BUY_GATE_REQUIRED")
        if not comparable:
            formal_blockers.append("VALUE_PRICE_COMPARISON_NOT_ELIGIBLE")
        selected = conditions["entry" if intent == "OPEN" else "add"]
        if not policy_usable or not selected or selected.get("kind") != "POLICY_PRICE_REVIEW":
            formal_blockers.append("VALUE_APPLICABLE_ACTION_PRICE_POLICY_REQUIRED")
        elif selected.get("triggered") is not True:
            formal_blockers.append("VALUE_ACTION_PRICE_CONDITION_NOT_MET")
    elif intent == "HOLD":
        selected = conditions.get("hold")
        if not selected or selected.get("triggered") is not True:
            formal_blockers.append("VALUE_HOLD_THESIS_CONDITION_REQUIRED")
    elif intent in {"REDUCE", "EXIT"}:
        selected = conditions[intent.lower()]
        thesis = ((selected.get("thesis_review") or {})
                  if selected and selected.get("kind") == "POLICY_PRICE_REVIEW" else selected)
        thesis_triggered = (isinstance(thesis, dict) and thesis.get("kind") == "THESIS_REVIEW"
                            and thesis.get("triggered") is True)
        # An independent thesis review must not wait for an overvaluation price.
        if not selected or not (selected.get("triggered") is True or thesis_triggered):
            formal_blockers.append("VALUE_" + intent + "_THESIS_CONDITION_REQUIRED")
    else:
        formal_blockers.append("VALUE_ACTION_CANDIDATE_REQUIRED")
    formal_eligible = review_eligible and not formal_blockers
    state = "VALIDATION_PENDING" if protected else "WATCH"
    if not scenario_ready and not protected:
        state = "BLOCKED"
    qualification = "CONDITIONAL_PRICE_PLAN" if policy_usable else "RESEARCH_SCENARIO"
    if intent == "HOLD":
        qualification = "EXISTING_THESIS_HOLD_REVIEW"
    elif intent in {"REDUCE", "EXIT"}:
        qualification = "INDEPENDENT_THESIS_REVIEW"
    dependency_refs = explanation.get("decision_dependency_refs") or []
    input_version = next((ref.get("payload_sha256") for ref in dependency_refs
                          if ref.get("role") == "valuation"), None)
    payload = dict(schema_version=SCHEMA_VERSION, symbol=symbol,
        company_name=explanation.get("company_name", symbol), strategy="CORE_VALUE", sleeve="CORE_VALUE",
        research_as_of=research_day.isoformat(), research_version=explanation.get("research_version"),
        research_as_of_basis=("RESEARCH_CASE" if explanation.get("research_as_of") else "PUBLISHED_DECISION_CUTOFF"),
        decision_as_of=decision_day.isoformat(), valuation_date=valuation.get("valuation_date"),
        model_id=explanation.get("model_id") or validity.get("model_id"), model_type=valuation.get("model_type"),
        model_identity_evidence=deepcopy(explanation.get("model_identity_evidence")),
        model_version=valuation.get("model_version"), bear=values["bear"], base=values["base"], bull=values["bull"],
        profile_id=(price_context.get("price_attractiveness") or {}).get("profile_id"),
        valuation_input_version=input_version, scenario_validity=dict(status=valuation.get("status", "not_ready"),
            model_validity=validity_status, assumptions=deepcopy(valuation.get("assumptions")),
            confidence=valuation.get("confidence")),
        price_comparison_eligible=comparable, reference_close=quote.get("price"),
        market_trade_date=quote.get("quote_date"), reference_price_scope=quote.get("scope", "RETAINED_PRICE_BRIDGE"),
        safety_margin_policy=policy_view, **{action + "_condition": conditions[action] for action in ACTIONS},
        hold_condition=conditions.get("hold"),
        thesis=explanation.get("thesis"), thesis_invalidation=deepcopy(explanation.get("thesis_breakers") or []),
        supporting_facts=deepcopy(explanation.get("support") or []),
        counter_evidence=deepcopy(explanation.get("counter_evidence") or []),
        next_observation=deepcopy(explanation.get("next_events") or []),
        evidence_refs=deepcopy(explanation.get("evidence_refs") or []),
        source_bindings=deepcopy(list(source_bindings)), blockers=list(dict.fromkeys(blockers)),
        required_confirmations=list(dict.fromkeys(blockers)),
        action_intent=intent, candidate_action=kind, signal_state=state, qualification=qualification,
        security_review_eligible=review_eligible, formal_eligibility=formal_eligible,
        formal_eligibility_scope="SECURITY_AUXILIARY_REVIEW_NOT_TRADE_AUTHORIZATION",
        formal_eligibility_blockers=list(dict.fromkeys(formal_blockers)),
        portfolio_eligibility=None, portfolio_eligibility_status="UNKNOWN_PRIVATE_INPUT_NOT_PROJECTED",
        requires_human_review=protected, position_guidance=None, action="no_order",
        model_or_rule_version=RULE_VERSION, valuation_recomputed=False, approval_changed=False,
        explanation=("已登记政策支持条件性价位，仍须完成现有研究、人工与组合门。" if policy_usable else
                     "保留真实研究估值；未登记适用投资价格政策，不能把估值情景称为建仓或退出价。"))
    payload["valuation_input_bindings"] = deepcopy([ref for ref in dependency_refs
        if ref.get("role") in {"research_case", "financial_facts", "valuation_assumptions", "valuation"}])
    for action in ACTIONS:
        payload[action + "_trigger_price"] = (conditions[action] or {}).get("price")
    payload["invalidation_price"] = None
    return ValueActionPlan(deepcopy(payload))
