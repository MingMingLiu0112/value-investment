from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from value_investment_agent.investment_decision import (
    ACTION_NO_ORDER,
    CONSISTENCY_BROKEN,
    CONSISTENCY_CONSISTENT,
    CONSISTENCY_FULFILLED,
    CONSISTENCY_WEAKENED,
    COMPARISON_BROKEN,
    COMPARISON_FULFILLED,
    COMPARISON_NEGATIVE,
    COMPARISON_NEUTRAL,
    DIMENSION_THESIS,
    DIMENSION_VALUATION,
    ENTRY_TYPE_ACTUAL,
    ENTRY_TYPE_RECONSTRUCTED,
    HUMAN_CONFIRM_BUY,
    HUMAN_REJECT,
    POSITIVE_ARTIFACT_TYPES,
    STATUS_HOLD,
    STATUS_INSUFFICIENT_RESEARCH,
    STATUS_MANUAL_ADD_REVIEW,
    STATUS_MANUAL_BUY_REVIEW,
    STATUS_MANUAL_EXIT_REVIEW,
    STATUS_MANUAL_REDUCE_REVIEW,
    STATUS_WATCH,
    STATUS_WAIT_FOR_PRICE,
    ConsistencyComparison,
    DecisionArtifactReference,
    DecisionEvidenceBundle,
    DecisionJournalEntry,
    EntryThesisSnapshot,
    InvestmentConsistencyReview,
    MinimalPortfolioPreconditions,
    aggregate_consistency_status,
    consistency_comparison_from_payload,
    decision_evidence_bundle_from_payload,
    decision_journal_entry_from_payload,
    entry_thesis_snapshot_from_payload,
    evaluate_investment_decision,
    investment_consistency_review_from_payload,
    investment_decision_review_from_payload,
    minimal_portfolio_preconditions_from_payload,
)
from value_investment_agent.pre_decision_eligibility import (
    PreDecisionEligibility,
    STATUS_ELIGIBLE,
    STATUS_NOT_ELIGIBLE,
)
from value_investment_agent.price_attractiveness import (
    STATUS_KEY_OBSERVATION,
    STATUS_NOT_ASSESSABLE,
    STATUS_PRICE_NOT_ATTRACTIVE,
    STATUS_RESEARCH_ATTRACTIVE,
    STATUS_WAITING_FOR_BETTER_PRICE,
)
from value_investment_agent.research_artifact_codecs import decode_artifact
from value_investment_agent.research_artifact_repository import (
    InMemoryResearchArtifactRepository,
)
from value_investment_agent.research_artifacts import (
    ARTIFACT_DECISION_EVIDENCE_BUNDLE,
    ARTIFACT_DECISION_JOURNAL_ENTRY,
    ARTIFACT_ENTRY_THESIS_SNAPSHOT,
    ARTIFACT_INVESTMENT_CONSISTENCY_REVIEW,
    ARTIFACT_INVESTMENT_DECISION_REVIEW,
    ARTIFACT_MINIMAL_PORTFOLIO_PRECONDITIONS,
    ResearchArtifactIdentity,
    SCOPE_REVIEW,
    SCOPE_SECURITY,
)


SYMBOL = "600887"
AS_OF = date(2026, 9, 24)
CONFIRMED_AT = datetime(2026, 9, 24, 2, 0, tzinfo=timezone.utc)
HASH = "a" * 64


def _artifact(artifact_type: str) -> DecisionArtifactReference:
    return DecisionArtifactReference(
        artifact_type=artifact_type,
        artifact_id=f"{artifact_type}-v1",
        sha256=HASH,
        schema_version="fixture-v1",
        available_at=AS_OF,
    )


def _bundle(*extra_types: str) -> DecisionEvidenceBundle:
    types = (*POSITIVE_ARTIFACT_TYPES, *extra_types)
    return DecisionEvidenceBundle(
        bundle_id=f"{SYMBOL}-bundle-v1",
        symbol=SYMBOL,
        decision_as_of=AS_OF,
        rule_version="m3-decision-v1",
        artifact_refs=tuple(_artifact(artifact_type) for artifact_type in types),
        evidence_refs=({"id": "bundle-evidence"},),
    )


