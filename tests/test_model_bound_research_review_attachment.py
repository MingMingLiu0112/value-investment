"""SYNTHETIC engineering contracts, never real issuer approval or trade evidence."""
from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json

import pytest

from test_d2_conditional_shared_service import SYNTHETIC, _store, synthetic_chain
from test_d2_source_bound_package_contract import source_package
from test_event_materiality import DECISION_NOT_MATERIAL, _decision, _review
from value_investment_agent.application.product.company_research import (
    ResearchInputValidationError,
    run_company_research_for_symbol,
)
from value_investment_agent.application.product.research_reviews import (
    attach_research_reviews,
    build_research_review_model_context,
)
from value_investment_agent.event_scan import AnnouncementReview, EventScanResult
from value_investment_agent.human_research_approval import artifact_fingerprint
from value_investment_agent.m1_valuation_package_builder import build_descriptor
from value_investment_agent.research_artifact_codecs import artifact_payload
from value_investment_agent.research_input import (
    build_research_run_spec,
    descriptor_from_payload,
)


CONTEXT_KEYS = (
    'input_descriptor_sha256', 'research_case_sha256', 'facts_sha256',
    'assumptions_sha256', 'model_id', 'model_version', 'profile_id', 'research_as_of',
)
V1 = 'shared-research-review-inputs-v1'
V2 = 'shared-research-review-inputs-v2'


def _context(descriptor):
    return build_research_review_model_context(
        descriptor=descriptor, spec=build_research_run_spec(descriptor),
    )


def _packet(root, symbol, review, context, *, schema=V2, outer_context=None):
    payload = review.as_policy()
    if context is not None:
        payload['model_context'] = context
    raw_path, raw_hash = _store(root, 'synthetic-bound-materiality.json', payload)
    packet = {
        'schema_version': schema, 'symbol': symbol, 'action': 'no_order',
        'scope': SYNTHETIC,
        'bindings': {'event_materiality': {'path': raw_path.name, 'sha256': raw_hash}},
    }
    if outer_context is not None:
        packet['model_context'] = outer_context
    path, digest = _store(root, 'synthetic-bound-reviews.json', packet)
    return path, digest, raw_path, raw_hash


def _attach(chain, *, descriptor=None, spec=None, context=None, schema=V2,
            strict=True, outer_context=None):
    root, _, original, _, _, _, review, scan_hash = chain
    descriptor = descriptor if descriptor is not None else original
    spec = spec if spec is not None else build_research_run_spec(descriptor)
    path, digest, _, _ = _packet(
        root, original.symbol, review, context, schema=schema, outer_context=outer_context,
    )
    return attach_research_reviews(
        root=root, spec=spec, descriptor=descriptor, path=path,
        expected_sha256=digest, event_sha256=scan_hash, require_model_binding=strict,
    )


def _changed_descriptor(descriptor, mutation):
    payload = deepcopy(descriptor.as_policy())
    payload.pop('input_sha256')
    if mutation == 'scenario':
        payload['facts']['scenario_inputs']['bull']['terminal_roe'] = '0.13'
        for item in payload['assumptions']['assumptions']:
            if item['name'] == 'terminal_roe':
                item['bull'] = '0.13'
        for binding in payload['assumption_bindings']:
            if binding['field_path'] == 'terminal_roe' and binding['scenario'] == 'bull':
                binding['expected_value'] = '0.13'
    elif mutation == 'assumptions':
        payload['assumptions']['assumptions'][0]['rationale'] = SYNTHETIC + '_CHANGED'
    elif mutation == 'facts':
        payload['facts']['operating_inputs']['ordinary_shares'] = '101'
    elif mutation == 'case':
        payload['research_case']['thesis'] = SYNTHETIC + '_CHANGED'
    elif mutation in ('model_version', 'rule_version', 'parser_version', 'scan_watermark'):
        payload['dependencies'][mutation] = 'synthetic-changed-dependency'
    elif mutation == 'model':
        payload['requested_model'] = 'residual_income_or_equity_value'
    elif mutation == 'research_as_of':
        payload['point_in_time']['research_as_of'] = '2026-09-22'
        payload['research_case']['as_of'] = '2026-09-22'
        payload['point_in_time']['available_at'] = '2026-09-22T09:00:00+00:00'
        payload['point_in_time']['computed_at'] = '2026-09-22T09:01:00+00:00'
    else:
        raise AssertionError(mutation)
    return descriptor_from_payload(payload)


