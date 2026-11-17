"""2026 official-list acquisition dates, not quote or historical PIT admission."""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from copy import deepcopy

from ..execution.exchange_calendar import is_exchange_session

VERSION = 'official-list-session-calendar-2026-v1'
CHINA = ZoneInfo('Asia/Shanghai')
# Independently checked against BSE notice 2025/58, not an SSE venue alias.
BSE_CLOSURES = (
    (date(2026, 1, 1), date(2026, 1, 3)),
    (date(2026, 2, 15), date(2026, 2, 23)),
    (date(2026, 4, 4), date(2026, 4, 6)),
    (date(2026, 5, 1), date(2026, 5, 5)),
    (date(2026, 6, 19), date(2026, 6, 21)),
    (date(2026, 9, 25), date(2026, 9, 27)),
    (date(2026, 10, 1), date(2026, 10, 7)),
)
NOTICE_SOURCES = {
    'BSE': {'notice': 'BSE-2025-58',
        'publisher_url': 'https://www.bse.cn/important_news/200027428.html',
        'archive_url': 'https://dataclouds.cninfo.com.cn/sjother2/regulatory/2025/20251222/55875a9937374da4ae2d4999dfda2722.pdf',
        'sha256': 'd512772d26260909147d1b349474cf8720140194cf80bf826c97ffdc304cb8be'},
    'SSE': {'notice': 'SSE-2025-45',
        'publisher_url': 'https://www.sse.com.cn/disclosure/announcement/general/c/c_20251222_10802507.shtml',
        'sha256': '090c75b3fb9bbcbd447fd93607e28cca821603b897a58ef7df84eb05ea4be841'},
    'SZSE': {'notice': 'SZSE-2025-481',
        'publisher_url': 'https://www.szse.cn/disclosure/notice/general/t20251222_618087.html',
        'sha256': '1656d8708d5faed33c7588538639d96128f39fdface02cfa6eb66d796c40f14e'},
}


def aware(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError('Official list clock must be timezone aware')
    return value.astimezone(CHINA)


def _session(venue: str, day: date) -> bool:
    if day.year != 2026:
        raise ValueError('Official list calendar covers 2026 only')
    if venue == 'BSE':
        return day.weekday() < 5 and not any(start <= day <= end for start, end in BSE_CLOSURES)
    return is_exchange_session(venue, day)


def completed_list_session(now: datetime) -> date:
    """Reject open sessions, rather than combining today's SSE/SZSE with old BSE."""
    local = aware(now)
    sessions = []
    for venue in NOTICE_SOURCES:
        cursor = local.date()
        if _session(venue, cursor) and local.time() < time(15, 5):
            raise ValueError('Official universe requires a completed trading day (15:05 buffer)')
        while not _session(venue, cursor):
            cursor -= timedelta(days=1)
        sessions.append(cursor)
    if len(set(sessions)) != 1:
        raise ValueError('Official venue sessions disagree')
    return sessions[0]


def validate_list_timing(*, provider_dates, fetched_at, started_at: datetime,
                         available_at: datetime) -> dict:
    """Provider date stays separate from acquisition and latest completed session."""
    start, finish = aware(started_at), aware(available_at)
    expected = completed_list_session(finish)
    if start > finish or start.date() != finish.date() or completed_list_session(start) != expected:
        raise ValueError('Official collection crossed dates or session boundaries')
    times = [aware(datetime.fromisoformat(value)) for value in fetched_at]
    if not times or any(not start <= stamp <= finish or stamp.date() != finish.date() for stamp in times):
        raise ValueError('Official source acquisition times are missing, future or cross-day')
    dates = {date.fromisoformat(value) for value in provider_dates}
    if dates != {expected}:
        raise ValueError('BSE provider date is future, stale, mixed or not the completed session')
    return dict(schema_version='official-list-timing-v2', calendar_version=VERSION,
        effective_session=expected.isoformat(), provider_dates=sorted(day.isoformat() for day in dates),
        collection_started_at=started_at.isoformat(), available_at=available_at.isoformat(),
        fetched_at=available_at.isoformat(), calendar_sources=deepcopy(NOTICE_SOURCES),
        provider_date_scope='BSE_ONLY_SSE_SZSE_EFFECTIVE_DATE_NOT_IN_RESPONSE',
        quote_date_verified=False, strict_contemporaneous_pit=False,
        scope='OBSERVED_OFFICIAL_LIST_NOT_VERIFIED_MARKET_QUOTE_OR_HISTORICAL_PIT')
