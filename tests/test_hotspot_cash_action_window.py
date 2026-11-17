"""TEST_ONLY raw archives; native coverage, source and cash checks are retained."""
from datetime import date, datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path

import pytest

from test_hotspot_cash_event_mapping import _fixture, _binding, PAGES
from test_retained_event_coverage import rebind
from value_investment_agent import disclosures
from value_investment_agent.application.product import daily_event_observation as collector
from value_investment_agent.application.hotspot.corporate_action_coverage import inspect_cash_action_window
from value_investment_agent.application.hotspot.cash_event_mapping import build_cash_event_mapping
from value_investment_agent.application.hotspot.report_text import render_cash_event_mapping_markdown
from value_investment_agent.infrastructure.hotspot import cash_implementation


def setup_archive(root, monkeypatch, *, related=None, include_implementation=True):
    registry, event = _fixture(root, monkeypatch)
    retained = root / "runtime/implementation.pdf"
    retained.parent.mkdir()
    retained.write_bytes((root / "implementation.pdf").read_bytes())
    event["evidence"][0]["path"] = retained.relative_to(root).as_posix()
    registry.write_text(json.dumps(dict(backtest_ready=False, events=[event])), encoding="utf-8")
    rows = []
    if include_implementation:
        rows.append(dict(secCode="600519", orgId="TEST_ONLY_org", announcementId="999999",
            announcementTitle="TEST_ONLY 实施公告", adjunctUrl="finalpage/2025-12-11/999999.PDF",
            announcementTime=int(datetime(2025, 12, 11, tzinfo=timezone.utc).timestamp() * 1000)))
    if related is not None:
        rows.append(dict(secCode="600519", orgId="TEST_ONLY_org", announcementId="999998",
            announcementTitle="TEST_ONLY 普通标题", adjunctUrl="finalpage/2025-12-12/999998.PDF",
            announcementTime=int(datetime(2025, 12, 12, tzinfo=timezone.utc).timestamp() * 1000)))

    def request(parameters, *, raw_response_sink):
        payload = dict(totalAnnouncement=len(rows), announcements=rows, hasMore=False)
        if not parameters["seDate"]:
            payload = dict(totalAnnouncement=1, announcements=[dict(secCode="600519", orgId="TEST_ONLY_org")])
        body = json.dumps(payload).encode()
        raw_response_sink(body, dict(url=disclosures.SEARCH_URL, method="POST", request=parameters,
            page=int(parameters["pageNum"]), acquired_at=datetime.now(timezone.utc).isoformat(),
            sha256=sha256(body).hexdigest(), size_bytes=len(body)))
        return payload

    monkeypatch.setattr(disclosures, "_request_json", request)
    monkeypatch.setattr(collector, "download_disclosure_pdf", lambda url, path:
        (path.write_bytes(retained.read_bytes()), sha256(path.read_bytes()).hexdigest())[1])
    monkeypatch.setattr(cash_implementation, "extract_pages", lambda path, limit:
        [f"证券代码：600519 TEST_ONLY {related}"] if path.name == "600519-999998.pdf" else PAGES)
    observation = collector.collect_daily_event_observation(root=root, symbol="600519", issuer_name="TEST_ONLY",
        start=date(2025, 12, 11), end=date(2025, 12, 19), output_dir=root / "runtime/events",
        retain_raw_index=True, retained_originals=[dict(path=retained.relative_to(root).as_posix(),
            sha256=sha256(retained.read_bytes()).hexdigest(), source_url=event["evidence"][0]["url"])])
    path = root / "runtime/events/observation.json"
    return registry, dict(path=path.relative_to(root).as_posix(), sha256=sha256(path.read_bytes()).hexdigest()), observation


def inspect(root, registry, observation, **overrides):
    args = dict(root=root, symbol="600519", record_date=date(2025, 12, 18),
        registry_binding=_binding(registry, root, available_at=datetime.now(timezone.utc)),
        start=date(2025, 12, 18), end=date(2025, 12, 19), now=datetime.now(timezone.utc),
        observation_binding=observation)
    args.update(overrides)
    return inspect_cash_action_window(**args)


def safe(result):
    assert result["price_comparability"] == "UNKNOWN" and result["no_change"] is None
    assert result["comparison_allowed"] is result["formal_eligibility"] is False
    assert result["opening_state_verified"] is result["revision_absence_proven"] is False
    assert result["action"] == "no_order"


@pytest.mark.parametrize("related", [None, "普通经营信息"])
def test_native_complete_window_binds_event_but_cannot_prove_no_change(tmp_path, monkeypatch, related):
    registry, ref, _ = setup_archive(tmp_path, monkeypatch, related=related)
    result = inspect(tmp_path, registry, ref)
    assert result["status"] == "IMPLEMENTATION_AND_PUBLICATION_WINDOW_BOUND", result
    assert result["implementation_in_index"] is True
    assert result["related_document_count"] == (0 if related is None else 1)
    assert result["revision_status"] == "ABSENCE_NOT_PROVEN"
    safe(result)


