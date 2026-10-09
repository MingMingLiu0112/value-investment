"""Build a fail-closed recommendation from already-evaluated research gates."""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from typing import Any, Mapping

from ...domain.decision.decision_recommendation import (
    ACTION_NO_ORDER,
    DecisionRecommendation,
    DECISION_RECOMMENDATION_SCHEMA,
    MarginOfSafety,
    PORTFOLIO_BLOCKED_PRIVATE_INPUT,
    PriceRange,
    RECOMMENDATION_BUY_CANDIDATE,
    RECOMMENDATION_NO_ACTION,
    ValuationRange,
    decision_input_fingerprint,
    recommendation_payload_fingerprint,
)
from ...domain.research.human_research_approval import (
    HumanResearchApprovalReceipt,
    resolve_human_research_approval,
)
from ...domain.research.research_case import ResearchCase
from ...event_materiality import EventMaterialityReview
from ...model_validity import ModelValidity, model_validity_identity_blockers
from ...pre_decision_eligibility import STATUS_ELIGIBLE, PreDecisionEligibility
from ...price_attractiveness import (
    STATUS_RESEARCH_ATTRACTIVE,
    PriceAttractivenessAssessment,
    price_attractiveness_binding_blockers,
)
from ...price_bridge import PriceBridgeResult, price_bridge_binding_blockers
from ...valuation_models.base import ValuationResult, merge_evidence_refs
from ...research_artifacts import (
    ARTIFACT_EVENT_MATERIALITY_REVIEW,
    ARTIFACT_FINANCIAL_FACTS,
    ARTIFACT_HUMAN_RESEARCH_APPROVAL,
    ARTIFACT_MODEL_VALIDITY,
    ARTIFACT_PRE_DECISION_ELIGIBILITY,
    ARTIFACT_PRICE_ATTRACTIVENESS,
    ARTIFACT_PRICE_BRIDGE,
    ARTIFACT_RESEARCH_CASE,
    ARTIFACT_RESEARCH_GATE,
    ARTIFACT_VALUATION_ASSUMPTIONS,
    ARTIFACT_VALUATION_RESULT,
    StoredResearchArtifact,
    canonicalize_artifact_payload,
)


DEPENDENCY_ARTIFACT_TYPES = {
    "research_case": ARTIFACT_RESEARCH_CASE,
    "financial_facts": ARTIFACT_FINANCIAL_FACTS,
    "research_gate": ARTIFACT_RESEARCH_GATE,
    "valuation_assumptions": ARTIFACT_VALUATION_ASSUMPTIONS,
    "valuation": ARTIFACT_VALUATION_RESULT,
    "model_validity": ARTIFACT_MODEL_VALIDITY,
    "price_bridge": ARTIFACT_PRICE_BRIDGE,
    "price_attractiveness": ARTIFACT_PRICE_ATTRACTIVENESS,
    "pre_decision": ARTIFACT_PRE_DECISION_ELIGIBILITY,
    "human_approval": ARTIFACT_HUMAN_RESEARCH_APPROVAL,
    "event_materiality": ARTIFACT_EVENT_MATERIALITY_REVIEW,
}


