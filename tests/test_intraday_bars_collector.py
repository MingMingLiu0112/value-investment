"""Mock transport only; collector tests never call Sina."""
import base64
from datetime import datetime, timezone
import hashlib

import pytest
import requests

from value_investment_agent.infrastructure.hotspot import intraday_bars as module


NOW = datetime(2026, 9, 28, 2, 55, tzinfo=timezone.utc)


class Response:
    status_code = 200

    def __init__(self, url, raw):
        self.url, self.raw, self.closed = url, raw, False

    def iter_content(self, chunk_size):
        yield self.raw

    def close(self):
        self.closed = True


class Session:
    def __init__(self, *, fail_first=False, raw=b"TEST_ONLY invalid source body", status=200):
        self.calls, self.responses = [], []
        self.fail_first, self.raw, self.status = fail_first, raw, status

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.fail_first and len(self.calls) == 1:
            raise requests.Timeout("TEST_ONLY")
        response = Response(url, self.raw)
        response.status_code = self.status
        self.responses.append(response)
        return response


def test_bounded_documents_retain_http_error_and_invalid_raw_without_parsing():
    session = Session(status=503)
    result = module.collect_intraday_bar_documents("000333", session=session, clock=lambda: NOW)
    assert set(result) == {"60m", "15m"} and len(session.calls) == 2
    for period, document in result.items():
        assert base64.b64decode(document["raw_base64"]) == session.raw
        assert document["sha256"] == hashlib.sha256(session.raw).hexdigest()
        assert document["http_status"] == 503
        assert document["fetched_at"] == NOW.isoformat()
        assert f"scale={period[:-1]}" in document["source_url"]
        assert "symbol=sz000333" in document["source_url"]
    assert all(response.closed for response in session.responses)
    assert all(kwargs == dict(timeout=(5, 10), stream=True, allow_redirects=False)
               for _, kwargs in session.calls)


def test_timeout_does_not_drop_other_period_or_fabricate_response():
    session = Session(fail_first=True)
    result = module.collect_intraday_bar_documents("600519", session=session, clock=lambda: NOW)
    assert result["60m"]["error"] == "SOURCE_REQUEST_FAILED"
    assert result["60m"]["http_status"] is None
    assert base64.b64decode(result["60m"]["raw_base64"]) == b""
    assert result["15m"]["http_status"] == 200


def test_oversize_retained_as_bounded_rejected_document(monkeypatch):
    monkeypatch.setattr(module, "MAX_BYTES", 8)
    result = module.collect_intraday_bar_documents("600519", session=Session(raw=b"x" * 100), clock=lambda: NOW)
    assert all(doc["error"] == "RESPONSE_TOO_LARGE" and
               len(base64.b64decode(doc["raw_base64"])) == 9 for doc in result.values())


@pytest.mark.parametrize("symbol", ["800001", "60051", "60051\uff11", None])
def test_bad_symbols_never_make_request(symbol):
    session = Session()
    with pytest.raises(ValueError):
        module.collect_intraday_bar_documents(symbol, session=session)
    assert not session.calls