@pytest.mark.parametrize("word", ["更正", "修订", "取消", "撤销"])
def test_neutral_title_cannot_hide_body_amendment_from_mapping(tmp_path, monkeypatch, word):
    registry, ref, _ = setup_archive(tmp_path, monkeypatch, related=f"关于临2025-001的{word}说明")
    result = inspect(tmp_path, registry, ref)
    assert result["status"] == "REVISION_REVIEW_REQUIRED", result
    assert result["related_document_count"] == 1
    mapped = build_cash_event_mapping(root=tmp_path, symbol="600519", record_date=date(2025, 12, 18),
        registry_binding=_binding(registry, tmp_path, available_at=datetime.now(timezone.utc)),
        now=datetime.now(timezone.utc), original_protection="100", current_price="99",
        original_basis_date=date(2025, 12, 18), current_basis_date=date(2025, 12, 19),
        official_event_observation_binding=ref)
    assert mapped["mapping"] is None
    assert "REVISION_OR_CANCELLATION_REQUIRES_LINKAGE" in mapped["blockers"]
    assert "REVISION_REVIEW_REQUIRED" in render_cash_event_mapping_markdown(mapped)
    safe(result)


def test_zero_announcements_not_proof_of_no_actions_or_no_revisions(tmp_path, monkeypatch):
    registry, ref, _ = setup_archive(tmp_path, monkeypatch, include_implementation=False)
    result = inspect(tmp_path, registry, ref)
    assert result["publication_coverage"]["announcement_count"] == 0
    assert result["status"] == "IMPLEMENTATION_NOT_IN_INDEX"
    safe(result)


def test_short_window_or_future_archive_cannot_enable_comparison(tmp_path, monkeypatch):
    registry, ref, _ = setup_archive(tmp_path, monkeypatch)
    for overrides in (dict(start=date(2025, 12, 1)), dict(now=datetime(2025, 12, 20, tzinfo=timezone.utc))):
        result = inspect(tmp_path, registry, ref, **overrides)
        assert result["status"] == "WINDOW_UNAVAILABLE"
        safe(result)


def test_rehashed_omission_of_indexed_document_is_rejected(tmp_path, monkeypatch):
    registry, ref, observation = setup_archive(tmp_path, monkeypatch, related="取消说明")
    path = tmp_path / observation["scan_binding"]["path"]
    scan = json.loads(path.read_bytes())
    scan["announcements"].pop()
    path.write_text(json.dumps(scan), encoding="utf-8")
    observation["announcement_count"] = 1
    rebind(tmp_path, observation)
    obs_path = tmp_path / ref["path"]
    obs_path.write_text(json.dumps(observation), encoding="utf-8")
    ref["sha256"] = sha256(obs_path.read_bytes()).hexdigest()
    result = inspect(tmp_path, registry, ref)
    assert result["status"] == "WINDOW_UNAVAILABLE"
    safe(result)


def test_real_sealed_cash_window_and_recent_window_negative():
    configured = os.environ.get("HOTSPOT_CASH_WINDOW_ROOT")
    if not configured:
        pytest.skip("Real sealed implementation window not configured")
    root = Path(configured)
    path = root / "runtime/swing-official-cash-window-20261023/6697ebf039cb4ce385e9f682be9869f8/observation.json"
    registry = root / "docs/reviewed-cash-distributions.json"
    ref = dict(path=path.relative_to(root).as_posix(), sha256=sha256(path.read_bytes()).hexdigest())
    result = inspect(root, registry, ref)
    assert result["status"] == "IMPLEMENTATION_AND_PUBLICATION_WINDOW_BOUND", result
    assert result["implementation_proof"]["terms"]["cash_per_share"] == "23.957"
    assert result["publication_coverage"]["announcement_count"] == 1
    safe(result)
    negative = inspect(root, registry, ref, start=date(2025, 11, 1))
    assert negative["status"] == "WINDOW_UNAVAILABLE"
    safe(negative)


def test_real_recent_complete_zero_window_does_not_cover_earlier_implementation():
    configured = os.environ.get("HOTSPOT_RETAINED_ROOT")
    if not configured:
        pytest.skip("Retained real recent official window not configured")
    root = Path(configured)
    path = root / "runtime/incremental-validity/600519/goal-20261023-completed-window/observation.json"
    if not path.is_file():
        pytest.skip("Retained recent official window absent")
    ref = dict(path=path.relative_to(root).as_posix(), sha256=sha256(path.read_bytes()).hexdigest())
    result = inspect(root, root / "docs/reviewed-cash-distributions.json", ref,
        start=date(2026, 10, 21), end=date(2026, 10, 22))
    assert result["publication_coverage"]["official_publication_coverage"] == "COMPLETE"
    assert result["publication_coverage"]["announcement_count"] == 0
    assert result["status"] == "IMPLEMENTATION_PUBLICATION_NOT_COVERED"
    safe(result)
