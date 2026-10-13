"""TL8-A: one hash-bound validity review; counterfactuals are never approvals."""
from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path

import pytest

from value_investment_agent.application.product import quote_bridge
from value_investment_agent.application.product.research_validity_review import (
    STATUS_BLOCKED_ON_HUMAN_EVENT_REVIEW, STATUS_REQUIRES_MATERIALITY_REVIEW,
    render_research_validity_review_markdown, review_research_validity,
)
from value_investment_agent.event_scan import (
    COVERAGE_COMPLETE, EVENT_SCAN_SCHEMA, PRE_MODEL_NONE, SCAN_PENDING_HUMAN_REVIEW,
    AnnouncementReview, EventScanResult,
)


ROOT = Path(__file__).resolve().parents[1]
REAL_REVIEW = ROOT / "docs/current/tl8-a-600887-research-validity-review-20261013.json"
TODAY = datetime(2026, 10, 13, 4, tzinfo=timezone.utc)
CUTOFF = date(2026, 10, 12)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, payload: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return _sha(path)


def _scan_payload(announcement: bool = False) -> dict:
    ref = {"id": "daily-index-600887", "path": "runtime/events/index.json",
           "sha256": "a" * 64, "source_url": "https://www.cninfo.com.cn/new/hisAnnouncement/query"}
    reviews = ()
    if announcement:
        reviews = (AnnouncementReview(
            announcement_id="1225511409",
            published_at=datetime(2026, 10, 12, 8, 30, tzinfo=timezone.utc),
            title="2026年第三季度报告", source_url="https://static.cninfo.com.cn/finalpage/a.PDF",
            rule_kind="unknown", review_status="PENDING_HUMAN_REVIEW",
            materiality_candidate=True, pre_model=False, evidence_refs=(ref,)),)
    scan = EventScanResult(
        schema_version=EVENT_SCAN_SCHEMA, symbol="600887", provider="cninfo",
        scan_from=date(2026, 10, 11), scan_to=CUTOFF, validity_from=date(2026, 10, 11),
        validity_to=CUTOFF, status=SCAN_PENDING_HUMAN_REVIEW, coverage_status=COVERAGE_COMPLETE,
        pre_model_review_status=PRE_MODEL_NONE, announcements=reviews,
        blockers=("This acquired query window does not replace earlier event/model/G3 reviews.",),
        evidence_refs=(ref,), retrieved_at=datetime(2026, 10, 13, 3, 0, tzinfo=timezone.utc),
        parser_version="cninfo-announcement-window-v1")
    return scan.as_policy()


def _fixture(tmp_path: Path, *, announcement: bool = False) -> dict:
    package = tmp_path / "runtime/cases/package.json"
    package_sha = _write(package, {
        "symbol": "600887", "name": "伊利股份",
        "package_version": "pending-600887-2026-10-11-test",
        "profile_id": "quality_compounder",
        "point_in_time": {"research_as_of": "2026-10-11", "report_period": "2026-06-30",
                          "available_at": "2026-10-11T08:00:00+00:00"},
        "model_validity_input": {"model_id": "residual-income-equity-shared-dated-v2",
                                 "valid_from": "2026-10-11", "events": [],
                                 "blockers": ["pending_complete_event_materiality_review"]}})
    scan = tmp_path / "runtime/events/event-scan.json"
    scan_sha = _write(scan, _scan_payload(announcement=announcement))
    return {"package": package, "package_sha256": package_sha,
            "scan": scan, "scan_sha256": scan_sha,
            "output": tmp_path / "runtime/reviews/review.json"}


def _run(tmp_path: Path, fixture: dict, **overrides):
    arguments = dict(root=tmp_path, symbol="600887", package_path=fixture["package"],
                     package_sha256=fixture["package_sha256"], review_cutoff=CUTOFF,
                     event_scan_path=fixture["scan"], event_scan_sha256=fixture["scan_sha256"],
                     output_path=fixture["output"], today=TODAY)
    arguments.update(overrides)
    return review_research_validity(**arguments)


def test_pending_empty_window_blocks_on_human_review(tmp_path):
    fixture = _fixture(tmp_path)
    review = _run(tmp_path, fixture)
    assert review["status"] == STATUS_BLOCKED_ON_HUMAN_EVENT_REVIEW
    assert review["action"] == "no_order"
    assert review["previous_research_version"]["research_as_of"] == "2026-10-11"
    assert review["facts_change"]["status"] == "NONE"
    assert review["material_events"]["status"] == "NONE_FOUND"
    assert review["model_validity_review"]["current"]["status"] == "UNKNOWN"
    assert "pending human review" in review["model_validity_review"]["current"]["blockers"][1]
    counterfactual = review["model_validity_review"]["if_event_window_reviewed"]
    assert counterfactual["status"] == "VALID"
    assert review["model_validity_review"]["single_missing_approval"] == "EVENT_WINDOW_HUMAN_REVIEW"
    gates = {item["gate"] for item in review["approval_required"]}
    assert gates == {"EVENT_WINDOW_HUMAN_REVIEW", "RESEARCH_VERSION_RE_REGISTRATION",
                     "G3_VALUATION_APPROVAL", "PRIVATE_PORTFOLIO_OR_IPS"}
    assert review["reopen_conditions"]
    assert json.loads(fixture["output"].read_text(encoding="utf-8")) == review