def _predecision(
    *,
    status: str = STATUS_ELIGIBLE,
    blockers: tuple[str, ...] = (),
    price_status: str | None = None,
    positive_price_eligible: bool | None = None,
) -> PreDecisionEligibility:
    resolved_price_status = (
        price_status
        or (
            STATUS_RESEARCH_ATTRACTIVE
            if status == STATUS_ELIGIBLE
            else STATUS_NOT_ASSESSABLE
        )
    )
    resolved_positive_eligible = (
        positive_price_eligible
        if positive_price_eligible is not None
        else status == STATUS_ELIGIBLE
        and resolved_price_status == STATUS_RESEARCH_ATTRACTIVE
    )
    return PreDecisionEligibility(
        symbol=SYMBOL,
        decision_as_of=AS_OF,
        status=status,
        approval_status="APPROVED_CONDITIONAL_LOW_CONFIDENCE",
        model_validity_status="VALID",
        price_bridge_status="READY" if status == STATUS_ELIGIBLE else "PENDING_EXTERNAL_DATA",
        event_review_watermark=AS_OF,
        blockers=blockers,
        evidence_refs=({"id": "predecision"},),
        price_attractiveness_status=resolved_price_status,
        positive_price_review_eligible=resolved_positive_eligible,
    )


def _portfolio() -> MinimalPortfolioPreconditions:
    return MinimalPortfolioPreconditions(
        provided=True,
        context_scope="fixture-review-scope",
        capacity_confirmed=True,
        confirmed_at=CONFIRMED_AT,
        evidence_refs=({"id": "portfolio-capacity"},),
    )


def _entry() -> EntryThesisSnapshot:
    return EntryThesisSnapshot(
        entry_id=f"{SYMBOL}-entry-v1",
        symbol=SYMBOL,
        confirmed_at=CONFIRMED_AT,
        entry_type=ENTRY_TYPE_ACTUAL,
        entry_date=AS_OF,
        entry_price=Decimal("20"),
        review_id=f"{SYMBOL}-decision-v1",
        bundle_id=f"{SYMBOL}-bundle-v1",
        thesis="Long thesis",
        return_driver="Return driver",
        mispricing_hypothesis="Market ignores durable cash generation",
        bear_value=Decimal("15"),
        base_value=Decimal("20"),
        bull_value=Decimal("25"),
        confidence="中",
        dividend_thesis="Dividend thesis",
        hold_logic="Hold logic",
        risks=("Risk one",),
        counter_evidence=("Counter evidence",),
        breakers=("Thesis breaker",),
        catalysts=("Annual report",),
        reasons_to_add=("Evidence improves",),
        reasons_not_to_add=("No capacity",),
        reasons_to_reduce=("Concentration",),
        reasons_to_exit=("Thesis broken",),
    )


def test_bundle_rejects_duplicate_artifact_types_and_bad_hashes():
    with pytest.raises(ValueError, match="must be unique"):
        DecisionEvidenceBundle(
            bundle_id="bundle",
            symbol=SYMBOL,
            decision_as_of=AS_OF,
            rule_version="v1",
            artifact_refs=(_artifact("valuation_result"), _artifact("valuation_result")),
        )
    with pytest.raises(ValueError, match="SHA-256"):
        _artifact("valuation_result").__class__(
            artifact_type="valuation_result",
            artifact_id="bad-hash",
            sha256="not-a-hash",
            schema_version="v1",
            available_at=AS_OF,
        )


def test_missing_portfolio_capacity_never_allows_positive_review():
    missing = MinimalPortfolioPreconditions.missing()
    assert missing.provided is False
    assert missing.allows_positive_review() is False
    assert "portfolio_input_missing" in missing.blockers
    assert _portfolio().allows_positive_review() is True


def test_non_eligible_predecision_produces_research_or_price_wait_not_buy():
    research_gap = evaluate_investment_decision(
        predecision=_predecision(
            status=STATUS_NOT_ELIGIBLE,
            blockers=("human_research_approval_not_valid",),
        ),
        bundle=_bundle(),
        decision_as_of=AS_OF,
        decision_intent="buy",
        confidence="中",
        portfolio_preconditions=_portfolio(),
    )
    price_wait = evaluate_investment_decision(
        predecision=_predecision(
            status=STATUS_NOT_ELIGIBLE,
            blockers=("price_bridge_pending_external_data",),
        ),
        bundle=_bundle(),
        decision_as_of=AS_OF,
        decision_intent="buy",
        confidence="中",
        portfolio_preconditions=_portfolio(),
    )

    assert research_gap.status == STATUS_INSUFFICIENT_RESEARCH
    assert price_wait.status == STATUS_WAIT_FOR_PRICE
    assert research_gap.action == ACTION_NO_ORDER
    assert price_wait.action == ACTION_NO_ORDER