def test_v2_exact_original_context_binds_spec_without_promoting_research(synthetic_chain):
    root, _, descriptor, app, baseline, _, review, scan_hash = synthetic_chain
    context = _context(descriptor)
    canonical = descriptor.as_policy()
    assert set(context) == set(CONTEXT_KEYS)
    assert context['input_descriptor_sha256'] == descriptor.input_sha256
    for role, key in (('research_case', 'research_case_sha256'), ('facts', 'facts_sha256'),
                      ('assumptions', 'assumptions_sha256')):
        assert context[key] == artifact_fingerprint(canonical[role])
    path, digest, raw_path, raw_hash = _packet(root, descriptor.symbol, review, context)
    original_bytes = raw_path.read_bytes()
    attached = attach_research_reviews(
        root=root, spec=build_research_run_spec(descriptor), descriptor=descriptor,
        path=path, expected_sha256=digest, event_sha256=scan_hash, require_model_binding=True,
    )
    assert attached.input_descriptor_sha256 == hashlib.sha256(json.dumps({
        'descriptor': descriptor.input_sha256, 'review_packet': digest,
        'model_context': context,
    }, sort_keys=True).encode('utf-8')).hexdigest()
    assert attached.input_descriptor_sha256 != descriptor.input_sha256
    assert raw_path.read_bytes() == original_bytes
    assert hashlib.sha256(original_bytes).hexdigest() == raw_hash
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    assert attached.event_materiality_review == review
    assert attached.human_research_approval is None
    assert attached.valuation_approval is None
    assert attached.facts == descriptor.facts
    assert attached.assumptions == descriptor.assumptions
    outcome = app.run_company_research(attached)
    assert outcome.valuation == baseline.valuation
    assert outcome.valuation.status == 'conditional_research_only'
    assert outcome.gate.results['G3_估值门'] is False
    recommendation = outcome.decision_recommendation
    assert recommendation.recommendation_action == 'NO_ACTION'
    assert recommendation.action == 'no_order'
    assert recommendation.position_guidance is None
    assert recommendation.portfolio_input_status == 'BLOCKED_PRIVATE_INPUT'
    # This attachment repair does not change the legacy domain codec: keep raw provenance.
    assert 'model_context' not in artifact_payload(attached.event_materiality_review)[1]
    assert json.loads(raw_path.read_text(encoding='utf-8'))['model_context'] == context


@pytest.mark.parametrize('key', CONTEXT_KEYS)
@pytest.mark.parametrize('mutation', ['missing', 'drift'])
def test_v2_rejects_every_missing_or_drifted_context_field(synthetic_chain, key, mutation):
    context = _context(synthetic_chain[2])
    if mutation == 'missing':
        del context[key]
    else:
        context[key] = '0' * 64 if key.endswith('sha256') else 'synthetic-drift'
    with pytest.raises(ValueError, match='artifact model context'):
        _attach(synthetic_chain, context=context)


@pytest.mark.parametrize('malformed', [None, [], 'synthetic', {}, {'unknown': 'value'}])
def test_v2_rejects_missing_or_malformed_original_context_even_with_outer_stamp(
    synthetic_chain, malformed,
):
    with pytest.raises(ValueError, match='artifact model context'):
        _attach(synthetic_chain, context=malformed, outer_context=_context(synthetic_chain[2]))


def test_v2_rejects_extra_key_and_nonstring_binding(synthetic_chain):
    context = _context(synthetic_chain[2])
    with pytest.raises(ValueError, match='artifact model context'):
        _attach(synthetic_chain, context={**context, 'approval': 'not-authorized'})
    with pytest.raises(ValueError, match='artifact model context'):
        _attach(synthetic_chain, context={**context, 'model_version': 1})


@pytest.mark.parametrize('mutation', [
    'scenario', 'assumptions', 'facts', 'case', 'model', 'model_version',
    'rule_version', 'parser_version', 'scan_watermark', 'research_as_of',
])
def test_same_scan_cannot_reuse_review_after_actual_input_or_dependency_change(
    synthetic_chain, mutation,
):
    descriptor = synthetic_chain[2]
    changed = _changed_descriptor(descriptor, mutation)
    assert changed.input_sha256 != descriptor.input_sha256
    assert changed.model_validity_input == descriptor.model_validity_input
    with pytest.raises(ValueError, match='artifact model context'):
        _attach(synthetic_chain, descriptor=changed, context=_context(descriptor))