def test_announcements_keep_the_materiality_review_instead_of_a_counterfactual(tmp_path):
    fixture = _fixture(tmp_path, announcement=True)
    review = _run(tmp_path, fixture)
    assert review["status"] == STATUS_REQUIRES_MATERIALITY_REVIEW
    assert review["facts_change"]["status"] == "REVIEW_REQUIRED"
    assert review["model_validity_review"]["if_event_window_reviewed"] is None
    assert review["model_validity_review"]["single_missing_approval"] == (
        "MATERIALITY_REVIEW_PER_ANNOUNCEMENT")
    assert len(review["material_events"]["announcements"]) == 1


def test_review_renders_markdown_without_approval_language(tmp_path):
    fixture = _fixture(tmp_path)
    review = _run(tmp_path, fixture)
    markdown = render_research_validity_review_markdown(review)
    assert "BLOCKED_ON_HUMAN_EVENT_REVIEW" in markdown
    assert "反事实，不是批准" in markdown
    assert "action=no_order" in markdown


def test_hash_or_window_mismatches_fail_closed(tmp_path):
    fixture = _fixture(tmp_path)
    with pytest.raises(ValueError, match="研究包 Hash"):
        _run(tmp_path, fixture, package_sha256="0" * 64)
    with pytest.raises(ValueError, match="事件扫描 Hash"):
        _run(tmp_path, fixture, event_scan_sha256="0" * 64)
    with pytest.raises(ValueError, match="事件扫描未覆盖复核截止日"):
        _run(tmp_path, fixture, review_cutoff=date(2026, 10, 13))
    with pytest.raises(ValueError, match="研究截止日不能晚于复核截止日"):
        _run(tmp_path, fixture, review_cutoff=date(2026, 10, 10))


def test_quote_ladder_keeps_research_coverage_and_comparison_separate(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path)
    bundle = tmp_path / "runtime/quotes/bundle.json"
    bundle_sha = _write(bundle, {"finished_at": "2026-10-12T09:23:13+00:00"})

    def fake_admit(root, path, symbol, research_day, *, today):
        return None, None, {"status": "QUOTE_VERIFIED_BUT_RESEARCH_STALE",
                            "reason": "行情晚于当前 ResearchCase 截止日；须先更新官方事件和模型有效性",
                            "quote_date": "2026-10-12", "display_price": "27.96",
                            "collected_at": "2026-10-12T09:23:13+00:00",
                            "bundle_path": "runtime/quotes/bundle.json", "bundle_sha256": bundle_sha,
                            "source_evidence": [{"provider": "tencent", "source_url": "https://x",
                                                 "fetched_at": "2026-10-12T09:23:12+00:00",
                                                 "sha256": "b" * 64}]}

    monkeypatch.setattr(quote_bridge, "admit_quote_for_research", fake_admit)
    review = _run(tmp_path, fixture, quote_bundle=bundle, quote_bundle_sha256=bundle_sha)
    ladder = review["price_compatibility"]["ladder"]
    assert ladder["verified_quote"]["eligible"] is True
    assert ladder["research_compatible"]["eligible"] is False
    assert ladder["historical_reconstruction_eligible"]["eligible"] is False
    assert ladder["comparison_eligible"]["eligible"] is False
    assert ladder["formal_decision_eligible"]["eligible"] is False
    assert review["price_compatibility"]["comparison_eligible_within_review"]["eligible"] is False
    assert review["quote_sources"][0]["provider"] == "tencent"


@pytest.mark.skipif(not REAL_REVIEW.is_file(),
                    reason="the tracked TL8-A review artifact is not present in this checkout")
def test_real_600887_review_revalidates_its_evidence_chain():
    review = json.loads(REAL_REVIEW.read_text(encoding="utf-8"))
    assert review["schema_version"] == "research-validity-review-v1"
    assert review["action"] == "no_order"
    assert review["symbol"] == "600887"
    assert review["status"] == STATUS_BLOCKED_ON_HUMAN_EVENT_REVIEW
    assert review["model_validity_review"]["current"]["status"] == "UNKNOWN"
    for ref in review["evidence_refs"]:
        target = ROOT / ref["path"]
        if target.is_file():
            assert _sha(target) == ref["sha256"], ref["id"]