@pytest.mark.parametrize(
    ("price_status", "expected_status"),
    [
        (STATUS_NOT_ASSESSABLE, STATUS_INSUFFICIENT_RESEARCH),
        (STATUS_WAITING_FOR_BETTER_PRICE, STATUS_WAIT_FOR_PRICE),
        (STATUS_KEY_OBSERVATION, STATUS_WATCH),
        (STATUS_PRICE_NOT_ATTRACTIVE, STATUS_WATCH),
    ],
)
def test_non_attractive_price_statuses_never_become_positive_reviews(
    price_status: str,
    expected_status: str,
):
    result = evaluate_investment_decision(
        predecision=_predecision(
            price_status=price_status,
            positive_price_eligible=False,
        ),
        bundle=_bundle(),
        decision_as_of=AS_OF,
        decision_intent="buy",
        confidence="中",
        portfolio_preconditions=_portfolio(),
    )

    assert result.status == expected_status
    assert result.is_positive_review() is False
    assert "positive_price_review_not_eligible" in result.blockers
    assert result.action == ACTION_NO_ORDER


@pytest.mark.parametrize(
    ("decision_intent", "expected_status", "needs_entry"),
    [
        ("buy", STATUS_MANUAL_BUY_REVIEW, False),
        ("add", STATUS_MANUAL_ADD_REVIEW, True),
    ],
)
def test_research_attractive_price_can_only_reach_manual_positive_review(
    decision_intent: str,
    expected_status: str,
    needs_entry: bool,
):
    result = evaluate_investment_decision(
        predecision=_predecision(),
        bundle=_bundle(),
        decision_as_of=AS_OF,
        decision_intent=decision_intent,
        confidence="中",
        portfolio_preconditions=_portfolio(),
        entry=_entry() if needs_entry else None,
        reason="Evidence improved" if needs_entry else None,
    )

    assert result.status == expected_status
    assert result.price_attractiveness_status == STATUS_RESEARCH_ATTRACTIVE
    assert result.requires_human_review is True
    assert result.action == ACTION_NO_ORDER


def test_eligible_research_still_requires_confirmed_portfolio_capacity():
    result = evaluate_investment_decision(
        predecision=_predecision(),
        bundle=_bundle(),
        decision_as_of=AS_OF,
        decision_intent="buy",
        confidence="中",
        portfolio_preconditions=MinimalPortfolioPreconditions.missing(),
    )

    assert result.status == STATUS_WATCH
    assert "portfolio_input_missing" in result.blockers


def test_complete_buy_review_is_manual_and_no_order():
    result = evaluate_investment_decision(
        predecision=_predecision(),
        bundle=_bundle(),
        decision_as_of=AS_OF,
        decision_intent="buy",
        confidence="中",
        portfolio_preconditions=_portfolio(),
        reason="Durable competitive advantage with an observable price gap",
    )

    assert result.status == STATUS_MANUAL_BUY_REVIEW
    assert result.is_positive_review() is True
    assert result.blockers == ()
    assert result.action == ACTION_NO_ORDER
    assert result.requires_human_review is True


def test_low_confidence_or_incomplete_bundle_blocks_positive_review():
    low_confidence = evaluate_investment_decision(
        predecision=_predecision(),
        bundle=_bundle(),
        decision_as_of=AS_OF,
        decision_intent="buy",
        confidence="低",
        portfolio_preconditions=_portfolio(),
    )
    incomplete = evaluate_investment_decision(
        predecision=_predecision(),
        bundle=DecisionEvidenceBundle(
            bundle_id=f"{SYMBOL}-bundle-partial",
            symbol=SYMBOL,
            decision_as_of=AS_OF,
            rule_version="m3-decision-v1",
            artifact_refs=(_artifact("valuation_result"),),
        ),
        decision_as_of=AS_OF,
        decision_intent="buy",
        confidence="中",
        portfolio_preconditions=_portfolio(),
    )

    assert low_confidence.status == STATUS_WATCH
    assert "positive_review_confidence_below_policy" in low_confidence.blockers
    assert incomplete.status == STATUS_WATCH
    assert "positive_review_evidence_bundle_incomplete" in incomplete.blockers


