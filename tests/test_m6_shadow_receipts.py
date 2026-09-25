"""Synthetic signatures exercise the future verifier; they are not real sessions."""
import base64
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from value_investment_agent import m6_exchange_sessions as exchange
from value_investment_agent.m6_operational_readiness import (
    M6PreflightConfig, RestoreTarget, assess_session_ledger,
)
from value_investment_agent.m6_shadow_receipts import VERSION, verify_shadow_bundle
from value_investment_agent.quote_sessions import (
    SSE_2026_CLOSURE_NOTICE_URL, SSE_2026_NOTICE_MARKERS,
)


def _bytes(payload):
    return json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def _public(key):
    return key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()


def _sign(payload, key, purpose):
    message = (purpose + '\0').encode() + _bytes(payload)
    return {'version': VERSION, 'payload': payload,
            'signature': key.sign(message).hex()}


def _hash(envelope):
    return hashlib.sha256(_bytes(envelope)).hexdigest()


def _fixture():
    raw = '\n'.join(SSE_2026_NOTICE_MARKERS).encode()
    document = {'source_url': SSE_2026_CLOSURE_NOTICE_URL,
                'fetched_at': '2026-09-24T08:00:00+00:00',
                'raw_base64': base64.b64encode(raw).decode(),
                'sha256': hashlib.sha256(raw).hexdigest()}
    calendar = {'venue': 'SSE', 'documents': [document],
                'observation_cutoff': '2026-09-24T08:30:00+00:00'}
    schedule = exchange.completed_exchange_sessions(
        'SSE', [document], datetime.fromisoformat(calendar['observation_cutoff']))
    days = [item['session_date'] for item in schedule['sessions'][-2:]]
    auth_key, run_key, witness_key = [Ed25519PrivateKey.generate() for _ in range(3)]
    auth = _sign({
        'action': 'no_order', 'authorization_id': 'synthetic-only', 'mode': 'SHADOW',
        'venue': 'SSE', 'valid_from': '2026-09-01T00:00:00+00:00',
        'valid_until': '2026-09-25T00:00:00+00:00',
        'deployment_sha256': 'a' * 64, 'config_sha256': 'b' * 64,
        'scope_manifest_sha256': 'd' * 64,
        'runtime_public_key': _public(run_key),
    }, auth_key, 'M6-AUTHORIZATION')
    trust = {'authorization_public_key': _public(auth_key),
             'witness_public_key': _public(witness_key),
             'approved_authorization_sha256': _hash(auth)}
    sessions, records = [], []
    previous_session = previous_witness = None
    for number, day in enumerate(days, 1):
        session = _sign({
            'action': 'no_order', 'authorization_sha256': _hash(auth),
            'mode': 'SHADOW', 'venue': 'SSE', 'session_date': day,
            'run_id': f'synthetic-{number}', 'started_at': day + 'T15:06:00+08:00',
            'completed_at': day + 'T15:10:00+08:00', 'status': 'success',
            'resource_baseline_ok': True, 'calendar_sha256': document['sha256'],
            'calendar_source_url': document['source_url'],
            'deployment_sha256': 'a' * 64, 'config_sha256': 'b' * 64,
            'artifact_sha256': 'c' * 64,
            'previous_receipt_sha256': previous_session,
        }, run_key, 'M6-SESSION')
        witness = _sign({
            'action': 'no_order', 'session_receipt_sha256': _hash(session),
            'received_at': day + 'T15:11:00+08:00', 'sequence': number,
            'previous_witness_sha256': previous_witness,
        }, witness_key, 'M6-WITNESS')
        sessions.append({'session': session, 'witness': witness})
        records.append({
            'action': 'no_order', 'exchange': 'SSE', 'session_date': day,
            'observed_at': day + 'T15:10:00+08:00',
            'calendar_sha256': document['sha256'],
            'calendar_source_url': document['source_url'],
            'observed': 'actual', 'status': 'success', 'resource_baseline_ok': True,
            'real_event_materialized': False, 'session_receipt_sha256': _hash(session),
        })
        previous_session, previous_witness = _hash(session), _hash(witness)
    return ({'authorization': auth, 'sessions': sessions}, trust, calendar, schedule,
            records, (auth_key, run_key, witness_key))


def _config():
    return M6PreflightConfig(
        target_rpo_hours=24, target_rto_hours=4, minimum_real_sessions=2,
        minimum_real_events=1,
        restore_target=RestoreTarget('127.0.0.1', 5433, 'value_agent_restore'),
        resource_limits={}, required_files=(), stage_status={}, authorization_required=(),
    )


