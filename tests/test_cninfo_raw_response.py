"""Synthetic HTTP bodies exercise the same CNINFO query/parser path."""
import hashlib
import io
import json

import pytest
import requests

from value_investment_agent import disclosures


def mock_http(monkeypatch, bodies):
    calls = []
    pending = iter(bodies)

    class Session:
        def post(self, url, **kwargs):
            calls.append((url, kwargs))
            response = requests.Response()
            response.status_code = 200
            response.url = url
            response.encoding = "utf-8"
            response.raw = io.BytesIO(next(pending))
            return response

        def close(self):
            pass

    monkeypatch.setattr(disclosures.requests, "Session", Session)
    return calls


def test_request_retains_received_content_not_reserialized_json(monkeypatch):
    body = b'{ "announcements" : [], "totalAnnouncement": 0 }\r\n'
    calls = mock_http(monkeypatch, [body])
    retained = []
    payload = disclosures._request_json({"pageNum": "1"},
        raw_response_sink=lambda *args: retained.append(args))
    raw, metadata = retained[0]
    assert raw == body and raw != json.dumps(payload).encode()
    assert metadata["sha256"] == hashlib.sha256(body).hexdigest()
    assert metadata["size_bytes"] == len(body)
    assert metadata["url"] == disclosures.SEARCH_URL
    assert metadata["request"] == {"pageNum": "1"}
    assert metadata["page"] == 1 and metadata["acquired_at"].endswith("+00:00")
    assert calls[0][1]["stream"] is True
    assert calls[0][1]["allow_redirects"] is False


def test_query_retains_discovery_and_all_pages(monkeypatch):
    bodies = [b'{"announcements":[{"secCode":"600519","orgId":"official-id"}]}',
        b'{ "totalAnnouncement":2, "announcements":[{"announcementId":"1","secCode":"600519"}]}',
        b'{"totalAnnouncement":2,"announcements":[{"announcementId":"2","secCode":"600519"}]}']
    calls = mock_http(monkeypatch, bodies)
    retained = []
    result = disclosures.search_announcement_window("600519", "2020-01-01", "2020-01-02",
        issuer_name="Synthetic", page_size=1, raw_response_sink=lambda *args: retained.append(args))
    assert [raw for raw, _ in retained] == bodies
    assert [metadata["page"] for _, metadata in retained] == [1, 1, 2]
    assert calls[0][1]["data"]["stock"] == ""
    assert result["parameters"]["stock"] == "600519,official-id"
    assert [row["announcementId"] for row in result["announcements"]] == ["1", "2"]


def test_missing_raw_from_legacy_mock_fails_closed_when_requested(monkeypatch):
    monkeypatch.setattr(disclosures, "_request_json", lambda *args, **kwargs: {"announcements": []})
    with pytest.raises(ValueError, match="raw response missing"):
        disclosures.search_announcement_window("600519", "2020-01-01", "2020-01-02",
            issuer_name="Synthetic", raw_response_sink=lambda *args: None)


def test_inconsistent_raw_and_parsed_response_rejected(monkeypatch):
    def request(data, *, raw_response_sink):
        raw = b'{"announcements":[]}'
        raw_response_sink(raw, {"sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw),
            "url": disclosures.SEARCH_URL, "request": data})
        return {"announcements": [{"secCode": "600519", "orgId": "wrong"}]}

    monkeypatch.setattr(disclosures, "_request_json", request)
    with pytest.raises(ValueError, match="inconsistent"):
        disclosures.search_announcement_window("600519", "2020-01-01", "2020-01-02",
            issuer_name="Synthetic", raw_response_sink=lambda *args: pytest.fail("inconsistent body archived"))


