from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from value_investment_agent.event_scan import (
    COVERAGE_COMPLETE,
    COVERAGE_INCOMPLETE,
    REVIEW_PENDING_HUMAN_REVIEW,
    SCAN_COMPLETE_NO_MATERIAL_EVENT,
    SCAN_PENDING_HUMAN_REVIEW,
    SCAN_UNKNOWN,
)
from value_investment_agent.m5_disclosure_queue import (
    DISCLOSURE_QUEUE_SCHEMA,
    DisclosureReviewQueue,
    build_cninfo_event_scan,
    classify_disclosure_title,
    disclosure_review_queue_from_payload,
    source_failure_event_scan,
)


RETRIEVED_AT = datetime(2026, 9, 24, 16, 0, tzinfo=timezone.utc)
SCAN_FROM = date(2026, 8, 27)
SCAN_TO = date(2026, 9, 24)


def _timestamp(hour: int = 1) -> int:
    return int(datetime(2026, 9, 2, hour, 0, tzinfo=timezone.utc).timestamp() * 1000)


def _row(
    *,
    announcement_id: str = "1225542001",
    title: str = "关于回购公司股份的公告",
    adjunct: str = "finalpage/2026-09-02/1225542001.PDF",
    timestamp: int | None = None,
    symbol: str = "600887",
) -> dict:
    return {
        "secCode": symbol,
        "announcementId": announcement_id,
        "announcementTitle": title,
        "announcementTime": timestamp if timestamp is not None else _timestamp(),
        "adjunctUrl": adjunct,
    }


def _payload(rows: list[dict], symbol: str = "600887") -> dict:
    return {
        "url": "https://www.cninfo.com.cn/new/hisAnnouncement/query",
        "total_announcements": len(rows),
        "announcements": rows,
    }


def _downloader(source_url: str, target: Path) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"%PDF-fixture")
    return "a" * 64


def test_title_classifier_keeps_unknown_and_routine_unknown_for_human_review():
    assert classify_disclosure_title("2026年半年度报告") == "financial_statement"
    assert classify_disclosure_title("关于回购公司股份的公告") == "buyback"
    assert classify_disclosure_title("董事会决议公告") == "governance"
    assert classify_disclosure_title("重大信息内部报告制度") == "governance"
    assert classify_disclosure_title("一项无法识别的临时事项") == "unknown"


def test_cninfo_scan_archives_index_and_pending_candidate_pdf(tmp_path):
    evidence_dir = tmp_path / "600887"
    scan = build_cninfo_event_scan(
        _payload(
            [
                _row(title="关于回购公司股份的公告"),
                _row(announcement_id="1225542002", title="董事会决议公告"),
            ]
        ),
        symbol="600887",
        scan_from=SCAN_FROM,
        scan_to=SCAN_TO,
        retrieved_at=RETRIEVED_AT,
        evidence_dir=evidence_dir,
        root=tmp_path,
        pdf_downloader=_downloader,
    )

    assert scan.status == SCAN_PENDING_HUMAN_REVIEW
    assert scan.coverage_status == COVERAGE_COMPLETE
    assert len(scan.announcements) == 2
    assert len(scan.pending_candidates if hasattr(scan, "pending_candidates") else scan.validity_material_candidates) == 1
    candidate = scan.validity_material_candidates[0]
    assert candidate.review_status == REVIEW_PENDING_HUMAN_REVIEW
    assert candidate.rule_kind == "buyback"
    assert candidate.evidence_refs[1]["sha256"] == "a" * 64
    assert len(scan.evidence_refs[0]["sha256"]) == 64
    assert (evidence_dir / "cninfo-index.json").is_file()
    assert (evidence_dir / "announcements" / "2026-09-02" / "1225542001.pdf").is_file()


def test_cninfo_scan_returns_no_material_candidate_only_when_rule_is_non_candidate(tmp_path):
    scan = build_cninfo_event_scan(
        _payload([_row(title="董事会决议公告")]),
        symbol="600887",
        scan_from=SCAN_FROM,
        scan_to=SCAN_TO,
        retrieved_at=RETRIEVED_AT,
        evidence_dir=tmp_path / "600887",
        root=tmp_path,
        pdf_downloader=_downloader,
    )
    assert scan.status == SCAN_COMPLETE_NO_MATERIAL_EVENT
    assert scan.coverage_status == COVERAGE_COMPLETE
    assert scan.validity_material_candidates == ()