def test_add_and_hold_require_the_original_entry_and_reason():
    no_entry = evaluate_investment_decision(
        predecision=_predecision(),
        bundle=_bundle(),
        decision_as_of=AS_OF,
        decision_intent="add",
        confidence="中",
        portfolio_preconditions=_portfolio(),
        reason="Evidence improved",
    )
    no_reason = evaluate_investment_decision(
        predecision=_predecision(),
        bundle=_bundle(),
        decision_as_of=AS_OF,
        decision_intent="hold",
        confidence="中",
        portfolio_preconditions=_portfolio(),
        entry=_entry(),
    )

    assert no_entry.status == STATUS_WATCH
    assert "original_entry_missing" in no_entry.blockers
    assert no_reason.status == STATUS_WATCH
    assert "hold_reason_missing" in no_reason.blockers


def test_reduce_and_exit_are_explicit_human_reviews_even_without_price_readiness():
    reduce_review = evaluate_investment_decision(
        predecision=_predecision(
            status=STATUS_NOT_ELIGIBLE,
            blockers=("price_bridge_pending_external_data",),
        ),
        bundle=_bundle(),
        decision_as_of=AS_OF,
        decision_intent="reduce",
        entry=_entry(),
        reason="Concentration risk increased",
    )
    exit_review = evaluate_investment_decision(
        predecision=_predecision(
            status=STATUS_NOT_ELIGIBLE,
            blockers=("unresolved_event_recalculation",),
        ),
        bundle=_bundle(),
        decision_as_of=AS_OF,
        decision_intent="exit",
        entry=_entry(),
        reason="Confirmed thesis breaker",
    )

    assert reduce_review.status == STATUS_MANUAL_REDUCE_REVIEW
    assert exit_review.status == STATUS_MANUAL_EXIT_REVIEW
    assert reduce_review.action == ACTION_NO_ORDER
    assert exit_review.action == ACTION_NO_ORDER
    assert exit_review.blockers


def test_entry_snapshot_requires_price_or_reconstruction_note():
    with pytest.raises(ValueError, match="require a price"):
        EntryThesisSnapshot(
            **_entry_payload(entry_price=None),
        )
    reconstructed = EntryThesisSnapshot(
        **_entry_payload(
            entry_type=ENTRY_TYPE_RECONSTRUCTED,
            entry_price=None,
            reconstructed_note="Historical baseline reconstructed from records",
        ),
    )
    assert reconstructed.entry_type == ENTRY_TYPE_RECONSTRUCTED
    assert reconstructed.action == ACTION_NO_ORDER


def test_journal_is_append_only_and_confirmed_decisions_need_entry():
    journal = DecisionJournalEntry(
        journal_id=f"{SYMBOL}-journal-v1",
        symbol=SYMBOL,
        decision_at=CONFIRMED_AT,
        review_id=f"{SYMBOL}-decision-v1",
        review_status=STATUS_MANUAL_BUY_REVIEW,
        system_reason="System reason",
        human_decision=HUMAN_CONFIRM_BUY,
        human_reason="Human reason",
        entry_id=_entry().entry_id,
        confirmed_price=Decimal("20"),
        namespace="simulated",
        previous_journal_id=f"{SYMBOL}-journal-v0",
    )
    rejected = DecisionJournalEntry(
        journal_id=f"{SYMBOL}-journal-v2",
        symbol=SYMBOL,
        decision_at=CONFIRMED_AT,
        review_id=f"{SYMBOL}-decision-v1",
        review_status=STATUS_WATCH,
        system_reason="System reason",
        human_decision=HUMAN_REJECT,
        human_reason="Human rejected",
        entry_id=None,
        confirmed_price=None,
        namespace="simulated",
    )

    assert journal.is_correction() is True
    assert journal.action == ACTION_NO_ORDER
    assert rejected.is_correction() is False


