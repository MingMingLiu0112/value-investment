from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from value_investment_agent.event_materiality import (
    DECISION_NOT_MATERIAL,
    EVENT_MATERIALITY_SCHEMA,
    EventMaterialityDecision,
    EventMaterialityReview,
)
from value_investment_agent.event_scan import (
    COVERAGE_COMPLETE,
    EVENT_SCAN_SCHEMA,
    PRE_MODEL_NONE,
    REVIEW_PENDING_HUMAN_REVIEW,
    SCAN_PENDING_HUMAN_REVIEW,
    AnnouncementReview,
    EventScanResult,
)
from value_investment_agent.m5_disclosure_queue import (
    DISCLOSURE_QUEUE_SCHEMA,
    PARSER_VERSION,
    PROVIDER_CNINFO,
    DisclosureReviewQueue,
)
from value_investment_agent.m5_human_review_reconciliation import (
    DISPOSITION_CARRY_FORWARD,
    DISPOSITION_PENDING_HUMAN_REVIEW,
    M5_RECONCILIATION_SCHEMA,
    REASON_NEW_ANNOUNCEMENT,
    REASON_SOURCE_PDF_HASH_CHANGED,
    REASON_SOURCE_PDF_HASH_MISSING,
    M5HumanReviewReconciliation,
    reconcile_m5_human_reviews,
)


SYMBOL = "600887"
SCAN_FROM = date(2026, 8, 27)
SCAN_TO = date(2026, 9, 24)
RETRIEVED_AT = datetime(2026, 9, 24, 8, 0, tzinfo=timezone.utc)
PUBLISHED_AT = datetime(2026, 9, 2, 0, 0, tzinfo=timezone(timedelta(hours=8)))
REVIEWED_AT = datetime(2026, 9, 24, 8, 30, tzinfo=timezone.utc)
AS_OF = datetime(2026, 9, 24, 9, 0, tzinfo=timezone.utc)


def _pdf_ref(hash_value: str) -> dict:
    return {
        "id": f"{SYMBOL}-pdf-1225542001",
        "path": f"fixtures/600887/1225542001.pdf",
        "sha256": hash_value,
        "source_url": "https://example.test/1225542001.PDF",
        "source_status": "SOURCE_ARCHIVED",
    }


def _candidate(
    *,
    announcement_id: str = "1225542001",
    pdf_hash: str | None = "a" * 64,
) -> AnnouncementReview:
    refs = [
        {
            "id": f"{SYMBOL}-cninfo-index",
            "path": f"fixtures/{SYMBOL}/cninfo-index.json",
            "sha256": "b" * 64,
            "source_url": "https://www.cninfo.com.cn/new/hisAnnouncement/query",
        }
    ]
    if pdf_hash is not None:
        refs.append(_pdf_ref(pdf_hash))
    return AnnouncementReview(
        announcement_id=announcement_id,
        published_at=PUBLISHED_AT,
        title="fixture disclosure",
        source_url="https://example.test/announcement.pdf",
        rule_kind="buyback",
        review_status=REVIEW_PENDING_HUMAN_REVIEW,
        materiality_candidate=True,
        pre_model=False,
        evidence_refs=tuple(refs),
        notes="fixture candidate",
    )


def _queue(candidates: tuple[AnnouncementReview, ...]) -> DisclosureReviewQueue:
    scan = EventScanResult(
        schema_version=EVENT_SCAN_SCHEMA,
        symbol=SYMBOL,
        provider=PROVIDER_CNINFO,
        scan_from=SCAN_FROM,
        scan_to=SCAN_TO,
        validity_from=SCAN_FROM,
        validity_to=SCAN_TO,
        status=SCAN_PENDING_HUMAN_REVIEW,
        coverage_status=COVERAGE_COMPLETE,
        pre_model_review_status=PRE_MODEL_NONE,
        announcements=candidates,
        blockers=(),
        evidence_refs=({"id": f"{SYMBOL}-index"},),
        retrieved_at=RETRIEVED_AT,
        parser_version=PARSER_VERSION,
    )
    return DisclosureReviewQueue(
        queue_id="fixture-queue-v1",
        schema_version=DISCLOSURE_QUEUE_SCHEMA,
        provider=PROVIDER_CNINFO,
        parser_version=PARSER_VERSION,
        scan_from=SCAN_FROM,
        scan_to=SCAN_TO,
        retrieved_at=RETRIEVED_AT,
        scans=(scan,),
    )


def _decision(
    *,
    announcement_id: str = "1225542001",
    source_hash: str = "a" * 64,
    reviewed_at: datetime | None = REVIEWED_AT,
    supersedes_event_id: str | None = None,
) -> EventMaterialityDecision:
    return EventMaterialityDecision(
        event_decision_id=f"{SYMBOL}-decision-{announcement_id}",
        symbol=SYMBOL,
        announcement_id=announcement_id,
        title="fixture disclosure",
        published_at=PUBLISHED_AT,
        source_ref={
            "id": f"{SYMBOL}-announcement-{announcement_id}",
            "path": f"fixtures/{SYMBOL}/{announcement_id}.pdf",
            "sha256": source_hash,
            "source_url": f"https://example.test/{announcement_id}.PDF",
        },
        source_sha256=source_hash,
        machine_candidate_reason="title-based machine candidate",
        human_decision=DECISION_NOT_MATERIAL,
        affected_domains=(),
        affected_fact_fields=(),
        affected_assumptions=(),
        affected_artifacts=(),
        requires_recalculation=False,
        requires_model_stale=False,
        requires_followup=False,
        supersedes_event_id=supersedes_event_id,
        reviewed_at=reviewed_at,
        reviewer_type="human_research_lead",
        review_notes=("fixture review",),
    )


