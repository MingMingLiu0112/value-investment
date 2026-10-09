"""Build the D3 advisory action without weakening the frozen v2 contract."""
from __future__ import annotations

from datetime import date
from typing import Any, Mapping

from ...domain.decision.advisory_dependency_admission import (
    validate_advisory_dependencies,
)
from ...domain.decision.decision_recommendation import (
    ACTION_NO_ORDER,
    DECISION_RECOMMENDATION_V3_SCHEMA,
    DecisionRecommendation,
    ENTRY_REQUIRED_ACTIONS,
    MarginOfSafety,
    PORTFOLIO_BLOCKED_PRIVATE_INPUT,
    POSITIVE_ACTIONS,
    PriceRange,
    RECOMMENDATION_BUY_CANDIDATE,
    RECOMMENDATION_NO_ACTION,
    ValuationRange,
    decision_input_fingerprint,
)
from ...domain.decision.recommendation_rules import (
    RecommendationRuleInputs,
    evaluate_recommendation_action,
)
from ...domain.research.human_research_approval import HumanResearchApprovalReceipt
from ...domain.research.research_case import ResearchCase
from ...event_materiality import EventMaterialityReview
from ...investment_decision import (
    COMPARISON_BROKEN,
    COMPARISON_FULFILLED,
    COMPARISON_NEGATIVE,
    CONSISTENCY_STATUSES,
    EntryThesisSnapshot,
    InvestmentConsistencyReview,
)
from ...model_validity import ModelValidity
from ...pre_decision_eligibility import PreDecisionEligibility
from ...price_attractiveness import (
    STATUS_NOT_ASSESSABLE,
    PriceAttractivenessAssessment,
    infer_profile_id,
)
from ...price_bridge import PriceBridgeResult
from ...research_artifact_codecs import artifact_payload
from ...research_artifacts import (
    ARTIFACT_ENTRY_THESIS_SNAPSHOT,
    ARTIFACT_INVESTMENT_CONSISTENCY_REVIEW,
    StoredResearchArtifact,
    canonicalize_artifact_payload,
)
from ...valuation_models.base import ValuationResult, merge_evidence_refs
from .build_decision_recommendation import build_decision_recommendation


D3_DEPENDENCY_ARTIFACT_TYPES = {
    "entry_thesis": ARTIFACT_ENTRY_THESIS_SNAPSHOT,
    "investment_consistency_review": ARTIFACT_INVESTMENT_CONSISTENCY_REVIEW,
}

_RISK_REDUCTION_INDEPENDENT_BLOCKER_PREFIXES = (
    "price_",
    "quote_",
    "predecision_",
    "model_validity_",
)


def _risk_reduction_relevant_blockers(blockers: tuple[str, ...]) -> tuple[str, ...]:
    """Keep only blockers that must gate a thesis-based risk reduction.

    A TRIM/SELL review rests on the original entry thesis and the consistency
    review, so a missing quote, an unassessable price, an ineligible
    pre-decision gate, an unresolved human approval or a model-validity status
    must not silence it. Research-integrity blockers still gate the action, and
    every one of these blockers is still reported on the recommendation.
    """
    relevant: list[str] = []
    for blocker in blockers:
        normalized = blocker.strip().lower()
        if normalized.startswith(_RISK_REDUCTION_INDEPENDENT_BLOCKER_PREFIXES):
            continue
        if normalized.startswith("human_") or "research approval" in normalized:
            continue
        if normalized == "decision_dependency_artifacts_unavailable":
            continue
        if "price" in normalized or "quote" in normalized:
            continue
        relevant.append(blocker)
    return tuple(relevant)


def _extra_dependency_refs(
    artifacts: Mapping[str, StoredResearchArtifact] | None,
    *,
    values: Mapping[str, Any],
    symbol: str,
) -> tuple[dict[str, Any], ...]:
    if artifacts is None:
        return ()
    refs: list[dict[str, Any]] = []
    for role, expected_type in D3_DEPENDENCY_ARTIFACT_TYPES.items():
        stored = artifacts.get(role)
        if stored is None:
            continue
        if not isinstance(stored, StoredResearchArtifact):
            raise TypeError(f"Decision dependency {role} must be a stored artifact")
        identity = stored.envelope.identity
        if identity.artifact_type != expected_type:
            raise ValueError(f"Decision dependency {role} has wrong artifact type")
        if identity.scope_type != "security" or identity.scope_key != symbol:
            raise ValueError(f"Decision dependency {role} has wrong security scope")
        value = values.get(role)
        if value is not None:
            actual_type, actual_payload = artifact_payload(value)
            if actual_type != expected_type or canonicalize_artifact_payload(
                actual_payload
            ) != stored.envelope.canonical_payload:
                raise ValueError(f"Decision dependency {role} payload does not match input")
        refs.append(
            {
                "role": role,
                "artifact_id": stored.artifact_id,
                "artifact_type": identity.artifact_type,
                "scope_type": identity.scope_type,
                "scope_key": identity.scope_key,
                "payload_sha256": stored.envelope.payload_sha256,
            }
        )
    return tuple(refs)


