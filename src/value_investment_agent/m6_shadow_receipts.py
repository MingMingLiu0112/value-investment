"""Offline verifier for future authorized Shadow session evidence.

This module never issues authorization or signs a production receipt. A trust
root must be supplied separately from the evidence bundle.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
import hashlib
import json
import re
from typing import Any, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .m6_authorization_artifacts import verify_authorization_artifacts


VERSION = 'm6-shadow-receipt-v1'
_SHA256 = re.compile(r'^[0-9a-f]{64}$')
_CST = timezone(timedelta(hours=8))
_AUTH_FIELDS = frozenset({
    'action', 'authorization_id', 'mode', 'venue', 'valid_from', 'valid_until',
    'deployment_sha256', 'config_sha256', 'runtime_public_key',
    'scope_manifest_sha256',
})
_SESSION_FIELDS = frozenset({
    'action', 'authorization_sha256', 'mode', 'venue', 'session_date', 'run_id',
    'started_at', 'completed_at', 'status', 'resource_baseline_ok',
    'calendar_sha256', 'calendar_source_url', 'deployment_sha256',
    'config_sha256', 'artifact_sha256', 'previous_receipt_sha256',
})
_WITNESS_FIELDS = frozenset({
    'action', 'session_receipt_sha256', 'received_at', 'sequence',
    'previous_witness_sha256',
})


def _timestamp(value: Any) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError('Shadow receipt timestamp is invalid') from exc
    if parsed.tzinfo is None:
        raise ValueError('Shadow receipt timestamp must be timezone-aware')
    return parsed


def _signed(envelope: Mapping[str, Any], public_key_hex: str, purpose: str,
            fields: frozenset[str]) -> tuple[dict, str]:
    if set(envelope) != {'version', 'payload', 'signature'} or envelope['version'] != VERSION:
        raise ValueError('Shadow signed envelope schema differs')
    payload = envelope['payload']
    if not isinstance(payload, dict) or set(payload) != fields or payload.get('action') != 'no_order':
        raise ValueError('Shadow signed payload schema or action differs')
    try:
        key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
        signature = bytes.fromhex(envelope['signature'])
        message = (purpose + '\0').encode('ascii') + json.dumps(
            payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
        key.verify(signature, message)
    except (ValueError, TypeError, InvalidSignature) as exc:
        raise ValueError('Shadow receipt signature is invalid') from exc
    digest = hashlib.sha256(json.dumps(envelope, sort_keys=True, separators=(',', ':'),
                                       ensure_ascii=False).encode('utf-8')).hexdigest()
    return payload, digest


def verify_shadow_bundle(bundle: Mapping[str, Any], trust_root: Mapping[str, str],
                         schedule: Mapping[str, Any], cutoff: datetime) -> dict[str, str]:
    """Return authenticated session-date -> receipt-hash mappings, never event credit."""
    if set(trust_root) != {'authorization_public_key', 'witness_public_key',
                           'approved_authorization_sha256'}:
        raise ValueError('An externally pinned Shadow trust root is required')
    if set(bundle) != {'authorization', 'authorization_artifacts', 'sessions'} or not isinstance(bundle['sessions'], list):
        raise ValueError('Shadow evidence bundle schema differs')
    authorization, authorization_hash = _signed(
        bundle['authorization'], trust_root['authorization_public_key'],
        'M6-AUTHORIZATION', _AUTH_FIELDS)
    if authorization_hash != trust_root['approved_authorization_sha256']:
        raise ValueError('Shadow authorization is not the approved external receipt')
    if len({trust_root['authorization_public_key'], trust_root['witness_public_key'],
            authorization['runtime_public_key']}) != 3:
        raise ValueError('Shadow authorization, runtime and witness signers must be distinct')
    if (authorization['mode'] != 'SHADOW' or authorization['venue'] != schedule['venue']
            or not authorization['authorization_id']
            or not _SHA256.fullmatch(authorization['deployment_sha256'])
            or not _SHA256.fullmatch(authorization['config_sha256'])):
        raise ValueError('Shadow authorization scope is invalid')
    if not _SHA256.fullmatch(authorization['scope_manifest_sha256']):
        raise ValueError('Shadow authorization scope manifest is invalid')
    verify_authorization_artifacts(authorization, bundle['authorization_artifacts'])
    valid_from = _timestamp(authorization['valid_from'])
    valid_until = _timestamp(authorization['valid_until'])
    if valid_from >= valid_until:
        raise ValueError('Shadow authorization validity window is invalid')
    calendar = {item['session_date']: item for item in schedule['sessions']}
    verified: dict[str, str] = {}
    previous_session = None
    previous_witness = None
    previous_received = None
    seen_runs: set[str] = set()
    seen_dates: set[str] = set()
    for sequence, item in enumerate(bundle['sessions'], 1):
        if set(item) != {'session', 'witness'}:
            raise ValueError('Shadow session evidence schema differs')
        session, session_hash = _signed(item['session'], authorization['runtime_public_key'],
                                        'M6-SESSION', _SESSION_FIELDS)
        witness, witness_hash = _signed(item['witness'], trust_root['witness_public_key'],
                                        'M6-WITNESS', _WITNESS_FIELDS)
        day = session['session_date']
        proof = calendar.get(day)
        started = _timestamp(session['started_at'])
        completed = _timestamp(session['completed_at'])
        received = _timestamp(witness['received_at'])
        if (proof is None or day in seen_dates or session['run_id'] in seen_runs
                or not session['run_id'] or session['venue'] != authorization['venue']
                or session['mode'] != 'SHADOW' or session['status'] not in {'success', 'failed'}
                or type(session['resource_baseline_ok']) is not bool
                or session['authorization_sha256'] != authorization_hash
                or session['deployment_sha256'] != authorization['deployment_sha256']
                or session['config_sha256'] != authorization['config_sha256']
                or session['calendar_sha256'] != proof['sha256']
                or session['calendar_source_url'] != proof['source_url']
                or not _SHA256.fullmatch(session['artifact_sha256'])
                or session['previous_receipt_sha256'] != previous_session
                or witness['session_receipt_sha256'] != session_hash
                or type(witness['sequence']) is not int or witness['sequence'] != sequence
                or witness['previous_witness_sha256'] != previous_witness
                or started < valid_from or received > valid_until
                or started > completed or completed > received or received > cutoff
                or received > datetime.now(timezone.utc)
                or received - completed > timedelta(minutes=15)
                or completed.astimezone(_CST).date().isoformat() != day
                or completed.astimezone(_CST).time() < time(15, 5)
                or (previous_received is not None and received <= previous_received)
                or (seen_dates and day <= max(seen_dates))):
            raise ValueError('Shadow session or independent witness does not satisfy scope and time')
        if session['status'] == 'success' and session['resource_baseline_ok']:
            verified[day] = session_hash
        seen_dates.add(day)
        seen_runs.add(session['run_id'])
        previous_session = session_hash
        previous_witness = witness_hash
        previous_received = received
    return verified