@pytest.mark.parametrize('field', [
    'facts', 'research_case', 'assumptions', 'requested_model', 'model_version',
    'rule_version', 'parser_version', 'scan_watermark', 'computed_at',
    'facts_payload', 'research_case_payload', 'assumptions_payload',
])
def test_v2_rebuilds_actual_spec_instead_of_trusting_its_old_hash(synthetic_chain, field):
    descriptor = synthetic_chain[2]
    spec = build_research_run_spec(descriptor)
    if field == 'facts':
        changed = replace(spec.facts, operating_inputs={
            **spec.facts.operating_inputs, 'ordinary_shares': Decimal('101'),
        })
    elif field == 'research_case':
        changed = replace(spec.research_case, thesis=SYNTHETIC + '_CHANGED')
    elif field == 'assumptions':
        changed = _changed_descriptor(descriptor, 'assumptions').assumptions
    elif field == 'requested_model':
        changed = 'residual_income_or_equity_value'
    elif field == 'computed_at':
        changed = datetime(2026, 9, 21, 10, tzinfo=timezone.utc)
    elif field.endswith('_payload'):
        changed = {'scope': SYNTHETIC, 'drift': True}
    else:
        changed = 'synthetic-changed-dependency'
    spec = replace(spec, **{field: changed})
    assert spec.input_descriptor_sha256 == descriptor.input_sha256
    with pytest.raises(ValueError, match='model context spec'):
        _attach(synthetic_chain, spec=spec, context=_context(descriptor))


def test_v2_recomputes_stale_nested_descriptor_hash(synthetic_chain):
    descriptor = deepcopy(synthetic_chain[2])
    context = _context(descriptor)
    descriptor.facts.operating_inputs['ordinary_shares'] = Decimal('101')
    with pytest.raises(ValueError, match='descriptor hash mismatch'):
        _attach(synthetic_chain, descriptor=descriptor, context=context)


def test_v2_requires_event_original_and_cannot_bypass_with_only_human_binding(synthetic_chain):
    root, _, descriptor, _, _, approval, _, scan_hash = synthetic_chain
    source, digest = _store(root, 'synthetic-human-only.json', approval.as_policy())
    path, packet_hash = _store(root, 'synthetic-human-only-packet.json', {
        'schema_version': V2, 'symbol': descriptor.symbol, 'action': 'no_order',
        'bindings': {'human_approval': {'path': source.name, 'sha256': digest}},
    })
    with pytest.raises(ValueError, match='model-bound event materiality'):
        attach_research_reviews(
            root=root, spec=build_research_run_spec(descriptor), descriptor=descriptor,
            path=path, expected_sha256=packet_hash, event_sha256=scan_hash,
        )


def test_v1_legacy_default_and_fingerprint_remain_unchanged_but_strict_rejects(synthetic_chain):
    root, _, descriptor, _, _, _, review, scan_hash = synthetic_chain
    path, digest, _, _ = _packet(root, descriptor.symbol, review, None, schema=V1)
    attached = attach_research_reviews(
        root=root, spec=build_research_run_spec(descriptor), descriptor=descriptor,
        path=path, expected_sha256=digest, event_sha256=scan_hash,
    )
    assert attached.input_descriptor_sha256 == hashlib.sha256(json.dumps({
        'descriptor': descriptor.input_sha256, 'review_packet': digest,
    }, sort_keys=True).encode('utf-8')).hexdigest()
    assert attached.event_materiality_review == review
    with pytest.raises(ValueError, match='requires a v2'):
        _attach(synthetic_chain, context=None, schema=V1)
    with pytest.raises(ValueError, match='artifact model context'):
        _attach(synthetic_chain, context=None, strict=False)


