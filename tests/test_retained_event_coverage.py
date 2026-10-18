"""TEST_ONLY retained public evidence replay; no external calls or approvals."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import json
import hashlib

import pytest

from value_investment_agent import disclosures
from value_investment_agent.application.product import daily_event_observation as service


START, END = date(2020, 1, 1), date(2020, 1, 2)


def read(path):
    return json.loads(path.read_bytes())


def write(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")
    return service.sha256_file(path)


def archive(root, monkeypatch, *, populated=False, two_pages=False):
    rows = []
    if populated:
        row = dict(secCode="600519", orgId="TEST_ONLY_org", announcementId="123", announcementTitle="TEST_ONLY filing",
            adjunctUrl="finalpage/2020-01-01/123.PDF", announcementTime=1577808000000)
        rows = [row]
        if two_pages:
            rows.append({**row, "announcementId": "124", "adjunctUrl": "finalpage/2020-01-01/124.PDF"})

        def synthetic_pdf(url, path):
            from pypdf import PdfWriter
            writer = PdfWriter()
            writer.add_blank_page(width=100, height=100)
            with path.open("wb") as stream:
                writer.write(stream)
            return service.sha256_file(path)

        monkeypatch.setattr(service, "download_disclosure_pdf", synthetic_pdf)
    else:
        monkeypatch.setattr(service, "download_disclosure_pdf", lambda *a: pytest.fail("no network"))
    def request(parameters, *, raw_response_sink):
        payload = dict(totalAnnouncement=len(rows), announcements=rows, hasMore=False)
        if two_pages and parameters["seDate"]:
            page = int(parameters["pageNum"])
            payload.update(announcements=rows[page - 1:page], hasMore=page < len(rows))
        if not parameters["seDate"]:
            payload = dict(totalAnnouncement=1, announcements=[dict(secCode="600519", orgId="TEST_ONLY_org")])
        body = json.dumps(payload).encode()
        raw_response_sink(body, dict(url=disclosures.SEARCH_URL, method="POST", request=parameters,
            page=int(parameters["pageNum"]), acquired_at=datetime.now(timezone.utc).isoformat(),
            sha256=hashlib.sha256(body).hexdigest(), size_bytes=len(body)))
        return payload

    monkeypatch.setattr(disclosures, "_request_json", request)
    def search(*args, **kwargs):
        return disclosures.search_announcement_window(*args, **kwargs, page_size=1 if two_pages else 30)

    monkeypatch.setattr(service, "search_announcement_window", search)
    observation = service.collect_daily_event_observation(root=root, symbol="600519",
        issuer_name="TEST_ONLY", start=START, end=END, output_dir=root / "runtime/events",
        retain_raw_index=True)
    monkeypatch.setattr(service, "search_announcement_window", lambda *a, **k: pytest.fail("no query"))
    return observation


def verify(root, observation, **overrides):
    args = dict(symbol="600519", required_from=START, required_to=END,
                now=datetime.now(timezone.utc))
    args.update(overrides)
    return service.verify_retained_event_coverage(root, observation, **args)


def rebind(root, observation):
    """Rehash the complete local chain; semantic forgeries must still fail."""
    folder = root / "runtime/events"
    manifest = read(folder / "raw-index-manifest.json")
    for record in manifest["responses"]:
        body = root / record["path"]
        record["sha256"] = service.sha256_file(body)
        record["size_bytes"] = body.stat().st_size
        metadata = {k: v for k, v in record.items() if k not in {"metadata_path", "metadata_sha256"}}
        record["metadata_sha256"] = write(root / record["metadata_path"], metadata)
    manifest["total_bytes"] = sum(r["size_bytes"] for r in manifest["responses"])
    write(folder / "raw-index-manifest.json", manifest)
    scan = read(folder / "event-scan.json")
    for ref in scan["evidence_refs"]:
        ref["sha256"] = service.sha256_file(root / ref["path"])
    for item in scan["announcements"]:
        for ref in item["evidence_refs"]:
            ref["sha256"] = service.sha256_file(root / ref["path"])
    observation["source_bindings"] = deepcopy(scan["evidence_refs"])
    observation["scan_binding"]["sha256"] = write(folder / "event-scan.json", scan)


@pytest.mark.parametrize("populated,two_pages", [(False, False), (True, False), (True, True)])
def test_real_collector_archive_replays_without_writes_or_approval(tmp_path, monkeypatch, populated, two_pages):
    observation = archive(tmp_path, monkeypatch, populated=populated, two_pages=two_pages)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    original = deepcopy(observation)
    result = verify(tmp_path, observation)
    assert result == dict(symbol="600519", scan_from=START.isoformat(), scan_to=END.isoformat(),
        coverage_status="COMPLETE", scan_binding=observation["scan_binding"], action="no_order",
        materiality_approved=False, model_revalidated=False)
    assert read(tmp_path / "runtime/events/event-scan.json")["status"] == "PENDING_HUMAN_REVIEW"
    assert observation == original
    result["scan_binding"]["sha256"] = "changed return value"
    assert observation == original
    assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before


@pytest.mark.parametrize("failure", ["symbol", "stale", "start", "partial", "snapshot", "future",
                                      "naive", "missing_raw", "tamper_raw", "missing_binding"])
def test_missing_partial_stale_unavailable_observations_fail_closed(tmp_path, monkeypatch, failure):
    observation = archive(tmp_path, monkeypatch)
    overrides = {}
    if failure == "symbol":
        overrides["symbol"] = "000001"
    elif failure == "stale":
        overrides["required_to"] = END + timedelta(days=1)
    elif failure == "start":
        overrides["required_from"] = START - timedelta(days=1)
    elif failure == "partial":
        observation["pagination_complete"] = False
    elif failure == "snapshot":
        observation["full_calendar_window_elapsed"] = False
    elif failure == "future":
        observation["acquired_at"] = "2099-01-01T00:00:00+00:00"
    elif failure == "naive":
        observation["acquired_at"] = "2026-01-01T00:00:00"
    elif failure == "missing_binding":
        observation.pop("scan_binding")
    else:
        path = tmp_path / "runtime/events/raw-index/response-0001.bin"
        if failure == "missing_raw":
            path.unlink()
        else:
            path.write_bytes(b"tampered")
    with pytest.raises(ValueError):
        verify(tmp_path, observation, **overrides)


@pytest.mark.parametrize("failure", ["issuer", "window", "scan_set", "scan_title", "count", "page",
    "metadata_url", "metadata_time", "filtered", "manifest_symbol", "duplicate_page", "coverage",
    "original", "same_day", "path_escape"])
def test_rehashed_forgeries_fail_semantic_replay(tmp_path, monkeypatch, failure):
    observation = archive(tmp_path, monkeypatch, populated=True)
    folder = tmp_path / "runtime/events"
    index = read(folder / "cninfo-index.json")
    manifest = read(folder / "raw-index-manifest.json")
    scan = read(folder / "event-scan.json")
    record = manifest["responses"][-1]
    body_path = tmp_path / record["path"]
    body = read(body_path)
    if failure == "issuer":
        body["announcements"][0]["secCode"] = "000001"
        index["announcements"] = body["announcements"]
    elif failure == "window":
        index["parameters"]["seDate"] = "2020-01-01~2020-01-01"
        record["request"]["seDate"] = index["parameters"]["seDate"]
    elif failure == "scan_set":
        scan["announcements"] = []
        observation["announcement_count"] = 0
    elif failure == "scan_title":
        scan["announcements"][0]["title"] = "FORGED"
    elif failure == "count":
        body["totalAnnouncement"] = 2
        index["total_announcements"] = 2
    elif failure == "page":
        record["request"]["pageNum"] = "2"
        record["page"] = 2
    elif failure == "metadata_url":
        record["url"] = "https://example.invalid/query"
    elif failure == "metadata_time":
        record["acquired_at"] = "2099-01-01T00:00:00+00:00"
    elif failure == "filtered":
        index["parameters"]["category"] = "annual_only"
        record["request"]["category"] = "annual_only"
    elif failure == "manifest_symbol":
        manifest["symbol"] = "000001"
    elif failure == "duplicate_page":
        manifest["responses"].append(deepcopy(record))
    elif failure == "coverage":
        scan["coverage_status"] = "INCOMPLETE"
    elif failure == "original":
        (folder / "600519-123.pdf").write_bytes(b"not a PDF")
    elif failure == "same_day":
        record["acquired_at"] = "2020-01-02T23:59:59+08:00"
    elif failure == "path_escape":
        record["path"] = "../outside.bin"
    write(body_path, body)
    write(folder / "cninfo-index.json", index)
    write(folder / "raw-index-manifest.json", manifest)
    write(folder / "event-scan.json", scan)
    if failure != "path_escape":
        rebind(tmp_path, observation)
    else:
        # Bind the escaped reference without opening anything outside the fixture.
        scan["evidence_refs"][1]["sha256"] = service.sha256_file(folder / "raw-index-manifest.json")
        observation["source_bindings"] = scan["evidence_refs"]
        observation["scan_binding"]["sha256"] = write(folder / "event-scan.json", scan)
    with pytest.raises(ValueError):
        verify(tmp_path, observation)


@pytest.mark.parametrize("target", ["event-scan.json", "cninfo-index.json", "raw-index-manifest.json",
                                    "raw-index/response-0001.bin", "raw-index/response-0001.json"])
def test_oversized_files_rejected_by_stat_before_read_or_hash(tmp_path, monkeypatch, target):
    observation = archive(tmp_path, monkeypatch)
    path = tmp_path / "runtime/events" / target
    limit = (32 * 1024 if target.endswith("0001.json") else
             service.MAX_CNINFO_RAW_RESPONSE_BYTES if target.endswith(".bin") else
             service.MAX_CNINFO_RAW_TOTAL_BYTES)
    # Sparse fixture: no large Python allocation, parse, or digest required.
    with path.open("r+b") as stream:
        stream.truncate(limit + 1)
    path_type = type(path)
    original_read = path_type.read_bytes
    original_hash = service.sha256_file

    def guarded_read(candidate):
        assert candidate != path, "oversized artifact was read"
        return original_read(candidate)

    def guarded_hash(candidate):
        assert candidate != path, "oversized artifact was hashed"
        return original_hash(candidate)

    monkeypatch.setattr(path_type, "read_bytes", guarded_read)
    monkeypatch.setattr(service, "sha256_file", guarded_hash)
    with pytest.raises(ValueError, match="byte bounds"):
        verify(tmp_path, observation)


@pytest.mark.parametrize("failure", ["wrong_org", "missing_identity", "ambiguous_identity", "fulltext",
    "page_size_zero", "page_size_large", "extra_filter", "has_more", "metadata_body_mismatch"])
def test_rehashed_empty_window_requires_identity_and_unfiltered_complete_pages(tmp_path, monkeypatch, failure):
    observation = archive(tmp_path, monkeypatch)
    folder = tmp_path / "runtime/events"
    index = read(folder / "cninfo-index.json")
    manifest = read(folder / "raw-index-manifest.json")
    discovery_path = tmp_path / manifest["responses"][0]["path"]
    window = manifest["responses"][-1]
    body_path = tmp_path / window["path"]
    body = read(body_path)
    if failure == "wrong_org":
        index["parameters"]["stock"] = "600519,FORGED_org"
    elif failure in {"missing_identity", "ambiguous_identity"}:
        discovery = read(discovery_path)
        if failure == "missing_identity":
            discovery["announcements"] = []
        else:
            discovery["announcements"].append(dict(secCode="600519", orgId="conflicting_org"))
        write(discovery_path, discovery)
    elif failure == "fulltext":
        index["parameters"]["tabName"] = "filtered"
    elif failure == "page_size_zero":
        index["parameters"]["pageSize"] = "0"
    elif failure == "page_size_large":
        index["parameters"]["pageSize"] = "31"
    elif failure == "extra_filter":
        index["parameters"]["unknownFilter"] = "hidden"
    elif failure == "has_more":
        body["hasMore"] = True
    elif failure == "metadata_body_mismatch":
        window["method"] = "GET"
    window["request"] = {**index["parameters"], "pageNum": "1"}
    write(body_path, body)
    write(folder / "cninfo-index.json", index)
    write(folder / "raw-index-manifest.json", manifest)
    rebind(tmp_path, observation)
    with pytest.raises(ValueError):
        verify(tmp_path, observation)


def test_missing_last_page_rejected_even_with_rehashed_scan_and_index(tmp_path, monkeypatch):
    observation = archive(tmp_path, monkeypatch, populated=True, two_pages=True)
    folder = tmp_path / "runtime/events"
    manifest = read(folder / "raw-index-manifest.json")
    manifest["responses"].pop()
    index = read(folder / "cninfo-index.json")
    index["announcements"].pop()
    # Keep official total=2; matching the shortened parsed list is insufficient.
    write(folder / "cninfo-index.json", index)
    write(folder / "raw-index-manifest.json", manifest)
    rebind(tmp_path, observation)
    with pytest.raises(ValueError):
        verify(tmp_path, observation)


def test_raw_total_budget_preflight_precedes_any_body_read_or_hash(tmp_path, monkeypatch):
    archive(tmp_path, monkeypatch)
    folder = tmp_path / "runtime/events"
    manifest = read(folder / "raw-index-manifest.json")
    index = read(folder / "cninfo-index.json")
    records = manifest["responses"]
    total = sum(record["size_bytes"] for record in records)
    assert all(record["size_bytes"] < total - 1 for record in records)
    monkeypatch.setattr(service, "MAX_CNINFO_RAW_TOTAL_BYTES", total - 1)
    monkeypatch.setattr(service, "sha256_file", lambda *a: pytest.fail("hash before aggregate preflight"))
    monkeypatch.setattr(type(folder), "read_bytes", lambda *a: pytest.fail("read before aggregate preflight"))
    with pytest.raises(ValueError, match="byte bounds"):
        service._replay_raw_index(tmp_path, folder, records, index)
