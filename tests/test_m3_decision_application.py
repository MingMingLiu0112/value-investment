from __future__ import annotations

from datetime import date, datetime, timezone
import json

import pytest

from value_investment_agent.investment_decision import (
    ACTION_NO_ORDER,
    STATUS_INSUFFICIENT_RESEARCH,
    STATUS_WAIT_FOR_PRICE,
    DecisionArtifactReference,
    DecisionEvidenceBundle,
    MinimalPortfolioPreconditions,
    evaluate_investment_decision,
)
from value_investment_agent.m3_decision_application import (
    build_nonpersonal_decision_card_collection,
    load_integrated_runs,
)
from value_investment_agent.pre_decision_eligibility import (
    PreDecisionEligibility,
    STATUS_ELIGIBLE,
    STATUS_NOT_ELIGIBLE,
)
from value_investment_agent.research_artifact_codecs import decode_artifact
from value_investment_agent.research_artifact_repository import (
    InMemoryResearchArtifactRepository,
)
from value_investment_agent.research_artifacts import (
    ARTIFACT_INVESTMENT_DECISION_REVIEW,
    ResearchArtifactIdentity,
    SCOPE_SECURITY,
    canonicalize_artifact_payload,
    sha256_text,
)


GENERATED_AT = datetime(2026, 9, 23, 11, 42, 28, tzinfo=timezone.utc)
AS_OF = date(2026, 9, 22)


def _run(symbol: str, blockers: tuple[str, ...], *, decision_as_of: str = "2026-09-22") -> dict:
    return {
        "run_id": f"{symbol}-m1-run",
        "symbol": symbol,
        "status": "COMPLETED_WITH_BLOCKERS",
        "action": ACTION_NO_ORDER,
        "pre_decision_eligibility": {
            "schema_version": "post-m1-predecision-eligibility-v1",
            "symbol": symbol,
            "decision_as_of": decision_as_of,
            "status": STATUS_NOT_ELIGIBLE,
            "approval_status": "REJECTED_NEEDS_REWORK",
            "model_validity_status": "STALE",
            "price_bridge_status": "STALE_MODEL",
            "event_review_watermark": decision_as_of,
            "blockers": list(blockers),
            "evidence_refs": [
                {"id": f"{symbol}-valuation-package", "sha256": "a" * 64},
                {"id": f"{symbol}-announcement", "sha256": "b" * 64},
            ],
            "action": ACTION_NO_ORDER,
        },
        "gate": {
            "conclusion": "估值未就绪",
            "blockers": list(blockers[:1]),
        },
        "human_approval": {
            "symbol": symbol,
            "status": "REJECTED_NEEDS_REWORK",
            "blockers": list(blockers[:1]),
            "action": ACTION_NO_ORDER,
        },
        "valuation": {
            "symbol": symbol,
            "model_type": "fixture",
            "valuation_date": decision_as_of,
            "confidence": "低",
            "status": "conditional_research_only",
        },
        "model_validity": {
            "symbol": symbol,
            "status": "STALE",
            "blockers": [],
        },
        "price_bridge": {
            "symbol": symbol,
            "bridge_status": "STALE_MODEL",
            "blockers": [],
        },
        "price_attractiveness": {
            "symbol": symbol,
            "status": "NOT_ASSESSABLE",
            "blockers": [],
        },
        "current_research_status": {
            "symbol": symbol,
            "research_conclusion": "估值未就绪",
            "blockers": [],
        },
    }


def test_real_shape_builds_only_nonpersonal_fail_closed_cards():
    collection = build_nonpersonal_decision_card_collection(
        [
            _run("000651", ("research_gate_not_ready",)),
            _run("600741", ("price_bridge_stale_model",)),
            _run("600887", ("human_research_approval_not_valid",)),
        ],
        generated_at=GENERATED_AT,
        source_run_id="fixture-m1-run",
    )

    assert collection.input_failures == ()
    assert len(collection.cards) == 3
    assert all(card.action == ACTION_NO_ORDER for card in collection.cards)
    assert all(card.requires_human_review for card in collection.cards)
    assert all(not card.is_positive_review() for card in collection.cards)
    assert all(card.decision_intent is None for card in collection.cards)
    assert all(card.portfolio_status == "MISSING" for card in collection.cards)
    assert all(card.entry_status == "NOT_REQUIRED" for card in collection.cards)
    assert {card.symbol for card in collection.cards} == {
        "000651",
        "600741",
        "600887",
    }
    assert collection.by_symbol["600741"].reason_kind == "PRICE_UNAVAILABLE"
    assert collection.by_symbol["000651"].status == STATUS_INSUFFICIENT_RESEARCH


