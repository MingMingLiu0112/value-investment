"""Synthetic calendar documents only; no real shadow evidence."""
import base64
from calendar import monthrange
from datetime import date, datetime, timezone
import hashlib
import json

import pytest

from value_investment_agent.m6_exchange_sessions import (
    completed_exchange_sessions, refetch_official_calendar,
)
from value_investment_agent.quote_sessions import (
    SSE_2026_CLOSURE_NOTICE_URL,
    SSE_2026_NOTICE_MARKERS,
)


def _document(raw, url, fetched):
    return {
        "source_url": url,
        "fetched_at": fetched,
        "raw_base64": base64.b64encode(raw).decode("ascii"),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def _szse(month, fetched="2026-09-25T08:00:00+00:00"):
    year, number = map(int, month.split("-"))
    rows = [
        {"jyrq": date(year, number, day).isoformat(),
         "jybz": "1" if date(year, number, day).weekday() < 5 and day != 25 else "0"}
        for day in range(1, monthrange(year, number)[1] + 1)
    ]
    raw = json.dumps({"nowdate": fetched[:10], "data": rows}).encode()
    return _document(raw, "https://www.szse.cn/api/report/exchange/onepersistenthour/monthList?month=" + month, fetched)


def _sse():
    raw = "\n".join(SSE_2026_NOTICE_MARKERS).encode("utf-8")
    return _document(raw, SSE_2026_CLOSURE_NOTICE_URL, "2026-09-25T08:00:00+00:00")


def test_szse_hash_bound_completed_schedule_excludes_holiday_weekend_and_future():
    doc = _szse("2026-09")
    result = completed_exchange_sessions(
        "SZSE", [doc], datetime(2026, 9, 25, 8, tzinfo=timezone.utc)
    )
    dates = [item["session_date"] for item in result["sessions"]]
    assert result["latest_completed_session"] == "2026-09-24"
    assert dates == sorted(dates)
    assert "2026-09-24" in dates
    assert "2026-09-25" not in dates
    assert "2026-09-26" not in dates
    assert all(item["sha256"] == doc["sha256"] for item in result["sessions"])


def test_szse_intraday_cutoff_and_incomplete_month_fail_closed():
    doc = _szse("2026-09", "2026-09-24T02:00:00+00:00")
    result = completed_exchange_sessions(
        "SZSE", [doc], datetime(2026, 9, 24, 2, tzinfo=timezone.utc)
    )
    assert result["latest_completed_session"] == "2026-09-23"
    body = json.loads(base64.b64decode(doc["raw_base64"]))
    body["data"].pop()
    bad = _document(json.dumps(body).encode(), doc["source_url"], doc["fetched_at"])
    with pytest.raises(ValueError, match="incomplete"):
        completed_exchange_sessions("SZSE", [bad], datetime(2026, 9, 24, 2, tzinfo=timezone.utc))


def test_szse_rejects_wrong_venue_gap_and_hash_tampering():
    cutoff = datetime(2026, 9, 25, 8, tzinfo=timezone.utc)
    doc = _szse("2026-09")
    with pytest.raises(ValueError):
        completed_exchange_sessions("SSE", [doc], cutoff)
    with pytest.raises(ValueError, match="contiguous"):
        completed_exchange_sessions("SZSE", [_szse("2026-07"), doc], cutoff)
    with pytest.raises(ValueError, match="SHA-256"):
        completed_exchange_sessions("SZSE", [{**doc, "sha256": "0" * 64}], cutoff)


def test_sse_2026_notice_schedule_is_bounded_and_hash_bound():
    doc = _sse()
    result = completed_exchange_sessions(
        "SSE", [doc], datetime(2026, 9, 25, 8, tzinfo=timezone.utc)
    )
    dates = [item["session_date"] for item in result["sessions"]]
    assert result["latest_completed_session"] == "2026-09-24"
    assert "2026-09-24" in dates and "2026-09-25" not in dates
    assert "2026-09-19" not in dates
    assert all(item["sha256"] == doc["sha256"] for item in result["sessions"])
    with pytest.raises(ValueError, match="another year"):
        completed_exchange_sessions("SSE", [doc], datetime(2027, 1, 4, 8, tzinfo=timezone.utc))


def test_unsupported_venue_or_naive_cutoff_fails_closed():
    with pytest.raises(ValueError, match="Unsupported"):
        completed_exchange_sessions("BSE", [], datetime(2026, 9, 25, 8, tzinfo=timezone.utc))
    with pytest.raises(ValueError, match="Timezone-aware"):
        completed_exchange_sessions("SSE", [_sse()], datetime(2026, 9, 25, 16))


def test_independent_official_refetch_requires_identical_tls_response(monkeypatch):
    document = _sse()
    raw = base64.b64decode(document['raw_base64'])

    class Response:
        url = document['source_url']
        content = raw

        def raise_for_status(self):
            pass

    class Session:
        trust_env = True

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def get(self, url, *, timeout):
            assert self.trust_env is False
            assert timeout == (10, 20)
            return Response()

    from value_investment_agent import m6_exchange_sessions as module
    monkeypatch.setattr(module.requests, 'Session', Session)
    assert refetch_official_calendar([document])['source_sha256'] == [document['sha256']]
    Response.content = raw + b'changed'
    with pytest.raises(ValueError, match='differs'):
        refetch_official_calendar([document])
    Response.content = raw
    Response.url = 'https://example.com/redirect'
    with pytest.raises(ValueError, match='URL'):
        refetch_official_calendar([document])