def _review(decisions: tuple[EventMaterialityDecision, ...]) -> EventMaterialityReview:
    return EventMaterialityReview(
        review_id=f"{SYMBOL}-event-materiality-review-v1",
        schema_version=EVENT_MATERIALITY_SCHEMA,
        symbol=SYMBOL,
        scan_id=f"{SYMBOL}-scan-v1",
        scan_sha256="c" * 64,
        scan_from=SCAN_FROM,
        scan_to=SCAN_TO,
        reviewed_at=REVIEWED_AT,
        review_as_of=REVIEWED_AT.date(),
        reviewer_type="human_research_lead",
        decisions=decisions,
        evidence_refs=({"id": "scan"},),
    )


def test_unchanged_pdf_hash_carries_forward_prior_human_decision():
    result = reconcile_m5_human_reviews(
        queue=_queue((_candidate(),)),
        prior_reviews=(_review((_decision(),)),),
        reconciliation_id="reconcile-carry-v1",
        as_of=AS_OF,
    )

    assert result.carried_forward_count == 1
    assert result.pending_resolutions == ()
    resolution = result.resolutions[0]
    assert resolution.disposition == DISPOSITION_CARRY_FORWARD
    assert resolution.prior_review_id == f"{SYMBOL}-event-materiality-review-v1"
    assert resolution.prior_review_sha256
    assert resolution.prior_event_decision_id == f"{SYMBOL}-decision-1225542001"
    assert resolution.prior_human_decision == DECISION_NOT_MATERIAL
    assert resolution.carried_forward_at == AS_OF
    assert result.action == "no_order"


def test_changed_pdf_hash_requires_new_human_review():
    result = reconcile_m5_human_reviews(
        queue=_queue((_candidate(pdf_hash="b" * 64),)),
        prior_reviews=(_review((_decision(source_hash="a" * 64),)),),
        reconciliation_id="reconcile-changed-v1",
        as_of=AS_OF,
    )

    assert result.hash_conflict_count == 1
    assert result.pending_human_review_count == 1
    resolution = result.pending_resolutions[0]
    assert resolution.reason == REASON_SOURCE_PDF_HASH_CHANGED
    assert resolution.current_source_sha256 == "b" * 64


def test_new_announcement_and_missing_pdf_hash_fail_to_human_review():
    new_result = reconcile_m5_human_reviews(
        queue=_queue(
            (_candidate(announcement_id="1225542002", pdf_hash="c" * 64),)
        ),
        prior_reviews=(_review((_decision(),)),),
        reconciliation_id="reconcile-new-v1",
        as_of=AS_OF,
    )
    missing_result = reconcile_m5_human_reviews(
        queue=_queue((_candidate(pdf_hash=None),)),
        prior_reviews=(_review((_decision(),)),),
        reconciliation_id="reconcile-missing-v1",
        as_of=AS_OF,
    )

    assert new_result.pending_resolutions[0].reason == REASON_NEW_ANNOUNCEMENT
    assert missing_result.pending_resolutions[0].reason == REASON_SOURCE_PDF_HASH_MISSING
    assert missing_result.pending_resolutions[0].current_source_sha256 is None


def test_prior_review_hash_and_schema_are_preserved_in_policy():
    result = reconcile_m5_human_reviews(
        queue=_queue((_candidate(),)),
        prior_reviews=(_review((_decision(),)),),
        reconciliation_id="reconcile-policy-v1",
        as_of=AS_OF,
    )

    payload = result.as_policy()
    assert payload["schema_version"] == M5_RECONCILIATION_SCHEMA
    assert payload["counts"]["current_candidates"] == 1
    assert payload["counts"]["carried_forward"] == 1
    assert result.current_queue_sha256
    assert result.prior_review_ids == (f"{SYMBOL}-event-materiality-review-v1",)


def test_supersedes_relationship_is_recorded_without_forcing_repeat_review():
    decision = _decision(supersedes_event_id="1225510000")
    result = reconcile_m5_human_reviews(
        queue=_queue((_candidate(),)),
        prior_reviews=(_review((decision,)),),
        reconciliation_id="reconcile-supersedes-v1",
        as_of=AS_OF,
    )

    assert result.carried_forward_count == 1
    assert result.resolutions[0].prior_supersedes_event_id == "1225510000"


def test_duplicate_prior_review_id_fails_closed():
    first = _review((_decision(),))
    second = _review(
        (
            _decision(
                announcement_id="1225542002",
                source_hash="d" * 64,
            ),
        )
    )

    assert first.review_id == second.review_id
    with pytest.raises(ValueError, match="Duplicate prior materiality review id"):
        reconcile_m5_human_reviews(
            queue=_queue((_candidate(),)),
            prior_reviews=(first, second),
            reconciliation_id="reconcile-duplicate-review-v1",
            as_of=AS_OF,
        )
