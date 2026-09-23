from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from value_investment_agent.decision_read_model import (
    CARD_ENTRY_MISSING,
    CARD_ENTRY_NOT_REQUIRED,
    CARD_JOURNAL_ABSENT,
    CARD_PORTFOLIO_CONFIRMED,
    CARD_PORTFOLIO_MISSING,
    CARD_REASON_ENTRY_MISSING,
    CARD_REASON_HUMAN_REVIEW_REQUIRED,
    CARD_REASON_RESEARCH_INCOMPLETE,
    DecisionCardCollection,
    decision_card_from_review,
)
from value_investment_agent.investment_decision import (
    ACTION_NO_ORDER,
    POSITIVE_ARTIFACT_TYPES,
    STATUS_INSUFFICIENT_RESEARCH,
    STATUS_MANUAL_BUY_REVIEW,
    STATUS_WATCH,
    STATUS_WAIT_FOR_PRICE,
    DecisionArtifactReference,
    DecisionEvidenceBundle,
    MinimalPortfolioPreconditions,
    evaluate_investment_decision,
)
from value_investment_agent.pre_decision_eligibility import (
    PreDecisionEligibility,
    STATUS_ELIGIBLE,
    STATUS_NOT_ELIGIBLE,
)
from value_investment_agent.research_artifacts import (
    canonicalize_artifact_payload,
    sha256_text,
)


SYMBOL = "600887"
AS_OF = date(2026, 9, 22)
CREATED_AT = datetime(2026, 9, 23, 11, 42, 28, tzinfo=timezone.utc)


def _ref(artifact_type: str) -> DecisionArtifactReference:
    return DecisionArtifactReference(
        artifact_type=artifact_type,
        artifact_id=f"{artifact_type}-fixture",
        sha256="a" * 64,
        schema_version="fixture-v1",
        available_at=AS_OF,
    )


def _bundle(*types: str) -> DecisionEvidenceBundle:
    selected = types or ("valuation_result",)
    return DecisionEvidenceBundle(
        bundle_id=f"{SYMBOL}-bundle",
        symbol=SYMBOL,
        decision_as_of=AS_OF,
        rule_version="m3-decision-v1",
        artifact_refs=tuple(_ref(item) for item in selected),
        evidence_refs=({"id": "fixture-evidence", "sha256": "b" * 64},),
    )


def _predecision(*, blockers: tuple[str, ...], status: str = STATUS_NOT_ELIGIBLE) -> PreDecisionEligibility:
    return PreDecisionEligibility(
        symbol=SYMBOL,
        decision_as_of=AS_OF,
        status=status,
        approval_status="APPROVED_CONDITIONAL_LOW_CONFIDENCE",
        model_validity_status="VALID" if status == STATUS_ELIGIBLE else "STALE",
        price_bridge_status="READY" if status == STATUS_ELIGIBLE else "STALE_MODEL",
        event_review_watermark=AS_OF,
        blockers=blockers,
        evidence_refs=({"id": "predecision-evidence"},),
    )


def _portfolio() -> MinimalPortfolioPreconditions:
    return MinimalPortfolioPreconditions(
        provided=True,
        context_scope="fixture-review-scope",
        capacity_confirmed=True,
        confirmed_at=CREATED_AT,
    )


def test_research_card_separates_negative_status_from_missing_personal_inputs():
    review = evaluate_investment_decision(
        predecision=_predecision(blockers=("research_gate_not_ready",)),
        bundle=_bundle(),
        decision_as_of=AS_OF,
        decision_intent=None,
        portfolio_preconditions=MinimalPortfolioPreconditions.missing(),
        created_at=CREATED_AT,
    )
    card = decision_card_from_review(review)

    assert review.status == STATUS_INSUFFICIENT_RESEARCH
    assert card.status == STATUS_INSUFFICIENT_RESEARCH
    assert card.reason_kind == CARD_REASON_RESEARCH_INCOMPLETE
    assert card.decision_intent is None
    assert card.portfolio_status == CARD_PORTFOLIO_MISSING
    assert card.entry_status == CARD_ENTRY_NOT_REQUIRED
    assert card.journal_status == CARD_JOURNAL_ABSENT
    assert card.missing_inputs == (
        "research_or_valuation_inputs",
        "portfolio_input",
    )
    assert card.action == ACTION_NO_ORDER
    assert card.requires_human_review is True
    assert card.is_positive_review() is False


