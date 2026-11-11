"""Synthetic signed transport only: never issuer or real human approval."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
import pytest

from test_pending_review_intake import _candidate
from test_human_research_approval import _receipt
from value_investment_agent.application.product.common import sha256_file, write_new_json
from value_investment_agent.application.product.decision_surface import verify_current_decision_workbench
from value_investment_agent.application.product.research_reviews import (
    REVIEW_RESPONSE_PURPOSE, prepare_pending_review_response, consume_pending_review_response,
    attach_research_reviews,
)
from value_investment_agent.human_research_approval import artifact_fingerprint
from value_investment_agent.m1_valuation_package_builder import build_descriptor
from value_investment_agent.research_input import build_research_run_spec
from value_investment_agent.research_run_contract import canonical_contract_payload
from value_investment_agent.operations.authorization.trust_root_registry import (
    _use_test_trust_registry, trust_root_fingerprint,
)


@pytest.fixture
def signed(tmp_path, monkeypatch, synthetic_pending_candidate_clock):
    path, candidate = _candidate(tmp_path)
    response = prepare_pending_review_response(root=tmp_path, candidate_path=path,
        candidate_sha256=sha256_file(path))
    key = Ed25519PrivateKey.generate()
    now = datetime.now(timezone.utc)
    response.update(reviewer_id='SYNTHETIC_HUMAN', reviewed_at=now.isoformat())
    response['groups'][0].update(response='VERIFIED', response_reason='Synthetic test rationale',
        confirmed_scope='Synthetic conditional use only')
    trust = dict(schema_version='research-review-transport-trust-root-v1', reviewer_id='SYNTHETIC_HUMAN',
        public_key=key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex(),
        scopes=['human_group_research', 'human_whole_model'], symbols=[candidate['symbol']],
        valid_from=(now-timedelta(days=1)).isoformat(), valid_until=(now+timedelta(days=1)).isoformat())
    registry = tmp_path / 'synthetic-registry.json'
    write_new_json(registry, dict(schema_version='authorization-trust-root-registry-v1',
        pinned_trust_root_sha256=[trust_root_fingerprint(trust)]))
    yield dict(root=tmp_path, path=path, candidate=candidate, response=response, key=key,
        trust=trust, registry=registry)


def consume(f, *, pin=True, suffix='', previous=None):
    root = f['root']
    signed = dict(payload=f['response'], signature=f['key'].sign(REVIEW_RESPONSE_PURPOSE +
        canonical_contract_payload(f['response']).encode('utf-8')).hex())
    for name, value in (('response'+suffix, signed), ('trust'+suffix, f['trust'])):
        write_new_json(root / (name + '.json'), value)
    args = dict(root=root, candidate_path=f['path'], candidate_sha256=sha256_file(f['path']),
        response_path=root/('response'+suffix+'.json'), response_sha256=sha256_file(root/('response'+suffix+'.json')),
        trust_root_path=root/('trust'+suffix+'.json'), trust_root_sha256=sha256_file(root/('trust'+suffix+'.json')),
        output_dir=root/('runtime/response-consumed'+suffix),
        previous_response_path=previous, previous_response_sha256=sha256_file(previous) if previous else None)
    if pin:
        with _use_test_trust_registry(f['registry']):
            return consume_pending_review_response(**args)
    return consume_pending_review_response(**args)


def whole_approval(f):
    wb = json.loads((f['path'].parent/'workbench.json').read_text(encoding='utf-8'))
    restored = verify_current_decision_workbench(wb)
    context = f['candidate']['model_context']
    reviewed = datetime.fromisoformat(f['response']['reviewed_at'])
    return replace(_receipt(decision='APPROVED_RESEARCH_ONLY', price_assessment_eligible=False),
        symbol=f['candidate']['symbol'], security_id=f['candidate']['symbol'],
        profile_id=context['profile_id'], valuation_artifact_sha256=f['response']['valuation_artifact_sha256'],
        valuation_model_id=context['model_id'],
        valuation_model_version=restored.dependency_objects['valuation'].model_version,
        research_case_sha256=context['research_case_sha256'], facts_artifact_sha256=context['facts_sha256'],
        assumption_set_sha256=context['assumptions_sha256'],
        reviewed_at=reviewed, review_as_of=reviewed.date(), reviewer_id='SYNTHETIC_HUMAN').as_policy()


def _resume_args(f):
    root = f['root']
    output = root/'runtime/response-consumed'
    return dict(root=root, candidate_path=f['path'], candidate_sha256=sha256_file(f['path']),
        response_path=root/'response.json', response_sha256=sha256_file(root/'response.json'),
        trust_root_path=root/'trust.json', trust_root_sha256=sha256_file(root/'trust.json'),
        output_dir=output, resume_incomplete=True,
        incomplete_consumption_sha256=sha256_file(output/'incomplete-consumption.json'))


@pytest.mark.parametrize('failure', ['journal', 'receipt'])
def test_incomplete_consumption_requires_exact_resume_and_blocks_attach(signed, monkeypatch, failure):
    from value_investment_agent.application.product import research_reviews as reviews
    signed['response']['whole_model_approval'] = whole_approval(signed)
    append = reviews._append_review_json
    def fail(path, payload):
        if ((failure == 'journal' and path.parent.parent.name == 'research-review-responses')
                or (failure == 'receipt' and path.name == 'receipt.json')):
            raise OSError('synthetic IO interruption')
        return append(path, payload)
    monkeypatch.setattr(reviews, '_append_review_json', fail)
    with pytest.raises(OSError, match='interruption'):
        consume(signed)
    root = signed['root']
    output = root/'runtime/response-consumed'
    assert not (output/'receipt.json').exists()
    preserved = {p: p.read_bytes() for p in output.glob('*.json')}
    packet = output/'research-reviews.json'
    package = json.loads((signed['path'].parent/'package.json').read_text(encoding='utf-8'))
    descriptor = build_descriptor(package, root=root)
    monkeypatch.setattr(reviews, '_append_review_json', append)
    with _use_test_trust_registry(signed['registry']):
        with pytest.raises(ValueError):
            attach_research_reviews(root=root, descriptor=descriptor,
                spec=build_research_run_spec(descriptor), path=packet,
                expected_sha256=sha256_file(packet), event_sha256=None, require_model_binding=True)
        args = _resume_args(signed)
        with pytest.raises(ValueError, match='exact pinned'):
            consume_pending_review_response(**dict(args, incomplete_consumption_sha256='0'*64))
        result = consume_pending_review_response(**args)
        assert result['authenticated_reviewer'] == 'SYNTHETIC_HUMAN'
        assert all(p.read_bytes() == raw for p, raw in preserved.items())
        attach_research_reviews(root=root, descriptor=descriptor,
            spec=build_research_run_spec(descriptor), path=packet,
            expected_sha256=sha256_file(packet), event_sha256=None, require_model_binding=True)
        with pytest.raises(ValueError, match='completed review replay'):
            consume_pending_review_response(**args)
        with pytest.raises(ValueError, match='replay|predecessor'):
            consume_pending_review_response(**dict(args, resume_incomplete=False,
                incomplete_consumption_sha256=None, output_dir=root/'runtime/replayed'))
    assert not (root/'runtime/replayed').exists()


def test_incomplete_resume_rejects_new_head_conflict(signed, monkeypatch):
    from value_investment_agent.application.product import research_reviews as reviews
    append = reviews._append_review_json
    def fail(path, payload):
        if path.parent.parent.name == 'research-review-responses':
            raise OSError('synthetic journal interruption')
        return append(path, payload)
    monkeypatch.setattr(reviews, '_append_review_json', fail)
    with pytest.raises(OSError):
        consume(signed)
    args = _resume_args(signed)
    monkeypatch.setattr(reviews, '_append_review_json', append)
    signed['response']['reviewed_at'] = datetime.now(timezone.utc).isoformat()
    signed['response']['groups'][0]['response'] = 'REJECTED'
    consume(signed, suffix='-conflict')
    with _use_test_trust_registry(signed['registry']):
        with pytest.raises(ValueError, match='predecessor|replay'):
            consume_pending_review_response(**args)
    assert not (args['output_dir']/'receipt.json').exists()


@pytest.mark.parametrize('remove_receipt', [False, True])
def test_stripped_completion_cannot_downgrade_to_legacy(signed, remove_receipt):
    from value_investment_agent.application.product.research_reviews import _authenticated_review_history
    consume(signed)
    root = signed['root']
    record = next((root/'runtime/research-review-responses').glob('*/*.json'))
    value = json.loads(record.read_text(encoding='utf-8'))
    del value['completion_receipt_binding']
    record.write_text(json.dumps(value), encoding='utf-8')
    if remove_receipt:
        (root/'runtime/response-consumed/receipt.json').unlink()
    with _use_test_trust_registry(signed['registry']):
        with pytest.raises(ValueError, match='not pinned legacy'):
            _authenticated_review_history(root, sha256_file(signed['path']))


def test_legacy_requires_exact_explicit_fixture_pin(signed, monkeypatch):
    from value_investment_agent.application.product import research_reviews as reviews
    consume(signed)
    root = signed['root']
    record = next((root/'runtime/research-review-responses').glob('*/*.json'))
    value = json.loads(record.read_text(encoding='utf-8'))
    del value['completion_receipt_binding']
    record.write_text(json.dumps(value), encoding='utf-8')
    monkeypatch.setattr(reviews, '_PINNED_LEGACY_REVIEW_RECORD_SHA256', frozenset({sha256_file(record)}))
    with _use_test_trust_registry(signed['registry']):
        assert reviews._authenticated_review_history(root, sha256_file(signed['path']))[1] is not None
        record.write_text(json.dumps(value) + '\n', encoding='utf-8')
        with pytest.raises(ValueError, match='not pinned legacy'):
            reviews._authenticated_review_history(root, sha256_file(signed['path']))


@pytest.mark.parametrize('other_company', [False, True])
def test_unrelated_model_incomplete_journal_does_not_block_attachment(signed, other_company):
    from value_investment_agent.application.product.pending_research_candidate import prepare_pending_research_candidate
    root = signed['root']
    signed['response']['whole_model_approval'] = whole_approval(signed)
    result = consume(signed)
    policy_path = root/'runtime/policy.json'
    policy = json.loads(policy_path.read_text(encoding='utf-8'))
    package_path = next(p for p in (root/'runtime').glob('*.json')
        if sha256_file(p) == policy['source_package_sha256'])
    if other_company:
        old_symbol = policy['symbol']
        new_symbol = '600000' if old_symbol != '600000' else '600001'
        def issuer(value):
            if isinstance(value, dict):
                return {key: issuer(item) for key, item in value.items()}
            if isinstance(value, list):
                return [issuer(item) for item in value]
            return new_symbol if value == old_symbol else value
        package = issuer(json.loads(package_path.read_text(encoding='utf-8')))
        package_path = root/'runtime/other-company-package.json'
        write_new_json(package_path, package)
        policy.update(symbol=new_symbol, source_package_sha256=sha256_file(package_path))
    policy['choices'][0]['growth_years'] = 9
    other_policy = root/'runtime/other-policy.json'
    write_new_json(other_policy, policy)
    request = dict(schema_version='research-schedule-request-v1', symbol=policy['symbol'],
        source_id='CNINFO', period=signed['candidate']['prior_research_as_of'],
        research_question_id='unrelated-test', blocker_id='no-active-evidence-stop',
        reopen_condition_met=False, new_evidence_ids=[])
    prepare_pending_research_candidate(root=root, package_path=package_path,
        package_sha256=sha256_file(package_path), policy_path=other_policy,
        policy_sha256=sha256_file(other_policy), choice_id='continuity',
        output_dir=root/'runtime/unrelated', schedule_request=request, schedule_request_sha256='b'*64)
    other = root/'runtime/unrelated/candidate.json'
    other_value = json.loads(other.read_text(encoding='utf-8'))
    assert other_value['model_context'] != signed['candidate']['model_context']
    if other_company:
        assert other_value['symbol'] != signed['candidate']['symbol']
    digest = sha256_file(other)
    write_new_json(root/'runtime/research-review-responses'/digest[:24]/('c'*24+'.json'),
        dict(candidate_binding=dict(path=other.relative_to(root).as_posix(), sha256=digest),
            completion_receipt_binding=dict(path='runtime/missing-receipt.json', sha256='d'*64)))
    package = json.loads((signed['path'].parent/'package.json').read_text(encoding='utf-8'))
    descriptor = build_descriptor(package, root=root)
    packet = root/result['review_packet_binding']['path']
    with _use_test_trust_registry(signed['registry']):
        assert attach_research_reviews(root=root, descriptor=descriptor,
            spec=build_research_run_spec(descriptor), path=packet,
            expected_sha256=sha256_file(packet), event_sha256=None).human_research_approval is not None


def test_authenticated_group_is_not_whole_model_or_price_approval(signed):
    result = consume(signed)
    assert result['authenticated_reviewer'] == 'SYNTHETIC_HUMAN'
    assert result['blockers'] == ['whole_model_review_missing']
    assert not result['research_admitted'] and not result['price_admitted']
    assert not (signed['root']/'runtime/response-consumed/research-reviews.json').exists()


def test_explicit_whole_model_reuses_typed_attachment_without_event_or_price(signed):
    signed['response']['whole_model_approval'] = whole_approval(signed)
    result = consume(signed)
    root = signed['root']
    package = json.loads((signed['path'].parent/'package.json').read_text(encoding='utf-8'))
    descriptor = build_descriptor(package, root=root)
    packet = root / result['review_packet_binding']['path']
    original_spec = build_research_run_spec(descriptor)
    with _use_test_trust_registry(signed['registry']):
        spec = attach_research_reviews(root=root, descriptor=descriptor, spec=original_spec,
            path=packet, expected_sha256=sha256_file(packet), event_sha256=None,
            require_model_binding=True)
    assert spec.human_research_approval.reviewer_id == 'SYNTHETIC_HUMAN'
    assert spec.model_validity_input is original_spec.model_validity_input
    assert spec.model_validity_input.blockers
    assert spec.event_materiality_review is None
    assert not result['event_materiality_approved'] and not result['price_admitted']
    assert package['research_case']['blockers']


def test_authenticated_g3_v1_cannot_carry_unbound_event_materiality(signed):
    signed['response']['whole_model_approval'] = whole_approval(signed)
    result = consume(signed)
    root = signed['root']
    package = json.loads((signed['path'].parent/'package.json').read_text(encoding='utf-8'))
    descriptor = build_descriptor(package, root=root)
    packet = json.loads((root/result['review_packet_binding']['path']).read_text(encoding='utf-8'))
    event = root/'unbound-event-review.json'
    write_new_json(event, {})
    packet['bindings']['event_materiality'] = dict(path=event.name, sha256=sha256_file(event))
    path = root/'g3-with-unbound-event.json'
    write_new_json(path, packet)
    with _use_test_trust_registry(signed['registry']):
        with pytest.raises(ValueError, match='requires a v2'):
            attach_research_reviews(root=root, descriptor=descriptor,
                spec=build_research_run_spec(descriptor), path=path,
                expected_sha256=sha256_file(path), event_sha256=None, require_model_binding=True)


@pytest.mark.parametrize('state', ['REJECTED', 'INSUFFICIENT', None])
def test_partial_negative_or_unknown_never_approves_whole(signed, state):
    signed['response']['groups'][0]['response'] = state
    result = consume(signed)
    assert any('EARNINGS:' in b for b in result['blockers'])
    assert not result['whole_model_review_present']


@pytest.mark.parametrize('change', ['reviewer', 'candidate', 'facts', 'assumptions', 'model', 'valuation',
                                   'scope', 'future', 'before_candidate', 'partial_whole', 'whole_scope'])
def test_response_rejects_version_identity_scope_and_time_drift(signed, change):
    response = signed['response']
    if change == 'reviewer': response['reviewer_id'] = 'UNAUTHORIZED'
    elif change == 'candidate': response['candidate_binding']['sha256'] = '0'*64
    elif change in ('facts', 'assumptions'):
        response['model_context'][change+'_sha256'] = '0'*64
    elif change == 'model': response['model_context']['model_version'] = 'CHANGED'
    elif change == 'valuation': response['valuation_artifact_sha256'] = '0'*64
    elif change == 'scope': response['groups'][0]['field_paths'] = ['facts.scenario_inputs']
    elif change == 'future': response['reviewed_at'] = (datetime.now(timezone.utc)+timedelta(days=2)).isoformat()
    elif change == 'before_candidate': response['reviewed_at'] = '2020-01-01T00:00:00+00:00'
    else:
        response['whole_model_approval'] = whole_approval(signed)
        if change == 'partial_whole': response['groups'][0]['response'] = 'INSUFFICIENT'
        else:
            signed['trust']['scopes'] = ['human_group_research']
            signed['registry'].write_text(json.dumps(dict(schema_version='authorization-trust-root-registry-v1',
                pinned_trust_root_sha256=[trust_root_fingerprint(signed['trust'])])), encoding='utf-8')
    with pytest.raises(ValueError): consume(signed)
    assert not (signed['root']/'runtime/response-consumed').exists()


def test_self_signed_unpinned_identity_is_not_authority(signed):
    with pytest.raises(ValueError, match='not pinned'): consume(signed, pin=False)


def test_editing_signed_response_invalidates_signature(signed, monkeypatch):
    key = signed['key']
    class WrongSignature:
        def sign(self, value): return key.sign(value + b'tampered')
    signed['key'] = WrongSignature()
    with pytest.raises(ValueError, match='signature'): consume(signed)


def test_whole_model_hash_cannot_be_rebound(signed):
    signed['response']['whole_model_approval'] = whole_approval(signed)
    signed['response']['whole_model_approval']['assumption_set_sha256'] = '0'*64
    with pytest.raises(ValueError, match='superseded'): consume(signed)


def test_revocation_blocks_old_response_packet_and_stripped_provenance(signed):
    root = signed['root']
    signed['response']['whole_model_approval'] = whole_approval(signed)
    first = consume(signed)
    old_payload = deepcopy(signed['response'])
    signed['response']['reviewed_at'] = datetime.now(timezone.utc).isoformat()
    signed['response']['supersedes_response_sha256'] = sha256_file(root/'response.json')
    signed['response']['groups'][0]['response'] = 'REJECTED'
    signed['response']['whole_model_approval'] = None
    second = consume(signed, suffix='-revoked', previous=root/'response.json')
    assert 'EARNINGS:REJECTED' in second['blockers']
    signed['response'] = old_payload
    with pytest.raises(ValueError, match='predecessor|replay'):
        consume(signed, suffix='-replay')
    package = json.loads((signed['path'].parent/'package.json').read_text(encoding='utf-8'))
    descriptor = build_descriptor(package, root=root)
    packet_path = root/first['review_packet_binding']['path']
    with _use_test_trust_registry(signed['registry']):
        with pytest.raises(ValueError, match='superseded'):
            attach_research_reviews(root=root, descriptor=descriptor, spec=build_research_run_spec(descriptor),
                path=packet_path, expected_sha256=sha256_file(packet_path), event_sha256=None)
        packet = json.loads(packet_path.read_text(encoding='utf-8'))
        packet.pop('authenticated_response_binding')
        packet.pop('reviewed_candidate_binding')
        stripped = root/'stripped.json'
        write_new_json(stripped, packet)
        with pytest.raises(ValueError, match='stripped|unsigned legacy G3'):
            attach_research_reviews(root=root, descriptor=descriptor, spec=build_research_run_spec(descriptor),
                path=stripped, expected_sha256=sha256_file(stripped), event_sha256=None)


def test_unconsumed_forged_predecessor_is_not_review_history(signed):
    root = signed['root']
    forged = root/'forged.json'
    write_new_json(forged, dict(payload=deepcopy(signed['response']), signature='00'*64))
    signed['response']['supersedes_response_sha256'] = sha256_file(forged)
    with pytest.raises(ValueError, match='not been authenticated'):
        consume(signed, previous=forged)


def test_prior_signed_original_tamper_blocks_supersession(signed):
    root = signed['root']
    consume(signed)
    prior = root/'response.json'
    value = json.loads(prior.read_text(encoding='utf-8'))
    value['signature'] = '00'*64
    prior.write_text(json.dumps(value), encoding='utf-8')
    signed['response']['reviewed_at'] = datetime.now(timezone.utc).isoformat()
    signed['response']['supersedes_response_sha256'] = sha256_file(prior)
    with pytest.raises(ValueError, match='drift'):
        consume(signed, suffix='-next', previous=prior)


@pytest.mark.parametrize('change', ['group_only', 'negative_group', 'future', 'before_candidate'])
def test_handmade_history_cannot_bypass_full_response_validator(signed, change):
    from value_investment_agent.application.product.research_reviews import _authenticated_review_history
    root = signed['root']
    signed['response']['whole_model_approval'] = whole_approval(signed)
    if change == 'group_only': signed['trust']['scopes'] = ['human_group_research']
    elif change == 'negative_group': signed['response']['groups'][0]['response'] = 'REJECTED'
    elif change == 'future':
        signed['response']['reviewed_at'] = (datetime.now(timezone.utc)+timedelta(hours=2)).isoformat()
    else: signed['response']['reviewed_at'] = '2020-01-01T00:00:00+00:00'
    registry = root/'manual-registry.json'
    write_new_json(registry, dict(schema_version='authorization-trust-root-registry-v1',
        pinned_trust_root_sha256=[trust_root_fingerprint(signed['trust'])]))
    envelope = dict(payload=signed['response'], signature=signed['key'].sign(REVIEW_RESPONSE_PURPOSE +
        canonical_contract_payload(signed['response']).encode('utf-8')).hex())
    response_path, trust_path = root/'manual-response.json', root/'manual-trust.json'
    write_new_json(response_path, envelope)
    write_new_json(trust_path, signed['trust'])
    digest = sha256_file(signed['path'])
    record = root/'runtime/research-review-responses'/digest[:24]/(sha256_file(response_path)[:24]+'.json')
    write_new_json(record, dict(candidate_binding=signed['response']['candidate_binding'],
        response_binding=dict(path=response_path.name, sha256=sha256_file(response_path)),
        trust_root_binding=dict(path=trust_path.name, sha256=sha256_file(trust_path))))
    with _use_test_trust_registry(registry):
        with pytest.raises(ValueError): _authenticated_review_history(root, digest)


def test_distinct_candidates_for_same_model_cannot_hide_a_rejection(signed):
    root = signed['root']
    signed['response']['whole_model_approval'] = whole_approval(signed)
    first = consume(signed)
    old_path = signed['path']
    copied = old_path.with_name('candidate-copy.json')
    candidate = json.loads(old_path.read_text(encoding='utf-8'))
    candidate['note'] = 'Synthetic nonmodel metadata fork'
    write_new_json(copied, candidate)
    signed['path'] = copied
    signed['response'] = prepare_pending_review_response(root=root, candidate_path=copied,
        candidate_sha256=sha256_file(copied))
    signed['response'].update(reviewer_id='SYNTHETIC_HUMAN', reviewed_at=datetime.now(timezone.utc).isoformat())
    signed['response']['groups'][0].update(response='REJECTED', response_reason='Synthetic refusal',
        confirmed_scope='Same exact financial model')
    consume(signed, suffix='-fork')
    package = json.loads((old_path.parent/'package.json').read_text(encoding='utf-8'))
    descriptor = build_descriptor(package, root=root)
    packet = root/first['review_packet_binding']['path']
    with _use_test_trust_registry(signed['registry']):
        with pytest.raises(ValueError, match='conflicting candidate heads'):
            attach_research_reviews(root=root, descriptor=descriptor, spec=build_research_run_spec(descriptor),
                path=packet, expected_sha256=sha256_file(packet), event_sha256=None)


def test_expired_history_can_be_superseded_by_new_valid_pinned_root(signed, monkeypatch):
    from value_investment_agent.application.product import research_reviews
    root = signed['root']
    old_trust = deepcopy(signed['trust'])
    consume(signed)
    later = datetime.now(timezone.utc) + timedelta(days=2)
    class LaterClock(datetime):
        @classmethod
        def now(cls, tz=None): return later
    monkeypatch.setattr(research_reviews, 'datetime', LaterClock)
    signed['response'].update(reviewed_at=later.isoformat(),
        supersedes_response_sha256=sha256_file(root/'response.json'))
    signed['trust'].update(valid_from=(later-timedelta(hours=1)).isoformat(),
        valid_until=(later+timedelta(days=1)).isoformat())
    signed['registry'].write_text(json.dumps(dict(schema_version='authorization-trust-root-registry-v1',
        pinned_trust_root_sha256=[trust_root_fingerprint(old_trust), trust_root_fingerprint(signed['trust'])])), encoding='utf-8')
    result = consume(signed, suffix='-renewed', previous=root/'response.json')
    assert result['authenticated_reviewer'] == 'SYNTHETIC_HUMAN'
    assert not result['price_admitted']