@pytest.mark.parametrize('target', ['raw', 'packet', 'scan'])
def test_v2_keeps_original_hash_and_acquired_scan_checks(synthetic_chain, target):
    root, _, descriptor, _, _, _, review, scan_hash = synthetic_chain
    path, digest, raw, _ = _packet(root, descriptor.symbol, review, _context(descriptor))
    if target == 'raw':
        raw.write_bytes(raw.read_bytes() + b' ')
    elif target == 'packet':
        path.write_bytes(path.read_bytes() + b' ')
    else:
        scan_hash = '0' * 64
    with pytest.raises(ValueError, match='hash mismatch|exact acquired event scan'):
        attach_research_reviews(
            root=root, spec=build_research_run_spec(descriptor), descriptor=descriptor,
            path=path, expected_sha256=digest, event_sha256=scan_hash,
            require_model_binding=True,
        )


def test_v2_attachment_preserves_financial_and_scan_blockers(synthetic_chain):
    descriptor = synthetic_chain[2]
    payload = deepcopy(descriptor.as_policy())
    payload.pop('input_sha256')
    payload['research_case']['research_status'] = 'synthetic-financial-gap'
    payload['model_validity_input']['blockers'] = ['synthetic-validity-gap']
    payload['model_validity_input']['event_scan']['blockers'] = ['synthetic-scan-gap']
    changed = descriptor_from_payload(payload)
    attached = _attach(synthetic_chain, descriptor=changed, context=_context(changed))
    assert attached.research_case.research_status == 'synthetic-financial-gap'
    assert attached.model_validity_input.blockers == ('synthetic-validity-gap', 'synthetic-scan-gap')
    assert attached.human_research_approval is None
    assert attached.valuation_approval is None
    outcome = synthetic_chain[3].run_company_research(attached)
    assert outcome.gate.results['G1_财务门'] is False
    assert outcome.gate.results['G3_估值门'] is False
    assert outcome.decision_recommendation.recommendation_action == 'NO_ACTION'
    assert outcome.decision_recommendation.action == 'no_order'
    assert outcome.decision_recommendation.position_guidance is None


@pytest.fixture
def source_v2_review(source_package):
    root, package = source_package
    day = date.fromisoformat(package['point_in_time']['research_as_of'])
    observed = datetime.combine(day, datetime.min.time(), timezone.utc).replace(hour=8)
    reviewed = observed.replace(hour=9)
    row = package['sources'][0]
    ref = {'id': row['id'], 'path': row['local_path'], 'sha256': row['sha256']}
    decision = replace(
        _decision(DECISION_NOT_MATERIAL), symbol=package['symbol'], title=SYNTHETIC,
        published_at=observed, reviewed_at=reviewed, source_ref=ref,
        source_sha256=row['sha256'], review_notes=(SYNTHETIC,),
    )
    scan = EventScanResult(
        schema_version='m1-event-scan-v1', symbol=package['symbol'], provider=SYNTHETIC,
        scan_from=day, scan_to=day, validity_from=day, validity_to=day,
        status='PENDING_HUMAN_REVIEW', coverage_status='COMPLETE',
        pre_model_review_status='NONE', retrieved_at=observed, parser_version='synthetic-v1',
        blockers=(), evidence_refs=(ref,), announcements=(AnnouncementReview(
            announcement_id=decision.announcement_id, published_at=observed, title=SYNTHETIC,
            source_url=row['location'], rule_kind='unknown', review_status='PENDING_HUMAN_REVIEW',
            materiality_candidate=True, pre_model=False, evidence_refs=(ref,),
        ),),
    )
    scan_path, scan_hash = _store(root, 'synthetic-v2-scan.json', scan.as_policy())
    package['sources'].append({
        'id': 'synthetic-v2-scan', 'kind': 'research_artifact',
        'location': 'https://example.test/synthetic-v2-scan', 'local_path': scan_path.name,
        'sha256': scan_hash, 'published_at': observed.isoformat(),
        'source_available_at': observed.isoformat(), 'availability_basis': SYNTHETIC,
    })
    package['model_validity_input'] = {
        'model_id': package['dependencies']['model_version'], 'valid_from': day.isoformat(),
        'event_scan_ref': {'id': 'synthetic-v2-scan', 'symbol': package['symbol'],
                           'path': scan_path.name, 'sha256': scan_hash},
    }
    review = replace(
        _review((decision,)), symbol=package['symbol'], scan_id='synthetic-v2-scan',
        scan_sha256=scan_hash, scan_from=day, scan_to=day, reviewed_at=reviewed,
        review_as_of=day, decisions=(decision,), evidence_refs=(ref,),
    )
    descriptor = build_descriptor(package, root=root)
    _store(root, 'config/research-evidence-stop-ledger-v1.json', {
        'schema_version': 'research-evidence-stop-ledger-v1', 'stops': [],
    })
    return root, package, descriptor, review