def test_journal_rejects_decision_status_and_confirmed_price_contradictions():
    common = {
        "journal_id": f"{SYMBOL}-journal-v1",
        "symbol": SYMBOL,
        "decision_at": CONFIRMED_AT,
        "review_id": f"{SYMBOL}-decision-v1",
        "system_reason": "System reason",
        "human_reason": "Human reason",
        "entry_id": _entry().entry_id,
        "namespace": "simulated",
    }

    with pytest.raises(ValueError, match="does not match review status"):
        DecisionJournalEntry(
            **common,
            review_status=STATUS_MANUAL_ADD_REVIEW,
            human_decision=HUMAN_CONFIRM_BUY,
            confirmed_price=Decimal("20"),
        )

    with pytest.raises(ValueError, match="cannot confirm a price"):
        DecisionJournalEntry(
            **common,
            review_status=STATUS_HOLD,
            human_decision=HUMAN_REJECT,
            confirmed_price=Decimal("20"),
        )


def test_consistency_status_is_conservative_and_validated():
    neutral = ConsistencyComparison(
        dimension=DIMENSION_THESIS,
        original_value="Same",
        current_value="Same",
        impact=COMPARISON_NEUTRAL,
        change_reason="",
    )
    weakened = ConsistencyComparison(
        dimension=DIMENSION_VALUATION,
        original_value="20",
        current_value="17",
        impact=COMPARISON_NEGATIVE,
        change_reason="Estimates declined",
    )
    broken = ConsistencyComparison(
        dimension=DIMENSION_THESIS,
        original_value="Scale advantage",
        current_value="Advantage lost",
        impact=COMPARISON_BROKEN,
        change_reason="Market structure changed",
    )
    fulfilled = ConsistencyComparison(
        dimension=DIMENSION_THESIS,
        original_value="Expected catalyst",
        current_value="Catalyst occurred",
        impact=COMPARISON_FULFILLED,
        change_reason="Catalyst confirmed",
    )

    assert aggregate_consistency_status((neutral,)) == CONSISTENCY_CONSISTENT
    assert aggregate_consistency_status((weakened,)) == CONSISTENCY_WEAKENED
    assert aggregate_consistency_status((broken,)) == CONSISTENCY_BROKEN
    assert aggregate_consistency_status((fulfilled,)) == CONSISTENCY_FULFILLED
    with pytest.raises(ValueError, match="does not match"):
        InvestmentConsistencyReview(
            review_id=f"{SYMBOL}-consistency-v1",
            symbol=SYMBOL,
            entry_id=f"{SYMBOL}-entry-v1",
            as_of=AS_OF,
            status=CONSISTENCY_CONSISTENT,
            comparisons=(weakened,),
        )


def test_decision_contracts_round_trip_without_losing_no_order_boundary():
    portfolio = _portfolio()
    review = evaluate_investment_decision(
        predecision=_predecision(),
        bundle=_bundle(),
        decision_as_of=AS_OF,
        decision_intent="buy",
        confidence="中",
        portfolio_preconditions=portfolio,
    )
    entry = _entry()
    consistency = InvestmentConsistencyReview(
        review_id=f"{SYMBOL}-consistency-v1",
        symbol=SYMBOL,
        entry_id=entry.entry_id,
        as_of=AS_OF,
        status=CONSISTENCY_CONSISTENT,
        comparisons=(
            ConsistencyComparison(
                dimension=DIMENSION_THESIS,
                original_value="Same",
                current_value="Same",
                impact=COMPARISON_NEUTRAL,
                change_reason="",
            ),
        ),
    )
    journal = DecisionJournalEntry(
        journal_id=f"{SYMBOL}-journal-v1",
        symbol=SYMBOL,
        decision_at=CONFIRMED_AT,
        review_id=review.review_id,
        review_status=review.status,
        system_reason=review.summary,
        human_decision=HUMAN_REJECT,
        human_reason="Deferred",
        entry_id=None,
        confirmed_price=None,
        namespace="simulated",
    )

    assert minimal_portfolio_preconditions_from_payload(portfolio.as_policy()) == portfolio
    assert decision_evidence_bundle_from_payload(review.bundle.as_policy()) == review.bundle
    assert investment_decision_review_from_payload(review.as_policy()) == review
    assert entry_thesis_snapshot_from_payload(entry.as_policy()) == entry
    assert investment_consistency_review_from_payload(consistency.as_policy()) == consistency
    assert decision_journal_entry_from_payload(journal.as_policy()) == journal


