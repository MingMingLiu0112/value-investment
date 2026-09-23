from __future__ import annotations

from datetime import date, datetime, timezone
from copy import deepcopy
from pathlib import Path

import pytest

from value_investment_agent.event_scan import (
    COVERAGE_COMPLETE,
    COVERAGE_INCOMPLETE,
    EVENT_SCAN_SCHEMA,
    PRE_MODEL_NONE,
    PRE_MODEL_PENDING_HUMAN_REVIEW,
    REVIEW_PENDING_HUMAN_REVIEW,
    REVIEW_REVIEWED_NO_MATERIAL_CANDIDATE,
    SCAN_COMPLETE_MATERIAL_EVENTS,
    SCAN_COMPLETE_NO_MATERIAL_EVENT,
    SCAN_PENDING_HUMAN_REVIEW,
    AnnouncementReview,
    EventScanResult,
    event_scan_from_payload,
)
from value_investment_agent.model_validity import evaluate_model_validity
from value_investment_agent.m1_valuation_package_builder import (
    build_descriptor,
    load_descriptor_payloads,
)


REF = {"id": "scan", "path": "runtime/scan.json", "sha256": "a" * 64}
ROOT = Path(__file__).resolve().parents[1]


def _announcement(
    *,
    published_at: datetime,
    candidate: bool = True,
    pre_model: bool = True,
) -> AnnouncementReview:
    return AnnouncementReview(
        announcement_id=f"a-{published_at.isoformat()}",
        published_at=published_at,
        title="buyback disclosure",
        source_url="https://static.cninfo.com.cn/finalpage/a.pdf",
        rule_kind="buyback",
        review_status=(
            REVIEW_PENDING_HUMAN_REVIEW
            if candidate else REVIEW_REVIEWED_NO_MATERIAL_CANDIDATE
        ),
        materiality_candidate=candidate,
        pre_model=pre_model,
        evidence_refs=({"id": "pdf"},),
    )


def _scan(
    *,
    status=SCAN_COMPLETE_NO_MATERIAL_EVENT,
    coverage=COVERAGE_COMPLETE,
    announcements=(),
    scan_to=date(2026, 9, 22),
    validity_from=date(2026, 9, 22),
    validity_to=date(2026, 9, 22),
    blockers=(),
) -> EventScanResult:
    return EventScanResult(
        schema_version=EVENT_SCAN_SCHEMA,
        symbol="600887",
        provider="cninfo",
        scan_from=date(2026, 8, 27),
        scan_to=scan_to,
        validity_from=validity_from,
        validity_to=validity_to,
        status=status,
        coverage_status=coverage,
        pre_model_review_status=(
            PRE_MODEL_PENDING_HUMAN_REVIEW
            if any(item.materiality_candidate and item.pre_model for item in announcements)
            else PRE_MODEL_NONE
        ),
        announcements=announcements,
        blockers=blockers,
        evidence_refs=(REF,),
        retrieved_at=datetime(2026, 9, 23, 5, 0, tzinfo=timezone.utc),
        parser_version="cninfo-announcement-window-v1",
    )


def test_event_scan_round_trip_preserves_pre_model_review_state():
    scan = _scan(
        announcements=(
            _announcement(
                published_at=datetime(2026, 9, 17, 0, 0, tzinfo=timezone.utc),
            ),
        ),
        blockers=("pre-model disclosures require human review",),
    )

    restored = event_scan_from_payload(scan.as_policy())

    assert restored == scan
    assert restored.validity_material_candidates == ()
    assert len(restored.pre_model_material_candidates) == 1


def test_complete_no_material_event_requires_evidence_and_can_remain_valid():
    scan = _scan(
        announcements=(
            _announcement(
                published_at=datetime(2026, 9, 17, 0, 0, tzinfo=timezone.utc),
            ),
        ),
        blockers=("pre-model disclosures require human review",),
    )

    checked = evaluate_model_validity(
        model_id="residual-income-equity-shared-v1",
        symbol="600887",
        model_as_of=date(2026, 9, 22),
        valid_from=date(2026, 9, 22),
        quote_date=date(2026, 9, 22),
        events=[],
        event_scan_evidence_refs=[REF],
        event_scan=scan,
    )

    assert checked.status == "VALID"
    assert "pre-model disclosures require human review" in checked.blockers
    assert any(ref["id"] == "scan" for ref in checked.evidence_refs)


