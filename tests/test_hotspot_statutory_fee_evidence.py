"""TEST_ONLY notice transport fixtures; date-aware fee arithmetic stays native."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path

import pytest

from value_investment_agent.infrastructure.hotspot import statutory_fee_evidence as subject
from value_investment_agent.application.hotspot import independent_validation
from test_hotspot_independent_validation import dependencies, execution


NOW = datetime(2026, 10, 23, 12, tzinfo=timezone.utc)


def archive(root, monkeypatch):
    folder = root / subject.ARCHIVE
    folder.mkdir(parents=True)
    records = []
    for source_id in subject.DIGESTS:
        raw = ("<html><body>TEST_ONLY<p>" + " ".join(subject.CLAUSES[source_id]) + "</p></body></html>").encode()
        path = folder / (source_id + ".html")
        path.write_bytes(raw)
        digest = sha256(raw).hexdigest()
        monkeypatch.setitem(subject.DIGESTS, source_id, digest)
        records.append(dict(source_id=source_id, path=path.relative_to(root).as_posix(),
            requested_url=subject.SOURCES[source_id], final_url=subject.SOURCES[source_id],
            sha256=digest, fetched_at=(NOW - timedelta(days=1)).isoformat()))
    manifest = folder / "manifest.json"
    manifest.write_text(json.dumps(records), encoding="utf-8")
    return manifest, records


def inspect(root, **overrides):
    return subject.inspect_statutory_fee_evidence(root=root, now=overrides.get("now", NOW))


def safe(result):
    assert result["action"] == "no_order"
    for key in ("complete_policy_continuity", "historical_availability_proven",
                "broker_invoice_verified", "full_cost_verified"):
        assert result[key] is False


def test_published_notices_replay_existing_fill_date_arithmetic(tmp_path, monkeypatch):
    archive(tmp_path, monkeypatch)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    result = inspect(tmp_path)
    assert result["source_status"] == "VERIFIED_RETAINED_OFFICIAL_NOTICES"
    assert result["published_components"]["sell_stamp_rate"] == "0.0005"
    assert result["published_components"]["transfer_rate"] == "0.00001"
    probes = result["arithmetic_probes"]
    assert [p["stamp_duty_unrounded_cny"] for p in probes] == ["100.000", "50.0000", "0"]
    assert [p["csdc_transfer_unrounded_cny"] for p in probes] == ["1.00000"] * 3
    assert [p["statutory_subtotal_unrounded_cny"] for p in probes] == ["101.00000", "51.00000", "1.00000"]
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    safe(result)


@pytest.mark.parametrize("damage", ["hash", "rehashed", "redirect", "requested_url", "future", "naive",
    "missing_source", "duplicate", "escape", "missing_file", "manifest_object", "oversize"])
def test_invalid_source_does_not_validate_statutory_rate_basis(tmp_path, monkeypatch, damage):
    manifest, rows = archive(tmp_path, monkeypatch)
    row = rows[0]
    path = tmp_path / row["path"]
    if damage in {"hash", "rehashed"}:
        path.write_bytes(b"maintenance page")
        if damage == "rehashed":
            row["sha256"] = sha256(path.read_bytes()).hexdigest()
    elif damage == "redirect":
        row["final_url"] = "https://example.com/maintenance"
    elif damage == "requested_url":
        row["requested_url"] = "https://example.com/fake"
    elif damage == "future":
        row["fetched_at"] = (NOW + timedelta(seconds=1)).isoformat()
    elif damage == "naive":
        row["fetched_at"] = "2026-10-22T12:00:00"
    elif damage == "missing_source":
        rows.pop()
    elif damage == "duplicate":
        rows.append(dict(row))
    elif damage == "escape":
        row["path"] = "../outside.html"
    elif damage == "missing_file":
        path.unlink()
    elif damage == "manifest_object":
        rows = dict(complete=True)
    manifest.write_text(json.dumps(rows), encoding="utf-8")
    if damage == "oversize":
        manifest.write_bytes(b" " * (128 * 1024 + 1))
    result = inspect(tmp_path)
    assert result["source_status"] == "INVALID_OR_UNAVAILABLE"
    assert result["published_components"] is None and result["source_bindings"] == []
    safe(result)


def test_http_success_or_rehashed_maintenance_body_cannot_substitute_policy(tmp_path, monkeypatch):
    manifest, records = archive(tmp_path, monkeypatch)
    row = records[-1]
    raw = b"<html><script>2022</script><body>Maintenance</body></html>"
    (tmp_path / row["path"]).write_bytes(raw)
    # TEST_ONLY emulate a newly reviewed hash; body must still contain the
    # exact effective date/rate/direction clauses rather than an HTTP 200 page.
    digest = sha256(raw).hexdigest()
    monkeypatch.setitem(subject.DIGESTS, row["source_id"], digest)
    row["sha256"] = digest
    manifest.write_text(json.dumps(records), encoding="utf-8")
    result = inspect(tmp_path)
    assert result["source_status"] == "INVALID_OR_UNAVAILABLE"
    safe(result)


def test_missing_archive_is_not_zero_cost_and_no_files_created(tmp_path):
    result = inspect(tmp_path)
    assert result["source_status"] == "MISSING" and result["published_components"] is None
    assert not list(tmp_path.iterdir())
    safe(result)


def test_source_path_guard_failure_stays_an_evidence_failure(tmp_path, monkeypatch):
    def rejected(*args):
        raise ValueError("Source outside allowed root")
    monkeypatch.setattr(subject, "require_inside", rejected)
    result = inspect(tmp_path)
    assert result["source_status"] == "INVALID_OR_UNAVAILABLE"
    assert result["published_components"] is None
    safe(result)


def test_notice_correspondence_cannot_grant_full_executable_cost_or_strategy(tmp_path, monkeypatch):
    archive(tmp_path, monkeypatch)
    proof = inspect(tmp_path)
    proof["declared_rates_match_notices"] = True
    dependencies(monkeypatch)
    data = execution()
    data["statutory_fee_evidence"] = proof
    monkeypatch.setattr(independent_validation, "_execution_evidence", lambda root, now: data)
    result = independent_validation.validate_current_hotspot_strategy(root=tmp_path, now=NOW)
    checks = {row["check"]: row["status"] for row in result["checks"]}
    assert checks["STATUTORY_FEE_NOTICE_CORRESPONDENCE"] == "PASS"
    assert checks["EXECUTABLE_COST_BASIS"] == "INSUFFICIENT_DATA"
    assert result["strict_pit_admitted"] is result["strict_oos_admitted"] is False
    assert result["formal_eligibility"] is result["trade_eligible"] is False


def test_optional_real_archived_statutory_fee_originals():
    configured = os.environ.get("HOTSPOT_FEE_EVIDENCE_ROOT")
    if not configured:
        pytest.skip("Real public fee archive root not configured")
    result = inspect(Path(configured))
    assert result["source_status"] == "VERIFIED_RETAINED_OFFICIAL_NOTICES", result
    assert len(result["source_bindings"]) == 4
    safe(result)
