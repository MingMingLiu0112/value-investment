"""Synthetic repository replay contracts for optional auxiliary input presence.

No real research approval, model execution or company admission is asserted here.
"""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from itertools import product
import json

import pytest

from test_decision_recommendation import AS_OF, MODEL_ID, SYMBOL, _dependencies, _stored_dependencies
from test_research_input import _assumptions, _facts
from value_investment_agent.application.decision.artifact_bundle import (
    ReadOnlyArtifactBundleRepository,
    export_artifact_bundle,
)
from value_investment_agent.application.decision.build_decision_recommendation import (
    build_decision_recommendation,
)
from value_investment_agent.application.decision.restore_decision_recommendation import (
    restore_decision_recommendation,
)
from value_investment_agent.domain.decision.decision_recommendation import (
    DECISION_RECOMMENDATION_SCHEMA,
    LEGACY_DECISION_RECOMMENDATION_SCHEMA,
    recommendation_payload_fingerprint,
)
from value_investment_agent.research_artifact_codecs import artifact_payload
from value_investment_agent.research_artifacts import (
    ARTIFACT_DECISION_RECOMMENDATION,
    ARTIFACT_FINANCIAL_FACTS,
    ARTIFACT_RESEARCH_GATE,
    ARTIFACT_VALUATION_ASSUMPTIONS,
    ResearchArtifactEnvelope,
    ResearchArtifactIdentity,
    StoredResearchArtifact,
)
from value_investment_agent.research_gate import evaluate


SCHEMAS = [LEGACY_DECISION_RECOMMENDATION_SCHEMA, DECISION_RECOMMENDATION_SCHEMA]
AUX_FIELDS = ("research_case_payload", "facts_payload", "assumptions_payload")
PRESENCE = list(product((False, True), repeat=len(AUX_FIELDS)))
AVAILABLE_AT = datetime(2026, 9, 22, tzinfo=timezone.utc)


def _stored(artifact_id, artifact_type, payload):
    return StoredResearchArtifact(
        artifact_id=artifact_id,
        envelope=ResearchArtifactEnvelope.build(
            identity=ResearchArtifactIdentity(
                scope_type="security", scope_key=SYMBOL,
                artifact_type=artifact_type, schema_version="research-artifact-v1",
                as_of=AS_OF, available_at=AVAILABLE_AT,
            ),
            payload=payload, run_id="synthetic-optional-payload-replay",
        ),
        created_at=AVAILABLE_AT,
    )


@pytest.fixture
def replay_inputs():
    dependencies = _dependencies()
    dependencies["research_case"] = replace(
        dependencies["research_case"], name="SYNTHETIC_REPLAY_TEST_ONLY",
        run_id="synthetic-optional-payload-replay", research_version="synthetic-replay-v1",
    )
    dependencies.pop("human_approval")
    dependencies.pop("pre_decision")
    stored = _stored_dependencies(dependencies)
    facts = replace(_facts(), symbol=SYMBOL, as_of=AS_OF)
    assumptions = _assumptions()
    assumptions = replace(
        assumptions, symbol=SYMBOL, as_of=AS_OF,
        assumptions=[replace(item, as_of=AS_OF) for item in assumptions.assumptions],
    )
    for role, value in (
        ("financial_facts", facts),
        ("valuation_assumptions", assumptions),
        ("research_gate", evaluate(dependencies["research_case"])),
    ):
        artifact_type, payload = artifact_payload(value)
        stored[role] = _stored("synthetic-" + role, artifact_type, payload)
    assert stored["financial_facts"].envelope.identity.artifact_type == ARTIFACT_FINANCIAL_FACTS
    assert stored["valuation_assumptions"].envelope.identity.artifact_type == ARTIFACT_VALUATION_ASSUMPTIONS
    assert stored["research_gate"].envelope.identity.artifact_type == ARTIFACT_RESEARCH_GATE
    auxiliary = {
        "research_case_payload": stored["research_case"].envelope.payload_object(),
        "facts_payload": stored["financial_facts"].envelope.payload_object(),
        "assumptions_payload": stored["valuation_assumptions"].envelope.payload_object(),
    }
    return dependencies, stored, auxiliary


def _build(inputs, schema, presence, *, auxiliary_override=None):
    dependencies, stored, auxiliary = inputs
    auxiliary = auxiliary if auxiliary_override is None else auxiliary_override
    return build_decision_recommendation(
        run_id="synthetic-optional-payload-replay",
        research_case=dependencies["research_case"], valuation=dependencies["valuation"],
        model_validity=dependencies["model_validity"], price_bridge=dependencies["price_bridge"],
        price_attractiveness=dependencies["price_attractiveness"],
        pre_decision=None, human_approval=None, model_id=MODEL_ID,
        event_materiality=dependencies["event_materiality"], decision_as_of=AS_OF,
        dependency_artifacts=stored, schema_version=schema,
        **{field: auxiliary[field] if present else None
           for field, present in zip(AUX_FIELDS, presence)},
    )


def _bundle(stored, payload):
    decision = _stored("synthetic-decision", ARTIFACT_DECISION_RECOMMENDATION, payload)
    bundle = export_artifact_bundle([*stored.values(), decision])
    # A cold repository has only the portable JSON evidence, never caller objects.
    portable = json.loads(json.dumps(bundle, ensure_ascii=False))
    return ReadOnlyArtifactBundleRepository(portable), portable, decision