def _dependency_refs(
    artifacts: Mapping[str, StoredResearchArtifact] | None,
    *,
    values: Mapping[str, Any],
    symbol: str,
) -> tuple[dict[str, Any], ...]:
    if artifacts is None:
        return ()
    refs: list[dict[str, Any]] = []
    from ...research_artifact_codecs import artifact_payload

    for role, stored in artifacts.items():
        expected_type = DEPENDENCY_ARTIFACT_TYPES.get(role)
        if expected_type is None:
            raise ValueError(f"Unknown decision dependency role: {role}")
        if not isinstance(stored, StoredResearchArtifact):
            raise TypeError(f"Decision dependency {role} must be a stored artifact")
        identity = stored.envelope.identity
        if identity.artifact_type != expected_type:
            raise ValueError(
                f"Decision dependency {role} has wrong artifact type"
            )
        if identity.scope_key != symbol:
            raise ValueError(f"Decision dependency {role} has wrong security")
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


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def build_decision_recommendation(
    *,
    run_id: str,
    research_case: ResearchCase,
    valuation: ValuationResult,
    model_validity: ModelValidity | None,
    price_bridge: PriceBridgeResult,
    price_attractiveness: PriceAttractivenessAssessment,
    pre_decision: PreDecisionEligibility | None,
    human_approval: HumanResearchApprovalReceipt | None = None,
    model_id: str | None = None,
    research_case_payload: Mapping[str, Any] | None = None,
    facts_payload: Mapping[str, Any] | None = None,
    assumptions_payload: Mapping[str, Any] | None = None,
    dependency_artifacts: Mapping[str, StoredResearchArtifact] | None = None,
    event_materiality: EventMaterialityReview | None = None,
    decision_as_of: date | None = None,
    additional_blockers: tuple[str, ...] = (),
    schema_version: str = DECISION_RECOMMENDATION_SCHEMA,
) -> DecisionRecommendation:
    """Summarize existing decisions without recomputing valuation or price rules."""
    if not (
        research_case.symbol
        == valuation.symbol
        == price_bridge.symbol
        == price_attractiveness.symbol
    ):
        raise ValueError("Decision inputs must share one symbol")
    if model_validity is not None and model_validity.symbol != valuation.symbol:
        raise ValueError("Model validity symbol does not match valuation")
    if pre_decision is not None and pre_decision.symbol != valuation.symbol:
        raise ValueError("Predecision eligibility symbol does not match valuation")
    if human_approval is not None and human_approval.symbol != valuation.symbol:
        raise ValueError("Human approval symbol does not match valuation")
    if event_materiality is not None and event_materiality.symbol != valuation.symbol:
        raise ValueError("Event materiality symbol does not match valuation")
    dependency_refs = _dependency_refs(
        dependency_artifacts,
        values={
            "research_case": research_case,
            "valuation": valuation,
            "model_validity": model_validity,
            "price_bridge": price_bridge,
            "price_attractiveness": price_attractiveness,
            "pre_decision": pre_decision,
            "human_approval": human_approval,
            "event_materiality": event_materiality,
        },
        symbol=valuation.symbol,
    )
    dependency_roles = {ref["role"] for ref in dependency_refs}
    effective_decision_as_of = (
        decision_as_of
        or (pre_decision.decision_as_of if pre_decision is not None else None)
        or research_case.as_of
    )
    if not isinstance(effective_decision_as_of, date) or isinstance(
        effective_decision_as_of, datetime
    ):
        raise ValueError("Decision as-of must be a date")

    identity_blockers: list[str] = []
    if research_case.as_of > effective_decision_as_of:
        identity_blockers.append("research_case_as_of_after_decision")
    if valuation.valuation_date > effective_decision_as_of:
        identity_blockers.append("valuation_date_after_decision")
    if model_validity is not None and model_validity.model_as_of > effective_decision_as_of:
        identity_blockers.append("model_validity_as_of_after_decision")
    if price_bridge.quote_date is not None and price_bridge.quote_date > effective_decision_as_of:
        identity_blockers.append("quote_date_after_decision")
    if (
        pre_decision is not None
        and pre_decision.decision_as_of != effective_decision_as_of
    ):
        identity_blockers.append("predecision_date_does_not_match_decision")
    if (
        human_approval is not None
        and human_approval.review_as_of > effective_decision_as_of
    ):
        identity_blockers.append("human_approval_after_decision")
    if (
        event_materiality is not None
        and event_materiality.review_as_of > effective_decision_as_of
    ):
        identity_blockers.append("event_review_after_decision")

    approval_decision = None
    approval_blockers: list[str] = []
    if human_approval is None:
        approval_blockers.append("human_research_approval_not_resolved")
    elif (
        not model_id
        or research_case_payload is None
        or facts_payload is None
        or assumptions_payload is None
    ):
        approval_blockers.append("human_research_approval_dependencies_unavailable")
    else:
        approval_decision = resolve_human_research_approval(
            human_approval,
            valuation,
            model_id=model_id,
            research_case_payload=research_case_payload,
            facts_payload=facts_payload,
            assumptions_payload=assumptions_payload,
        )
        approval_blockers.extend(approval_decision.blockers)

    binding_blockers = price_bridge_binding_blockers(valuation, price_bridge)
    validity_identity_blockers = (
        model_validity_identity_blockers(model_validity, valuation)
        if model_validity is not None
        else ()
    )
    attractiveness_binding_blockers = price_attractiveness_binding_blockers(
        valuation,
        price_bridge,
        price_attractiveness,
    )
    state_blockers: list[str] = []
    if research_case.blockers:
        state_blockers.extend(
            f"research_case:{blocker}" for blocker in research_case.blockers
        )
    if valuation.blockers:
        state_blockers.extend(
            f"valuation:{blocker}" for blocker in valuation.blockers
        )
    if research_case.evidence_status != "verified":
        state_blockers.append("research_evidence_not_verified")
    if research_case.research_status != "financial_scope_approved":
        state_blockers.append("research_scope_not_approved")
    approval_eligible = (
        approval_decision is not None
        and approval_decision.approved
        and approval_decision.price_assessment_eligible
        and not approval_decision.blockers
    )
    if research_case.valuation_status not in {
        "approved", "approved_low_confidence",
    } and not approval_eligible:
        state_blockers.append("research_case_valuation_not_approved")
    if valuation.status not in {"approved_research_only", "ready"} and not (
        valuation.status == "conditional_research_only" and approval_eligible
    ):
        state_blockers.append("valuation_status_not_approved_for_research")
    if model_validity is None:
        state_blockers.append("model_validity_unavailable")
    elif model_validity.status != "VALID":
        state_blockers.append(f"model_validity_{model_validity.status.lower()}")
    if price_bridge.bridge_status != "READY":
        state_blockers.append(
            f"price_bridge_{price_bridge.bridge_status.lower()}"
        )
    if event_materiality is None:
        state_blockers.append("event_materiality_review_unavailable")
    elif not event_materiality.covers(effective_decision_as_of):
        state_blockers.append("event_review_watermark_not_current")
    required_roles = {
        "research_case", "valuation", "price_bridge", "price_attractiveness",
        "pre_decision", "event_materiality", "human_approval",
    }
    if required_roles - dependency_roles:
        state_blockers.append("decision_dependency_artifacts_unavailable")

    blockers = tuple(
        dict.fromkeys(
            [
                *additional_blockers,
                *state_blockers,
                *identity_blockers,
                *(
                    pre_decision.blockers
                    if pre_decision is not None
                    else ("predecision_eligibility_unavailable",)
                ),
                *(model_validity.blockers if model_validity is not None else ()),
                *(price_bridge.blockers),
                *(price_attractiveness.blockers),
                *binding_blockers,
                *validity_identity_blockers,
                *attractiveness_binding_blockers,
                *(human_approval.remaining_blockers if human_approval is not None else ()),
                *approval_blockers,
                *(
                    event_materiality.review_blockers
                    if event_materiality is not None
                    else ("event_materiality_review_unavailable",)
                ),
            ]
        )
    )
    positive = (
        pre_decision is not None
        and pre_decision.status == STATUS_ELIGIBLE
        and pre_decision.positive_price_review_eligible
        and price_attractiveness.status == STATUS_RESEARCH_ATTRACTIVE
        and price_attractiveness.confidence != "低"
        and model_validity is not None
        and model_validity.status == "VALID"
        and price_bridge.bridge_status == "READY"
        and not binding_blockers
        and not validity_identity_blockers
        and not attractiveness_binding_blockers
        and approval_decision is not None
        and approval_decision.approved
        and approval_decision.price_assessment_eligible
        and event_materiality is not None
        and event_materiality.covers(effective_decision_as_of)
        and not identity_blockers
        and not state_blockers
        and not blockers
    )
    recommendation_action = (
        RECOMMENDATION_BUY_CANDIDATE if positive else RECOMMENDATION_NO_ACTION
    )
    if positive:
        reasons = (
            "predecision_eligible",
            "price_assessment_research_attractive",
            "model_validity_valid",
            "price_bridge_ready",
        )
        entry_zone = PriceRange(
            low=valuation.bear_value,
            high=valuation.base_value,
            basis="approved_research_value_band_not_execution_threshold",
        )
    else:
        reasons = blockers or ("no_positive_gate_combination",)
        entry_zone = None

    exit_conditions = tuple(
        text
        for item in research_case.thesis_breakers
        if (text := _optional_text(item.get("text"))) is not None
    )
    evidence_refs = merge_evidence_refs(
        research_case.evidence_refs,
        valuation.evidence_refs,
        model_validity.evidence_refs if model_validity is not None else (),
        price_bridge.evidence_refs,
        price_bridge.quote_evidence_refs,
        price_attractiveness.evidence_refs,
        pre_decision.evidence_refs if pre_decision is not None else (),
        human_approval.evidence_refs if human_approval is not None else (),
        event_materiality.evidence_refs if event_materiality is not None else (),
    )
    model_validity_payload: dict[str, Any] = {
        "status": model_validity.status if model_validity is not None else "UNKNOWN",
        "model_id": model_validity.model_id if model_validity is not None else None,
        "model_as_of": (
            model_validity.model_as_of.isoformat()
            if model_validity is not None
            else None
        ),
        "valid_from": (
            model_validity.valid_from.isoformat()
            if model_validity is not None
            else None
        ),
        "last_material_event_check": (
            model_validity.last_material_event_check.isoformat()
            if model_validity is not None
            and model_validity.last_material_event_check is not None
            else None
        ),
        "blockers": list(model_validity.blockers) if model_validity is not None else [],
    }
    recommendation = DecisionRecommendation(
        symbol=valuation.symbol,
        run_id=run_id,
        decision_as_of=effective_decision_as_of,
        recommendation_action=recommendation_action,
        confidence=valuation.confidence,
        valuation_range=ValuationRange(
            bear=valuation.bear_value,
            base=valuation.base_value,
            bull=valuation.bull_value,
        ),
        current_price=price_bridge.current_price,
        margin_of_safety=MarginOfSafety(
            to_bear=price_bridge.margin_to_bear,
            to_base=price_bridge.margin_to_base,
        ),
        entry_zone=entry_zone,
        reduce_zone=None,
        exit_conditions=exit_conditions,
        thesis=research_case.thesis,
        counter_evidence=tuple(dict(item) for item in research_case.counter_evidence),
        thesis_breakers=tuple(dict(item) for item in research_case.thesis_breakers),
        next_events=tuple(dict(item) for item in research_case.next_events),
        evidence_refs=tuple(evidence_refs),
        model_validity=model_validity_payload,
        price_bridge_status=price_bridge.bridge_status,
        price_attractiveness_status=price_attractiveness.status,
        recommendation_reasons=tuple(reasons),
        blockers=blockers,
        portfolio_input_status=PORTFOLIO_BLOCKED_PRIVATE_INPUT,
        position_guidance=None,
        action=ACTION_NO_ORDER,
        schema_version=schema_version,
        decision_input_sha256=decision_input_fingerprint(
            research_case=research_case,
            valuation=valuation,
            model_validity=model_validity,
            price_bridge=price_bridge,
            price_attractiveness=price_attractiveness,
            pre_decision=pre_decision,
            human_approval=human_approval,
            event_materiality=event_materiality,
            decision_as_of=effective_decision_as_of,
            model_id=model_id,
            research_case_payload=research_case_payload,
            facts_payload=facts_payload,
            assumptions_payload=assumptions_payload,
            additional_blockers=tuple(additional_blockers),
        ),
        input_model_id=model_id,
        input_additional_blockers=tuple(additional_blockers),
        decision_dependency_refs=dependency_refs,
    )
    return replace(
        recommendation,
        recommendation_payload_sha256=recommendation_payload_fingerprint(
            recommendation.as_policy()
        ),
    )


__all__ = ["build_decision_recommendation"]
