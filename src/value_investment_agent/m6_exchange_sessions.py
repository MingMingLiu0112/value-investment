"""Official, completed exchange-session schedules for offline M6 validation.

Calendar membership is not evidence of a successful shadow run or execution.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from urllib.parse import parse_qs

import requests

from .quote_sessions import (
    CALENDAR_PATH,
    SSE_2026_CLOSURE_RANGES,
    _raw,
    _stamp,
    latest_sse_2026_session,
    latest_szse_session,
)


def completed_exchange_sessions(
    venue: str, documents: list[dict], observation_cutoff: datetime
) -> dict:
    """Return ordered completed sessions covered by retained official documents.

    SZSE coverage starts at the first supplied month and must be contiguous
    through the cutoff month. SSE coverage starts on 2026-01-01 and ends at
    the cutoff. Every returned date names the raw document that supports it.
    """
    cutoff = _stamp(observation_cutoff)
    if venue == "SZSE":
        latest, _ = latest_szse_session(documents, cutoff)
        months = {}
        for document in documents:
            raw, _, url = _raw(
                document, cutoff, host="www.szse.cn",
                path_prefix=CALENDAR_PATH, max_age=timedelta(days=7),
            )
            month = parse_qs(url.query)["month"][0]
            if month in months:
                raise ValueError("Repeated SZSE calendar month")
            months[month] = (json.loads(raw)["data"], document)
        ordered_months = sorted(months)
        cutoff_month = cutoff.strftime("%Y-%m")
        if ordered_months[-1] != cutoff_month:
            raise ValueError("SZSE calendar does not cover cutoff month")
        first = date.fromisoformat(ordered_months[0] + "-01")
        expected_months = []
        cursor = first
        while cursor <= cutoff.date().replace(day=1):
            expected_months.append(cursor.strftime("%Y-%m"))
            cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
        if ordered_months != expected_months:
            raise ValueError("SZSE calendar months are not contiguous")
        sessions = [
            {"session_date": row["jyrq"], "source_url": document["source_url"],
             "sha256": document["sha256"]}
            for month in ordered_months
            for rows, document in [months[month]]
            for row in rows
            if row["jybz"] == "1" and row["jyrq"] <= latest
        ]
        sessions.sort(key=lambda item: item["session_date"])
    elif venue == "SSE":
        latest, _ = latest_sse_2026_session(documents, cutoff)
        document = documents[0]
        closures = {
            start + timedelta(days=offset)
            for start, end in SSE_2026_CLOSURE_RANGES
            for offset in range((end - start).days + 1)
        }
        sessions = []
        cursor = date(2026, 1, 1)
        last = date.fromisoformat(latest)
        while cursor <= last:
            if cursor.weekday() < 5 and cursor not in closures:
                sessions.append({
                    "session_date": cursor.isoformat(),
                    "source_url": document["source_url"],
                    "sha256": document["sha256"],
                })
            cursor += timedelta(days=1)
    else:
        raise ValueError("Unsupported exchange venue")
    if not sessions or sessions[-1]["session_date"] != latest:
        raise ValueError("Official completed session coverage is incomplete")
    return {
        "venue": venue,
        "observation_cutoff": cutoff.isoformat(),
        "latest_completed_session": latest,
        "sessions": sessions,
    }


def refetch_official_calendar(documents: list[dict]) -> dict:
    """Independently compare retained official bytes with a fresh TLS response."""
    hashes = []
    with requests.Session() as session:
        session.trust_env = False
        for document in documents:
            url = document['source_url']
            response = session.get(url, timeout=(10, 20))
            response.raise_for_status()
            if response.url != url or len(response.content) > 1_000_000:
                raise ValueError('Official calendar refetch URL or response size differs')
            digest = hashlib.sha256(response.content).hexdigest()
            if digest != document['sha256']:
                raise ValueError('Official calendar live response differs from archived source')
            hashes.append(digest)
    return {'source_sha256': hashes, 'verified_at': datetime.now(timezone.utc).isoformat()}
