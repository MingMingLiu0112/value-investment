from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone
import hashlib
from pathlib import Path

import pytest

from value_investment_agent.event_materiality import (
    DECISION_NOT_MATERIAL,
    DECISION_REQUIRES_DECOMPOSITION,
    DECISION_REQUIRES_RECALCULATION,
    DECISION_RISK_MONITOR,
)
from value_investment_agent.m5_disclosure_queue import (
    DISCLOSURE_QUEUE_SCHEMA,
    PARSER_VERSION,
    PROVIDER_CNINFO,
    DisclosureReviewQueue,
    build_cninfo_event_scan,
)
from value_investment_agent.m5_disclosure_review import (
    ACTION_NO_ORDER,
    CN_TZ,
    DECISION_VERSION,
    DISCLOSURE_REVIEW_INTAKE_SCHEMA,
    DisclosureReviewDecisionInput,
    DisclosureReviewIntake,
    build_disclosure_materiality_reviews,
    disclosure_queue_sha256,
    disclosure_review_intake_from_payload,
)


SCAN_FROM = date(2026, 8, 27)
SCAN_TO = date(2026, 9, 24)
RETRIEVED_AT = datetime(2026, 9, 24, 16, 0, tzinfo=timezone.utc)
REVIEWED_AT = datetime(2026, 9, 24, 18, 0, tzinfo=CN_TZ)
PDF_BYTES = b"%PDF-fixture"
PDF_SHA256 = hashlib.sha256(PDF_BYTES).hexdigest()


def _timestamp(day: int = 2, hour: int = 1) -> int:
    return int(
        datetime(2026, 9, day, hour, 0, tzinfo=timezone.utc).timestamp() * 1000
    )


def _row(
    *,
    announcement_id: str,
    title: str = "关于回购公司股份的公告",
    adjunct: str | None = None,
    timestamp: int | None = None,
) -> dict:
    return {
        "secCode": "600887",
        "announcementId": announcement_id,
        "announcementTitle": title,
        "announcementTime": timestamp if timestamp is not None else _timestamp(),
        "adjunctUrl": (
            adjunct
            if adjunct is not None
            else f"finalpage/2026-09-02/{announcement_id}.PDF"
        ),
    }


def _payload(rows: list[dict]) -> dict:
    return {
        "url": "https://www.cninfo.com.cn/new/hisAnnouncement/query",
        "total_announcements": len(rows),
        "announcements": rows,
    }


def _downloader(source_url: str, target: Path) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(PDF_BYTES)
    return PDF_SHA256


def _queue(tmp_path: Path, rows: list[dict]) -> DisclosureReviewQueue:
    scan = build_cninfo_event_scan(
        _payload(rows),
        symbol="600887",
        scan_from=SCAN_FROM,
        scan_to=SCAN_TO,
        retrieved_at=RETRIEVED_AT,
        evidence_dir=tmp_path / "600887",
        root=tmp_path,
        pdf_downloader=_downloader,
    )
    return DisclosureReviewQueue(
        queue_id="fixture-cninfo-review",
        schema_version=DISCLOSURE_QUEUE_SCHEMA,
        provider=PROVIDER_CNINFO,
        parser_version=PARSER_VERSION,
        scan_from=SCAN_FROM,
        scan_to=SCAN_TO,
        retrieved_at=RETRIEVED_AT,
        scans=(scan,),
        action=ACTION_NO_ORDER,
    )


def _decision(
    announcement_id: str,
    *,
    human_decision: str = DECISION_NOT_MATERIAL,
    domains: tuple[str, ...] = (),
    artifacts: tuple[str, ...] = (),
    notes: tuple[str, ...] = ("human reviewed",),
) -> DisclosureReviewDecisionInput:
    return DisclosureReviewDecisionInput(
        announcement_id=announcement_id,
        symbol="600887",
        human_decision=human_decision,
        affected_domains=domains,
        affected_artifacts=artifacts,
        review_notes=notes,
    )


def _intake(
    queue: DisclosureReviewQueue,
    decisions: tuple[DisclosureReviewDecisionInput, ...],
    *,
    reviewed_at: datetime = REVIEWED_AT,
) -> DisclosureReviewIntake:
    return DisclosureReviewIntake(
        schema_version=DISCLOSURE_REVIEW_INTAKE_SCHEMA,
        queue_id=queue.queue_id,
        queue_sha256=disclosure_queue_sha256(queue),
        reviewed_at=reviewed_at,
        decisions=decisions,
        action=ACTION_NO_ORDER,
    )


def test_intake_round_trip_and_binding(tmp_path: Path):
    queue = _queue(tmp_path, [_row(announcement_id="1")])
    intake = _intake(queue, (_decision("1"),))

    restored = disclosure_review_intake_from_payload(
        __import__("json").loads(intake.to_json())
    )
    assert restored == intake
    reviews = build_disclosure_materiality_reviews(
        queue,
        restored,
        archive_root=tmp_path,
    )

    assert len(reviews) == 1
    assert reviews[0].action == ACTION_NO_ORDER
    assert reviews[0].decisions[0].source_sha256 == PDF_SHA256
    assert reviews[0].decisions[0].human_decision == DECISION_NOT_MATERIAL
    assert reviews[0].decisions[0].requires_recalculation is False


