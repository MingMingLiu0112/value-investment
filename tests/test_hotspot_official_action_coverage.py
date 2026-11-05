"""TEST_ONLY raw official archive fixtures; native verifier, no live queries."""
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path

import pytest

from test_retained_event_coverage import START, END, archive, read, rebind, write
from value_investment_agent.application.hotspot.corporate_action_coverage import (
    ACTION_FAMILIES, inspect_official_action_coverage,
)


def binding(root, observation):
    path = root / "runtime/events/observation.json"
    digest = write(path, observation)
    return dict(path=path.relative_to(root).as_posix(), sha256=digest)


def inspect(root, observation_binding=None, **overrides):
    args = dict(root=root, symbol="600519", start=START, end=END,
        now=datetime.now(timezone.utc), observation_binding=observation_binding)
    args.update(overrides)
    return inspect_official_action_coverage(**args)


def assert_not_admitted(result):
    assert result["action"] == "no_order"
    assert result["corporate_action_coverage"] == "UNKNOWN"
    assert result["price_comparability"] == "UNKNOWN"
    assert result["action_family_coverage"] == {key: "UNKNOWN" for key in ACTION_FAMILIES}
    for field in ("formal_eligibility", "historical_availability_proven",
                  "pdf_semantics_reverified", "effective_terms_verified", "opening_pending_actions_verified"):
        assert result[field] is False
    assert result["adjusted_protection_price"] is None
    assert result["original_protection_preserved"] is True
    assert result["strategy_validation"] == "NOT_PROVEN"
    assert "OPENING_PENDING_ACTION_STATE_MISSING" in result["gaps"]


@pytest.mark.parametrize("populated,two_pages", [(False, False), (True, False), (True, True)])
def test_complete_raw_scan_does_not_prove_effective_action_coverage(tmp_path, monkeypatch, populated, two_pages):
    observation = archive(tmp_path, monkeypatch, populated=populated, two_pages=two_pages)
    ref = binding(tmp_path, observation)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    result = inspect(tmp_path, ref)
    assert result["official_publication_coverage"] == "COMPLETE"
    assert result["announcement_count"] == (2 if two_pages else 1 if populated else 0)
    assert_not_admitted(result)
    assert result["source_available_at"] == observation["acquired_at"]
    for item in result["pending_announcements"]:
        assert item["review_status"] == "PENDING_EFFECTIVE_ACTION_REVIEW"
        assert item["effective_at"] is None and item["action_family"] == "UNCLASSIFIED"
        assert item["evidence_bindings"] and item["source_url"].startswith("https://static.cninfo.com.cn/")
    for ref in result["evidence_bindings"]:
        assert hashlib.sha256((tmp_path / ref["path"]).read_bytes()).hexdigest() == ref["sha256"]
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


@pytest.mark.parametrize("field", ["complete", "coverage_complete", "complete_corporate_action_coverage",
    "effective_terms_verified", "opening_pending_actions_verified", "historical_availability_proven"])
def test_rehashed_user_flags_cannot_grant_same_basis(tmp_path, monkeypatch, field):
    observation = archive(tmp_path, monkeypatch)
    observation[field] = True
    result = inspect(tmp_path, binding(tmp_path, observation))
    assert result["official_publication_coverage"] == "COMPLETE"
    assert_not_admitted(result)


@pytest.mark.parametrize("failure", ["hash", "future", "naive", "symbol", "missing_raw", "tampered_raw",
    "filtered_rehashed", "rehashed_missing_announcements", "pdf", "path_escape", "extra_binding_flag", "not_object"])