def test_decision_artifacts_persist_and_restore_from_repository():
    portfolio = _portfolio()
    review = evaluate_investment_decision(
        predecision=_predecision(),
        bundle=_bundle(),
        decision_as_of=AS_OF,
        decision_intent="buy",
        confidence="中",
        portfolio_preconditions=portfolio,
    )
    entry = _entry()
    consistency = InvestmentConsistencyReview(
        review_id=f"{SYMBOL}-consistency-v1",
        symbol=SYMBOL,
        entry_id=entry.entry_id,
        as_of=AS_OF,
        status=CONSISTENCY_CONSISTENT,
        comparisons=(
            ConsistencyComparison(
                dimension=DIMENSION_THESIS,
                original_value="Same",
                current_value="Same",
                impact=COMPARISON_NEUTRAL,
                change_reason="",
            ),
        ),
    )
    journal = DecisionJournalEntry(
        journal_id=f"{SYMBOL}-journal-v1",
        symbol=SYMBOL,
        decision_at=CONFIRMED_AT,
        review_id=review.review_id,
        review_status=review.status,
        system_reason=review.summary,
        human_decision=HUMAN_REJECT,
        human_reason="Deferred",
        entry_id=None,
        confirmed_price=None,
        namespace="simulated",
    )
    values = (
        (ARTIFACT_DECISION_EVIDENCE_BUNDLE, SCOPE_SECURITY, review.bundle),
        (ARTIFACT_MINIMAL_PORTFOLIO_PRECONDITIONS, SCOPE_REVIEW, portfolio),
        (ARTIFACT_INVESTMENT_DECISION_REVIEW, SCOPE_SECURITY, review),
        (ARTIFACT_ENTRY_THESIS_SNAPSHOT, SCOPE_SECURITY, entry),
        (ARTIFACT_DECISION_JOURNAL_ENTRY, SCOPE_SECURITY, journal),
        (ARTIFACT_INVESTMENT_CONSISTENCY_REVIEW, SCOPE_SECURITY, consistency),
    )

    repository = InMemoryResearchArtifactRepository()
    for artifact_type, scope_type, value in values:
        identity = ResearchArtifactIdentity(
            scope_type=scope_type,
            scope_key=SYMBOL if scope_type == SCOPE_SECURITY else f"{SYMBOL}-review",
            artifact_type=artifact_type,
            schema_version="m3-investment-decision-v1",
            as_of=AS_OF,
            available_at=CONFIRMED_AT,
        )
        stored = repository.save_object(
            value,
            identity=identity,
            run_id=f"m3-{artifact_type}-v1",
        )
        restored = decode_artifact(
            artifact_type,
            stored.envelope.payload_object(),
        )
        assert restored.to_json() == value.to_json()


def _entry_payload(**overrides):
    payload = {
        "entry_id": f"{SYMBOL}-entry-v1",
        "symbol": SYMBOL,
        "confirmed_at": CONFIRMED_AT,
        "entry_type": ENTRY_TYPE_ACTUAL,
        "entry_date": AS_OF,
        "entry_price": Decimal("20"),
        "review_id": f"{SYMBOL}-decision-v1",
        "bundle_id": f"{SYMBOL}-bundle-v1",
        "thesis": "Long thesis",
        "return_driver": "Return driver",
        "mispricing_hypothesis": "Mispricing",
        "bear_value": Decimal("15"),
        "base_value": Decimal("20"),
        "bull_value": Decimal("25"),
        "confidence": "中",
        "dividend_thesis": "Dividend thesis",
        "hold_logic": "Hold logic",
        "risks": ("Risk",),
        "counter_evidence": ("Counter",),
        "breakers": ("Breaker",),
        "catalysts": ("Catalyst",),
        "reasons_to_add": ("Add reason",),
        "reasons_not_to_add": ("No add reason",),
        "reasons_to_reduce": ("Reduce reason",),
        "reasons_to_exit": ("Exit reason",),
        "reconstructed_note": "",
    }
    payload.update(overrides)
    return payload