def test_event_scan_stales_the_model_when_a_candidate_is_in_the_window():
    scan = _scan(
        status=SCAN_COMPLETE_MATERIAL_EVENTS,
        announcements=(
            _announcement(
                published_at=datetime(2026, 9, 22, 0, 0, tzinfo=timezone.utc),
                pre_model=False,
            ),
        ),
    )

    checked = evaluate_model_validity(
        model_id="residual-income-equity-shared-v1",
        symbol="600887",
        model_as_of=date(2026, 9, 22),
        valid_from=date(2026, 9, 22),
        quote_date=date(2026, 9, 22),
        events=[],
        event_scan_evidence_refs=[REF],
        event_scan=scan,
    )

    assert checked.status == "STALE"
    assert checked.material_event_found is True


def test_pending_human_review_cannot_be_reported_as_valid():
    scan = _scan(status=SCAN_PENDING_HUMAN_REVIEW)

    checked = evaluate_model_validity(
        model_id="residual-income-equity-shared-v1",
        symbol="600887",
        model_as_of=date(2026, 9, 22),
        valid_from=date(2026, 9, 22),
        quote_date=date(2026, 9, 22),
        events=[],
        event_scan_evidence_refs=[REF],
        event_scan=scan,
    )

    assert checked.status == "UNKNOWN"
    assert "event scan is pending human review" in checked.blockers


def test_scan_must_cover_the_quote_date():
    scan = _scan(
        scan_to=date(2026, 9, 21),
        validity_from=date(2026, 9, 20),
        validity_to=date(2026, 9, 21),
    )

    checked = evaluate_model_validity(
        model_id="residual-income-equity-shared-v1",
        symbol="600887",
        model_as_of=date(2026, 9, 20),
        valid_from=date(2026, 9, 20),
        quote_date=date(2026, 9, 22),
        events=[],
        event_scan_evidence_refs=[REF],
        event_scan=scan,
    )

    assert checked.status == "INVALID"
    assert "event scan does not cover the quote date" in checked.blockers


def test_incomplete_coverage_is_unknown():
    scan = _scan(coverage=COVERAGE_INCOMPLETE)

    checked = evaluate_model_validity(
        model_id="residual-income-equity-shared-v1",
        symbol="600887",
        model_as_of=date(2026, 9, 22),
        valid_from=date(2026, 9, 22),
        quote_date=date(2026, 9, 22),
        events=[],
        event_scan_evidence_refs=[REF],
        event_scan=scan,
    )

    assert checked.status == "UNKNOWN"
    assert "event scan coverage is incomplete" in checked.blockers


def test_no_material_status_rejects_a_hidden_validity_candidate():
    with pytest.raises(ValueError, match="No-material-event status"):
        _scan(
            announcements=(
                _announcement(
                    published_at=datetime(2026, 9, 22, 0, 0, tzinfo=timezone.utc),
                    pre_model=False,
                ),
            ),
        )


def test_package_binds_the_hash_pinned_cninfo_event_scan():
    payload = load_descriptor_payloads(ROOT)["600887"]
    descriptor = build_descriptor(payload, root=ROOT)
    event_scan = descriptor.model_validity_input.event_scan

    assert event_scan is not None
    assert event_scan.symbol == "600887"
    assert event_scan.coverage_status == "COMPLETE"
    assert event_scan.status == "COMPLETE_NO_MATERIAL_EVENT_IN_VALIDITY_WINDOW"
    assert event_scan.pre_model_review_status == "PENDING_HUMAN_REVIEW"
    assert event_scan.pre_model_material_candidates
    assert event_scan.validity_material_candidates == ()
    assert any(
        str(ref.get("id", "")).startswith("600887-event-scan-")
        for ref in descriptor.model_validity_input.event_scan_evidence_refs
    )
    assert any(
        ref.get("id") == "600887-cninfo-event-index"
        for ref in event_scan.evidence_refs
    )


def test_package_rejects_a_tampered_event_scan_hash():
    payload = load_descriptor_payloads(ROOT)["600887"]
    payload = deepcopy(payload)
    reference = payload["model_validity_input"]["event_scan_ref"]
    reference["sha256"] = "0" * 64

    with pytest.raises(ValueError, match="event_scan evidence hash changed"):
        build_descriptor(payload, root=ROOT)