def test_bad_or_unavailable_source_is_not_coverage(tmp_path, monkeypatch, failure):
    observation = archive(tmp_path, monkeypatch, populated=True)
    if failure == "future":
        observation["acquired_at"] = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    elif failure == "naive":
        observation["acquired_at"] = "2020-01-03T00:00:00"
    elif failure == "symbol":
        observation["symbol"] = "600887"
    elif failure in {"missing_raw", "tampered_raw"}:
        raw = tmp_path / "runtime/events/raw-index/response-0001.bin"
        if failure == "missing_raw":
            raw.unlink()
        else:
            raw.write_bytes(b"tampered")
    elif failure == "filtered_rehashed":
        path = tmp_path / "runtime/events/cninfo-index.json"
        index = read(path)
        index["parameters"]["searchkey"] = "TEST_ONLY dividend"
        write(path, index)
        rebind(tmp_path, observation)
    elif failure == "rehashed_missing_announcements":
        path = tmp_path / "runtime/events/event-scan.json"
        scan = read(path)
        scan["announcements"] = []
        observation["announcement_count"] = 0
        write(path, scan)
        rebind(tmp_path, observation)
    elif failure == "pdf":
        scan = read(tmp_path / observation["scan_binding"]["path"])
        (tmp_path / scan["announcements"][0]["evidence_refs"][0]["path"]).write_bytes(b"not PDF")
        rebind(tmp_path, observation)
    ref = binding(tmp_path, observation if failure != "not_object" else [])
    if failure == "hash":
        ref["sha256"] = "0" * 64
    elif failure == "path_escape":
        ref["path"] = "../outside/observation.json"
    elif failure == "extra_binding_flag":
        ref["complete"] = True
    result = inspect(tmp_path, ref)
    assert result["official_publication_coverage"] == "INVALID_OR_UNAVAILABLE"
    assert result["announcement_count"] is None and result["evidence_bindings"] == []
    assert_not_admitted(result)


@pytest.mark.parametrize("start,end", [(START - timedelta(days=1), END),
    (START, END + timedelta(days=1)), (END + timedelta(days=2), END + timedelta(days=3))])
def test_verified_but_incomplete_price_formation_window_stays_partial(tmp_path, monkeypatch, start, end):
    ref = binding(tmp_path, archive(tmp_path, monkeypatch))
    result = inspect(tmp_path, ref, start=start, end=end)
    assert result["official_publication_coverage"] == "PARTIAL"
    assert "PUBLICATION_SCAN_DOES_NOT_COVER_PRICE_FORMATION_WINDOW" in result["gaps"]
    assert_not_admitted(result)


def test_covering_scan_may_be_wider_but_never_backdates_acquisition(tmp_path, monkeypatch):
    observation = archive(tmp_path, monkeypatch)
    ref = binding(tmp_path, observation)
    result = inspect(tmp_path, ref, start=END, end=END)
    assert result["official_publication_coverage"] == "COMPLETE"
    result = inspect(tmp_path, ref, now=datetime(2020, 1, 3, tzinfo=timezone.utc))
    assert result["official_publication_coverage"] == "INVALID_OR_UNAVAILABLE"
    assert_not_admitted(result)


def test_missing_is_not_an_empty_scan(tmp_path):
    result = inspect(tmp_path)
    assert result["official_publication_coverage"] == "MISSING"
    assert result["announcement_count"] is None
    assert_not_admitted(result)


@pytest.mark.parametrize("overrides", [dict(symbol="123"), dict(symbol="１２３４５６"),
    dict(now=datetime(2026, 1, 1)), dict(start=END, end=START),
    dict(end=date(2099, 1, 1))])
def test_invalid_request_is_rejected(tmp_path, overrides):
    with pytest.raises(ValueError):
        inspect(tmp_path, **overrides)


def test_optional_real_retained_official_window_remains_research_only():
    configured = os.environ.get("HOTSPOT_RETAINED_ROOT")
    if not configured:
        pytest.skip("Optional retained public archive not configured")
    root = Path(configured)
    path = root / "runtime/incremental-validity/600519/goal-20261023-completed-window/observation.json"
    if not path.is_file():
        pytest.skip("Retained raw official observation absent")
    result = inspect(root, dict(path=path.relative_to(root).as_posix(),
        sha256=hashlib.sha256(path.read_bytes()).hexdigest()),
        start=date(2026, 10, 11), end=date(2026, 10, 22))
    assert result["official_publication_coverage"] == "COMPLETE"
    assert_not_admitted(result)
