from __future__ import annotations

from datetime import date
import hashlib
import importlib
import json

import pytest


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class _FakeResponse:
    def __init__(self, content: bytes, status_code: int = 200):
        self.content = content
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def _prefix_payload() -> _FakeResponse:
    body = json.dumps(
        {"more": "1", "stockInfo": [{"stockId": 1000231771, "code": "00300", "name": "美的集團"}]},
        ensure_ascii=True,
    )
    return _FakeResponse(f"callback({body});\r\n".encode("utf-8"))


def _window_payload(records: list[dict], *, has_next_row: bool = False) -> _FakeResponse:
    envelope = {
        "result": json.dumps(records, ensure_ascii=False),
        "hasNextRow": has_next_row,
        "sortList": "[[0,0]]",
        "rowRange": 100,
        "lang": "C",
        "loadedRecord": len(records),
        "recordCnt": len(records),
    }
    return _FakeResponse(json.dumps(envelope).encode("utf-8"))


def _record(
    news_id: str = "12365201",
    stamp: str = "07/10/2026 16:39",
    title: str = "截至2026年9月30日止月份之股份發行人的證券變動月報表",
    link: str = "/listedco/listconews/sehk/2026/1007/2026100700897_c.pdf",
    code: str = "00300",
) -> dict:
    return {
        "NEWS_ID": news_id,
        "DATE_TIME": stamp,
        "TITLE": title,
        "LONG_TEXT": title,
        "FILE_TYPE": "PDF",
        "FILE_LINK": link,
        "STOCK_CODE": code,
        "STOCK_NAME": "美的集團",
    }


class _FakeSession:
    def __init__(self, prefix: _FakeResponse, window: _FakeResponse, pdf: bytes = b"%PDF-1.4 fake"):
        self._prefix = prefix
        self._window = window
        self._pdf = pdf
        self.downloaded: list[str] = []

    def get(self, url, params=None, headers=None, timeout=None):
        module = importlib.import_module("scripts.cases.capture_hkex_issuer_disclosure_window")
        if url == module.PREFIX_URL:
            return self._prefix
        if url == module.SEARCH_URL:
            return self._window
        if url.startswith(module.FILE_BASE_URL):
            self.downloaded.append(url)
            return _FakeResponse(self._pdf)
        raise AssertionError(f"unexpected URL {url}")

    def close(self) -> None:
        pass


def _install(tmp_path, monkeypatch, session, *extra: str):
    module = importlib.import_module("scripts.cases.capture_hkex_issuer_disclosure_window")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module.requests, "Session", lambda: session)
    monkeypatch.setattr("sys.argv", [
        "capture", "--code", "00300", "--start", "2026-09-30", "--end", "2026-10-13",
        "--output-dir", "runtime/window", *extra,
    ])
    return module


def test_capture_pins_identity_window_and_originals(tmp_path, monkeypatch):
    session = _FakeSession(_prefix_payload(), _window_payload([_record()]))
    module = _install(tmp_path, monkeypatch, session, "--download")
    assert module.main() == 0

    run_dir = tmp_path / "runtime" / "window"
    index = json.loads((run_dir / "window-index.json").read_text(encoding="utf-8"))
    receipt = json.loads((run_dir / "capture-receipt.json").read_text(encoding="utf-8"))

    assert index["action"] == "no_order"
    assert index["stock_id"] == "1000231771"
    assert index["total_records"] == 1
    assert index["coverage_status"] == "COMPLETE"
    assert [entry["news_id"] for entry in index["records"]] == ["12365201"]
    assert index["records"][0]["released_at"] == "2026-10-07T16:39:00+08:00"
    assert index["records"][0]["source_url"].endswith("/2026100700897_c.pdf")
    assert session.downloaded == [
        "https://www1.hkexnews.hk/listedco/listconews/sehk/2026/1007/2026100700897_c.pdf"
    ]
    assert index["originals"][0]["sha256"] == _sha256(b"%PDF-1.4 fake")
    assert (run_dir / "stock-id.raw.json").read_bytes().startswith(b"callback(")
    assert receipt["record_count"] == 1
    assert receipt["index_sha256"] == _sha256((run_dir / "window-index.json").read_bytes())
    assert receipt["action"] == "no_order"
    assert "not covered" in receipt["limitations"][0]


def test_capture_refuses_a_window_that_overflows_the_bounded_row_range(tmp_path, monkeypatch):
    session = _FakeSession(_prefix_payload(), _window_payload([_record()], has_next_row=True))
    module = _install(tmp_path, monkeypatch, session)
    with pytest.raises(ValueError, match="bounded row range"):
        module.main()


def test_capture_rejects_foreign_issuer_and_out_of_window_records():
    module = importlib.import_module("scripts.cases.capture_hkex_issuer_disclosure_window")
    with pytest.raises(ValueError, match="another issuer"):
        module._normalize_records([_record(code="09999")], "00300", date(2026, 9, 30), date(2026, 10, 13))
    with pytest.raises(ValueError, match="outside the requested window"):
        module._normalize_records(
            [_record(stamp="20/10/2026 16:39")], "00300", date(2026, 9, 30), date(2026, 10, 13),
        )


def test_capture_refuses_to_overwrite_an_existing_evidence_directory(tmp_path, monkeypatch):
    session = _FakeSession(_prefix_payload(), _window_payload([_record()]))
    (tmp_path / "runtime" / "window").mkdir(parents=True)
    module = _install(tmp_path, monkeypatch, session)
    with pytest.raises(SystemExit):
        module.main()