def test_price_wait_card_keeps_verified_price_missing():
    review = evaluate_investment_decision(
        predecision=_predecision(
            blockers=("price_bridge_pending_external_data",),
        ),
        bundle=_bundle(),
        decision_as_of=AS_OF,
        decision_intent=None,
        portfolio_preconditions=MinimalPortfolioPreconditions.missing(),
        created_at=CREATED_AT,
    )
    card = decision_card_from_review(review)

    assert card.status == STATUS_WATCH
    assert card.reason_kind == "PRICE_UNAVAILABLE"
    assert "verified_price_or_quote" in card.missing_inputs
    assert "research_or_valuation_inputs" not in card.missing_inputs


def test_entry_missing_is_distinct_from_negative_review_status():
    review = evaluate_investment_decision(
        predecision=_predecision(status=STATUS_ELIGIBLE, blockers=()),
        bundle=_bundle(),
        decision_as_of=AS_OF,
        decision_intent="hold",
        portfolio_preconditions=_portfolio(),
        created_at=CREATED_AT,
    )
    card = decision_card_from_review(review, decision_intent="hold")

    assert review.status == STATUS_WATCH
    assert card.entry_status == CARD_ENTRY_MISSING
    assert card.reason_kind == CARD_REASON_ENTRY_MISSING
    assert "original_entry" in card.missing_inputs
    assert "human_decision" in card.missing_inputs
    assert card.portfolio_status == CARD_PORTFOLIO_CONFIRMED


def test_positive_review_card_preserves_intent_but_never_becomes_an_order():
    bundle = _bundle(*POSITIVE_ARTIFACT_TYPES)
    review = evaluate_investment_decision(
        predecision=_predecision(status=STATUS_ELIGIBLE, blockers=()),
        bundle=bundle,
        decision_as_of=AS_OF,
        decision_intent="buy",
        confidence="中",
        portfolio_preconditions=_portfolio(),
        created_at=CREATED_AT,
    )
    card = decision_card_from_review(review, decision_intent="buy")

    assert card.status == STATUS_MANUAL_BUY_REVIEW
    assert card.reason_kind == CARD_REASON_HUMAN_REVIEW_REQUIRED
    assert card.action == ACTION_NO_ORDER
    assert card.requires_human_review is True
    assert card.decision_intent == "buy"
    assert card.journal_status == CARD_JOURNAL_ABSENT
    assert card.entry_status == CARD_ENTRY_NOT_REQUIRED


def test_card_source_hashes_bind_review_and_bundle_payloads():
    review = evaluate_investment_decision(
        predecision=_predecision(blockers=("research_gate_not_ready",)),
        bundle=_bundle(),
        decision_as_of=AS_OF,
        decision_intent=None,
        portfolio_preconditions=MinimalPortfolioPreconditions.missing(),
        created_at=CREATED_AT,
    )
    card = decision_card_from_review(review)
    hashes = {source.source_key: source.sha256 for source in card.source_hashes}

    assert hashes["investment_decision_review"] == sha256_text(
        canonicalize_artifact_payload(review.as_policy())
    )
    assert hashes["decision_evidence_bundle"] == sha256_text(
        canonicalize_artifact_payload(review.bundle.as_policy())
    )


def test_collection_rejects_duplicate_card_ids():
    review = evaluate_investment_decision(
        predecision=_predecision(blockers=("research_gate_not_ready",)),
        bundle=_bundle(),
        decision_as_of=AS_OF,
        decision_intent=None,
        portfolio_preconditions=MinimalPortfolioPreconditions.missing(),
        created_at=CREATED_AT,
    )
    card = decision_card_from_review(review)

    with pytest.raises(ValueError, match="must be unique"):
        DecisionCardCollection(
            schema_version="m3-decision-card-read-model-v1",
            generated_at=CREATED_AT,
            source_run_id="fixture-run",
            cards=(card, card),
        )
