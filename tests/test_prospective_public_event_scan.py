from __future__ import annotations

import importlib
import hashlib
import json
from pathlib import Path

import pytest

from value_investment_agent.disclosures import validate_cninfo_announcement_window


def _run_mock_scan(tmp_path, monkeypatch, payload, *, discovered_id="fallback"):
    scanner = importlib.import_module("scripts.cases.scan_prospective_public_event_window")
    monkeypatch.setattr(scanner, "ROOT", tmp_path)
    monkeypatch.setattr(scanner, "_cninfo_security_id", lambda _symbol: ("sse", "fallback"))
    monkeypatch.setattr(scanner, "_discover_security_id", lambda *_args: discovered_id)

    class Response:
        status_code = 200
        content = json.dumps(payload).encode()

        @staticmethod
        def raise_for_status():
            pass

    class Session:
        def post(self, *_args, **_kwargs):
            return Response()

        @staticmethod
        def close():
            pass

    monkeypatch.setattr(scanner.requests, "Session", Session)
    monkeypatch.setattr(
        "sys.argv",
        ["scan", "--symbol", "601088", "--name", "中国神华", "--start", "2026-03-31", "--end", "2026-03-31"],
    )
    return scanner.main()


def test_cninfo_announcement_window_accepts_china_local_date_boundaries():
    validate_cninfo_announcement_window(
        [{"announcementTime": 1774886400000}], "2026-03-31", "2026-03-31",
    )
    validate_cninfo_announcement_window(
        [{"announcementTime": 1774972799999}], "2026-03-31", "2026-03-31",
    )


@pytest.mark.parametrize("timestamp", [
    1774800000000,  # previous China calendar date
    1774972800000,  # next China calendar date
    None,
    "1774886400000",
])
def test_cninfo_announcement_window_rejects_outside_or_invalid_timestamps(timestamp):
    with pytest.raises(ValueError):
        validate_cninfo_announcement_window(
            [{"announcementTime": timestamp}], "2026-03-31", "2026-03-31",
        )


def test_scan_uses_cninfo_page_cap_and_archives_all_pages(tmp_path, monkeypatch, capsys):
    scanner = importlib.import_module("scripts.cases.scan_prospective_public_event_window")
    monkeypatch.setattr(scanner, "ROOT", tmp_path)
    monkeypatch.setattr(scanner, "_cninfo_security_id", lambda _symbol: ("szse", "fallback"))
    monkeypatch.setattr(scanner, "_discover_security_id", lambda *_args: "org-1")
    calls = []

    def page(start, count, has_more):
        return {
            "totalAnnouncement": 36,
            "hasMore": has_more,
            "announcements": [
                {"announcementId": str(index), "secCode": "000333", "announcementTime": 1774886400000}
                for index in range(start, start + count)
            ],
        }

    responses = [page(0, 30, True), page(30, 6, False)]

    class Response:
        status_code = 200

        def __init__(self, payload):
            self.content = json.dumps(payload).encode()

        def raise_for_status(self):
            pass

    class Session:
        trust_env = True

        def post(self, _url, *, data, **_kwargs):
            calls.append(dict(data))
            return Response(responses[len(calls) - 1])

        def close(self):
            pass

    monkeypatch.setattr(scanner.requests, "Session", Session)
    monkeypatch.setattr(
        "sys.argv",
        ["scan", "--symbol", "000333", "--name", "美的集团", "--start", "2026-03-31", "--end", "2026-03-31"],
    )

    assert scanner.main() == 0
    result = json.loads(capsys.readouterr().out)
    index_path = tmp_path / result["directory"] / "index.json"
    receipt_path = tmp_path / result["scan_receipt_path"]
    index = json.loads(index_path.read_text(encoding="utf-8"))
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert [query["pageNum"] for query in calls] == ["1", "2"]
    assert {query["pageSize"] for query in calls} == {"30"}
    assert result["coverage_status"] == "COMPLETE"
    assert result["total_announcements"] == result["returned_announcements"] == 36
    assert len({item["announcementId"] for item in index["announcements"]}) == 36
    assert len(index["pages"]) == 2
    assert all((tmp_path / ref["path"]).is_file() for ref in index["pages"])
    assert receipt["schema_version"] == "cninfo-exact-issuer-single-day-receipt-v1"
    assert receipt["capture_status"] == "SNAPSHOT_CAPTURED_NOT_FULL_DAY_COMPLETENESS"
    assert receipt["index_sha256"] == result["index_sha256"]
    assert receipt["pagination"]["page_count"] == 2
    assert len(receipt["requests"]) == 2
    assert all(request["response_sha256"] for request in receipt["requests"])
    assert hashlib.sha256(receipt_path.read_bytes()).hexdigest() == result["scan_receipt_sha256"]