@pytest.mark.parametrize("kind", ["response", "total", "requests"])
def test_raw_capture_has_bounded_resources(monkeypatch, kind):
    mock_http(monkeypatch, [b'{"announcements":[]}'])
    if kind == "response":
        monkeypatch.setattr(disclosures, "MAX_CNINFO_RAW_RESPONSE_BYTES", 5)
    elif kind == "total":
        monkeypatch.setattr(disclosures, "MAX_CNINFO_RAW_TOTAL_BYTES", 5)
    else:
        monkeypatch.setattr(disclosures, "MAX_CNINFO_RAW_REQUESTS", 0)
    with pytest.raises(ValueError, match="limit"):
        disclosures.search_announcement_window("600519", "2020-01-01", "2020-01-02",
            issuer_name="Synthetic", raw_response_sink=lambda *args: pytest.fail("limit exceeded"))


def test_changed_pagination_total_never_returns_complete_index(monkeypatch):
    mock_http(monkeypatch, [b'{"announcements":[{"secCode":"600519","orgId":"id"}]}',
        b'{"totalAnnouncement":2,"announcements":[{"announcementId":"1","secCode":"600519"}]}',
        b'{"totalAnnouncement":3,"announcements":[{"announcementId":"2","secCode":"600519"}]}'])
    with pytest.raises(ValueError, match="total changed"):
        disclosures.search_announcement_window("600519", "2020-01-01", "2020-01-02",
            issuer_name="Synthetic", page_size=1, raw_response_sink=lambda *args: None)


@pytest.mark.parametrize("invalid", ["redirect", "html", "not_object"])
def test_invalid_http_body_or_redirect_never_archived(monkeypatch, invalid):
    bodies = {"redirect": b'{}', "html": b'<html>challenge</html>', "not_object": b'[]'}
    mock_http(monkeypatch, [bodies[invalid]])
    if invalid == "redirect":
        original = disclosures.requests.Session

        class RedirectSession(original):
            def post(self, *args, **kwargs):
                response = super().post(*args, **kwargs)
                response.status_code = 302
                return response

        monkeypatch.setattr(disclosures.requests, "Session", RedirectSession)
    with pytest.raises(ValueError):
        disclosures._request_json({"pageNum": "1"},
            raw_response_sink=lambda *args: pytest.fail("invalid HTTP body archived"))


def test_service_archives_full_real_query_path_and_pages(tmp_path, monkeypatch):
    from datetime import date
    from pypdf import PdfWriter
    from value_investment_agent.application.product import daily_event_observation as service

    rows = [dict(secCode="600519", announcementId=str(i), announcementTitle="Synthetic",
                 adjunctUrl=f"finalpage/2020-01-01/{i}.PDF", announcementTime=1577808000000)
            for i in range(1, 32)]
    bodies = [b'{"announcements":[{"secCode":"600519","orgId":"official-id"}]}',
              json.dumps({"totalAnnouncement": 31, "announcements": rows[:30]}).encode(),
              json.dumps({"totalAnnouncement": 31, "announcements": rows[30:]}).encode()]
    mock_http(monkeypatch, bodies)

    def download(url, path):
        document = PdfWriter()
        document.add_blank_page(width=100, height=100)
        with path.open("wb") as handle:
            document.write(handle)
        return service.sha256_file(path)

    monkeypatch.setattr(service, "download_disclosure_pdf", download)
    folder = tmp_path / "runtime/events"
    result = service.collect_daily_event_observation(root=tmp_path, symbol="600519", issuer_name="Synthetic",
        start=date(2020, 1, 1), end=date(2020, 1, 2), output_dir=folder, retain_raw_index=True)
    manifest = json.loads((folder / "raw-index-manifest.json").read_text(encoding="utf-8"))
    assert [item["request_kind"] for item in manifest["responses"]] == ["issuer_discovery", "window", "window"]
    assert [(tmp_path / item["path"]).read_bytes() for item in manifest["responses"]] == bodies
    assert result["announcement_count"] == 31 and result["pagination_complete"]
    assert not result["materiality_approved"] and not result["research_date_advanced"]