def test_recalculation_maps_effects_and_flags(tmp_path: Path):
    queue = _queue(tmp_path, [_row(announcement_id="1")])
    intake = _intake(
        queue,
        (
            _decision(
                "1",
                human_decision=DECISION_REQUIRES_RECALCULATION,
                domains=("balance_sheet_risk",),
                notes=("liability facts changed",),
            ),
        ),
    )

    review = build_disclosure_materiality_reviews(
        queue,
        intake,
        archive_root=tmp_path,
    )[0]
    decision = review.decisions[0]
    assert decision.requires_recalculation is True
    assert decision.requires_model_stale is True
    assert decision.requires_followup is False
    assert decision.affected_domains == ("balance_sheet_risk",)
    assert decision.action == ACTION_NO_ORDER


def test_recalculation_without_any_effect_fails(tmp_path: Path):
    queue = _queue(tmp_path, [_row(announcement_id="1")])
    intake = _intake(
        queue,
        (
            _decision(
                "1",
                human_decision=DECISION_REQUIRES_RECALCULATION,
                notes=("effect is required",),
            ),
        ),
    )

    with pytest.raises(ValueError, match="at least one affected"):
        build_disclosure_materiality_reviews(
            queue,
            intake,
            archive_root=tmp_path,
        )


def test_recalculation_unknown_domain_is_preserved_for_human_mapping(tmp_path: Path):
    queue = _queue(tmp_path, [_row(announcement_id="1")])
    intake = _intake(
        queue,
        (
            _decision(
                "1",
                human_decision=DECISION_REQUIRES_RECALCULATION,
                domains=("an_unknown_domain",),
                notes=("future domain requires explicit mapping",),
            ),
        ),
    )

    review = build_disclosure_materiality_reviews(
        queue,
        intake,
        archive_root=tmp_path,
    )[0]
    assert review.decisions[0].affected_domains == ("an_unknown_domain",)


def test_risk_monitor_and_decomposition_do_not_require_effect_mapping(tmp_path: Path):
    queue = _queue(
        tmp_path,
        [_row(announcement_id="1"), _row(announcement_id="2", timestamp=_timestamp(3))],
    )
    intake = _intake(
        queue,
        (
            _decision(
                "1",
                human_decision=DECISION_RISK_MONITOR,
                notes=("watch for follow-up",),
            ),
            _decision(
                "2",
                human_decision=DECISION_REQUIRES_DECOMPOSITION,
                notes=("split into sub-events",),
            ),
        ),
    )

    review = build_disclosure_materiality_reviews(
        queue,
        intake,
        archive_root=tmp_path,
    )[0]
    assert [item.human_decision for item in review.decisions] == [
        DECISION_RISK_MONITOR,
        DECISION_REQUIRES_DECOMPOSITION,
    ]
    assert all(item.requires_followup for item in review.decisions)


def test_missing_and_extra_decisions_fail(tmp_path: Path):
    queue = _queue(
        tmp_path,
        [_row(announcement_id="1"), _row(announcement_id="2", timestamp=_timestamp(3))],
    )
    missing = _intake(queue, (_decision("1"),))
    extra = _intake(queue, (_decision("1"), _decision("2"), _decision("3")))

    with pytest.raises(ValueError, match="missing=.*2"):
        build_disclosure_materiality_reviews(
            queue,
            missing,
            archive_root=tmp_path,
        )
    with pytest.raises(ValueError, match="extra=.*3"):
        build_disclosure_materiality_reviews(
            queue,
            extra,
            archive_root=tmp_path,
        )


def test_review_cannot_precede_publication(tmp_path: Path):
    queue = _queue(tmp_path, [_row(announcement_id="1", timestamp=_timestamp(20))])
    early = datetime(2026, 9, 2, 1, 0, tzinfo=CN_TZ)
    intake = _intake(queue, (_decision("1"),), reviewed_at=early)

    with pytest.raises(ValueError, match="cannot precede publication"):
        build_disclosure_materiality_reviews(
            queue,
            intake,
            archive_root=tmp_path,
        )


def test_queue_hash_mismatch_fails_closed(tmp_path: Path):
    queue = _queue(tmp_path, [_row(announcement_id="1")])
    other = DisclosureReviewIntake(
        schema_version=DISCLOSURE_REVIEW_INTAKE_SCHEMA,
        queue_id=queue.queue_id,
        queue_sha256="b" * 64,
        reviewed_at=REVIEWED_AT,
        decisions=(_decision("1"),),
        action=ACTION_NO_ORDER,
    )

    with pytest.raises(ValueError, match="queue hash"):
        build_disclosure_materiality_reviews(
            queue,
            other,
            archive_root=tmp_path,
        )


def test_missing_pdf_keeps_review_blocked(tmp_path: Path):
    queue = _queue(tmp_path, [_row(announcement_id="1", adjunct="")])
    intake = _intake(queue, (_decision("1"),))

    with pytest.raises(ValueError, match="incomplete"):
        build_disclosure_materiality_reviews(
            queue,
            intake,
            archive_root=tmp_path,
        )