def test_synthetic_signatures_verify_contract_but_never_prove_real_event(monkeypatch):
    bundle, trust, calendar, schedule, records, _ = _fixture()
    cutoff = datetime.fromisoformat(calendar['observation_cutoff'])
    verified = verify_shadow_bundle(bundle, trust, schedule, cutoff)
    assert len(verified) == 2
    monkeypatch.setattr(exchange, 'refetch_official_calendar', lambda _: {
        'source_sha256': [calendar['documents'][0]['sha256']],
        'verified_at': '2026-09-24T08:20:00+00:00',
    })
    records[0]['real_event_materialized'] = True
    result = assess_session_ledger(
        _config(), records, calendar_evidence=calendar, verify_live_calendar=True,
        signed_session_bundle=bundle, trusted_shadow_root=trust)
    assert result['evidence']['latest_streak'] == 2
    assert result['evidence']['real_events'] == 0
    assert result['status'] == 'NOT_STARTED'
    assert assess_session_ledger(_config(), records, calendar_evidence=calendar)[
        'evidence']['latest_streak'] == 0


@pytest.mark.parametrize('change', ['payload', 'wrong_root', 'late_witness', 'duplicate', 'wrong_venue'])
def test_shadow_bundle_rejects_forged_or_out_of_scope_evidence(change):
    bundle, trust, calendar, schedule, _, _ = _fixture()
    bundle, trust = deepcopy(bundle), dict(trust)
    if change == 'payload':
        bundle['sessions'][0]['session']['payload']['status'] = 'failed'
    elif change == 'wrong_root':
        trust['authorization_public_key'] = _public(Ed25519PrivateKey.generate())
    elif change == 'late_witness':
        bundle['sessions'][0]['witness']['payload']['received_at'] = '2026-09-24T17:00:00+08:00'
    elif change == 'duplicate':
        bundle['sessions'].append(bundle['sessions'][-1])
    else:
        bundle['authorization']['payload']['venue'] = 'SZSE'
    with pytest.raises(ValueError):
        verify_shadow_bundle(bundle, trust, schedule,
                             datetime.fromisoformat(calendar['observation_cutoff']))


def test_signed_bundle_without_live_calendar_or_external_root_cannot_count():
    bundle, trust, calendar, _, records, _ = _fixture()
    with pytest.raises(ValueError, match='pinned root and live official calendar'):
        assess_session_ledger(_config(), records, calendar_evidence=calendar,
                              signed_session_bundle=bundle, trusted_shadow_root=trust)


def test_witnessed_failed_session_breaks_the_verified_streak(monkeypatch):
    bundle, trust, calendar, schedule, records, (_, run_key, witness_key) = _fixture()
    first = bundle['sessions'][0]
    failed = dict(first['session']['payload'], status='failed', resource_baseline_ok=False)
    first['session'] = _sign(failed, run_key, 'M6-SESSION')
    first['witness'] = _sign(dict(first['witness']['payload'],
                                  session_receipt_sha256=_hash(first['session'])),
                             witness_key, 'M6-WITNESS')
    second = bundle['sessions'][1]
    second['session'] = _sign(dict(second['session']['payload'],
                                   previous_receipt_sha256=_hash(first['session'])),
                              run_key, 'M6-SESSION')
    second['witness'] = _sign(dict(second['witness']['payload'],
                                   session_receipt_sha256=_hash(second['session']),
                                   previous_witness_sha256=_hash(first['witness'])),
                              witness_key, 'M6-WITNESS')
    records[0].update(status='failed', resource_baseline_ok=False,
                      session_receipt_sha256=_hash(first['session']))
    records[1]['session_receipt_sha256'] = _hash(second['session'])
    verified = verify_shadow_bundle(bundle, trust, schedule,
                                    datetime.fromisoformat(calendar['observation_cutoff']))
    assert list(verified) == [records[1]['session_date']]
    monkeypatch.setattr(exchange, 'refetch_official_calendar', lambda _: {
        'source_sha256': [calendar['documents'][0]['sha256']],
        'verified_at': '2026-09-24T08:20:00+00:00',
    })
    result = assess_session_ledger(
        _config(), records, calendar_evidence=calendar, verify_live_calendar=True,
        signed_session_bundle=bundle, trusted_shadow_root=trust)
    assert result['evidence']['latest_streak'] == 1


def test_signer_reuse_is_not_independent_witness():
    bundle, trust, calendar, schedule, _, _ = _fixture()
    trust['witness_public_key'] = bundle['authorization']['payload']['runtime_public_key']
    with pytest.raises(ValueError, match='must be distinct'):
        verify_shadow_bundle(bundle, trust, schedule,
                             datetime.fromisoformat(calendar['observation_cutoff']))


def test_correctly_signed_but_late_witness_is_rejected():
    bundle, trust, calendar, schedule, _, (_, _, witness_key) = _fixture()
    first = bundle['sessions'][0]
    first['witness'] = _sign(dict(first['witness']['payload'],
                                  received_at=first['session']['payload']['session_date'] + 'T16:10:00+08:00'),
                             witness_key, 'M6-WITNESS')
    with pytest.raises(ValueError, match='scope and time'):
        verify_shadow_bundle(bundle, trust, schedule,
                             datetime.fromisoformat(calendar['observation_cutoff']))