def test_malformed_and_future_runs_become_visible_input_failures():
    valid = _run("000651", ("research_gate_not_ready",))
    future = _run(
        "600741",
        ("research_gate_not_ready",),
        decision_as_of="2026-09-25",
    )
    collection = build_nonpersonal_decision_card_collection(
        [
            valid,
            future,
            {"run_id": "broken", "symbol": "600887"},
            "not-an-object",
        ],
        generated_at=GENERATED_AT,
        source_run_id="fixture-m1-run",
    )

    assert [card.symbol for card in collection.cards] == ["000651"]
    assert len(collection.input_failures) == 3
    assert any("later than" in failure.error for failure in collection.input_failures)
    assert any(
        failure.symbol == "600887"
        for failure in collection.input_failures
    )


def test_integrated_run_hash_is_bound_to_the_card():
    raw = _run("000651", ("research_gate_not_ready",))
    collection = build_nonpersonal_decision_card_collection(
        [raw],
        generated_at=GENERATED_AT,
        source_run_id="fixture-m1-run",
    )
    card = collection.cards[0]
    hashes = {source.source_key: source.sha256 for source in card.source_hashes}

    assert hashes["m1_integrated_run"] == sha256_text(
        canonicalize_artifact_payload(raw)
    )
    assert hashes["investment_decision_review"]
    assert hashes["decision_evidence_bundle"]


def test_decision_review_round_trips_through_in_memory_repository():
    predecision = PreDecisionEligibility(
        symbol="000651",
        decision_as_of=AS_OF,
        status=STATUS_NOT_ELIGIBLE,
        approval_status="REJECTED_NEEDS_REWORK",
        model_validity_status="STALE",
        price_bridge_status="STALE_MODEL",
        event_review_watermark=AS_OF,
        blockers=("research_gate_not_ready",),
        evidence_refs=({"id": "fixture-predecision"},),
    )
    bundle = DecisionEvidenceBundle(
        bundle_id="000651-fixture-bundle",
        symbol="000651",
        decision_as_of=AS_OF,
        rule_version="m3-decision-v1",
        artifact_refs=(
            DecisionArtifactReference(
                artifact_type="valuation_result",
                artifact_id="000651-valuation",
                sha256="a" * 64,
                schema_version="fixture-v1",
                available_at=AS_OF,
            ),
        ),
        evidence_refs=({"id": "fixture-evidence"},),
    )
    review = evaluate_investment_decision(
        predecision=predecision,
        bundle=bundle,
        decision_as_of=AS_OF,
        decision_intent=None,
        portfolio_preconditions=MinimalPortfolioPreconditions.missing(),
        created_at=GENERATED_AT,
    )
    repository = InMemoryResearchArtifactRepository()
    stored = repository.save_object(
        review,
        identity=ResearchArtifactIdentity(
            scope_type=SCOPE_SECURITY,
            scope_key="000651",
            artifact_type=ARTIFACT_INVESTMENT_DECISION_REVIEW,
            schema_version="m3-investment-decision-v1",
            as_of=AS_OF,
            available_at=GENERATED_AT,
        ),
        run_id="fixture-run",
    )
    restored = decode_artifact(
        ARTIFACT_INVESTMENT_DECISION_REVIEW,
        json.loads(stored.envelope.canonical_payload),
    )

    assert restored.review_id == review.review_id
    assert restored.action == ACTION_NO_ORDER
    assert stored.envelope.payload_sha256 == sha256_text(
        canonicalize_artifact_payload(review.as_policy())
    )


def test_load_integrated_runs_requires_array_and_contained_path(tmp_path):
    source = _run("000651", ("research_gate_not_ready",))
    target = tmp_path / "runs.json"
    target.write_text(json.dumps([source]), encoding="utf-8")

    payload, receipt = load_integrated_runs(tmp_path, target)
    assert payload == [source]
    assert receipt["sha256"] == sha256_text(target.read_bytes())

    outside = tmp_path.parent / "outside.json"
    outside.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="escapes project root"):
        load_integrated_runs(tmp_path, outside)

    with pytest.raises(ValueError, match="JSON array"):
        bad = tmp_path / "bad.json"
        bad.write_text("{}", encoding="utf-8")
        load_integrated_runs(tmp_path, bad)