def test_scan_does_not_publish_complete_index_for_out_of_window_record(tmp_path, monkeypatch):
    scanner = importlib.import_module("scripts.cases.scan_prospective_public_event_window")
    monkeypatch.setattr(scanner, "ROOT", tmp_path)
    monkeypatch.setattr(scanner, "_cninfo_security_id", lambda _symbol: ("sse", "fallback"))
    monkeypatch.setattr(scanner, "_discover_security_id", lambda *_args: "org-1")

    class Response:
        status_code = 200
        content = json.dumps({
                "totalAnnouncement": 1, "hasMore": False,
                "announcements": [{
                    "announcementId": "12345", "secCode": "601088",
                    "announcementTime": 1,
                }],
        }).encode()

        @staticmethod
        def raise_for_status():
            pass

    class Session:
        def post(self, *_args, **_kwargs):
            return Response()

        @staticmethod
        def close():
            pass

    monkeypatch.setattr(scanner.requests, "Session", Session)
    monkeypatch.setattr(
        "sys.argv",
        ["scan", "--symbol", "601088", "--name", "中国神华", "--start", "2026-03-31", "--end", "2026-03-31"],
    )

    with pytest.raises(ValueError, match="outside its requested date window"):
        scanner.main()
    assert not list(tmp_path.rglob("index.json"))


@pytest.mark.parametrize("payload", [
    {"hasMore": False, "announcements": []},
    {"totalAnnouncement": 0, "announcements": []},
    {"totalAnnouncement": 0, "hasMore": False},
    {"totalAnnouncement": True, "hasMore": False, "announcements": []},
    {"totalAnnouncement": "0", "hasMore": False, "announcements": []},
    {"totalAnnouncement": 0, "hasMore": 0, "announcements": []},
    {"totalAnnouncement": 0, "hasMore": False, "announcements": {}},
    {"totalAnnouncement": 1, "hasMore": False, "announcements": None},
    {"totalAnnouncement": 1, "hasMore": False, "announcements": "not-an-array"},
])
def test_scan_rejects_malformed_cninfo_response_without_complete_index(tmp_path, monkeypatch, payload):
    with pytest.raises(ValueError):
        _run_mock_scan(tmp_path, monkeypatch, payload, discovered_id="org-exact")
    assert not list(tmp_path.rglob("index.json"))


@pytest.mark.parametrize("announcement", [
    {"secCode": "601088", "announcementTime": 1774886400000},
    {"announcementId": None, "secCode": "601088", "announcementTime": 1774886400000},
    {"announcementId": "", "secCode": "601088", "announcementTime": 1774886400000},
    {"announcementId": "abc", "secCode": "601088", "announcementTime": 1774886400000},
    {"announcementId": "12.3", "secCode": "601088", "announcementTime": 1774886400000},
    {"announcementId": 123, "secCode": "601088", "announcementTime": 1774886400000},
])
def test_scan_rejects_missing_or_non_numeric_string_announcement_id(tmp_path, monkeypatch, announcement):
    payload = {
        "totalAnnouncement": 1, "hasMore": False,
        "announcements": [announcement],
    }
    with pytest.raises(ValueError, match="announcementId"):
        _run_mock_scan(tmp_path, monkeypatch, payload, discovered_id="org-exact")
    assert not list(tmp_path.rglob("index.json"))


@pytest.mark.parametrize("announcements", [None, []])
def test_scan_accepts_explicit_zero_result_with_discovered_exact_id(
    tmp_path, monkeypatch, capsys, announcements,
):
    payload = {"totalAnnouncement": 0, "hasMore": False, "announcements": announcements}
    assert _run_mock_scan(tmp_path, monkeypatch, payload, discovered_id="org-exact") == 0
    result = json.loads(capsys.readouterr().out)
    index_path = tmp_path / result["directory"] / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    assert result["coverage_status"] == index["coverage_status"] == "COMPLETE"
    assert index["organization_id"] == "org-exact"
    assert index["total_announcements"] == index["returned_announcements"] == 0
    assert len(index["pages"]) == 1


def test_scan_rejects_zero_result_when_organization_id_is_guessed_fallback(tmp_path, monkeypatch):
    payload = {"totalAnnouncement": 0, "hasMore": False, "announcements": []}
    with pytest.raises(ValueError, match="guessed organization ID fallback"):
        _run_mock_scan(tmp_path, monkeypatch, payload, discovered_id="fallback")
    assert not list(tmp_path.rglob("index.json"))