def test_missing_candidate_pdf_is_fail_closed_not_silence(tmp_path):
    scan = build_cninfo_event_scan(
        _payload([_row(adjunct="")]),
        symbol="600887",
        scan_from=SCAN_FROM,
        scan_to=SCAN_TO,
        retrieved_at=RETRIEVED_AT,
        evidence_dir=tmp_path / "600887",
        root=tmp_path,
        pdf_downloader=_downloader,
    )
    assert scan.status == SCAN_PENDING_HUMAN_REVIEW
    assert scan.coverage_status == COVERAGE_INCOMPLETE
    assert scan.blockers
    assert "unavailable" in scan.blockers[0].lower()
    assert scan.validity_material_candidates[0].evidence_refs[1]["source_status"] == "SOURCE_UNAVAILABLE"


def test_duplicate_announcement_ids_are_rejected(tmp_path):
    with pytest.raises(ValueError, match="duplicate ids"):
        build_cninfo_event_scan(
            _payload([_row(), _row()]),
            symbol="600887",
            scan_from=SCAN_FROM,
            scan_to=SCAN_TO,
            retrieved_at=RETRIEVED_AT,
            evidence_dir=tmp_path / "600887",
            root=tmp_path,
            pdf_downloader=_downloader,
        )


def test_future_and_outside_window_timestamps_are_rejected(tmp_path):
    future = int(datetime(2026, 9, 25, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)
    with pytest.raises(ValueError, match="future"):
        build_cninfo_event_scan(
            _payload([_row(timestamp=future)]),
            symbol="600887",
            scan_from=SCAN_FROM,
            scan_to=SCAN_TO,
            retrieved_at=RETRIEVED_AT,
            evidence_dir=tmp_path / "future",
            root=tmp_path,
            pdf_downloader=_downloader,
        )

    old = int(datetime(2026, 8, 26, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)
    with pytest.raises(ValueError, match="outside"):
        build_cninfo_event_scan(
            _payload([_row(timestamp=old)]),
            symbol="600887",
            scan_from=SCAN_FROM,
            scan_to=SCAN_TO,
            retrieved_at=RETRIEVED_AT,
            evidence_dir=tmp_path / "outside",
            root=tmp_path,
            pdf_downloader=_downloader,
        )


def test_source_failure_scan_is_an_explicit_unknown_event():
    scan = source_failure_event_scan(
        symbol="600741",
        scan_from=SCAN_FROM,
        scan_to=SCAN_TO,
        retrieved_at=RETRIEVED_AT,
        error=RuntimeError("cninfo timeout"),
    )
    assert scan.status == SCAN_UNKNOWN
    assert scan.coverage_status == COVERAGE_INCOMPLETE
    assert scan.blockers and "cninfo timeout" in scan.blockers[0]


def test_queue_round_trip_and_validation(tmp_path):
    scans = tuple(
        build_cninfo_event_scan(
            _payload(
                [_row(title="关于股份回购进展情况的公告", symbol=symbol)],
                symbol=symbol,
            ),
            symbol=symbol,
            scan_from=SCAN_FROM,
            scan_to=SCAN_TO,
            retrieved_at=RETRIEVED_AT,
            evidence_dir=tmp_path / symbol,
            root=tmp_path,
            pdf_downloader=_downloader,
        )
        for symbol in ("600887", "600741")
    )
    queue = DisclosureReviewQueue(
        queue_id="fixture-queue",
        schema_version=DISCLOSURE_QUEUE_SCHEMA,
        provider="cninfo",
        parser_version="m5-cninfo-announcement-title-v1",
        scan_from=SCAN_FROM,
        scan_to=SCAN_TO,
        retrieved_at=RETRIEVED_AT,
        scans=scans,
    )
    restored = disclosure_review_queue_from_payload(queue.as_policy())
    assert restored.as_policy() == queue.as_policy()
    assert len(restored.pending_candidates) == 2
