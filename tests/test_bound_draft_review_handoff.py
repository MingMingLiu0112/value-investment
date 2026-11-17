"""Exact bound-input handoff uses real scheduling and review verification."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json

import pytest

from test_bound_research_draft import (
    bound_draft, market_package, source_package, publish, write_binding,
)
from value_investment_agent.application.product.bound_draft_review import (
    prepare_bound_draft_review_candidate, verify_bound_draft_review_candidate,
)
from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.application.product.pending_research_candidate import (
    verify_pending_research_candidate,
)
from value_investment_agent.application.product.research_review_wizard import (
    build_external_review_handoff,
)
from value_investment_agent.application.product.research_reviews import (
    prepare_pending_review_intake,
)
from value_investment_agent.application.product.user_research_workflow import (
    selected_review_candidate,
)
from value_investment_agent.m1_valuation_package_builder import build_descriptor


def _workflow(root, symbol, binding=None):
    return write_binding(root, "config/user-research-workflow-v1.json", {
        "schema_version": "user-research-workflow-v1", "action": "no_order",
        "review_candidates": {},
        "bound_draft_review_candidates": {symbol: binding} if binding else {},
    })


@pytest.fixture
def prepared(bound_draft):
    root, package, draft, now = bound_draft
    write_binding(root, "config/research-evidence-stop-ledger-v1.json", {
        "schema_version": "research-evidence-stop-ledger-v1", "stops": [],
    })
    result = prepare_bound_draft_review_candidate(
        root=root, symbol=package["symbol"], output_dir=root / "runtime/bound-review",
    )
    binding = result["candidate_binding"]
    _workflow(root, package["symbol"], binding)
    return root, package, draft, datetime.now(timezone.utc), result


def _handoff(prepared):
    root, package, _, _, _ = prepared
    return build_external_review_handoff(
        root=root, symbol=package["symbol"], now=datetime.now(timezone.utc), bound_draft=True,
    )


def _assert_not_ready(result):
    assert result["status"] == "NOT_READY"
    assert result["verification"]["approval_changed"] is False
    assert result["verification"]["research_admitted"] is False
    assert "commands" not in result
    assert "steps" not in result
    assert "unsigned_response" not in result


def test_exact_bound_candidate_real_scheduler_verifier_intake_and_handoff(prepared):
    root, package, draft, now, result = prepared
    binding = result["candidate_binding"]
    path = root / binding["path"]
    candidate = verify_pending_research_candidate(
        root=root, path=path, expected_sha256=binding["sha256"],
    )
    assert verify_bound_draft_review_candidate(
        root=root, symbol=package["symbol"], binding=binding, now=now,
    ) == candidate
    assert (path.parent / "package.json").read_bytes() == (
        root / draft["model_input_binding"]["package"]["path"]
    ).read_bytes()
    assert candidate["model_context"]["input_descriptor_sha256"] == (
        build_descriptor(package, root=root).input_sha256
    ) == draft["model_input_binding"]["input_sha256"]
    assert candidate["model_context_scope"] == "ACTUALLY_CONSUMED"
    assert candidate["schedule_gate"]["allowed"] is True
    assert candidate["schedule_gate"]["status"] == "ALLOW_NORMAL_RESEARCH"
    request = json.loads((path.parent / "schedule-request.json").read_bytes())
    assert request["research_question_id"] == "consumed_input_review_handoff"
    assert request["source_id"] == "LOCAL_VERIFIED_RESEARCH"
    assert request["new_evidence_ids"] == []
    assert request["reopen_condition_met"] is False
    assert not (root / "runtime/research-evidence-stop-consumptions").exists()
    assert not (root / "runtime/research-evidence-stop-resolutions").exists()
    for key in ("approval_changed", "research_admitted", "price_admitted",
                "canonical_written", "registered_current_case_changed"):
        assert candidate[key] is False
    assert candidate["position_guidance"] is None
    intake = prepare_pending_review_intake(
        root=root, candidate_path=path, candidate_sha256=binding["sha256"],
    )
    assert intake["status"] == "AWAITING_HUMAN_RESPONSES"
    assert intake["valuation_artifact_sha256"]
    assert {group["id"] for group in intake["groups"]} == {
        "CAPITAL_BASIS", "ECONOMIC_ASSUMPTIONS", "FINANCIAL_AND_EVENTS",
    }
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    handoff = _handoff(prepared)
    assert handoff["status"] == "EXTERNAL_SIGNATURE_REQUIRED"
    assert handoff["candidate_binding"] == binding
    assert handoff["model_context"] == candidate["model_context"]
    assert handoff["valuation_artifact_sha256"] == intake["valuation_artifact_sha256"]
    assert handoff["unsigned_response"]["reviewer_id"] is None
    assert handoff["verification"]["approval_changed"] is False
    assert handoff["verification"]["research_admitted"] is False
    assert handoff["position_guidance"] is None
    assert handoff["commands"]["draft_preview"]
    assert {p: p.read_bytes() for p in root.rglob("*") if p.is_file()} == before


@pytest.mark.parametrize("mutation", [
    "package-changed", "draft-changed", "predecessor", "missing-candidate",
    "candidate-changed", "source-absent",
])
def test_invalid_bound_handoff_has_no_signing_instructions(prepared, mutation):
    root, package, draft, _, result = prepared
    binding = result["candidate_binding"]
    if mutation == "package-changed":
        path = root / draft["model_input_binding"]["package"]["path"]
        path.write_bytes(path.read_bytes() + b"\n")
    elif mutation == "draft-changed":
        path = root / "artifacts/current/synthetic-bound/draft.json"
        path.write_bytes(path.read_bytes() + b"\n")
    elif mutation == "predecessor":
        successor = deepcopy(draft)
        successor["research_version"] = "SYNTHETIC_SUCCESSOR_SAME_ECONOMIC_INPUTS"
        publish(root, successor)
    elif mutation == "missing-candidate":
        _workflow(root, package["symbol"])
    elif mutation == "candidate-changed":
        path = root / binding["path"]
        path.write_bytes(path.read_bytes() + b"\n")
    else:
        (root / package["sources"][0]["local_path"]).unlink()
    _assert_not_ready(_handoff(prepared))


def test_missing_candidate_file_has_no_signing_instructions(prepared):
    root, _, _, _, result = prepared
    (root / result["candidate_binding"]["path"]).unlink()
    _assert_not_ready(_handoff(prepared))


@pytest.mark.parametrize("field", [
    "consumed_operating_inputs", "official_fact_anchors", "assumptions",
    "decision_blockers", "input_descriptor_sha256",
])
def test_rehashed_review_packet_must_match_verified_economics(prepared, field):
    root, package, _, _, result = prepared
    candidate_binding = result["candidate_binding"]
    candidate_path = root / candidate_binding["path"]
    packet_path = candidate_path.parent / "consumed-review.json"
    original_packet_sha = sha256_file(packet_path)
    packet = json.loads(packet_path.read_bytes())
    if field == "consumed_operating_inputs":
        packet[field]["start_book_equity"] = "999999"
    elif field == "official_fact_anchors":
        assert packet[field]
        packet[field][0]["source_value"] = "999999"
    elif field == "assumptions":
        assert packet[field]
        packet[field][0]["values"]["base"] = "0.99"
    elif field == "decision_blockers":
        assert packet[field]
        packet[field] = []
    else:
        packet[field] = "0" * 64
    packet_binding = write_binding(root, packet_path.relative_to(root).as_posix(), packet)
    assert packet_binding["sha256"] != original_packet_sha
    candidate = json.loads(candidate_path.read_bytes())
    old_binding = next(item for item in candidate["source_bindings"]
                       if item["path"] == packet_binding["path"])
    assert old_binding["sha256"] == original_packet_sha
    old_binding.update(packet_binding)
    rehashed_candidate = write_binding(root, candidate_binding["path"], candidate)
    assert rehashed_candidate["sha256"] != candidate_binding["sha256"]
    _workflow(root, package["symbol"], rehashed_candidate)
    # The generic hash-bound contract still accepts these consistently rehashed bytes.
    verify_pending_research_candidate(
        root=root, path=candidate_path, expected_sha256=rehashed_candidate["sha256"],
    )
    with pytest.raises(ValueError, match="packet differs from verified research"):
        verify_bound_draft_review_candidate(
            root=root, symbol=package["symbol"], binding=rehashed_candidate,
            now=datetime.now(timezone.utc),
        )
    _assert_not_ready(_handoff(prepared))


def test_legacy_selector_does_not_use_bound_draft_registration(prepared):
    root, package, _, now, result = prepared
    binding = result["candidate_binding"]
    assert selected_review_candidate(
        root=root, symbol=package["symbol"], published={}, bound_draft=True, now=now,
    ) == binding
    with pytest.raises(ValueError, match="not bound to current publication"):
        selected_review_candidate(
            root=root, symbol=package["symbol"], published={"source_bindings": [binding]},
        )
    assert sha256_file(root / binding["path"]) == binding["sha256"]


@pytest.mark.parametrize("timestamp", ["future", "naive"])
def test_rehashed_candidate_requires_available_aware_generation_time(prepared, timestamp):
    root, package, _, _, result = prepared
    original = result["candidate_binding"]
    path = root / original["path"]
    candidate = json.loads(path.read_bytes())
    generated = datetime.now(timezone.utc) + timedelta(days=1)
    if timestamp == "naive":
        generated = generated.replace(tzinfo=None)
    candidate["generated_at"] = generated.isoformat()
    binding = write_binding(root, original["path"], candidate)
    _workflow(root, package["symbol"], binding)
    # Rehashing the envelope cannot make a future or timezone-free candidate available.
    verify_pending_research_candidate(root=root, path=path, expected_sha256=binding["sha256"])
    with pytest.raises(ValueError, match="not yet available"):
        verify_bound_draft_review_candidate(
            root=root, symbol=package["symbol"], binding=binding,
            now=datetime.now(timezone.utc),
        )
    _assert_not_ready(_handoff(prepared))


def test_bound_handoff_api_reuses_session_and_trusted_principal(prepared):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from value_investment_agent.application.decision.value_policy_interaction import (
        PERMISSION, PolicyPrincipal, ValuePolicyInteractionService,
    )
    from value_investment_agent.presentation.web_api.local_auth import LocalOperatorSession
    from value_investment_agent.presentation.web_api.value_policy_routes import (
        register_value_policy_routes,
    )

    root, package, _, _, result = prepared
    api = FastAPI()
    session = LocalOperatorSession(bootstrap_secret="SYNTHETIC_BOUND_HANDOFF_ONLY")
    token = session.unlock("SYNTHETIC_BOUND_HANDOFF_ONLY")
    principal = [PolicyPrincipal("SYNTHETIC_READ_ONLY", frozenset())]
    service = ValuePolicyInteractionService(
        root, storage_relative=".tmp/value-policy-review/bound-handoff", isolated=True,
    )
    register_value_policy_routes(
        api, sessions=session, principal_resolver=lambda request: principal[0],
        service=service,
    )
    path = f"/api/v1/value-policy-review/{package['symbol']}/handoff?bound_draft=true"
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    with TestClient(api, base_url="http://127.0.0.1:8001",
                    client=("127.0.0.1", 12345)) as client:
        assert client.get(path).status_code == 401
        headers = {"X-Local-Session": token}
        assert client.get(path, headers=headers).status_code == 403
        principal[0] = PolicyPrincipal("SYNTHETIC_POLICY_OWNER", frozenset({PERMISSION}))
        response = client.get(path, headers=headers)
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "no-store"
        payload = response.json()
        assert payload["status"] == "EXTERNAL_SIGNATURE_REQUIRED"
        assert payload["candidate_binding"] == result["candidate_binding"]
        assert payload["verification"]["approval_changed"] is False
        assert payload["verification"]["research_admitted"] is False
        assert payload["unsigned_response"]["reviewer_id"] is None
    assert {p: p.read_bytes() for p in root.rglob("*") if p.is_file()} == before


def test_test_only_signed_groups_consume_adapter_candidate_without_approval(prepared):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    from test_pending_review_response import consume
    from value_investment_agent.application.product.research_reviews import (
        prepare_pending_review_response,
    )
    from value_investment_agent.infrastructure.evidence.trust_root_registry import (
        trust_root_fingerprint,
    )

    root, package, _, _, prepared_result = prepared
    binding = prepared_result["candidate_binding"]
    path = root / binding["path"]
    response = prepare_pending_review_response(
        root=root, candidate_path=path, candidate_sha256=binding["sha256"],
    )
    now = datetime.now(timezone.utc)
    reviewer = "SYNTHETIC_TEST_ONLY_BOUND_DRAFT_REVIEWER"
    response.update(reviewer_id=reviewer, reviewed_at=now.isoformat())
    assert response["whole_model_approval"] is None
    for group in response["groups"]:
        group.update(
            response="VERIFIED",
            response_reason="SYNTHETIC TEST_ONLY signing-contract integration, not economic approval.",
            confirmed_scope="SYNTHETIC TEST_ONLY exact adapter candidate group fields only.",
        )
    key = Ed25519PrivateKey.generate()
    trust = dict(
        schema_version="research-review-transport-trust-root-v1", reviewer_id=reviewer,
        public_key=key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex(),
        scopes=["human_group_research"], symbols=[package["symbol"]],
        valid_from=(now - timedelta(days=1)).isoformat(),
        valid_until=(now + timedelta(days=1)).isoformat(),
    )
    registry_binding = write_binding(root, "SYNTHETIC_TEST_ONLY_registry.json", {
        "schema_version": "authorization-trust-root-registry-v1",
        "pinned_trust_root_sha256": [trust_root_fingerprint(trust)],
    })
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    result = consume(dict(
        root=root, path=path, response=response, key=key, trust=trust,
        registry=root / registry_binding["path"],
    ), suffix="-SYNTHETIC-TEST-ONLY-bound-draft")
    assert result["schema_version"] == "pending-research-review-consumption-v1"
    assert result["action"] == "no_order"
    assert result["candidate_binding"] == binding
    assert result["authenticated_reviewer"] == reviewer
    assert result["groups"] == response["groups"]
    assert all(group["response"] == "VERIFIED" for group in result["groups"])
    assert result["whole_model_review_present"] is False
    assert result["blockers"] == ["whole_model_review_missing"]
    for flag in ("research_admitted", "event_materiality_approved", "price_admitted",
                 "registered_current_case_changed"):
        assert result[flag] is False
    assert result["position_guidance"] is None
    assert "review_packet_binding" not in result
    output = root / "runtime/response-consumed-SYNTHETIC-TEST-ONLY-bound-draft"
    assert json.loads((output / "receipt.json").read_bytes()) == result
    assert not (output / "research-reviews.json").exists()
    assert not (output / "human-approval.json").exists()
    # Every original, config and public pointer remains byte-identical.
    assert all(p.read_bytes() == raw for p, raw in before.items())
    assert {p for p in root.rglob("*") if p.is_file() and "config" in p.parts} == {
        p for p in before if "config" in p.parts
    }
    candidate = verify_bound_draft_review_candidate(
        root=root, symbol=package["symbol"], binding=binding,
        now=datetime.now(timezone.utc),
    )
    assert candidate["approval_changed"] is False
    assert candidate["research_admitted"] is False
    assert candidate["price_admitted"] is False
