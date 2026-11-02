"""Optional no-cache replay; synthetic bytes stay explicitly TEST_ONLY."""
from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

import pytest
import requests

from value_investment_agent.infrastructure.screening import value_evidence_enrichment_v1 as adapter
from value_investment_agent.application.research import value_evidence_enrichment_v1 as app
from test_value_evidence_enrichment_v1 import source

NOW = datetime(2026, 11, 2, tzinfo=timezone.utc)


def snapshot(root):
    return {p.relative_to(root).as_posix(): (p.read_bytes() if p.is_file() else None, p.stat().st_mtime_ns)
            for p in root.rglob("*")}


def extract(root, source, **kwargs):
    return adapter.extract_retained_annual(root, source, evaluation_at=NOW,
        cache_dir=root / ".tmp/cache", **kwargs)


def test_no_cache_cold_calls_do_not_create_directory(tmp_path, source, monkeypatch):
    calls = []
    native = adapter.extract_pages
    def count(*args, **kwargs):
        calls.append(True)
        return native(*args, **kwargs)
    monkeypatch.setattr(adapter, "extract_pages", count)
    before = snapshot(tmp_path)
    first = extract(tmp_path, source, write_cache=False)
    second = extract(tmp_path, source, write_cache=False, verify_cache=True)
    assert first == second and first["reused"] is False
    assert len(calls) == 2
    assert not (tmp_path / ".tmp/cache").exists()
    assert snapshot(tmp_path) == before


def test_default_write_reuse_and_readonly_bypasses_corrupt_cache(tmp_path, source, monkeypatch):
    first = extract(tmp_path, source)
    cache_file = next((tmp_path / ".tmp/cache").glob("*.json"))
    before = snapshot(tmp_path)
    second = extract(tmp_path, source)
    assert second == dict(first, reused=True)
    assert snapshot(tmp_path) == before
    cache_file.write_bytes(b"TEST_ONLY_CORRUPT_CACHE")
    before = snapshot(tmp_path)
    native_read = Path.read_bytes
    def forbid_cache_read(path):
        if path == cache_file:
            raise AssertionError("Readonly replay must not read existing cache")
        return native_read(path)
    with monkeypatch.context() as patch:
        patch.setattr(Path, "read_bytes", forbid_cache_read)
        cold = extract(tmp_path, source, write_cache=False, verify_cache=True)
    assert cold == first and snapshot(tmp_path) == before
    with pytest.raises(ValueError):
        extract(tmp_path, source)


@pytest.mark.parametrize("cache", ["cache-outside-dot-tmp", "../outside"])
def test_readonly_still_checks_cache_boundary(tmp_path, source, cache):
    before = snapshot(tmp_path)
    with pytest.raises(ValueError, match="cache|outside"):
        adapter.extract_retained_annual(tmp_path, source, evaluation_at=NOW,
                                       cache_dir=tmp_path / cache, write_cache=False)
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("damage", ["hash", "future", "byte_budget", "page_budget"])
def test_readonly_still_validates_original_time_and_budgets(tmp_path, source, damage):
    kwargs = {}
    if damage == "hash":
        source = replace(source, sha256="0"*64)
    elif damage == "future":
        source = replace(source, available_at="2099-01-01T00:00:00+00:00")
    elif damage == "byte_budget":
        kwargs["max_bytes"] = 1
    elif damage == "page_budget":
        kwargs["max_pages"] = 0
    before = snapshot(tmp_path)
    with pytest.raises(ValueError):
        extract(tmp_path, source, write_cache=False, **kwargs)
    assert snapshot(tmp_path) == before


def test_enrich_and_consume_forward_option_default_unchanged(tmp_path, source, monkeypatch):
    seen = []
    native = app.extract_retained_annual
    def observed(*args, **kwargs):
        seen.append(kwargs["write_cache"])
        return native(*args, **kwargs)
    monkeypatch.setattr(app, "extract_retained_annual", observed)
    before = snapshot(tmp_path)
    readonly = app.enrich_retained_company(tmp_path, source, [], evaluation_at=NOW,
                                           cache_dir=tmp_path / ".tmp/cache", write_cache=False)
    merged, reports = app.consume_retained_enrichment(tmp_path, [], [asdict(source)],
                                                      evaluation_at=NOW, write_cache=False)
    assert seen == [False, False] and snapshot(tmp_path) == before
    assert merged == [] and len(reports) == 1
    default = app.enrich_retained_company(tmp_path, source, [], evaluation_at=NOW,
                                         cache_dir=tmp_path / ".tmp/cache")
    assert default == readonly
    expected = app.consume_retained_enrichment(tmp_path, [], [asdict(source)], evaluation_at=NOW)
    assert expected == (merged, reports)
    assert seen == [False, False, True, True]
    assert list((tmp_path / ".tmp/cache").glob("*.json"))
    assert list((tmp_path / ".tmp/value-enrichment-consumption").glob("*.json"))


@pytest.mark.parametrize("index,digest", [
    ("0", "474905deeaf0f875fc0a1b097a626c0c7852c427faadc5d7fc7816cbf45ea288"),
    ("1", "d17b8c541c42f65d092317093eb0cfbb5aeed4f44eafa2d2f6182041cdcdbaac"),
])
def test_real_original_cold_readonly_extraction_and_consumption(tmp_path, monkeypatch, index, digest):
    configured = os.environ.get("OFFICIAL_FUNDING_REAL_ROOT")
    if not configured:
        if os.environ.get("OFFICIAL_FUNDING_REAL_REQUIRED") == "1":
            pytest.fail("Explicit original root required")
        pytest.skip("Set OFFICIAL_FUNDING_REAL_ROOT to reuse public PDFs")
    root = Path(configured)
    receipt_path = root / ("runtime/public-evidence/20261030-a-first/"+index+"/acquisition/receipt.json")
    declaration = json.loads(receipt_path.read_bytes())["source"]
    original = root / declaration["path"]
    raw = original.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == digest == declaration["sha256"]
    original_state = (original.stat().st_mtime_ns, receipt_path.read_bytes(), receipt_path.stat().st_mtime_ns)
    copy = tmp_path / "original.pdf"
    copy.write_bytes(raw)
    source = adapter.RetainedAnnualSource(**dict(declaration, path="original.pdf"))
    def no_network(*args, **kwargs):
        raise AssertionError("No network during retained-original replay")
    monkeypatch.setattr(requests.sessions.Session, "request", no_network)
    before = snapshot(tmp_path)
    cold = extract(tmp_path, source, write_cache=False)
    assert cold["page_count"] > 100 and cold["reused"] is False
    assert cold["candidates"] and cold["balance_total_candidates"]
    merged, reports = app.consume_retained_enrichment(tmp_path, [], [asdict(source)],
                                                      evaluation_at=NOW, write_cache=False)
    assert len(reports) == 1 and reports[0]["formal_eligibility"] is False
    assert snapshot(tmp_path) == before
    assert not (tmp_path / ".tmp").exists()
    assert original.read_bytes() == raw
    assert (original.stat().st_mtime_ns, receipt_path.read_bytes(), receipt_path.stat().st_mtime_ns) == original_state
    # Default mode still creates/reuses the same packet after the readonly run.
    first = extract(tmp_path, source)
    cached = extract(tmp_path, source)
    assert first == cold and cached == dict(cold, reused=True)
    default_consumption = app.consume_retained_enrichment(
        tmp_path, [], [asdict(source)], evaluation_at=NOW)
    assert default_consumption == (merged, reports)