@pytest.mark.parametrize('mutation', [
    'match', 'v1', 'missing', 'outer-only', 'unknown', 'scenario', 'assumptions',
    'facts', 'case', 'model_version',
])
def test_actual_source_bound_product_entry_enforces_original_context(source_v2_review, mutation):
    root, package, descriptor, review = source_v2_review
    context = _context(descriptor)
    if mutation in ('missing', 'outer-only', 'v1'):
        context = None
    elif mutation == 'unknown':
        context['approval'] = 'not-authorized'
    elif mutation == 'scenario':
        package['facts']['scenario_inputs']['bull']['terminal_roe'] = '0.13'
        for item in package['assumptions']['assumptions']:
            if item['name'] == 'terminal_roe':
                item['bull'] = '0.13'
        for item in package['assumption_bindings']:
            if item['scenario'] == 'bull' and item['field_path'] == 'terminal_roe':
                item['expected_value'] = '0.13'
    elif mutation == 'assumptions':
        package['assumptions']['assumptions'][0]['rationale'] = SYNTHETIC + '_CHANGED'
    elif mutation == 'facts':
        package['facts']['operating_inputs']['ordinary_shares'] = '101'
    elif mutation == 'case':
        package['research_case']['thesis'] = SYNTHETIC + '_CHANGED'
    elif mutation == 'model_version':
        package['dependencies']['model_version'] = 'synthetic-changed-model'
    # Prove the drifted package is valid and still consumes exactly the same scan.
    current = build_descriptor(package, root=root)
    assert current.model_validity_input == descriptor.model_validity_input
    path, digest, raw_path, raw_hash = _packet(
        root, package['symbol'], review, context, schema=V1 if mutation == 'v1' else V2,
        outer_context=_context(descriptor) if mutation == 'outer-only' else None,
    )
    package_path, package_hash = _store(root, 'synthetic-source-bound-package.json', package)
    output = root / 'synthetic-source-bound-output.json'
    args = dict(
        root=root, symbol=package['symbol'], package_path=package_path,
        output_path=output, reviews_path=path, reviews_sha256=digest,
        schedule_request={
            'schema_version': 'research-schedule-request-v1', 'symbol': package['symbol'],
            'source_id': SYNTHETIC, 'period': package['point_in_time']['research_as_of'],
            'research_question_id': 'synthetic-model-binding', 'blocker_id': 'initial_research',
            'reopen_condition_met': False, 'new_evidence_ids': [],
        },
    )
    if mutation != 'match':
        with pytest.raises(ResearchInputValidationError, match='model context|requires a v2'):
            run_company_research_for_symbol(**args)
        assert not output.exists()
        return
    result = run_company_research_for_symbol(**args)
    payload = result['result']
    assert payload['event_materiality_review']['scan_sha256'] == review.scan_sha256
    assert result['receipt']['input_sha256']['valuation_package'] == package_hash
    assert result['receipt']['input_sha256']['research_reviews'] == digest
    assert json.loads(path.read_text(encoding='utf-8'))['bindings']['event_materiality']['sha256'] == raw_hash
    assert json.loads(raw_path.read_text(encoding='utf-8'))['model_context'] == context
    assert hashlib.sha256(raw_path.read_bytes()).hexdigest() == raw_hash
    assert payload['source_verification']['status'] == 'LOCAL_BYTES_VERIFIED'
    assert payload['gate']['results']['G3_估值门'] is False
    assert payload['human_research_approval'] is None
    assert payload['decision_recommendation']['recommendation_type'] == 'NO_ACTION'
    assert payload['decision_recommendation']['position_guidance'] is None
    assert payload['decision_recommendation']['portfolio_input_status'] == 'BLOCKED_PRIVATE_INPUT'
    assert payload['action'] == 'no_order'
    assert hashlib.sha256(output.read_bytes()).hexdigest() == result['receipt']['output_sha256']