def _entry_reason_present(values: tuple[str, ...]) -> bool:
    return any(str(value).strip() for value in values)


def _comparison_has_evidence(
    consistency_review: InvestmentConsistencyReview | None,
    impact: str,
) -> bool:
    """Require the exact comparison that supports an action to cite evidence."""
    return bool(
        consistency_review is not None
        and any(
            item.impact == impact and bool(item.evidence_refs)
            for item in consistency_review.comparisons
        )
    )


def _event_review_current(
    event_materiality: EventMaterialityReview | None,
    decision_as_of: date,
) -> bool:
    return (
        event_materiality is not None
        and event_materiality.covers(decision_as_of)
        and not event_materiality.review_blockers
    )


def derive_recommendation_rule_inputs(
    *,
    entry_thesis: EntryThesisSnapshot | None,
    consistency_review: InvestmentConsistencyReview | None,
    base_exit_conditions: tuple[str, ...] = (),
    base_positive: bool = False,
    model_validity_status: str = "UNKNOWN",
    event_review_current: bool = False,
    base_blockers: tuple[str, ...] = (),
) -> RecommendationRuleInputs:
    """Derive the complete D3 rule evidence from immutable dependencies."""
    blockers = _risk_reduction_relevant_blockers(tuple(base_blockers))
    if entry_thesis is None:
        return RecommendationRuleInputs(
            has_entry=False,
            full_buy_gate_passed=base_positive,
            event_review_current=event_review_current,
            model_validity_status=model_validity_status,
            blockers=blockers,
        )
    status = consistency_review.status if consistency_review is not None else None
    return RecommendationRuleInputs(
        has_entry=True,
        consistency_status=status,
        full_buy_gate_passed=base_positive,
        add_evidence_present=(
            status == "FULFILLED"
            and _comparison_has_evidence(
                consistency_review, COMPARISON_FULFILLED
            )
            and _entry_reason_present(entry_thesis.reasons_to_add)
        ),
        hold_logic_present=bool(entry_thesis.hold_logic.strip()),
        trim_reason_present=(
            status == "WEAKENED"
            and _entry_reason_present(entry_thesis.reasons_to_reduce)
            and _comparison_has_evidence(
                consistency_review, COMPARISON_NEGATIVE
            )
        ),
        sell_reason_present=(
            status == "BROKEN"
            and _entry_reason_present(entry_thesis.reasons_to_exit)
            and _comparison_has_evidence(
                consistency_review, COMPARISON_BROKEN
            )
        ),
        exit_condition_present=bool(
            _entry_reason_present(entry_thesis.reasons_to_exit)
            or _entry_reason_present(base_exit_conditions)
        ),
        event_review_current=event_review_current,
        model_validity_status=model_validity_status,
        blockers=blockers,
    )


def _no_quote_price_bridge(
    valuation: ValuationResult,
    model_validity: ModelValidity | None,
) -> PriceBridgeResult:
    """Represent a quote not yet obtained without inventing price evidence."""
    return PriceBridgeResult(
        symbol=valuation.symbol,
        valuation_date=valuation.valuation_date,
        quote_date=None,
        current_price=None,
        margin_to_bear=None,
        margin_to_base=None,
        model_validity_status=(
            model_validity.status if model_validity is not None else "UNKNOWN"
        ),
        quote_status="PENDING_EXTERNAL_DATA",
        bridge_status="PENDING_EXTERNAL_DATA",
        evidence_refs=[],
        quote_evidence_refs=[],
        blockers=["quote_unavailable"],
    )


def _no_quote_price_assessment(
    valuation: ValuationResult,
) -> PriceAttractivenessAssessment:
    """Bind a not-yet-assessable price state to the valuation without fake refs."""
    return PriceAttractivenessAssessment(
        symbol=valuation.symbol,
        profile_id=infer_profile_id(valuation) or "unassessed",
        status=STATUS_NOT_ASSESSABLE,
        margin_to_bear=None,
        margin_to_base=None,
        downside_reference=None,
        upside_reference=None,
        confidence=valuation.confidence,
        reasons=["current quote unavailable"],
        blockers=["quote_unavailable"],
        evidence_refs=[],
    )