@pytest.mark.parametrize("schema", SCHEMAS, ids=["v1", "v2"])
@pytest.mark.parametrize("presence", PRESENCE, ids=[
    "none", "assumptions", "facts", "facts-assumptions",
    "case", "case-assumptions", "case-facts", "all",
])
def test_unapproved_bundle_restores_exact_optional_presence_and_legacy_output(
    replay_inputs, schema, presence,
):
    recommendation = _build(replay_inputs, schema, presence)
    payload = recommendation.as_policy()
    assert recommendation.recommendation_action == "NO_ACTION"
    assert "human_research_approval_not_resolved" in recommendation.blockers
    assert recommendation.action == "no_order"
    assert recommendation.position_guidance is None
    assert recommendation.portfolio_input_status == "BLOCKED_PRIVATE_INPUT"
    classification = "recommendation_action" if schema == SCHEMAS[0] else "recommendation_type"
    assert payload[classification] == "NO_ACTION"
    assert ("recommendation_type" if schema == SCHEMAS[0] else "recommendation_action") not in payload
    repository, bundle, decision = _bundle(replay_inputs[1], payload)
    original_bundle = deepcopy(bundle)
    restored = restore_decision_recommendation(repository, artifact_id=decision.artifact_id)
    assert restored.recommendation.as_policy() == payload
    assert restored.recommendation.decision_input_sha256 == recommendation.decision_input_sha256
    assert restored.recommendation.recommendation_payload_sha256 == recommendation.recommendation_payload_sha256
    assert restored.recommendation_artifact.envelope.canonical_payload == decision.envelope.canonical_payload
    assert restored.verification["repository_replay"] is True
    assert restored.verification["semantic_revalidation"] is True
    assert "human_approval" not in restored.dependencies
    assert {"research_case", "financial_facts", "valuation_assumptions", "research_gate",
            "valuation", "model_validity", "price_bridge", "price_attractiveness",
            "event_materiality"} <= set(restored.dependencies)
    assert bundle == original_bundle


@pytest.mark.parametrize("schema", SCHEMAS, ids=["v1", "v2"])
def test_unmatched_input_fingerprint_rejected_even_with_valid_outer_hashes(replay_inputs, schema):
    payload = _build(replay_inputs, schema, (True, True, True)).as_policy()
    payload["decision_input_sha256"] = "0" * 64
    payload["recommendation_payload_sha256"] = recommendation_payload_fingerprint(payload)
    repository, _, decision = _bundle(replay_inputs[1], payload)
    assert decision.envelope.verify_payload() == decision.envelope.payload_sha256
    with pytest.raises(ValueError, match="fingerprint|repository replay"):
        restore_decision_recommendation(repository, artifact_id=decision.artifact_id)


@pytest.mark.parametrize("schema", SCHEMAS, ids=["v1", "v2"])
def test_matching_input_fingerprint_still_requires_complete_rebuild(replay_inputs, schema):
    payload = _build(replay_inputs, schema, (True, False, True)).as_policy()
    original_input_hash = payload["decision_input_sha256"]
    payload["recommendation_reasons"].append("SYNTHETIC_FORGED_REASON")
    payload["recommendation_payload_sha256"] = recommendation_payload_fingerprint(payload)
    repository, _, decision = _bundle(replay_inputs[1], payload)
    assert payload["decision_input_sha256"] == original_input_hash
    assert decision.envelope.verify_payload() == decision.envelope.payload_sha256
    with pytest.raises(ValueError, match="full repository replay"):
        restore_decision_recommendation(repository, artifact_id=decision.artifact_id)


@pytest.mark.parametrize("schema", SCHEMAS, ids=["v1", "v2"])
@pytest.mark.parametrize("field, role", [
    ("facts_payload", "financial_facts"),
    ("assumptions_payload", "valuation_assumptions"),
])
@pytest.mark.parametrize("mutation", ["caller_payload", "dependency_artifact"])
def test_wrong_auxiliary_payload_cannot_be_recovered_by_presence_search(
    replay_inputs, schema, field, role, mutation,
):
    changed = deepcopy(replay_inputs[2])
    if field == "facts_payload":
        changed[field]["operating_inputs"]["start_book_equity"] = "1001"
    else:
        changed[field]["assumptions"][0]["rationale"] = "SYNTHETIC_CHANGED_ASSUMPTION"
    if mutation == "caller_payload":
        # Original decision fingerprints a payload absent from its dependency bundle.
        payload = _build(replay_inputs, schema, (True, True, True),
                         auxiliary_override=changed).as_policy()
        stored = replay_inputs[1]
    else:
        # Reseal the replacement dependency and its ref, keeping the original input hash.
        payload = _build(replay_inputs, schema, (True, True, True)).as_policy()
        stored = dict(replay_inputs[1])
        previous = stored[role]
        stored[role] = _stored(previous.artifact_id, previous.envelope.identity.artifact_type,
                               changed[field])
        for reference in payload["decision_dependency_refs"]:
            if reference["role"] == role:
                reference["payload_sha256"] = stored[role].envelope.payload_sha256
        payload["recommendation_payload_sha256"] = recommendation_payload_fingerprint(payload)
    repository, _, decision = _bundle(stored, payload)
    assert decision.envelope.verify_payload() == decision.envelope.payload_sha256
    assert repository.load_by_id(stored[role].artifact_id).envelope.verify_payload() == stored[role].envelope.payload_sha256
    with pytest.raises(ValueError, match="fingerprint|repository replay"):
        restore_decision_recommendation(repository, artifact_id=decision.artifact_id)
