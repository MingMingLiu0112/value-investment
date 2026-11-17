"""Integrated TEST_ONLY coverage for the frozen five-action plan contract."""
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from test_bound_draft_review_handoff import prepared
from test_bound_research_draft import bound_draft, write_binding
from test_d2_source_bound_package_contract import market_package, source_package
from test_pending_review_response import consume
from test_value_decision_explanation import synthetic_restored
from value_investment_agent.application.decision.value_action_plan import project_value_action_plan
from value_investment_agent.application.product.research_reviews import prepare_pending_review_response
from value_investment_agent.domain.decision.value_action_plan import ACTION_INTENTS
from value_investment_agent.infrastructure.evidence.trust_root_registry import trust_root_fingerprint


def test_bound_draft_test_only_signature_fails_closed_before_five_action_plan(prepared):
    root, package, _, _, prepared_result = prepared
    binding = prepared_result["candidate_binding"]
    path = root / binding["path"]
    response = prepare_pending_review_response(
        root=root, candidate_path=path, candidate_sha256=binding["sha256"],
    )
    assert response["whole_model_approval"] is None

    now = datetime.now(timezone.utc)
    reviewer = "SYNTHETIC_TEST_ONLY_FIVE_ACTION_REVIEWER"
    response.update(reviewer_id=reviewer, reviewed_at=now.isoformat())
    for group in response["groups"]:
        group.update(
            response="VERIFIED",
            response_reason="TEST_ONLY signature integration; not an economic approval.",
            confirmed_scope="TEST_ONLY exact bound-draft group fields only.",
        )

    key = Ed25519PrivateKey.generate()
    trust = dict(
        schema_version="research-review-transport-trust-root-v1",
        reviewer_id=reviewer,
        public_key=key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex(),
        scopes=["human_group_research"], symbols=[package["symbol"]],
        valid_from=(now - timedelta(days=1)).isoformat(),
        valid_until=(now + timedelta(days=1)).isoformat(),
    )
    registry_binding = write_binding(root, "SYNTHETIC_TEST_ONLY_five_action_registry.json", {
        "schema_version": "authorization-trust-root-registry-v1",
        "pinned_trust_root_sha256": [trust_root_fingerprint(trust)],
    })

    consumed = consume(dict(
        root=root, path=path, response=response, key=key, trust=trust,
        registry=root / registry_binding["path"],
    ), suffix="-SYNTHETIC-TEST-ONLY-five-action")
    assert consumed["schema_version"] == "pending-research-review-consumption-v1"
    assert consumed["action"] == "no_order"
    assert consumed["whole_model_review_present"] is False
    assert consumed["blockers"] == ["whole_model_review_missing"]
    assert consumed["research_admitted"] is False
    assert consumed["event_materiality_approved"] is False
    assert consumed["price_admitted"] is False
    assert consumed["position_guidance"] is None
    assert "review_packet_binding" not in consumed
    output = root / "runtime/response-consumed-SYNTHETIC-TEST-ONLY-five-action"
    assert not (output / "research-reviews.json").exists()
    assert not (output / "human-approval.json").exists()


@pytest.mark.parametrize("kind,intent,selected,qualification", [
    ("HOLD", "HOLD", "hold", "EXISTING_THESIS_HOLD_REVIEW"),
    ("TRIM_CANDIDATE", "REDUCE", "reduce", "INDEPENDENT_THESIS_REVIEW"),
    ("SELL_CANDIDATE", "EXIT", "exit", "INDEPENDENT_THESIS_REVIEW"),
])
def test_synthetic_repository_replay_projects_hold_reduce_exit(
        kind, intent, selected, qualification):
    restored = synthetic_restored(kind)
    assert restored.verification["repository_replay"] is True

    plan = project_value_action_plan(restored, evidence_scope="SYNTHETIC_TEST")
    assert plan["action_intent"] == intent
    assert plan["action_intent"] in ACTION_INTENTS
    assert plan["candidate_action"] == kind
    assert plan["security_review_eligible"] is True
    assert plan["formal_eligibility"] is True
    assert plan["formal_eligibility_blockers"] == []
    assert plan["qualification"] == qualification
    assert plan["requires_human_review"] is True
    assert "VALUE_DECISION_REQUIRES_HUMAN_CONFIRMATION" in plan["blockers"]
    assert plan["portfolio_eligibility"] is None
    assert plan["position_guidance"] is None
    assert plan["action"] == "no_order"

    entry = restored.dependency_objects["entry_thesis"]
    if selected == "hold":
        condition = plan["hold_condition"]
        assert condition["kind"] == "HOLD_THESIS"
        assert condition["reasoning"] == entry.hold_logic
    else:
        assert plan["hold_condition"] is None
        condition = plan[selected + "_condition"]
        assert condition["kind"] == "THESIS_REVIEW"
        assert condition["reasons"] == list(getattr(entry, "reasons_to_" + selected))
    assert condition["triggered"] is True
    assert condition["price"] is None
    assert condition["entry_id"] == entry.entry_id
    for other in {"hold", "reduce", "exit"} - {selected}:
        other_condition = plan["hold_condition"] if other == "hold" else plan[other + "_condition"]
        assert other_condition is None or other_condition["triggered"] is False
