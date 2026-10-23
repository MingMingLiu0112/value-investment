"""M2 official-list collection date orchestration, separate from quote admission."""
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path

from ...domain.discovery.official_list_calendar import (
    NOTICE_SOURCES, aware, completed_list_session, validate_list_timing,
)
from ...infrastructure.screening.official_universe_v2 import (
    collect_security_lists_v2, replay_official_documents, VERSION,
)
from ...official_universe import VERSION as LEGACY_VERSION
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


def official_input_version(payload: dict) -> str:
    """Dispatch declared versions; only the complete unversioned v1 shape is legacy."""
    v2_fields = {'collection_timing', 'available_at', 'effective_session'}
    if 'parser_version' in payload:
        version = payload['parser_version']
        if version == VERSION:
            return VERSION
        if version == LEGACY_VERSION and not v2_fields.intersection(payload):
            return LEGACY_VERSION
        raise ValueError('Unsupported official list parser version')
    legacy_keys = {'records', 'sources', 'fetched_at', 'exchange_counts',
                   'board_counts', 'scope', 'complete'}
    if (set(payload) == legacy_keys and payload['complete'] is True
            and isinstance(payload['records'], list) and bool(payload['records'])
            and isinstance(payload['sources'], list) and bool(payload['sources'])
            and isinstance(payload['exchange_counts'], dict)
            and isinstance(payload['board_counts'], dict)
            and isinstance(payload['scope'], str) and bool(payload['scope'])
            and isinstance(payload['fetched_at'], str)):
        aware(datetime.fromisoformat(payload['fetched_at']))
        return LEGACY_VERSION
    raise ValueError('Unsupported unversioned official list format')


def verify_retained_official_input(payload: dict, *, root: Path) -> None:
    """V2 replay proves the retained projection against its bound raw documents.

    This is not a signature or proof of the historical HTTP acquisition time.
    V1 keeps its historical replay semantics, without receiving V2 guarantees.
    """
    if official_input_version(payload) == LEGACY_VERSION:
        return
    root = root.resolve(strict=True)
    documents = []
    try:
        for reference in payload['sources']:
            path = Path(reference['local_path'])
            path = path if path.is_absolute() else root / path
            resolved = path.resolve(strict=True)
            if not resolved.is_relative_to(root):
                raise ValueError('Official raw document is outside replay root')
            for ancestor in (path, *path.parents):
                if ancestor.is_symlink() or ancestor.is_junction():
                    raise ValueError('Official raw document uses a linked path')
                if ancestor == root:
                    break
            if not resolved.is_file() or resolved.stat().st_size > 8 * 1024**2:
                raise ValueError('Invalid official raw document size or type')
            documents.append(dict(reference, raw=resolved.read_bytes()))
        rebuilt = replay_official_documents(documents,
            started_at=datetime.fromisoformat(payload['collection_timing']['collection_started_at']),
            available_at=datetime.fromisoformat(payload['available_at']))
        if rebuilt != payload:
            raise ValueError('Retained official projection differs from raw replay')
    except (KeyError, TypeError, OSError) as exc:
        raise ValueError('Incomplete retained official raw replay binding') from exc


def screening_quote_date(official_payload: dict, generated_at: datetime, *,
                         retained_quote_date: str | None = None) -> str:
    """Session label only. The existing M2 quote_date_verified=False remains."""
    generated_at = aware(generated_at)
    if official_input_version(official_payload) == LEGACY_VERSION:
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