def build_advisory_decision_recommendation_v3(
    *,
    run_id: str,
    research_case: ResearchCase,
    valuation: ValuationResult,
    model_validity: ModelValidity | None,
    price_bridge: PriceBridgeResult | None,
    price_attractiveness: PriceAttractivenessAssessment | None,
    pre_decision: PreDecisionEligibility | None,
    human_approval: HumanResearchApprovalReceipt | None = None,
    entry_thesis: EntryThesisSnapshot | None = None,
    investment_consistency_review: InvestmentConsistencyReview | None = None,
    rule_evidence: RecommendationRuleInputs | None = None,
    model_id: str | None = None,
    research_case_payload: Mapping[str, Any] | None = None,
    facts_payload: Mapping[str, Any] | None = None,
    assumptions_payload: Mapping[str, Any] | None = None,
    dependency_artifacts: Mapping[str, StoredResearchArtifact] | None = None,
    event_materiality: EventMaterialityReview | None = None,
    decision_as_of: date | None = None,
    additional_blockers: tuple[str, ...] = (),
) -> DecisionRecommendation:
    """Build one v3 recommendation from already-evaluated research contracts."""
    effective_price_bridge = price_bridge or _no_quote_price_bridge(
        valuation, model_validity
    )
    effective_price_attractiveness = (
        price_attractiveness or _no_quote_price_assessment(valuation)
    )
    base_dependency_artifacts = (
        {
            role: stored
            for role, stored in dependency_artifacts.items()
            if role not in D3_DEPENDENCY_ARTIFACT_TYPES
        }
        if dependency_artifacts is not None
        else None
    )
    base = build_decision_recommendation(
        run_id=run_id,
        research_case=research_case,
        valuation=valuation,
        model_validity=model_validity,
        price_bridge=effective_price_bridge,
        price_attractiveness=effective_price_attractiveness,
        pre_decision=pre_decision,
        human_approval=human_approval,
        model_id=model_id,
        research_case_payload=research_case_payload,
        facts_payload=facts_payload,
        assumptions_payload=assumptions_payload,
        dependency_artifacts=base_dependency_artifacts,
        event_materiality=event_materiality,
        decision_as_of=decision_as_of,
        additional_blockers=additional_blockers,
    )
    base_positive = base.recommendation_action == RECOMMENDATION_BUY_CANDIDATE
    model_status = base.model_validity.get("status", "UNKNOWN")
    event_current = _event_review_current(event_materiality, base.decision_as_of)
    validate_advisory_dependencies(
        symbol=valuation.symbol,
        decision_as_of=base.decision_as_of,
        recommendation_schema_version=DECISION_RECOMMENDATION_V3_SCHEMA,
        entry_thesis=entry_thesis,
        investment_consistency_review=investment_consistency_review,
    )
    rule_inputs = derive_recommendation_rule_inputs(
        entry_thesis=entry_thesis,
        consistency_review=investment_consistency_review,
        base_positive=base_positive,
        base_exit_conditions=tuple(base.exit_conditions),
        model_validity_status=str(model_status),
        event_review_current=event_current,
        base_blockers=tuple(base.blockers),
    )
    if rule_evidence is not None and rule_evidence != rule_inputs:
        raise ValueError(
            "rule evidence does not match the immutable decision dependencies"
        )
    rule_decision = evaluate_recommendation_action(rule_inputs)
    action = rule_decision.action
    # Price, pre-decision, approval and model-validity blockers never silence a
    # thesis-based action, but they must still be visible on the recommendation.
    reported_blockers = tuple(
        dict.fromkeys((*base.blockers, *rule_decision.blockers))
    )

    if action == RECOMMENDATION_BUY_CANDIDATE:
        entry_id = None
        consistency_status = None
        entry_zone = base.entry_zone
        reason_codes = rule_decision.reason_codes
    elif action in ENTRY_REQUIRED_ACTIONS:
        entry_id = entry_thesis.entry_id if entry_thesis is not None else None
        consistency_status = (
            investment_consistency_review.status
            if investment_consistency_review is not None
            else None
        )
        entry_zone = (
            PriceRange(
                low=valuation.bear_value,
                high=valuation.base_value,
                basis="approved_research_value_band_not_execution_threshold",
            )
            if action in POSITIVE_ACTIONS
            else None
        )
        reason_codes = rule_decision.reason_codes
    else:
        entry_id = entry_thesis.entry_id if entry_thesis is not None else None
        consistency_status = (
            investment_consistency_review.status
            if investment_consistency_review is not None
            else None
        )
        entry_zone = None
        reason_codes = rule_decision.reason_codes
    blockers = reported_blockers

    extra_refs = _extra_dependency_refs(
        dependency_artifacts,
        values={
            "entry_thesis": entry_thesis,
            "investment_consistency_review": investment_consistency_review,
        },
        symbol=valuation.symbol,
    )
    dependency_refs_by_role: dict[str, dict[str, Any]] = {}
    for reference in (*base.decision_dependency_refs, *extra_refs):
        role = str(reference["role"])
        if role in dependency_refs_by_role:
            raise ValueError(f"Duplicate decision dependency role: {role}")
        dependency_refs_by_role[role] = dict(reference)
    dependency_refs = tuple(dependency_refs_by_role.values())
    evidence_refs = merge_evidence_refs(
        base.evidence_refs,
        investment_consistency_review.evidence_refs
        if investment_consistency_review is not None else (),
    )
    decision_input_sha256 = decision_input_fingerprint(
        research_case=research_case,
        valuation=valuation,
        model_validity=model_validity,
        price_bridge=price_bridge,
        price_attractiveness=price_attractiveness,
        pre_decision=pre_decision,
        human_approval=human_approval,
        event_materiality=event_materiality,
        decision_as_of=base.decision_as_of,
        model_id=model_id,
        research_case_payload=research_case_payload,
        facts_payload=facts_payload,
        assumptions_payload=assumptions_payload,
        additional_blockers=tuple(additional_blockers),
        include_d3_dependencies=True,
        entry_thesis=entry_thesis,
        investment_consistency_review=investment_consistency_review,
    )
    return DecisionRecommendation(
        symbol=valuation.symbol,
        run_id=run_id,
        decision_as_of=base.decision_as_of,
        recommendation_action=action,
        confidence=base.confidence,
        valuation_range=ValuationRange(
            bear=valuation.bear_value,
            base=valuation.base_value,
            bull=valuation.bull_value,
        ),
        current_price=base.current_price,
        margin_of_safety=MarginOfSafety(
            to_bear=base.margin_of_safety.to_bear,
            to_base=base.margin_of_safety.to_base,
        ),
        entry_zone=entry_zone,
        reduce_zone=None,
        exit_conditions=base.exit_conditions,
        thesis=base.thesis,
        counter_evidence=base.counter_evidence,
        thesis_breakers=base.thesis_breakers,
        next_events=base.next_events,
        evidence_refs=tuple(evidence_refs),
        model_validity=base.model_validity,
        price_bridge_status=base.price_bridge_status,
        price_attractiveness_status=base.price_attractiveness_status,
        recommendation_reasons=tuple(reason_codes),
        blockers=tuple(dict.fromkeys(blockers)),
        requires_human_review=action != RECOMMENDATION_NO_ACTION,
        entry_id=entry_id,
        thesis_consistency_status=consistency_status,
        rule_evidence={
            "has_entry": rule_inputs.has_entry,
            "consistency_status": rule_inputs.consistency_status,
            "full_buy_gate_passed": rule_inputs.full_buy_gate_passed,
            "add_evidence_present": rule_inputs.add_evidence_present,
            "hold_logic_present": rule_inputs.hold_logic_present,
            "trim_reason_present": rule_inputs.trim_reason_present,
            "sell_reason_present": rule_inputs.sell_reason_present,
            "exit_condition_present": rule_inputs.exit_condition_present,
            "event_review_current": rule_inputs.event_review_current,
            "model_validity_status": rule_inputs.model_validity_status,
            "blockers": list(rule_inputs.blockers),
        },
        portfolio_input_status=PORTFOLIO_BLOCKED_PRIVATE_INPUT,
        position_guidance=None,
        action=ACTION_NO_ORDER,
        schema_version=DECISION_RECOMMENDATION_V3_SCHEMA,
        decision_input_sha256=decision_input_sha256,
        input_model_id=model_id,
        input_additional_blockers=tuple(additional_blockers),
        decision_dependency_refs=dependency_refs,
    )


__all__ = [
    "build_advisory_decision_recommendation_v3",
    "derive_recommendation_rule_inputs",
]
