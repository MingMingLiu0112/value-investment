"""TEST_ONLY signing/transport integration; no real identity or approval."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
import pytest

from test_d2_conditional_shared_service import synthetic_chain, _store, SYMBOL, SYNTHETIC, DAY
from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.application.product.research_materiality_reviews import (
    MATERIALITY_RESPONSE_PURPOSE, prepare_materiality_review_handoff,
    consume_materiality_review_response,
)
from value_investment_agent.application.product import research_materiality_reviews as transport_service
from value_investment_agent.application.product.research_reviews import attach_research_reviews
from value_investment_agent.application.product.company_research import (
    ResearchInputValidationError,
    run_company_research_for_symbol,
)
from value_investment_agent.m1_valuation_package_builder import build_descriptor
from value_investment_agent.research_input import build_research_run_spec
from value_investment_agent.research_run_contract import canonical_contract_payload
from value_investment_agent.infrastructure.evidence.trust_root_registry import (
    _use_test_trust_registry, trust_root_fingerprint,
)


@pytest.fixture
def transport(synthetic_chain):
    root, package, _, app, _, approval, review, _ = synthetic_chain
    original = json.loads(package.read_text(encoding='utf-8'))
    original['model_validity_input'].pop('event_scan_ref')
    _store(root, package.name, original)
    scan_path = root / 'synthetic-scan.json'
    scan = json.loads(scan_path.read_text(encoding='utf-8'))
    second = deepcopy(scan['announcements'][0])
    second['announcement_id'] = '9000000002'
    second['title'] = 'SECOND_TEST_ONLY_ANNOUNCEMENT'
    path, digest = _store(root, 'second-source.pdf', {'scope': SYNTHETIC, 'second': True})
    second['evidence_refs'] = [dict(id='second-original', path=path.name, sha256=digest)]
    scan['announcements'].append(second)
    _store(root, scan_path.name, scan)
    scan_hash = sha256_file(scan_path)
    handoff = prepare_materiality_review_handoff(root=root, package_path=package,
        package_sha256=sha256_file(package), scan_path=scan_path, scan_sha256=scan_hash)
    handoff_path, handoff_hash = _store(root, 'handoff.json', handoff)
    reviewer = 'TEST_ONLY_MATERIALITY_REVIEWER'
    reviewed = review.reviewed_at
    first = replace(review.decisions[0], reviewer_id=reviewer, reviewed_at=reviewed)
    second_decision = replace(first, announcement_id=second['announcement_id'],
        event_decision_id='second-test-decision', title=second['title'],
        source_ref=dict(id='second-original', path=path.name), source_sha256=digest)
    typed = replace(review, reviewer_id=reviewer, scan_sha256=scan_hash,
        decisions=(first, second_decision)).as_policy()
    typed['model_context'] = handoff['model_context']
    response = dict(handoff['unsigned_response'], reviewer_id=reviewer,
                    reviewed_at=reviewed.isoformat(), event_materiality=typed)
    key = Ed25519PrivateKey.generate()
    trust = dict(schema_version='research-review-transport-trust-root-v1', reviewer_id=reviewer,
        public_key=key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex(),
        scopes=['human_event_materiality'], symbols=[SYMBOL],
        valid_from=(reviewed-timedelta(days=1)).isoformat(),
        valid_until=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat())
    return dict(root=root, package=package, scan_path=scan_path, scan_hash=scan_hash,
        handoff=handoff, handoff_path=handoff_path, handoff_hash=handoff_hash,
        response=response, key=key, trust=trust, app=app, approval=approval)


def _inputs(f, *, mutate_signature=False, suffix=''):
    root = f['root']
    signature = f['key'].sign(MATERIALITY_RESPONSE_PURPOSE +
        canonical_contract_payload(f['response']).encode('utf-8')).hex()
    if mutate_signature:
        signature = '0' * 128
    response, rh = _store(root, 'response'+suffix+'.json',
                          dict(payload=f['response'], signature=signature))
    trust, th = _store(root, 'trust'+suffix+'.json', f['trust'])
    registry, _ = _store(root, 'registry.json', dict(
        schema_version='authorization-trust-root-registry-v1',
        pinned_trust_root_sha256=[trust_root_fingerprint(f['trust'])]))
    return registry, dict(root=root, handoff_path=f['handoff_path'], handoff_sha256=f['handoff_hash'],
        response_path=response, response_sha256=rh, trust_root_path=trust,
        trust_root_sha256=th, output_dir=root / ('runtime/import'+suffix))


def _descriptor(f):
    package = json.loads(f['package'].read_text(encoding='utf-8'))
    ref = dict(id='daily-event-'+f['scan_hash'], symbol=SYMBOL,
        path=f['scan_path'].name, sha256=f['scan_hash'])
    package['model_validity_input'] = dict(package['model_validity_input'],
        event_scan_ref=ref, event_scan_evidence_refs=[ref])
    return build_descriptor(package, root=f['root'])


def _attach(f, packet):
    descriptor = _descriptor(f)
    return attach_research_reviews(root=f['root'], descriptor=descriptor,
        spec=build_research_run_spec(descriptor), path=packet,
        expected_sha256=sha256_file(packet), event_sha256=f['scan_hash'], require_model_binding=True)


def test_signed_materiality_cannot_use_unsigned_g3_for_a_positive_candidate(transport):
    f = transport
    registry, args = _inputs(f)
    with _use_test_trust_registry(registry):
        receipt = consume_materiality_review_response(**args)
        packet = f['root'] / receipt['review_packet_binding']['path']
        spec = _attach(f, packet)
        result = f['app'].run_company_research(spec)
        assert result.model_validity.status == 'VALID'
        assert result.price_bridge.bridge_status == 'READY'
        assert len(result.event_materiality_review.decisions) == 2
        assert result.decision_recommendation.recommendation_action == 'NO_ACTION'
        assert receipt['whole_model_approved'] is False
        assert receipt['research_admitted'] is receipt['price_admitted'] is False
        # An unsigned G3 attached beside signed materiality must never become a positive candidate.
        approval_path, approval_hash = _store(f['root'], 'test-only-g3.json', f['approval'].as_policy())
        combined = json.loads(packet.read_text(encoding='utf-8'))
        combined['bindings']['human_approval'] = dict(path=approval_path.name, sha256=approval_hash)
        merged, _ = _store(f['root'], 'combined.json', combined)
        with pytest.raises(ResearchInputValidationError, match='unsigned legacy G3'):
            run_company_research_for_symbol(root=f['root'], symbol=SYMBOL,
                package_path=f['package'], event_path=f['scan_path'], event_sha256=f['scan_hash'],
                reviews_path=merged, reviews_sha256=sha256_file(merged), schedule_request=dict(
                    schema_version='research-schedule-request-v1', symbol=SYMBOL, source_id=SYNTHETIC,
                    period=DAY.isoformat(), research_question_id='test-only-materiality-transport',
                    blocker_id='initial_research', reopen_condition_met=False, new_evidence_ids=[]))


@pytest.mark.parametrize('drift', [
    'signature', 'symbol', 'scope', 'reviewer', 'future', 'expired', 'descriptor',
    'scan_hash', 'window', 'announcement_id', 'published_at', 'source_sha256',
    'missing_decision', 'duplicate_decision', 'decision_reviewer', 'original_bytes',
])
def test_signed_materiality_rejects_wrong_or_tampered_objects(transport, drift):
    f = transport
    response = f['response']
    review = response['event_materiality']
    if drift == 'symbol': response['symbol'] = '600887'
    if drift == 'scope': f['trust']['scopes'] = ['human_whole_model']
    if drift == 'reviewer': response['reviewer_id'] = 'WRONG_TEST_ONLY'
    if drift == 'future': response['reviewed_at'] = (datetime.now(timezone.utc)+timedelta(days=3)).isoformat()
    if drift == 'expired': f['trust']['valid_until'] = response['reviewed_at']
    if drift == 'descriptor': response['model_context']['facts_sha256'] = '0'*64
    if drift == 'scan_hash': review['scan_sha256'] = '0'*64
    if drift == 'window': review['scan_from'] = '2026-09-20'
    if drift == 'announcement_id': review['decisions'][0]['announcement_id'] = '9000000003'
    if drift == 'published_at': review['decisions'][0]['published_at'] = '2026-09-21T07:00:00+00:00'
    if drift == 'source_sha256': review['decisions'][0]['source_sha256'] = '0'*64
    if drift == 'missing_decision': review['decisions'].pop()
    if drift == 'duplicate_decision': review['decisions'].append(deepcopy(review['decisions'][0]))
    if drift == 'decision_reviewer': review['decisions'][0]['reviewer_id'] = 'WRONG_TEST_ONLY'
    if drift == 'original_bytes':
        _store(f['root'], 'second-source.pdf', dict(tampered=True))
    registry, args = _inputs(f, mutate_signature=(drift == 'signature'))
    with _use_test_trust_registry(registry), pytest.raises(ValueError):
        consume_materiality_review_response(**args)
    assert not args['output_dir'].exists()


@pytest.mark.parametrize('drift', ['revoked', 'replay', 'stripped', 'artifact', 'receipt', 'scan', 'package'])
def test_consumption_revalidates_provenance_and_current_trust(transport, drift):
    f = transport
    registry, args = _inputs(f)
    with _use_test_trust_registry(registry):
        receipt = consume_materiality_review_response(**args)
        packet = f['root'] / receipt['review_packet_binding']['path']
        if drift == 'replay':
            with pytest.raises(ValueError, match='replay'):
                consume_materiality_review_response(**dict(args, output_dir=f['root']/'runtime/another'))
            return
        if drift == 'revoked':
            _store(f['root'], registry.name, dict(schema_version='authorization-trust-root-registry-v1',
                                                pinned_trust_root_sha256=[]))
        elif drift == 'stripped':
            obj = json.loads(packet.read_text(encoding='utf-8'))
            del obj['authenticated_materiality_binding']
            packet, _ = _store(f['root'], 'stripped.json', obj)
        elif drift == 'artifact':
            obj = json.loads(packet.read_text(encoding='utf-8'))
            artifact = f['root'] / obj['bindings']['event_materiality']['path']
            value = json.loads(artifact.read_text(encoding='utf-8'))
            value['review_id'] = 'tampered'
            _store(f['root'], artifact.relative_to(f['root']).as_posix(), value)
            obj['bindings']['event_materiality']['sha256'] = sha256_file(artifact)
            packet, _ = _store(f['root'], 'tampered-packet.json', obj)
        elif drift == 'receipt':
            _store(f['root'], 'runtime/import/consumption.json', dict(tampered=True))
        elif drift == 'scan':
            _store(f['root'], f['scan_path'].name, dict(tampered=True))
        elif drift == 'package':
            obj = json.loads(f['package'].read_text(encoding='utf-8'))
            obj['rationale'] = 'tampered package'
            _store(f['root'], f['package'].name, obj)
        with pytest.raises((ValueError, KeyError)):
            _attach(f, packet)


@pytest.mark.parametrize('schema', ['shared-research-review-inputs-v1', 'shared-research-review-inputs-v2'])
def test_fresh_unsigned_context_cannot_reach_real_application(transport, schema):
    f = transport
    source, digest = _store(f['root'], 'unsigned-materiality.json', f['response']['event_materiality'])
    packet, _ = _store(f['root'], 'unsigned-packet.json', dict(schema_version=schema,
        action='no_order', symbol=SYMBOL,
        bindings=dict(event_materiality=dict(path=source.name, sha256=digest))))
    with pytest.raises(ValueError, match='provenance|v2 research review'):
        _attach(f, packet)
    assert not (f['root'] / 'runtime/materiality-review-responses').exists()


@pytest.mark.parametrize('failure', ['event-materiality.json', 'consumption.json', 'completion.json'])
def test_interrupted_consumption_resumes_only_exact_original_inputs(transport, monkeypatch, failure):
    f = transport
    registry, args = _inputs(f)
    original = transport_service._append_review_json
    def fail_once(path, payload):
        if path.name == failure:
            raise OSError('TEST_ONLY injected interruption')
        return original(path, payload)
    with _use_test_trust_registry(registry):
        monkeypatch.setattr(transport_service, '_append_review_json', fail_once)
        with pytest.raises(OSError, match='injected'):
            consume_materiality_review_response(**args)
        monkeypatch.setattr(transport_service, '_append_review_json', original)
        checkpoint_hash = sha256_file(args['output_dir'] / 'incomplete-consumption.json')
        resume = dict(args, resume_incomplete=True, incomplete_consumption_sha256=checkpoint_hash)
        changed = deepcopy(f['response'])
        changed['event_materiality']['review_id'] = 'different-valid-signed-response'
        signed, signed_hash = _store(f['root'], 'different-response.json', dict(payload=changed,
            signature=f['key'].sign(MATERIALITY_RESPONSE_PURPOSE +
                canonical_contract_payload(changed).encode('utf-8')).hex()))
        with pytest.raises(ValueError, match='exact original'):
            consume_materiality_review_response(**dict(resume, response_path=signed,
                                                       response_sha256=signed_hash))
        receipt = consume_materiality_review_response(**resume)
        packet = f['root'] / receipt['review_packet_binding']['path']
        result = f['app'].run_company_research(_attach(f, packet))
        assert result.model_validity.status == 'VALID'
        with pytest.raises(ValueError, match='already completed'):
            consume_materiality_review_response(**resume)


def test_signed_recalculation_reaches_real_shared_service_and_projection(transport):
    f = transport
    decision = f['response']['event_materiality']['decisions'][0]
    decision.update(human_decision='MATERIAL_REQUIRES_RECALCULATION', requires_model_stale=True,
                    requires_recalculation=True, requires_followup=False)
    registry, args = _inputs(f)
    with _use_test_trust_registry(registry):
        receipt = consume_materiality_review_response(**args)
        result = f['app'].run_company_research(_attach(f, f['root']/receipt['review_packet_binding']['path']))
        assert result.model_validity.status == 'STALE'
        assert result.price_bridge.bridge_status != 'READY'
        from value_investment_agent.application.product.company_research import _serialize_outcome
        from value_investment_agent.presentation.read_models.shadow_daily_review import render_shadow_company_review
        serialized = _serialize_outcome(result)
        product = dict(symbol=SYMBOL, suggested_state='NOT_READY', position_guidance=None,
                       blockers=list(result.blockers))
        card = render_shadow_company_review(research=dict(result=serialized,
            session_date=DAY.isoformat(), run_id=result.run_id), model=dict(
                model_validity=serialized['model_validity'], price_bridge=serialized['price_bridge'],
                valuation_result=serialized['valuation']), decision=product, product=product,
            audit=dict(blockers=list(result.blockers), input_consistency_status='SHADOW_INPUT_INCOMPLETE'))
        assert 'STALE' in card and 'action=no_order' in card
        assert 'requires recalculation' in card


@pytest.fixture
def registered_transport(transport):
    from value_investment_agent.application.product.quote_bridge import pin_quote_bridge_for_symbol
    from value_investment_agent.application.product.incremental_validity import register_incremental_validity_binding
    f = transport
    root = f['root']
    package_payload = json.loads(f['package'].read_text(encoding='utf-8'))
    f['package'], _ = _store(root, 'runtime/registered/package.json', package_payload)
    quote = json.loads((root / 'synthetic-quote.json').read_text(encoding='utf-8'))
    bundle, _ = _store(root, 'runtime/registered/quote.json', quote)
    pin_quote_bridge_for_symbol(root, SYMBOL, bundle, f['package'])
    scan = json.loads(f['scan_path'].read_text(encoding='utf-8'))
    scan['retrieved_at'] = '2026-09-22T00:00:00+00:00'
    f['scan_path'], f['scan_hash'] = _store(root, 'registered-scan.json', scan)
    scan_ref = dict(path=f['scan_path'].name, sha256=f['scan_hash'])
    observation, obs_sha = _store(root, 'observation.json', dict(
        schema_version='daily-event-observation-v1', symbol=SYMBOL, scan_from=DAY.isoformat(),
        scan_to=DAY.isoformat(), scan_binding=scan_ref, acquired_at=scan['retrieved_at'],
        pagination_complete=True, collection_status='OFFICIAL_QUERY_ARCHIVED', announcement_count=2,
        source_bindings=scan['evidence_refs'], full_calendar_window_elapsed=True))
    f['handoff'] = prepare_materiality_review_handoff(root=root, package_path=f['package'],
        package_sha256=sha256_file(f['package']), scan_path=f['scan_path'], scan_sha256=f['scan_hash'])
    f['handoff_path'], f['handoff_hash'] = _store(root, 'registered-handoff.json', f['handoff'])
    typed = f['response']['event_materiality']
    typed.update(scan_sha256=f['scan_hash'], model_context=f['handoff']['model_context'],
                 reviewed_at='2026-09-22T00:30:00+00:00', review_as_of='2026-09-22')
    for item in typed['decisions']:
        item['reviewed_at'] = typed['reviewed_at']
    f['response'] = dict(f['handoff']['unsigned_response'], reviewer_id=f['trust']['reviewer_id'],
        reviewed_at=typed['reviewed_at'], event_materiality=typed)
    binding_path, binding_hash = _store(root, 'incremental-binding.json', dict(
        schema_version='incremental-validity-binding-v1', action='no_order', symbol=SYMBOL,
        package_ref=dict(path=f['package'].relative_to(root).as_posix(), sha256=sha256_file(f['package'])),
        research_as_of=DAY.isoformat(), review_cutoff=DAY.isoformat(),
        model_id=package_payload['model_validity_input']['model_id'], scan_ref=scan_ref,
        observation_ref=dict(path=observation.name, sha256=obs_sha)))
    f['incremental_ref'] = dict(path=binding_path.name, sha256=binding_hash)
    f['today'] = datetime(2026, 9, 22, 1, tzinfo=timezone.utc)
    register_incremental_validity_binding(root, SYMBOL, f['incremental_ref'], DAY, f['today'])
    return f


def test_registered_quote_consumes_signed_materiality_and_identity_tracks_revocation(registered_transport):
    from value_investment_agent.application.product.quote_bridge import execute_quote_bridge_for_symbol
    from value_investment_agent.application.product.incremental_validity import incremental_validity_identity
    from value_investment_agent.application.product.daily_public_packet import build_daily_public_packet
    from test_daily_public_packet_identity import build_verified_tree
    f = registered_transport
    root = f['root']
    build_verified_tree(root)
    registry, args = _inputs(f)
    with _use_test_trust_registry(registry):
        identity_before = incremental_validity_identity(root, f['incremental_ref'])
        publication_before = build_daily_public_packet(root, generated_at=f['today'])['publication_id']
        before = execute_quote_bridge_for_symbol(root, SYMBOL, today=f['today'])
        route = before['incremental_validity']['materiality_review_route']
        assert route['status'] == 'EXTERNAL_SIGNATURE_REQUIRED'
        assert before['price_comparison']['bridge_status'] == 'INVALID'
        assert route['handoff_binding']['sha256']
        receipt = consume_materiality_review_response(**args)
        identity_after = incremental_validity_identity(root, f['incremental_ref'])
        assert identity_before != identity_after
        publication_after = build_daily_public_packet(root, generated_at=f['today'])['publication_id']
        assert publication_after != publication_before
        after = execute_quote_bridge_for_symbol(root, SYMBOL, today=f['today'])
        assert after['incremental_validity'].get('materiality_review_route', {}).get('status') == 'AUTHENTICATED_RESPONSE_IMPORTED', after
        # Authentication approves its exact historical window, not unqueried later dates.
        assert after['historical_model_validity']['status'] == 'VALID'
        assert after['historical_price_comparison']['bridge_status'] == 'READY'
        assert after['incremental_validity']['status'] == 'UNKNOWN'
        assert 'CURRENT_EVENT_COVERAGE_NOT_VERIFIED' in after['incremental_validity']['blockers']
        assert after['price_comparison']['bridge_status'] != 'READY'
        assert after['price_admitted'] is False
        assert after['incremental_validity']['formal_eligibility'] is False
        assert receipt['whole_model_approved'] is False
        _store(root, registry.name, dict(schema_version='authorization-trust-root-registry-v1',
                                        pinned_trust_root_sha256=[]))
        assert incremental_validity_identity(root, f['incremental_ref']) != identity_after
        assert build_daily_public_packet(root, generated_at=f['today'])['publication_id'] != publication_after
        revoked = execute_quote_bridge_for_symbol(root, SYMBOL, today=f['today'])
        assert revoked['incremental_validity']['status'] == 'UNKNOWN'
        assert revoked.get('price_comparison', {}).get('bridge_status') != 'READY'
        assert revoked.get('historical_model_validity', {}).get('status') != 'VALID'
        assert revoked.get('historical_price_comparison', {}).get('bridge_status') != 'READY'


@pytest.mark.parametrize('role', ['response', 'trust_root', 'receipt', 'packet', 'materiality'])
def test_publication_identity_binds_each_authenticated_original_byte(registered_transport, role):
    from value_investment_agent.application.product.daily_public_packet import build_daily_public_packet
    from value_investment_agent.application.product.quote_bridge import execute_quote_bridge_for_symbol
    from test_daily_public_packet_identity import build_verified_tree
    f = registered_transport
    root = f['root']
    build_verified_tree(root)
    registry, args = _inputs(f)
    with _use_test_trust_registry(registry):
        receipt = consume_materiality_review_response(**args)
        packet_path = root / receipt['review_packet_binding']['path']
        packet = json.loads(packet_path.read_text(encoding='utf-8'))
        paths = dict(response=args['response_path'], trust_root=args['trust_root_path'],
            receipt=args['output_dir']/'consumption.json', packet=packet_path,
            materiality=root/packet['bindings']['event_materiality']['path'])
        before = build_daily_public_packet(root, generated_at=f['today'])
        paths[role].write_bytes(paths[role].read_bytes() + b' ')
        after = build_daily_public_packet(root, generated_at=f['today'])
        assert after['publication_id'] != before['publication_id']
        execution = execute_quote_bridge_for_symbol(root, SYMBOL, today=f['today'])
        assert execution['incremental_validity']['status'] == 'UNKNOWN'
        assert execution.get('price_comparison', {}).get('bridge_status') != 'READY'
