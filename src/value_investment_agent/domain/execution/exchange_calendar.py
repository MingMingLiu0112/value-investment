"""Fail-closed exchange-session membership for manual portfolio records.

The current schedule is intentionally year-bounded. It is sourced from the
official SSE 2026 closure notice already archived by the quote pipeline; a
new notice must be admitted before the portfolio can write another year.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta


SCHEDULE_VERSION = "official-cn-exchange-closures-2026-v1"
SUPPORTED_VENUES = frozenset({"SSE", "SZSE"})
OFFICIAL_SOURCE_URL = (
    "https://www.sse.com.cn/disclosure/announcement/general/c/"
    "c_20251222_10802507.shtml"
)
EXCHANGE_CLOSURES_2026 = (
    (date(2026, 1, 1), date(2026, 1, 3)),
    (date(2026, 2, 15), date(2026, 2, 23)),
    (date(2026, 4, 4), date(2026, 4, 6)),
    (date(2026, 5, 1), date(2026, 5, 5)),
    (date(2026, 6, 19), date(2026, 6, 21)),
    (date(2026, 9, 25), date(2026, 9, 27)),
    (date(2026, 10, 1), date(2026, 10, 7)),
)


class ExchangeCalendarCoverageError(ValueError):
    """The admitted calendar cannot establish membership for this date."""


def _require_covered_date(day: date) -> None:
    if not isinstance(day, date) or isinstance(day, datetime):
        raise ValueError("exchange calendar requires a date-only value")
    if day.year != 2026:
        raise ExchangeCalendarCoverageError(
            f"exchange calendar {SCHEDULE_VERSION} does not cover {day.year}"
        )


def _require_venue(venue: str) -> None:
    if venue not in SUPPORTED_VENUES:
        raise ExchangeCalendarCoverageError(
            f"exchange calendar {SCHEDULE_VERSION} does not cover {venue}"
        )


def is_exchange_session(venue: str, day: date) -> bool:
    """Return membership only when the admitted schedule covers the date."""
    _require_venue(venue)
    _require_covered_date(day)
    closures = {
        start + timedelta(days=offset)
        for start, end in EXCHANGE_CLOSURES_2026
        for offset in range((end - start).days + 1)
    }
    return day.weekday() < 5 and day not in closures


def next_exchange_session(venue: str, after: date) -> date:
    """Return the first actual session after the supplied trade date."""
    if not is_exchange_session(venue, after):
        raise ValueError("trade date is not a covered exchange session")
    cursor = after + timedelta(days=1)
    while cursor.year == after.year:
        if is_exchange_session(venue, cursor):
            return cursor
        cursor += timedelta(days=1)
    raise ExchangeCalendarCoverageError(
        f"next exchange session for {after} is outside calendar coverage"
    )


def validate_buy_settlement(
    venue: str, trade_date: date, next_sell_session: date | None
) -> date:
    """Validate broker-confirmed T+1 availability against exchange sessions."""
    expected = next_exchange_session(venue, trade_date)
    if next_sell_session is None:
        raise ValueError("BUY requires an explicit later sell session")
    _require_covered_date(next_sell_session)
    if next_sell_session <= trade_date:
        raise ValueError("BUY requires an explicit later sell session")
    if next_sell_session != expected:
        raise ValueError(
            "next_sell_session must equal the next covered exchange session: "
            + expected.isoformat()
        )
    return expected