def test_scan_accepts_zero_result_when_hash_bound_identity_index_confirms_fallback(
    tmp_path, monkeypatch, capsys,
):
    scanner = importlib.import_module("scripts.cases.scan_prospective_public_event_window")
    monkeypatch.setattr(scanner, "ROOT", tmp_path)
    monkeypatch.setattr(scanner, "_cninfo_security_id", lambda _symbol: ("sse", "fallback"))
    monkeypatch.setattr(scanner, "_discover_security_id", lambda *_args: "fallback")
    identity_path = tmp_path / "runtime" / "identity.json"
    identity_path.parent.mkdir(parents=True)
    identity_bytes = json.dumps({"symbol": "600887", "organization_id": "fallback"}).encode()
    identity_path.write_bytes(identity_bytes)
    identity_sha256 = hashlib.sha256(identity_bytes).hexdigest()

    class Response:
        status_code = 200
        content = json.dumps({"totalAnnouncement": 0, "hasMore": False, "announcements": []}).encode()

        @staticmethod
        def raise_for_status():
            pass

    class Session:
        def post(self, *_args, **_kwargs):
            return Response()

        @staticmethod
        def close():
            pass

    monkeypatch.setattr(scanner.requests, "Session", Session)
    monkeypatch.setattr(
        "sys.argv",
        [
            "scan", "--symbol", "600887", "--name", "伊利股份",
            "--start", "2026-09-28", "--end", "2026-09-28",
            "--identity-index", "runtime/identity.json",
            "--identity-index-sha256", identity_sha256,
        ],
    )

    assert scanner.main() == 0
    result = json.loads(capsys.readouterr().out)
    receipt = json.loads((tmp_path / result["scan_receipt_path"]).read_text(encoding="utf-8"))
    assert receipt["issuer_identity_status"] == "HASH_BOUND_PREVIOUS_CNINFO_QUERY"
    assert receipt["identity_source"]["sha256"] == identity_sha256


@pytest.mark.parametrize(("raw_timestamp", "indexed_timestamp", "error", "scan_from", "scan_to", "category"), [
    (1774800000000, 1774800000000, "outside its requested date window", "2026-03-31", "2026-03-31", ""),
    (1774972800000, 1774972800000, "outside its requested date window", "2026-03-31", "2026-03-31", ""),
    (None, None, "timestamp must be Unix milliseconds", "2026-03-31", "2026-03-31", ""),
    (1774886400000, 1774972800000, "raw CNINFO pages do not reconcile", "2026-03-31", "2026-03-31", ""),
    (1774886400000, 1774886400000, "index scan dates differ from the independently supplied expected window", "2026-01-01", "2026-12-31", ""),
    (1774886400000, 1774886400000, "query filters differ from the complete exact-issuer window contract", "2026-03-31", "2026-03-31", "2"),
    (1774886400000, 1774886400000, None, "2026-03-31", "2026-03-31", ""),
])
def test_scan_evidence_builder_rechecks_dates_and_index_binding(
    tmp_path, monkeypatch, raw_timestamp, indexed_timestamp, error,
    scan_from, scan_to, category,
):
    builder = importlib.import_module("scripts.cases.build_prospective_baseline_scan_evidence")
    monkeypatch.setattr(builder, "ROOT", tmp_path)
    raw_path = tmp_path / "runtime" / "page.json"
    raw_path.parent.mkdir(parents=True)
    row = {
        "announcementId": "filing-1", "secCode": "601088",
        "announcementTime": raw_timestamp, "announcementTitle": "filing",
        "adjunctUrl": "finalpage/2026-03-31/filing-1.PDF",
    }
    raw_bytes = json.dumps({
        "totalAnnouncement": 1, "hasMore": False, "announcements": [row],
    }).encode()
    raw_path.write_bytes(raw_bytes)
    index_path = tmp_path / "runtime" / "index.json"
    index_path.write_text(json.dumps({
        "coverage_status": "COMPLETE",
        "coverage_scope": "CNINFO exact issuer and bounded date window only",
        "symbol": "601088", "organization_id": "org-1",
        "query": {
            "pageNum": "1", "pageSize": "30", "tabName": "fulltext",
            "column": "sse", "stock": "601088,org-1", "searchkey": "",
            "secid": "", "plate": "", "category": category, "trade": "",
            "seDate": f"{scan_from}~{scan_to}", "sortName": "", "sortType": "",
            "isHLtitle": "true",
        },
        "scan_from": scan_from, "scan_to": scan_to,
        "retrieved_at": "2026-04-01T00:00:00+00:00",
        "total_announcements": 1, "returned_announcements": 1,
        "pages": [{"page": 1, "path": "runtime/page.json", "sha256": hashlib.sha256(raw_bytes).hexdigest(), "returned_count": 1}],
        "announcements": [{**row, "announcementTime": indexed_timestamp}],
    }), encoding="utf-8")
    source_path = tmp_path / "runtime" / "filing.pdf"
    source_path.write_bytes(b"%PDF-1.4 test")

    output_path = tmp_path / "runtime" / "evidence.json"
    if error is None:
        result = builder.build(
            index_path, "601088", "filing-1", source_path, output_path,
            expected_start="2026-03-31", expected_end="2026-03-31",
        )
        assert result["action"] == "no_order"
        assert json.loads(output_path.read_text(encoding="utf-8"))["coverage_status"] == "COMPLETE"
    else:
        with pytest.raises(ValueError, match=error):
            builder.build(
                index_path, "601088", "filing-1", source_path, output_path,
                expected_start="2026-03-31", expected_end="2026-03-31",
            )
