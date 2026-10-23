"""TL8-A: one hash-bound validity review; counterfactuals are never approvals."""
from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import runpy
import sys

import pytest

from value_investment_agent.application.product import quote_bridge
from value_investment_agent.application.product.research_validity_review import (
    STATUS_BLOCKED_ON_HUMAN_EVENT_REVIEW, STATUS_REQUIRES_MATERIALITY_REVIEW,
    STATUS_BLOCKED_ON_EVENT_COVERAGE, STATUS_BLOCKED_ON_MODEL_VALIDITY,
    STATUS_INCREMENTAL_REVIEW_COMPLETE_PRICE_BRIDGE_PENDING,
    review_registered_research_validity,
    render_research_validity_review_markdown, review_research_validity,
)
from value_investment_agent.event_scan import (
    COVERAGE_COMPLETE, EVENT_SCAN_SCHEMA, PRE_MODEL_NONE, SCAN_PENDING_HUMAN_REVIEW,
    SCAN_COMPLETE_NO_MATERIAL_EVENT,
    REVIEW_REVIEWED_NO_MATERIAL_CANDIDATE,
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
    payload = _scan_payload(announcement=announcement)
    source_sha = _write(tmp_path / "runtime/events/index.json", {"TEST_ONLY": "retained official query response"})
    payload["evidence_refs"][0]["sha256"] = source_sha
    for item in payload["announcements"]:
        item["evidence_refs"][0]["sha256"] = source_sha
    scan_sha = _write(scan, payload)
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


def _completed_fixture(tmp_path):
    fixture = _fixture(tmp_path)
    package = json.loads(fixture["package"].read_text(encoding="utf-8"))
    package["model_validity_input"]["blockers"] = []
    fixture["package_sha256"] = _write(fixture["package"], package)
    scan = json.loads(fixture["scan"].read_text(encoding="utf-8"))
    scan.update(status=SCAN_COMPLETE_NO_MATERIAL_EVENT, blockers=[])
    fixture["scan_sha256"] = _write(fixture["scan"], scan)
    return fixture


def test_completed_incremental_window_reuses_model_without_changing_research_or_approval(tmp_path):
    fixture = _completed_fixture(tmp_path)
    before = {path: path.read_bytes() for path in tmp_path.rglob("*.json")}
    review = _run(tmp_path, fixture, output_path=None)
    incremental = review["incremental_review"]
    assert incremental["status"] == "MODEL_VALID_AT_REVIEW_CUTOFF"
    assert incremental["model_recalculation_required"] is False
    assert incremental["model_valid_through"] == CUTOFF.isoformat()
    assert incremental["original_model_as_of"] == "2026-10-11"
    assert incremental["research_cutoff_changed"] is incremental["g3_approval_granted"] is False
    assert incremental["formal_eligibility"] is incremental["price_bridge_changed"] is False
    assert review["model_validity_review"]["current"]["status"] == "VALID"
    assert all(row["status"] == "VERIFIED" for row in review["event_source_audit"])
    assert review["previous_research_version"]["package_sha256"] == fixture["package_sha256"]
    assert review["price_compatibility"]["comparison_eligible_within_review"]["eligible"] is False
    assert {path: path.read_bytes() for path in tmp_path.rglob("*.json")} == before


@pytest.mark.parametrize("failure", ["missing", "tampered", "unbound", "escape", "incomplete"])
def test_empty_scan_cannot_claim_unchanged_facts_without_retained_coverage(tmp_path, failure):
    fixture = _completed_fixture(tmp_path)
    source = tmp_path / "runtime/events/index.json"
    scan = json.loads(fixture["scan"].read_text(encoding="utf-8"))
    if failure == "missing":
        source.unlink()
    elif failure == "tampered":
        source.write_text("changed", encoding="utf-8")
    elif failure == "unbound":
        scan["evidence_refs"][0].pop("sha256")
    elif failure == "escape":
        scan["evidence_refs"][0]["path"] = "../outside.json"
    else:
        scan["coverage_status"] = "INCOMPLETE"
    fixture["scan_sha256"] = _write(fixture["scan"], scan)
    review = _run(tmp_path, fixture)
    assert review["status"] == STATUS_BLOCKED_ON_EVENT_COVERAGE
    assert review["model_validity_review"]["current"]["status"] == "UNKNOWN"
    assert review["facts_change"]["status"] == review["assumptions_change"]["status"] == "UNKNOWN"
    assert review["material_events"]["status"] == "UNKNOWN"
    assert review["model_validity_review"]["if_event_window_reviewed"] is None
    assert review["incremental_review"]["model_recalculation_required"] is None


@pytest.mark.parametrize("field,value", [
    ("clock", "2026-10-13T04:00:00"),
    ("clock", "2026-10-11T04:00:00+00:00"),
    ("package_available", "2099-10-13T04:00:00+00:00"),
    ("scan_available", "2099-10-13T04:00:00+00:00"),
    ("validity_to", "2026-10-11"),
    ("scan_to", "2026-10-13"),
])
def test_incremental_review_rejects_future_or_mismatched_evidence_before_writing(tmp_path, field, value):
    fixture = _completed_fixture(tmp_path)
    overrides = {}
    if field == "clock":
        overrides["today"] = datetime.fromisoformat(value)
    elif field == "package_available":
        package = json.loads(fixture["package"].read_text(encoding="utf-8"))
        package["point_in_time"]["available_at"] = value
        fixture["package_sha256"] = _write(fixture["package"], package)
    else:
        scan = json.loads(fixture["scan"].read_text(encoding="utf-8"))
        scan["retrieved_at" if field == "scan_available" else field] = value
        fixture["scan_sha256"] = _write(fixture["scan"], scan)
    with pytest.raises(ValueError):
        _run(tmp_path, fixture, **overrides)
    assert not fixture["output"].exists()


@pytest.mark.parametrize("context", ["blockers", "events"])
def test_empty_new_window_preserves_registered_model_context(tmp_path, context):
    fixture = _completed_fixture(tmp_path)
    package = json.loads(fixture["package"].read_text(encoding="utf-8"))
    package["model_validity_input"][context] = (["MODEL_APPLICABILITY_NOT_PROVEN"] if context == "blockers" else [
        {"event_date": "2026-10-11", "kind": "financial_report", "description": "TEST_ONLY unresolved report",
         "material": True, "evidence_refs": [{"id": "TEST_ONLY-original-event"}]}])
    fixture["package_sha256"] = _write(fixture["package"], package)
    review = _run(tmp_path, fixture)
    assert review["status"] == STATUS_BLOCKED_ON_MODEL_VALIDITY
    assert review["incremental_review"]["model_recalculation_required"] is None
    assert review["price_compatibility"]["comparison_eligible_within_review"]["eligible"] is False
    assert review["model_validity_review"]["current"]["blockers"]


def test_source_availability_uses_instants_instead_of_iso_string_order(tmp_path):
    fixture = _completed_fixture(tmp_path)
    package = json.loads(fixture["package"].read_text(encoding="utf-8"))
    package["point_in_time"]["available_at"] = "2026-10-13T10:00:00+08:00"
    fixture["package_sha256"] = _write(fixture["package"], package)
    review = _run(tmp_path, fixture)
    assert datetime.fromisoformat(review["source_availability_cutoff"]) == datetime(2026, 10, 13, 3, tzinfo=timezone.utc)


def test_reviewed_nonmaterial_disclosure_reuses_existing_review(tmp_path):
    fixture = _completed_fixture(tmp_path)
    scan = json.loads(fixture["scan"].read_text(encoding="utf-8"))
    announcement = _scan_payload(announcement=True)["announcements"][0]
    announcement.update(materiality_candidate=False, review_status=REVIEW_REVIEWED_NO_MATERIAL_CANDIDATE,
                        evidence_refs=scan["evidence_refs"])
    scan["announcements"] = [announcement]
    fixture["scan_sha256"] = _write(fixture["scan"], scan)
    review = _run(tmp_path, fixture)
    assert review["incremental_review"]["status"] == "MODEL_VALID_AT_REVIEW_CUTOFF"
    assert review["facts_change"]["status"] == "REVIEWED_NO_MODEL_INVALIDATION"
    assert review["approval_required"][0]["required"] is False
    markdown = render_research_validity_review_markdown(review)
    assert "`EVENT_WINDOW_HUMAN_REVIEW`" not in markdown
    assert "`G3_VALUATION_APPROVAL`" in markdown


def test_incremental_model_validity_does_not_admit_later_quote(tmp_path, monkeypatch):
    fixture = _completed_fixture(tmp_path)
    bundle = tmp_path / "runtime/quotes/bundle.json"
    bundle_sha = _write(bundle, {"TEST_ONLY": True})

    def admit(root, path, symbol, research_day, *, today):
        assert research_day == "2026-10-11"
        return None, None, {"status": "QUOTE_VERIFIED_BUT_RESEARCH_STALE", "quote_date": "2026-10-12"}

    monkeypatch.setattr(quote_bridge, "admit_quote_for_research", admit)
    review = _run(tmp_path, fixture, quote_bundle=bundle, quote_bundle_sha256=bundle_sha)
    assert review["status"] == STATUS_INCREMENTAL_REVIEW_COMPLETE_PRICE_BRIDGE_PENDING
    assert review["incremental_review"]["model_recalculation_required"] is False
    assert review["incremental_review"]["g3_approval_granted"] is False
    assert review["price_compatibility"]["comparison_eligible_within_review"]["eligible"] is False


def _registered_fixture(tmp_path, *, fallback=False):
    fixture = _completed_fixture(tmp_path)
    package = json.loads(fixture["package"].read_text(encoding="utf-8"))
    ref = {"id": "TEST_ONLY-scan", "path": fixture["scan"].relative_to(tmp_path).as_posix(),
           "sha256": fixture["scan_sha256"]}
    package["model_validity_input"]["event_scan_evidence_refs" if fallback else "event_scan_ref"] = (
        [ref] if fallback else ref)
    fixture["package_sha256"] = _write(fixture["package"], package)
    _write(tmp_path / "config/current-quote-bridge.json", {
        "schema_version": "current-quote-bridge-v1", "action": "no_order", "quotes": {
            "600887": {"research_package": fixture["package"].relative_to(tmp_path).as_posix(),
                       "research_package_sha256": fixture["package_sha256"]},
            "000651": {"research_package": "missing.json", "research_package_sha256": "0" * 64}}})
    return fixture


def _progress_fixture(tmp_path):
    fixture = _registered_fixture(tmp_path)
    output = tmp_path / "runtime/reviews/daily.json"
    result = review_registered_research_validity(root=tmp_path, review_cutoff=CUTOFF,
        today=TODAY, output_path=output)
    binding = {"path": output.relative_to(tmp_path).as_posix(), "sha256": _sha(output)}
    return fixture, output, binding, result


def _progress(tmp_path, binding, **overrides):
    from value_investment_agent.application.product.research_validity_review import replay_registered_review_progress
    options = dict(root=tmp_path, binding=binding, started_at=TODAY.replace(hour=3).isoformat(),
        finished_at=TODAY.replace(hour=5).isoformat(), now=TODAY.replace(hour=6))
    return replay_registered_review_progress(**{**options, **overrides})


def test_daily_machine_review_progress_replays_and_preserves_missing_company(tmp_path):
    _, output, binding, _ = _progress_fixture(tmp_path)
    original = output.read_bytes()
    progress = _progress(tmp_path, binding)
    assert progress["status"] == "SOURCE_REPLAYED"
    assert progress["checked_at"] == TODAY.isoformat()
    assert progress["research_cutoff_changed"] is False
    assert progress["formal_eligibility"] is False
    rows = {row["symbol"]: row for row in progress["rows"]}
    assert rows["600887"]["research_as_of"] == "2026-10-11"
    assert rows["600887"]["scan_through"] == CUTOFF.isoformat()
    # The legacy fixture has no raw pagination receipt, hence no complete-day claim.
    assert rows["600887"]["event_coverage_through"] is None
    assert rows["600887"]["event_coverage_status"] == "UNCONFIRMED"
    assert rows["600887"]["facts_change_status"] == "UNKNOWN"
    assert rows["600887"]["formal_eligibility"] is False
    assert rows["000651"]["model_validity_status"] == "UNKNOWN"
    assert rows["000651"]["scan_through"] is None
    assert output.read_bytes() == original
    assert _progress(tmp_path, binding) == progress


@pytest.mark.parametrize("changed", ["result", "rehashed_result", "source", "package", "pointer", "missing"])
def test_daily_review_progress_rejects_changed_dependencies(tmp_path, changed):
    fixture, output, binding, result = _progress_fixture(tmp_path)
    if changed in {"result", "rehashed_result"}:
        result["reviews"][0]["model_validity_status"] = "VALID"
        _write(output, result)
        if changed == "rehashed_result":
            binding["sha256"] = _sha(output)
    elif changed == "source":
        (tmp_path / "runtime/events/index.json").write_text("changed", encoding="utf-8")
    elif changed == "package":
        fixture["package"].write_text("{}", encoding="utf-8")
    elif changed == "pointer":
        _write(tmp_path / "config/current-quote-bridge.json", {"quotes": {}})
    else:
        output.unlink()
    progress = _progress(tmp_path, binding)
    assert progress["status"] == "UNVERIFIED"
    assert progress["checked_at"] is None and progress["rows"] == []
    assert progress["formal_eligibility"] is False


@pytest.mark.parametrize("overrides", [
    {"started_at": "2026-10-13T05:00:00+00:00"},
    {"finished_at": "2026-10-13T03:00:00+00:00"},
    {"finished_at": "2026-10-13T07:00:00+00:00"},
    {"started_at": "2026-10-13T03:00:00"},
    {"now": TODAY.replace(tzinfo=None)},
])
def test_daily_review_progress_cannot_borrow_another_run_or_future_clock(tmp_path, overrides):
    _, _, binding, _ = _progress_fixture(tmp_path)
    assert _progress(tmp_path, binding, **overrides)["status"] == "UNVERIFIED"


def test_daily_status_consumes_replayed_research_receipt_without_advancing_research(tmp_path):
    from value_investment_agent.application.product.daily_refresh import read_latest_run
    _, _, binding, _ = _progress_fixture(tmp_path)
    path = tmp_path / ".tmp/daily-workbench-latest-run.json"
    receipt = {"schema_version": "daily-workbench-run-v1", "action": "no_order",
        "status": "PARTIAL", "mode": "SAFE_REFRESH", "notes": [],
        "started_at": TODAY.replace(hour=3).isoformat(),
        "finished_at": TODAY.replace(hour=5).isoformat(), "research_validity_review": binding,
        "node_receipt_scope": "COMMAND_EXECUTION_ONLY_NOT_DATA_ADMISSION", "nodes": [{
            "sequence": 1, "command": "scripts/current/review_registered_research_validity.py",
            "operation": "RUN", "started_at": TODAY.replace(minute=0, second=0).isoformat(),
            "finished_at": TODAY.replace(minute=1).isoformat(), "execution_status": "SUCCEEDED",
            "exit_code": 0, "output_status": "JSON_OBJECT",
            "output_binding": {**binding, "review_cutoff": CUTOFF.isoformat(), "symbols": ["000651", "600887"]}}]}
    _write(path, receipt)
    progress = read_latest_run(tmp_path)["research_review"]
    assert progress["status"] == "SOURCE_REPLAYED"
    assert progress["checked_at"] == TODAY.isoformat()
    assert progress["formal_eligibility"] is False
    receipt.pop("research_validity_review")
    _write(path, receipt)
    assert read_latest_run(tmp_path)["research_review"]["status"] == "RECEIPT_UNAVAILABLE"
    receipt["nodes"] = []
    _write(path, receipt)
    assert read_latest_run(tmp_path)["research_review"]["status"] == "NOT_RECORDED"


@pytest.mark.parametrize("failure", ["no_node", "failed", "another_artifact", "another_time", "read_only", "cutoff", "symbols"])
def test_daily_progress_must_belong_to_this_successful_execution_node(tmp_path, failure):
    from value_investment_agent.application.product.daily_refresh import read_latest_run
    _progress_fixture(tmp_path)
    output = tmp_path / "runtime/reviews/daily.json"
    binding = {"path": output.relative_to(tmp_path).as_posix(), "sha256": _sha(output)}
    node = {"sequence": 1, "command": "scripts/current/review_registered_research_validity.py",
        "operation": "RUN", "started_at": TODAY.isoformat(), "finished_at": TODAY.replace(minute=1).isoformat(),
        "execution_status": "SUCCEEDED", "exit_code": 0, "output_status": "JSON_OBJECT",
        "output_binding": {**binding, "review_cutoff": CUTOFF.isoformat(), "symbols": ["000651", "600887"]}}
    receipt = {"schema_version": "daily-workbench-run-v1", "action": "no_order", "status": "PARTIAL",
        "mode": "SAFE_REFRESH", "notes": [], "started_at": TODAY.replace(hour=3).isoformat(),
        "finished_at": TODAY.replace(hour=5).isoformat(), "research_validity_review": binding,
        "node_receipt_scope": "COMMAND_EXECUTION_ONLY_NOT_DATA_ADMISSION", "nodes": [node]}
    if failure == "no_node":
        receipt["nodes"] = []
    elif failure == "failed":
        node.update(execution_status="FAILED", exit_code=2)
    elif failure == "another_artifact":
        node["output_binding"]["sha256"] = "0" * 64
    elif failure == "another_time":
        node["started_at"] = TODAY.replace(second=1).isoformat()
    elif failure == "read_only":
        receipt["mode"] = "READ_ONLY"
    elif failure == "cutoff":
        node["output_binding"]["review_cutoff"] = "2026-10-11"
    else:
        node["output_binding"]["symbols"] = ["600887"]
    _write(tmp_path / ".tmp/daily-workbench-latest-run.json", receipt)
    progress = read_latest_run(tmp_path)["research_review"]
    assert progress["status"] == "UNVERIFIED"
    assert progress["checked_at"] is None and progress["rows"] == []


@pytest.mark.parametrize("populated,prior_pending", [(False, False), (True, False), (False, True)])
def test_daily_progress_replays_raw_pagination_before_claiming_event_coverage(tmp_path, monkeypatch, populated, prior_pending):
    from datetime import timedelta
    from test_retained_event_coverage import archive, START, END

    observation = archive(tmp_path, monkeypatch, populated=populated)
    now = datetime.now(timezone.utc)
    package = {"symbol": "600519", "name": "TEST_ONLY", "package_version": "TEST_ONLY",
        "profile_id": "quality_compounder", "point_in_time": {
            "research_as_of": START.isoformat(), "report_period": START.isoformat(),
            "available_at": "2020-01-01T00:00:00+00:00"},
        "model_validity_input": {"model_id": "TEST_ONLY", "valid_from": START.isoformat(),
                                 "events": [], "blockers": []}}
    if prior_pending:
        scan_path = tmp_path / observation["scan_binding"]["path"]
        scan = json.loads(scan_path.read_bytes())
        old_ref = {"path": "runtime/prior-pending.json",
                   "sha256": _write(tmp_path / "runtime/prior-pending.json", scan)}
        package["model_validity_input"]["event_scan_ref"] = old_ref
        scan.update(status=SCAN_COMPLETE_NO_MATERIAL_EVENT, blockers=[])
        observation["scan_binding"]["sha256"] = _write(scan_path, scan)
        _write(tmp_path / "runtime/events/observation.json", observation)
    package_ref = {"path": "runtime/package.json", "sha256": _write(tmp_path / "runtime/package.json", package)}
    observation_ref = {"path": "runtime/events/observation.json",
                       "sha256": _sha(tmp_path / "runtime/events/observation.json")}
    supplement = {"schema_version": "incremental-validity-binding-v1", "symbol": "600519",
        "package_ref": package_ref, "research_as_of": START.isoformat(), "review_cutoff": END.isoformat(),
        "model_id": "TEST_ONLY", "observation_ref": observation_ref,
        "scan_ref": observation["scan_binding"], "action": "no_order"}
    supplement_ref = {"path": "runtime/supplement.json",
                      "sha256": _write(tmp_path / "runtime/supplement.json", supplement)}
    _write(tmp_path / "config/current-quote-bridge.json", {"schema_version": "current-quote-bridge-v1",
        "action": "no_order", "quotes": {"600519": {"research_package": package_ref["path"],
            "research_package_sha256": package_ref["sha256"], "incremental_validity_binding": supplement_ref}}})
    output = tmp_path / "runtime/reviews/daily.json"
    report = review_registered_research_validity(root=tmp_path, review_cutoff=END, today=now,
        output_path=output, incremental_bindings=[supplement_ref])
    binding = {"path": output.relative_to(tmp_path).as_posix(), "sha256": _sha(output)}
    options = dict(started_at=(now - timedelta(minutes=1)).isoformat(), finished_at=now.isoformat(), now=now)
    progress = _progress(tmp_path, binding, **options)
    assert progress["status"] == "SOURCE_REPLAYED"
    row = progress["rows"][0]
    assert row["event_coverage_through"] == END.isoformat()
    assert row["event_coverage_status"] == "COMPLETE"
    assert row["announcement_count"] == int(populated)
    assert row["facts_change_status"] == ("REVIEW_REQUIRED" if populated else "NONE")
    assert row["model_validity_status"] == "UNKNOWN"
    assert row["model_recalculation_required"] is None
    if not prior_pending:
        assert row["materiality_review_required"] is True
    else:
        assert report["reviews"][0]["model_validity_status"] == "VALID"
        (tmp_path / "runtime/prior-pending.json").write_text("{}", encoding="utf-8")
        assert _progress(tmp_path, binding, **options)["status"] == "UNVERIFIED"
    assert row["formal_eligibility"] is False
    raw = next((tmp_path / "runtime/events/raw-index").glob("*.bin"))
    raw.write_bytes(b"changed raw response")
    assert _progress(tmp_path, binding, **options)["status"] == "UNVERIFIED"


@pytest.mark.parametrize("fallback", [False, True])
def test_registered_reviews_isolate_symbols_and_reuse_immutable_artifact(tmp_path, fallback):
    _registered_fixture(tmp_path, fallback=fallback)
    output = tmp_path / "runtime/reviews/registered.json"
    arguments = dict(root=tmp_path, review_cutoff=CUTOFF, today=TODAY, output_path=output)
    review = review_registered_research_validity(**arguments)
    rows = {row["symbol"]: row for row in review["reviews"]}
    assert rows["000651"]["status"] == "PENDING"
    assert rows["000651"]["model_validity_status"] == "UNKNOWN"
    assert rows["600887"]["review"]["incremental_review"]["model_recalculation_required"] is False
    before = output.read_bytes()
    arguments["today"] = TODAY.replace(hour=5)
    assert review_registered_research_validity(**arguments) == review
    assert output.read_bytes() == before
    with pytest.raises(FileExistsError):
        review_registered_research_validity(**{**arguments, "symbols": ["000651"]})


@pytest.mark.parametrize("failure", ["missing", "short", "tampered", "unbound"])
def test_registered_review_missing_or_insufficient_scan_is_unknown(tmp_path, failure):
    fixture = _registered_fixture(tmp_path)
    if failure == "missing":
        fixture["scan"].unlink()
    elif failure == "tampered":
        fixture["scan"].write_text("{}", encoding="utf-8")
    elif failure == "unbound":
        package = json.loads(fixture["package"].read_text(encoding="utf-8"))
        package["model_validity_input"].pop("event_scan_ref")
        digest = _write(fixture["package"], package)
        pointer = tmp_path / "config/current-quote-bridge.json"
        payload = json.loads(pointer.read_text(encoding="utf-8"))
        payload["quotes"]["600887"]["research_package_sha256"] = digest
        _write(pointer, payload)
    result = review_registered_research_validity(root=tmp_path,
        review_cutoff=date(2026, 10, 13) if failure == "short" else CUTOFF, today=TODAY,
        output_path=tmp_path / "runtime/reviews/registered.json", symbols=["600887"])
    row = result["reviews"][0]
    assert row["status"] == "PENDING"
    assert row["model_validity_status"] == "UNKNOWN"
    assert row["review"] is None
    assert row["reason"]
    assert row["g3_approval_granted"] is False


def test_registered_review_cli_calls_application_and_reports_audit_hash(tmp_path, monkeypatch, capsys):
    _registered_fixture(tmp_path)
    namespace = runpy.run_path(str(ROOT / "scripts/current/review_registered_research_validity.py"))
    main = namespace["main"]
    main.__globals__["ROOT"] = tmp_path
    monkeypatch.setattr(sys, "argv", ["review_registered_research_validity.py",
        "--review-cutoff", CUTOFF.isoformat(), "--symbol", "600887",
        "--output", "runtime/reviews/cli.json"])
    assert main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["artifact_sha256"] == _sha(tmp_path / "runtime/reviews/cli.json")
    assert result["action"] == "no_order"
    assert result["reviews"][0]["model_validity_status"] == "VALID"


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
