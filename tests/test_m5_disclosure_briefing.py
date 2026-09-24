from __future__ import annotations

from value_investment_agent.m5_disclosure_briefing import (
    M5_DISCLOSURE_BRIEFING_SCHEMA,
    build_disclosure_review_briefing,
)
from value_investment_agent.m5_disclosure_review import ACTION_NO_ORDER

from test_m5_disclosure_review import _queue, _row


def test_briefing_binds_pdf_and_never_supplies_human_verdict(tmp_path):
    queue = _queue(
        tmp_path,
        [_row(announcement_id="1", title="关于会计政策变更的公告")],
    )

    result = build_disclosure_review_briefing(
        queue,
        archive_root=tmp_path,
        page_extractor=lambda _: ("会计政策 影响 财务报表",),
    )

    item = result["briefings"][0]
    assert result["schema_version"] == M5_DISCLOSURE_BRIEFING_SCHEMA
    assert result["boundary"] == "reading_aid_only_no_materiality_decision"
    assert item["human_decision"] is None
    assert item["action"] == ACTION_NO_ORDER
    assert item["page_count"] == 1
    assert item["literal_term_hits"][0]["term"] == "会计政策"
    assert item["literal_term_hits"][0]["hits"][0]["page"] == 1


def test_briefing_fails_closed_when_pdf_hash_changes(tmp_path):
    queue = _queue(tmp_path, [_row(announcement_id="1")])
    pdf = next((tmp_path / "600887" / "announcements").rglob("*.pdf"))
    pdf.write_bytes(b"%PDF-tampered")

    import pytest

    with pytest.raises(ValueError, match="hash mismatch"):
        build_disclosure_review_briefing(
            queue,
            archive_root=tmp_path,
            page_extractor=lambda _: ("ignored",),
        )