def test_archived_pdf_bytes_must_match_recorded_hash(tmp_path: Path):
    queue = _queue(tmp_path, [_row(announcement_id="1")])
    intake = _intake(queue, (_decision("1"),))
    archived_pdf = next(tmp_path.rglob("*.pdf"))
    archived_pdf.write_bytes(b"%PDF-tampered")

    with pytest.raises(ValueError, match="hash mismatch"):
        build_disclosure_materiality_reviews(
            queue,
            intake,
            archive_root=tmp_path,
        )


def test_archived_pdf_must_still_exist(tmp_path: Path):
    queue = _queue(tmp_path, [_row(announcement_id="1")])
    intake = _intake(queue, (_decision("1"),))
    next(tmp_path.rglob("*.pdf")).unlink()

    with pytest.raises(ValueError, match="PDF is missing"):
        build_disclosure_materiality_reviews(
            queue,
            intake,
            archive_root=tmp_path,
        )


def test_archived_pdf_cannot_escape_archive_root(tmp_path: Path):
    queue = _queue(tmp_path, [_row(announcement_id="1")])
    scan = queue.scans[0]
    candidate = scan.validity_material_candidates[0]
    outside = tmp_path.parent / f"{tmp_path.name}-outside.pdf"
    outside.write_bytes(PDF_BYTES)
    escape_ref = next(
        dict(ref)
        for ref in candidate.evidence_refs
        if ref.get("source_status") == "SOURCE_ARCHIVED"
    )
    escape_ref["path"] = f"../{outside.name}"
    escaped_candidate = replace(
        candidate,
        evidence_refs=tuple(
            escape_ref if ref.get("id") == escape_ref["id"] else ref
            for ref in candidate.evidence_refs
        ),
    )
    escaped_queue = replace(
        queue,
        scans=(
            replace(
                scan,
                announcements=tuple(
                    escaped_candidate
                    if item.announcement_id == candidate.announcement_id
                    else item
                    for item in scan.announcements
                ),
            ),
        ),
    )
    intake = _intake(escaped_queue, (_decision("1"),))

    with pytest.raises(ValueError, match="not canonical"):
        build_disclosure_materiality_reviews(
            escaped_queue,
            intake,
            archive_root=tmp_path,
        )


def test_archived_pdf_requires_exactly_one_hashed_reference(tmp_path: Path):
    queue = _queue(tmp_path, [_row(announcement_id="1")])
    scan = queue.scans[0]
    candidate = scan.validity_material_candidates[0]
    archived = next(
        dict(ref)
        for ref in candidate.evidence_refs
        if ref.get("source_status") == "SOURCE_ARCHIVED"
    )
    duplicate = dict(archived)
    duplicate["id"] = f"{archived['id']}-duplicate"
    ambiguous_candidate = replace(
        candidate,
        evidence_refs=(*candidate.evidence_refs, duplicate),
    )
    ambiguous_queue = replace(
        queue,
        scans=(
            replace(
                scan,
                announcements=tuple(
                    ambiguous_candidate
                    if item.announcement_id == candidate.announcement_id
                    else item
                    for item in scan.announcements
                ),
            ),
        ),
    )
    intake = _intake(ambiguous_queue, (_decision("1"),))

    with pytest.raises(ValueError, match="exactly one PDF reference"):
        build_disclosure_materiality_reviews(
            ambiguous_queue,
            intake,
            archive_root=tmp_path,
        )


def test_archived_pdf_rejects_non_pdf_content(tmp_path: Path):
    queue = _queue(tmp_path, [_row(announcement_id="1")])
    intake = _intake(queue, (_decision("1"),))
    next(tmp_path.rglob("*.pdf")).write_bytes(b"not a pdf")

    with pytest.raises(ValueError, match="not a PDF"):
        build_disclosure_materiality_reviews(
            queue,
            intake,
            archive_root=tmp_path,
        )


def test_archived_pdf_rejects_source_url_identity_mismatch(tmp_path: Path):
    queue = _queue(tmp_path, [_row(announcement_id="1")])
    scan = queue.scans[0]
    candidate = scan.validity_material_candidates[0]
    archived = next(
        dict(ref)
        for ref in candidate.evidence_refs
        if ref.get("source_status") == "SOURCE_ARCHIVED"
    )
    archived["source_url"] = "https://evil.example/1.PDF"
    mismatched_candidate = replace(
        candidate,
        evidence_refs=tuple(
            archived if ref.get("id") == archived["id"] else ref
            for ref in candidate.evidence_refs
        ),
    )
    mismatched_queue = replace(
        queue,
        scans=(
            replace(
                scan,
                announcements=tuple(
                    mismatched_candidate
                    if item.announcement_id == candidate.announcement_id
                    else item
                    for item in scan.announcements
                ),
            ),
        ),
    )
    intake = _intake(mismatched_queue, (_decision("1"),))

    with pytest.raises(ValueError, match="source URL does not match"):
        build_disclosure_materiality_reviews(
            mismatched_queue,
            intake,
            archive_root=tmp_path,
        )
