"""M2 official-list collection date orchestration, separate from quote admission."""
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path

from ...domain.discovery.official_list_calendar import (
    NOTICE_SOURCES, aware, completed_list_session, validate_list_timing,
)
from ...infrastructure.screening.official_universe_v2 import collect_security_lists_v2, VERSION
from ...m2_opportunity_discovery import EvidenceReference
from ..product.common import write_new_bytes


def verify_calendar_archives(root: Path):
    for venue, source in NOTICE_SOURCES.items():
        path = root / 'docs/evidence/official-list-calendar-2026' / (venue + '.raw')
        if sha256(path.read_bytes()).hexdigest() != source['sha256']:
            raise ValueError('Official calendar notice hash mismatch: ' + venue)


def collect_official_m2_input(directory: Path, root: Path):
    """Never guess a retained fallback or copy an old list into a fresh run."""
    verify_calendar_archives(root)
    payload = collect_security_lists_v2(directory / 'official-raw')
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2).encode('utf-8')
    path = directory / 'official-universe.json'
    write_new_bytes(path, raw)
    reference = EvidenceReference(id='official', path=path.relative_to(root).as_posix(),
        sha256=sha256(raw).hexdigest(), source_name='Official SSE/SZSE/BSE lists, session-date v2',
        source_url='https://www.szse.cn | https://query.sse.com.cn | https://www.bse.cn',
        fetched_at=datetime.fromisoformat(payload['fetched_at']))
    return payload, reference


def screening_quote_date(official_payload: dict, generated_at: datetime, *,
                         retained_quote_date: str | None = None) -> str:
    """Session label only. The existing M2 quote_date_verified=False remains."""
    generated_at = aware(generated_at)
    if official_payload.get('parser_version') != VERSION:
        # Historical v1 semantics and test/legacy callers remain unchanged.
        return retained_quote_date if retained_quote_date is not None else generated_at.date().isoformat()
    timing = official_payload['collection_timing']
    verified = validate_list_timing(
        provider_dates=[row['as_of'] for row in official_payload['records'] if row['exchange'] == 'BSE'],
        fetched_at=[row['fetched_at'] for row in official_payload['sources']],
        started_at=datetime.fromisoformat(timing['collection_started_at']),
        available_at=datetime.fromisoformat(official_payload['available_at']))
    acquired = aware(datetime.fromisoformat(official_payload['available_at']))
    if (verified != timing or official_payload['fetched_at'] != official_payload['available_at']
            or official_payload['effective_session'] != verified['effective_session']
            or acquired > generated_at or acquired.date() != generated_at.date()
            or completed_list_session(generated_at).isoformat() != verified['effective_session']):
        raise ValueError('M2 collection dates or session changed before receipt generation')
    session = verified['effective_session']
    if retained_quote_date is not None and retained_quote_date != session:
        raise ValueError('Retained v2 quote session differs from its original acquisition')
    return session
