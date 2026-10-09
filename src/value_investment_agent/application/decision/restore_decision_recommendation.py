"""Repository-backed restoration for auditable decision recommendations.

Restoration never trusts caller-supplied dependency objects. It resolves the
exact stored artifacts referenced by the recommendation, verifies their hashes,
re-runs semantic checks, rebuilds the recommendation, and requires an exact
payload match.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Any, Mapping

from ...domain.decision.decision_recommendation import (
    DECISION_RECOMMENDATION_V3_SCHEMA,
    DecisionRecommendation,
    ENTRY_REQUIRED_ACTIONS,
    RECOMMENDATION_ADD_CANDIDATE,
    RECOMMENDATION_BUY_CANDIDATE,
    RECOMMENDATION_HOLD,
    RECOMMENDATION_NO_ACTION,
    RECOMMENDATION_SELL_CANDIDATE,
    RECOMMENDATION_TRIM_CANDIDATE,
    decision_input_fingerprint,
    decision_recommendation_from_payload,
)
from ...domain.decision.recommendation_rules import RecommendationRuleInputs
from ...pre_decision_eligibility import evaluate_pre_decision_eligibility
from ...research_artifact_codecs import decode_artifact
from ...research_artifact_repository import ResearchArtifactRepository
from ...research_artifacts import (
    ARTIFACT_DECISION_RECOMMENDATION,
    ARTIFACT_EVENT_MATERIALITY_REVIEW,
    ARTIFACT_FINANCIAL_FACTS,
    ARTIFACT_HUMAN_RESEARCH_APPROVAL,
    ARTIFACT_MODEL_VALIDITY,
    ARTIFACT_PRE_DECISION_ELIGIBILITY,
    ARTIFACT_PRICE_ATTRACTIVENESS,
    ARTIFACT_PRICE_BRIDGE,
    ARTIFACT_RESEARCH_CASE,
    ARTIFACT_RESEARCH_GATE,
    ARTIFACT_ENTRY_THESIS_SNAPSHOT,
    ARTIFACT_INVESTMENT_CONSISTENCY_REVIEW,
    ARTIFACT_VALUATION_ASSUMPTIONS,
    ARTIFACT_VALUATION_RESULT,
    StoredResearchArtifact,
)
from .build_decision_recommendation import build_decision_recommendation
from .build_advisory_decision_recommendation_v3 import (
    build_advisory_decision_recommendation_v3,
)


CANONICAL_DEPENDENCY_TYPES = {
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
    "entry_thesis": ARTIFACT_ENTRY_THESIS_SNAPSHOT,
    "investment_consistency_review": ARTIFACT_INVESTMENT_CONSISTENCY_REVIEW,
}

BASE_REQUIRED_ROLES = frozenset(
    {
        "research_case",
        "financial_facts",
        "research_gate",
        "valuation",
        "price_bridge",
        "price_attractiveness",
    }
)


def _required_roles(recommendation: DecisionRecommendation) -> frozenset[str]:
    if recommendation.schema_version != DECISION_RECOMMENDATION_V3_SCHEMA:
        return BASE_REQUIRED_ROLES
    required = {
        "research_case",
        "financial_facts",
        "research_gate",
        "valuation",
    }
    action = recommendation.recommendation_action
    if action in {
        RECOMMENDATION_ADD_CANDIDATE,
        RECOMMENDATION_HOLD,
        RECOMMENDATION_TRIM_CANDIDATE,
        RECOMMENDATION_SELL_CANDIDATE,
    }:
        required |= {
            "model_validity",
            "event_materiality",
            "entry_thesis",
            "investment_consistency_review",
        }
    if action == RECOMMENDATION_ADD_CANDIDATE:
        required |= {
            "price_bridge",
            "price_attractiveness",
            "pre_decision",
            "human_approval",
        }
    elif action == RECOMMENDATION_BUY_CANDIDATE:
        required |= {
            "model_validity",
            "event_materiality",
            "price_bridge",
            "price_attractiveness",
            "pre_decision",
            "human_approval",
        }
    elif action == RECOMMENDATION_NO_ACTION:
        # A v3 NO_ACTION may be produced when optional model/event inputs are
        # unavailable.  The builder then records only the dependencies it
        # actually used; replay must require the same contract instead of
        # inventing dependencies that were never emitted.
        pass
    return frozenset(required)


@dataclass(frozen=True)
class RestoredDecisionRecommendation:
    recommendation: DecisionRecommendation
    recommendation_artifact: StoredResearchArtifact | None
    dependencies: Mapping[str, StoredResearchArtifact]
    dependency_objects: Mapping[str, Any]
    verification: Mapping[str, Any]


def _load_reference(
    repository: ResearchArtifactRepository,
    *,
    symbol: str,
    reference: Mapping[str, Any],
) -> StoredResearchArtifact:
    role = str(reference["role"])
    expected_type = CANONICAL_DEPENDENCY_TYPES.get(role)
    if expected_type is None:
        raise ValueError(f"Unknown decision dependency role: {role}")
    stored = repository.load_by_id(str(reference["artifact_id"]))
    identity = stored.envelope.identity
    if identity.artifact_type != expected_type:
        raise ValueError(f"Decision dependency {role} artifact type changed")
    if identity.scope_key != symbol:
        raise ValueError(f"Decision dependency {role} belongs to another symbol")
    if identity.scope_type != "security":
        raise ValueError(f"Decision dependency {role} is not security-scoped")
    if stored.envelope.payload_sha256 != str(reference["payload_sha256"]):
        raise ValueError(f"Decision dependency {role} payload hash changed")
    if stored.envelope.verify_payload() != stored.envelope.payload_sha256:
        raise ValueError(f"Decision dependency {role} failed payload verification")
    return stored


def _decode_dependencies(
    dependencies: Mapping[str, StoredResearchArtifact],
) -> dict[str, Any]:
    objects: dict[str, Any] = {}
    ordered_roles = [
        role for role in ("valuation", "model_validity") if role in dependencies
    ] + [role for role in dependencies if role not in {"valuation", "model_validity"}]
    for role in ordered_roles:
        stored = dependencies[role]
        payload = stored.envelope.payload_object()
        if role == "price_bridge":
            valuation = objects.get("valuation")
            if valuation is None:
                raise ValueError("PriceBridge restoration requires valuation first")
            objects[role] = decode_artifact(
                stored.envelope.identity.artifact_type,
                payload,
                dependencies={"valuation": valuation},
            )
        else:
            objects[role] = decode_artifact(
                stored.envelope.identity.artifact_type,
                payload,
            )
    return objects


def _verify_predecision(
    recommendation: DecisionRecommendation,
    dependencies: Mapping[str, StoredResearchArtifact],
    objects: Mapping[str, Any],
) -> None:
    stored_predecision = objects.get("pre_decision")
    if stored_predecision is None:
        if (
            recommendation.schema_version == DECISION_RECOMMENDATION_V3_SCHEMA
            and recommendation.recommendation_action
            in {
                RECOMMENDATION_HOLD,
                RECOMMENDATION_TRIM_CANDIDATE,
                RECOMMENDATION_SELL_CANDIDATE,
            }
        ):
            return
        if recommendation.recommendation_action != "NO_ACTION":
            raise ValueError("Protected recommendation requires pre_decision")
        return
    required = (
        "research_gate",
        "valuation",
        "human_approval",
        "model_validity",
        "price_bridge",
        "event_materiality",
        "price_attractiveness",
    )
    missing = [role for role in required if role not in objects]
    if missing:
        raise ValueError(
            "Pre-decision restoration dependencies are incomplete: "
            + ", ".join(missing)
        )
    rebuilt = evaluate_pre_decision_eligibility(
        gate=objects["research_gate"],
        valuation=objects["valuation"],
        approval=objects["human_approval"],
        model_validity=objects["model_validity"],
        price_bridge=objects["price_bridge"],
        event_materiality=objects["event_materiality"],
        decision_as_of=recommendation.decision_as_of,
        model_id=str(recommendation.input_model_id or ""),
        research_case_payload=dependencies["research_case"].envelope.payload_object(),
        facts_payload=dependencies["financial_facts"].envelope.payload_object(),
        assumptions_payload=(
            dependencies["valuation_assumptions"].envelope.payload_object()
            if "valuation_assumptions" in dependencies
            else {}
        ),
        price_attractiveness=objects["price_attractiveness"],
    )
    if rebuilt.as_policy() != stored_predecision.as_policy():
        raise ValueError("Stored PreDecisionEligibility does not reproduce")


def _restore_optional_payload_inputs(
    recommendation: DecisionRecommendation,
    dependencies: Mapping[str, StoredResearchArtifact],
    objects: Mapping[str, Any],
) -> dict[str, Any]:
    payloads = {
        "research_case_payload": dependencies["research_case"].envelope.payload_object(),
        "facts_payload": dependencies["financial_facts"].envelope.payload_object(),
        "assumptions_payload": (
            dependencies["valuation_assumptions"].envelope.payload_object()
            if "valuation_assumptions" in dependencies else {}
        ),
    }
    # Legacy contracts seal optional payload presence in the input hash only.
    # Recover that exact presence, independently of whether approval was supplied.
    for present in product((False, True), repeat=len(payloads)):
        inputs = {key: value if keep else None
                  for (key, value), keep in zip(payloads.items(), present)}
        fingerprint = decision_input_fingerprint(
            research_case=objects["research_case"],
            valuation=objects["valuation"],
            model_validity=objects.get("model_validity"),
            price_bridge=objects.get("price_bridge"),
            price_attractiveness=objects.get("price_attractiveness"),
            pre_decision=objects.get("pre_decision"),
            human_approval=objects.get("human_approval"),
            event_materiality=objects.get("event_materiality"),
            decision_as_of=recommendation.decision_as_of,
            model_id=recommendation.input_model_id,
            additional_blockers=recommendation.input_additional_blockers,
            **inputs,
            include_d3_dependencies=(
                recommendation.schema_version == DECISION_RECOMMENDATION_V3_SCHEMA
            ),
            entry_thesis=objects.get("entry_thesis"),
            investment_consistency_review=objects.get(
                "investment_consistency_review"
            ),
        )
        if fingerprint == recommendation.decision_input_sha256:
            return inputs
    raise ValueError(
        "Decision recommendation failed full repository replay: input fingerprint mismatch"
    )


def verify_decision_recommendation_payload(
    repository: ResearchArtifactRepository,
    *,
    payload: Mapping[str, Any],
    recommendation_artifact: StoredResearchArtifact | None = None,
) -> RestoredDecisionRecommendation:
    """Rebuild one recommendation solely from repository-resolved dependencies."""
    data = dict(payload)
    if recommendation_artifact is not None:
        identity = recommendation_artifact.envelope.identity
        if identity.artifact_type != ARTIFACT_DECISION_RECOMMENDATION:
            raise ValueError("Decision artifact type changed")
        if recommendation_artifact.envelope.payload_object() != data:
            raise ValueError("Decision artifact payload differs from supplied recommendation")
        if recommendation_artifact.envelope.verify_payload() != recommendation_artifact.envelope.payload_sha256:
            raise ValueError("Decision artifact hash changed")
    recommendation = decision_recommendation_from_payload(
        data,
        verify_dependencies=False,
    )
    if not recommendation.decision_dependency_refs:
        raise ValueError("Canonical recommendation requires repository dependency refs")
    by_role: dict[str, StoredResearchArtifact] = {}
    for reference in recommendation.decision_dependency_refs:
        role = str(reference["role"])
        if role in by_role:
            raise ValueError(f"Duplicate decision dependency role: {role}")
        by_role[role] = _load_reference(
            repository,
            symbol=recommendation.symbol,
            reference=reference,
        )
    missing = _required_roles(recommendation) - set(by_role)
    if missing:
        raise ValueError(
            "Canonical recommendation dependency refs are incomplete: "
            + ", ".join(sorted(missing))
        )
    objects = _decode_dependencies(by_role)
    _verify_predecision(recommendation, by_role, objects)

    research_case = objects["research_case"]
    payload_inputs = _restore_optional_payload_inputs(recommendation, by_role, objects)
    if recommendation.schema_version == DECISION_RECOMMENDATION_V3_SCHEMA:
        if not recommendation.rule_evidence:
            raise ValueError("v3 recommendation restore requires rule evidence")
        rebuilt = build_advisory_decision_recommendation_v3(
            run_id=recommendation.run_id,
            research_case=research_case,
            valuation=objects["valuation"],
            model_validity=objects.get("model_validity"),
            price_bridge=objects.get("price_bridge"),
            price_attractiveness=objects.get("price_attractiveness"),
            pre_decision=objects.get("pre_decision"),
            human_approval=objects.get("human_approval"),
            entry_thesis=objects.get("entry_thesis"),
            investment_consistency_review=objects.get(
                "investment_consistency_review"
            ),
            rule_evidence=RecommendationRuleInputs(
                **recommendation.rule_evidence
            ),
            model_id=recommendation.input_model_id,
            **payload_inputs,
            event_materiality=objects.get("event_materiality"),
            decision_as_of=recommendation.decision_as_of,
            additional_blockers=recommendation.input_additional_blockers,
            dependency_artifacts=by_role,
        )
    else:
        rebuilt = build_decision_recommendation(
            run_id=recommendation.run_id,
            research_case=research_case,
            valuation=objects["valuation"],
            model_validity=objects.get("model_validity"),
            price_bridge=objects["price_bridge"],
            price_attractiveness=objects["price_attractiveness"],
            pre_decision=objects.get("pre_decision"),
            human_approval=objects.get("human_approval"),
            model_id=recommendation.input_model_id,
            **payload_inputs,
            event_materiality=objects.get("event_materiality"),
            decision_as_of=recommendation.decision_as_of,
            additional_blockers=recommendation.input_additional_blockers,
            dependency_artifacts=by_role,
            schema_version=recommendation.schema_version,
        )
    if rebuilt.as_policy() != data:
        raise ValueError("Decision recommendation failed full repository replay")
    return RestoredDecisionRecommendation(
        recommendation=rebuilt,
        recommendation_artifact=recommendation_artifact,
        dependencies=by_role,
        dependency_objects=objects,
        verification={
            "recommendation_artifact_id": (
                recommendation_artifact.artifact_id
                if recommendation_artifact is not None else None
            ),
            "recommendation_payload_sha256": (
                recommendation_artifact.envelope.payload_sha256
                if recommendation_artifact is not None else None
            ),
            "dependency_artifacts": [
                {
                    "role": role,
                    "artifact_id": item.artifact_id,
                    "payload_sha256": item.envelope.payload_sha256,
                }
                for role, item in sorted(by_role.items())
            ],
            "repository_replay": True,
            "semantic_revalidation": True,
        },
    )


def restore_decision_recommendation(
    repository: ResearchArtifactRepository,
    *,
    artifact_id: str,
) -> RestoredDecisionRecommendation:
    """Restore one recommendation exclusively from immutable repository rows."""
    stored = repository.load_by_id(artifact_id)
    if stored.envelope.identity.artifact_type != ARTIFACT_DECISION_RECOMMENDATION:
        raise ValueError("Requested artifact is not a decision recommendation")
    if stored.envelope.verify_payload() != stored.envelope.payload_sha256:
        raise ValueError("Decision recommendation payload hash changed")
    return verify_decision_recommendation_payload(
        repository,
        payload=stored.envelope.payload_object(),
        recommendation_artifact=stored,
    )


__all__ = [
    "BASE_REQUIRED_ROLES",
    "CANONICAL_DEPENDENCY_TYPES",
    "RestoredDecisionRecommendation",
    "restore_decision_recommendation",
    "verify_decision_recommendation_payload",
]
