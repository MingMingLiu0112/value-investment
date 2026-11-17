"""M2 official-list collection date orchestration, separate from quote admission."""
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path

from ...domain.discovery.official_list_calendar import (
    NOTICE_SOURCES, aware, completed_list_session, validate_list_timing,
)
from ...infrastructure.screening.official_universe_v2 import (
    collect_security_lists_v2, collect_security_lists_with_coverage,
    replay_official_documents, replay_official_venue_coverage, VERSION, PARTIAL_VERSION,
)
from ...official_universe import VERSION as LEGACY_VERSION
from ...m2_opportunity_discovery import EvidenceReference
from ..product.common import write_new_bytes


def verify_calendar_archives(root: Path):
    for venue, source in NOTICE_SOURCES.items():
        path = root / 'docs/evidence/official-list-calendar-2026' / (venue + '.raw')
        if sha256(path.read_bytes()).hexdigest() != source['sha256']:
            raise ValueError('Official calendar notice hash mismatch: ' + venue)


def collect_official_m2_input(directory: Path, root: Path, *, allow_partial: bool = False):
    """Never guess a retained fallback or copy an old list into a fresh run."""
    verify_calendar_archives(root)
    if type(allow_partial) is not bool:
        raise ValueError('Official partial acquisition requires an explicit boolean')
    if allow_partial and not directory.resolve().is_relative_to(root.resolve()):
        raise ValueError('Official partial acquisition must remain inside project root')
    collector = collect_security_lists_with_coverage if allow_partial else collect_security_lists_v2
    payload = collector(directory / 'official-raw')
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2).encode('utf-8')
    path = directory / 'official-universe.json'
    write_new_bytes(path, raw)
    reference = EvidenceReference(id='official', path=path.relative_to(root).as_posix(),
        sha256=sha256(raw).hexdigest(), source_name=(
            'Official lists, observed venues only; incomplete all-A coverage'
            if payload['parser_version'] == PARTIAL_VERSION
            else 'Official SSE/SZSE/BSE lists, session-date v2'),
        source_url='https://www.szse.cn | https://query.sse.com.cn | https://www.bse.cn',
        fetched_at=datetime.fromisoformat(payload['fetched_at']))
    return payload, reference


def official_input_version(payload: dict) -> str:
    """Dispatch declared versions; only the complete unversioned v1 shape is legacy."""
    v2_fields = {'collection_timing', 'available_at', 'effective_session'}
    if 'parser_version' in payload:
        version = payload['parser_version']
        if version != PARTIAL_VERSION and {'required_venues', 'covered_venues', 'missing_venues',
                'failed_venues', 'venue_coverage', 'request_failures'}.intersection(payload):
            raise ValueError('Partial official coverage cannot be relabelled as a complete or legacy contract')
        if version == PARTIAL_VERSION:
            if (payload.get('complete') is not False or payload.get('action') != 'no_order'
                    or payload.get('scope') != 'OBSERVED_VENUES_ONLY_NOT_ALL_A'):
                raise ValueError('Invalid partial official list contract')
            return PARTIAL_VERSION
        if version == VERSION:
            return VERSION
        if version == LEGACY_VERSION:
            if (payload.get('complete') is not True
                    or payload.get('status') in ('PARTIAL', 'UNAVAILABLE')
                    or payload.get('scope') == 'OBSERVED_VENUES_ONLY_NOT_ALL_A'):
                raise ValueError('Legacy official input must be complete and contain no partial coverage semantics')
            if not v2_fields.intersection(payload):
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
            and payload['scope'] != 'OBSERVED_VENUES_ONLY_NOT_ALL_A'
            and isinstance(payload['fetched_at'], str)):
        aware(datetime.fromisoformat(payload['fetched_at']))
        return LEGACY_VERSION
    raise ValueError('Unsupported unversioned official list format')


def read_receipt_bound_official_input(path: Path, *, root: Path, receipt: dict) -> bytes:
    """Check the original receipt identity before parsing version-controlled input.

    The retained receipt is the replay anchor, not a signature/trust root. This
    does not authenticate a receipt and input that were both maliciously replaced.
    """
    references = receipt.get('evidence_refs')
    if not isinstance(references, list):
        raise ValueError('Missing original official receipt binding')
    matches = [ref for ref in references if isinstance(ref, dict) and ref.get('id') == 'official']
    if len(matches) != 1:
        raise ValueError('Original official receipt binding must be unique')
    reference = matches[0]
    name, digest = reference.get('path'), reference.get('sha256')
    if (not isinstance(name, str) or not name or Path(name).is_absolute()
            or '..' in Path(name).parts or not isinstance(digest, str)
            or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest)):
        raise ValueError('Invalid original official receipt binding')
    try:
        root = root.resolve(strict=True)
        expected = (root / name).resolve(strict=True)
        actual = path.resolve(strict=True)
        if not actual.is_relative_to(root) or expected != actual:
            raise ValueError('Original official receipt input identity mismatch')
        raw = path.read_bytes()
    except OSError as exc:
        raise ValueError('Original official receipt input unavailable') from exc
    if sha256(raw).hexdigest() != digest:
        raise ValueError('Original official receipt input hash mismatch')
    return raw


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
        options = dict(started_at=datetime.fromisoformat(payload['collection_timing']['collection_started_at']),
                       available_at=datetime.fromisoformat(payload['available_at']))
        if official_input_version(payload) == PARTIAL_VERSION:
            rebuilt = replay_official_venue_coverage(documents,
                request_failures=payload['request_failures'], **options)
        else:
            rebuilt = replay_official_documents(documents, **options)
        if rebuilt != payload:
            raise ValueError('Retained official projection differs from raw replay')
    except (KeyError, TypeError, OSError) as exc:
        raise ValueError('Incomplete retained official raw replay binding') from exc


def screening_quote_date(official_payload: dict, generated_at: datetime, *,
                         retained_quote_date: str | None = None) -> str:
    """Session label only. The existing M2 quote_date_verified=False remains."""
    generated_at = aware(generated_at)
    version = official_input_version(official_payload)
    if version == LEGACY_VERSION:
        # Historical v1 semantics and test/legacy callers remain unchanged.
        return retained_quote_date if retained_quote_date is not None else generated_at.date().isoformat()
    timing = official_payload['collection_timing']
    if version == PARTIAL_VERSION:
        start = aware(datetime.fromisoformat(timing['collection_started_at']))
        acquired = aware(datetime.fromisoformat(official_payload['available_at']))
        session = completed_list_session(acquired).isoformat()
        if (start > acquired or start.date() != acquired.date()
                or acquired > generated_at or acquired.date() != generated_at.date()
                or completed_list_session(start).isoformat() != session
                or completed_list_session(generated_at).isoformat() != session
                or official_payload['effective_session'] != session
                or timing['effective_session'] != session
                or timing['available_at'] != official_payload['available_at']
                or official_payload['fetched_at'] != official_payload['available_at']):
            raise ValueError('Partial M2 collection dates or session changed')
        if retained_quote_date is not None and retained_quote_date != session:
            raise ValueError('Retained partial quote session differs from its original acquisition')
        return session
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
