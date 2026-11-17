"""Wizard views retain the real materiality transport's exact signing packet."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from materiality_transport_helpers import authenticated_materiality_packet
from test_pending_research_candidate import prior_session_inputs
from value_investment_agent.application.product import (
    bound_draft_review, pending_candidate_supplement, pending_replay_publication,
    research_review_wizard as wizard, user_research_workflow,
)
from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.application.decision.value_price_policy import REVIEW_MANIFEST_PATH


def read(path):
    return json.loads(path.read_bytes())


def save(root, path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    return bind(root, path)


def bind(root, path):
    return dict(path=path.relative_to(root).as_posix(), sha256=sha256_file(path))


def snapshot(root):
    return {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}


@pytest.fixture
def materiality_candidate(tmp_path, monkeypatch, synthetic_pending_candidate_clock):
    producer = tmp_path / pending_candidate_supplement.GENERATOR
    producer.parent.mkdir(parents=True)
    producer.write_bytes((Path(__file__).resolve().parents[1] / pending_candidate_supplement.GENERATOR).read_bytes())
    package, policy, request, options = prior_session_inputs(tmp_path, monkeypatch)
    original = tmp_path / 'runtime/TEST_ONLY-original-scope.json'
    scope = save(tmp_path, original, request)
    from value_investment_agent.application.product.pending_research_candidate import prepare_pending_research_candidate
    candidate = prepare_pending_research_candidate(root=tmp_path,
        package_path=package, package_sha256=sha256_file(package),
        policy_path=policy, policy_sha256=sha256_file(policy), choice_id='continuity',
        output_dir=tmp_path / 'runtime/pending', schedule_request=request,
        schedule_request_sha256=scope['sha256'], **options)
    path = tmp_path / 'runtime/pending/candidate.json'
    (path.parent / 'schedule-request.json').write_bytes(original.read_bytes())
    save(tmp_path, tmp_path / 'config/user-research-workflow-v1.json',
        dict(schema_version='user-research-workflow-v1', action='no_order',
             supplemental_review_candidates={candidate['symbol']: bind(tmp_path, path)}))
    return tmp_path, path, candidate


def view(materiality_candidate, **overrides):
    root, path, candidate = materiality_candidate
    args = dict(root=root, candidate_binding=bind(root, path), candidate=candidate,
        package_binding=bind(root, path.parent / 'package.json'), now=datetime.now(timezone.utc))
    args.update(overrides)
    return wizard._materiality_handoff_view(**args)


@pytest.mark.parametrize('branch', ['supplement', 'replay', 'bound_draft'])
def test_wizard_branches_expose_exact_raw_transport_without_writing(
    materiality_candidate, monkeypatch, branch,
):
    root, path, candidate = materiality_candidate
    candidate_ref = bind(root, path)
    package_ref = bind(root, path.parent / 'package.json')
    if branch == 'replay':
        monkeypatch.setattr(pending_candidate_supplement, 'load_current_pending_candidate_supplement', lambda **k: None)
        manifest = save(root, root / REVIEW_MANIFEST_PATH, dict(items={}))
        replay = dict(candidate=candidate, registry_binding=manifest, publication_binding=manifest,
            publication=dict(generated_at=candidate['generated_at'],
                candidate_binding=candidate_ref, predecessor_binding=candidate_ref,
                package_binding=package_ref, workbench_binding=bind(root, path.parent / 'workbench.json'),
                review_packet_binding=bind(root, path.parent / 'consumed-review.json')))
        monkeypatch.setattr(pending_replay_publication, 'load_current_pending_replay', lambda **k: replay)
    elif branch == 'bound_draft':
        draft = save(root, root / 'artifacts/current/TEST_ONLY-draft.json', dict(summary='TEST_ONLY'))
        inputs = dict(draft=draft, package=package_ref, input_sha256=candidate['model_context']['input_descriptor_sha256'])
        monkeypatch.setattr(bound_draft_review, 'current_bound_draft_inputs', lambda **k: inputs)
        monkeypatch.setattr(user_research_workflow, 'selected_review_candidate', lambda **k: candidate_ref)
        # Exercise the legacy sibling packet path; selection validation has its own suite.
        selected = {k: v for k, v in candidate.items() if k != 'coverage_binding'}
        monkeypatch.setattr(bound_draft_review, 'verify_bound_draft_review_candidate', lambda **k: selected)
    before = snapshot(root)
    result = wizard.build_external_review_handoff(root=root, symbol=candidate['symbol'],
        now=datetime.now(timezone.utc), bound_draft=branch == 'bound_draft')
    event = result['materiality_handoff']
    ref = candidate['coverage_binding']['handoff_binding']
    raw = read(root / ref['path'])
    assert event['status'] == 'EXTERNAL_SIGNATURE_REQUIRED'
    assert event['handoff_binding'] == ref
    assert event['unsigned_response'] == raw['unsigned_response']
    assert event['signature_contract'] == raw['signature_contract']
    assert event['model_context'] == candidate['model_context'] == result['model_context']
    assert ref in result['source_bindings']
    assert all(event[k] is False for k in ('approval_granted', 'g3_approval_granted', 'research_admitted', 'price_admitted'))
    command = event['commands']['consume_signed_response']
    assert ref['path'] in command and ref['sha256'] in command
    assert 'scripts/current/review_materiality.py consume ' in command
    assert '--response-sha256 ' in command and '--trust-root-sha256 ' in command
    assert '--research-reviews ' in event['commands']['recompute']
    assert event['schedule_binding'] == bind(root, path.parent / 'schedule-request.json')
    assert event['schedule_binding'] in result['source_bindings']
    assert '--schedule-request ' in event['commands']['recompute']
    assert '--event ' not in event['commands']['recompute']
    assert snapshot(root) == before


def test_replay_copy_uses_original_packet_locator_and_frozen_signature_contract(materiality_candidate):
    root, path, candidate = materiality_candidate
    copied = root / 'runtime/replayed/package.json'
    copied.parent.mkdir()
    copied.write_bytes((path.parent / 'package.json').read_bytes())
    before = snapshot(root)
    result = view(materiality_candidate, package_binding=bind(root, copied))
    assert result['status'] == 'EXTERNAL_SIGNATURE_REQUIRED'
    assert result['handoff_binding'] == candidate['coverage_binding']['handoff_binding']
    assert result['package_binding']['path'] == (path.parent / 'package.json').relative_to(root).as_posix()
    assert copied.relative_to(root).as_posix() in result['commands']['recompute']
    assert snapshot(root) == before


def test_legacy_registered_view_does_not_require_new_adapter_fields(materiality_candidate, monkeypatch):
    from value_investment_agent.application.product import publication_chain, research_materiality_reviews
    root, path, candidate = materiality_candidate
    ref = bind(root, path)
    save(root, root / REVIEW_MANIFEST_PATH, dict(items={}))
    monkeypatch.setattr(pending_candidate_supplement, 'load_current_pending_candidate_supplement', lambda **k: None)
    monkeypatch.setattr(pending_replay_publication, 'load_current_pending_replay', lambda **k: None)
    monkeypatch.setattr(publication_chain, 'load_current_chain', lambda root: dict(sources=dict(source_bindings=[ref])))
    monkeypatch.setattr(user_research_workflow, 'selected_review_candidate', lambda **k: ref)
    legacy = dict(status='EXTERNAL_SIGNATURE_REQUIRED', action='no_order',
        handoff_binding=candidate['coverage_binding']['handoff_binding'],
        commands=dict(recompute='python scripts/current/review_materiality.py recheck --symbol 600887'))
    monkeypatch.setattr(research_materiality_reviews, 'registered_materiality_handoff', lambda **k: legacy)
    before = snapshot(root)
    result = wizard.build_external_review_handoff(root=root, symbol=candidate['symbol'], now=datetime.now(timezone.utc))
    assert result['materiality_handoff'] == legacy
    assert result['source_bindings'] == [ref]
    assert snapshot(root) == before


def test_recompute_includes_only_hash_bound_schedule_request(materiality_candidate):
    from value_investment_agent.application.product.company_research import load_schedule_request
    root, path, original = materiality_candidate
    candidate = deepcopy(original)
    schedule = path.parent / 'schedule-request.json'
    scope = read(schedule)
    ref = bind(root, schedule)
    # A retained byte hash in the bound workbench supports the unlisted sidecar.
    assert ref not in candidate['source_bindings']
    assert view(materiality_candidate)['schedule_binding'] == ref
    candidate['source_bindings'].append(ref)
    before = snapshot(root)
    result = view(materiality_candidate, candidate=candidate)
    assert f"--schedule-request '{ref['path']}' " in result['commands']['recompute']
    assert load_schedule_request(root, schedule) == (scope, ref['sha256'])
    assert snapshot(root) == before
    schedule.write_bytes(schedule.read_bytes() + b' ')
    result = view(materiality_candidate, candidate=candidate)
    assert result['recompute_status'] == 'BLOCKED'
    assert 'recompute' not in result['commands']


@pytest.mark.parametrize('mutation', [
    'missing_request', 'tampered_request', 'missing_workbench_binding', 'tampered_workbench',
    'wrong_workbench_hash', 'missing_receipt_hash', 'wrong_receipt_hash', 'schema', 'symbol', 'scope',
])
def test_schedule_recovery_fails_closed_without_invalidating_signing_packet(materiality_candidate, mutation):
    root, path, original = materiality_candidate
    candidate = deepcopy(original)
    schedule = path.parent / 'schedule-request.json'
    workbench_path = path.parent / 'workbench.json'
    workbench_ref = next(r for r in candidate['source_bindings'] if r['path'] == bind(root, workbench_path)['path'])
    workbench = read(workbench_path)
    if mutation == 'missing_request':
        schedule.unlink()
    elif mutation == 'tampered_request':
        schedule.write_bytes(schedule.read_bytes() + b' ')
    elif mutation == 'missing_workbench_binding':
        candidate['source_bindings'].remove(workbench_ref)
    elif mutation == 'tampered_workbench':
        workbench_path.write_bytes(workbench_path.read_bytes() + b' ')
    elif mutation == 'wrong_workbench_hash':
        workbench_ref['sha256'] = '0' * 64
    else:
        if mutation == 'missing_receipt_hash':
            del workbench['research_receipt']['input_sha256']['schedule_request']
        elif mutation == 'wrong_receipt_hash':
            workbench['research_receipt']['input_sha256']['schedule_request'] = '0' * 64
        else:
            request = read(schedule)
            if mutation == 'schema':
                request['schema_version'] = 'TEST_ONLY-wrong-schema'
            elif mutation == 'symbol':
                request['symbol'] = '000001'
            else:
                candidate['schedule_gate']['scope_key'] = dict(source_id='OTHER', period='other',
                    research_question_id='other', blocker_id='other')
                workbench['schedule_gate'] = deepcopy(candidate['schedule_gate'])
            workbench['research_receipt']['input_sha256']['schedule_request'] = save(root, schedule, request)['sha256']
        workbench_ref.update(save(root, workbench_path, workbench))
    before = snapshot(root)
    result = view(materiality_candidate, candidate=candidate)
    assert result['status'] == 'EXTERNAL_SIGNATURE_REQUIRED'
    assert result['handoff_binding'] == candidate['coverage_binding']['handoff_binding']
    assert result['recompute_status'] == 'BLOCKED'
    assert result['recompute_reason']
    assert 'schedule_binding' not in result
    assert set(result['commands']) == {'consume_signed_response'}
    assert snapshot(root) == before


def test_missing_retained_packet_is_blocked_and_only_offers_explicit_prepare(materiality_candidate):
    root, path, candidate = materiality_candidate
    (root / candidate['coverage_binding']['handoff_binding']['path']).unlink()
    unbound = {k: v for k, v in candidate.items() if k != 'coverage_binding'}
    before = snapshot(root)
    result = view(materiality_candidate, candidate=unbound)
    assert result['status'] == 'MATERIALITY_HANDOFF_BLOCKED'
    assert set(result['commands']) == {'prepare_handoff'}
    assert not {'handoff_binding', 'unsigned_response', 'model_context'} & result.keys()
    assert '--package-sha256 ' in result['commands']['prepare_handoff']
    assert '--scan-sha256 ' in result['commands']['prepare_handoff']
    assert '--event ' not in result['commands']['prepare_handoff']
    assert snapshot(root) == before


@pytest.mark.parametrize('mutation', ['hash', 'signed_template', 'context', 'issuer', 'null', 'missing'])
def test_invalid_declared_raw_packet_is_never_replaced_by_a_signable_view(materiality_candidate, mutation):
    root, _, original = materiality_candidate
    candidate = deepcopy(original)
    ref = candidate['coverage_binding']['handoff_binding']
    path = root / ref['path']
    if mutation == 'hash':
        path.write_bytes(path.read_bytes() + b' ')
    elif mutation == 'null':
        candidate['coverage_binding']['handoff_binding'] = None
    elif mutation == 'missing':
        path.unlink()
    else:
        raw = read(path)
        if mutation == 'signed_template':
            raw['unsigned_response']['reviewer_id'] = 'TEST_ONLY invented reviewer'
        elif mutation == 'context':
            raw['model_context']['input_descriptor_sha256'] = '0' * 64
        else:
            raw['symbol'] = '000001'
        candidate['coverage_binding']['handoff_binding'] = save(root, path, raw)
    before = snapshot(root)
    with pytest.raises((ValueError, OSError)):
        view(materiality_candidate, candidate=candidate)
    assert snapshot(root) == before


def signed_import(materiality_candidate, authenticated_materiality_packet):
    from value_investment_agent.event_materiality import event_materiality_review_from_payload
    root, path, candidate = materiality_candidate
    handoff = read(root / candidate['coverage_binding']['handoff_binding']['path'])
    review = deepcopy(handoff['unsigned_response']['event_materiality'])
    now = datetime.now(timezone.utc)
    review.update(review_id='TEST_ONLY_wizard_materiality', reviewed_at=now.isoformat(),
        review_as_of=now.date().isoformat(), reviewer_id='TEST_ONLY_fixture_reviewer')
    for decision in review['decisions']:
        decision.update(event_decision_id='TEST_ONLY_' + decision['announcement_id'], reviewed_at=now.isoformat(),
            reviewer_id=review['reviewer_id'], human_decision='NOT_MATERIAL', requires_recalculation=False,
            requires_model_stale=False, requires_followup=False,
            review_notes=['TEST_ONLY synthetic sources; never actual issuer approval'])
    return authenticated_materiality_packet(path.parent / 'package.json', event_materiality_review_from_payload(review))[0]


@pytest.mark.parametrize('mutation', [None, 'revoked', 'partial', 'tamper'])
def test_existing_authenticated_consumer_controls_imported_view(
    materiality_candidate, authenticated_materiality_packet, mutation,
):
    from value_investment_agent.application.product.research_materiality_reviews import _context_key
    from value_investment_agent.infrastructure.evidence import trust_root_registry
    root, _, candidate = materiality_candidate
    packet = signed_import(materiality_candidate, authenticated_materiality_packet)
    if mutation == 'revoked':
        save(root, trust_root_registry._TEST_REGISTRY_PATH,
            dict(schema_version='authorization-trust-root-registry-v1', pinned_trust_root_sha256=[]))
    elif mutation == 'partial':
        (root / 'runtime/materiality-review-responses' / _context_key(candidate['model_context']) / 'completion.json').unlink()
    elif mutation == 'tamper':
        packet.write_bytes(packet.read_bytes() + b' ')
    before = snapshot(root)
    result = wizard.build_external_review_handoff(root=root, symbol=candidate['symbol'], now=datetime.now(timezone.utc))
    event = result['materiality_handoff']
    if mutation:
        assert event['status'] == 'MATERIALITY_HANDOFF_BLOCKED'
        assert not {'commands', 'unsigned_response', 'model_context'} & event.keys()
    else:
        assert event['status'] == 'AUTHENTICATED_RESPONSE_IMPORTED'
        assert event['review_packet_binding'] == bind(root, packet)
        assert packet.relative_to(root).as_posix() in event['commands']['recompute']
        assert event['g3_approval_granted'] is event['research_admitted'] is event['price_admitted'] is False
    assert snapshot(root) == before


def test_raw_packet_drift_during_view_construction_is_blocked(materiality_candidate, monkeypatch):
    root, _, candidate = materiality_candidate
    original = wizard._materiality_handoff_view
    calls = 0
    def changing(**kwargs):
        nonlocal calls
        result = original(**kwargs)
        calls += 1
        if calls == 1:
            path = root / candidate['coverage_binding']['handoff_binding']['path']
            path.write_bytes(path.read_bytes() + b' ')
        return result
    monkeypatch.setattr(wizard, '_materiality_handoff_view', changing)
    with pytest.raises(ValueError, match='pending candidate source drift'):
        wizard.build_external_review_handoff(root=root, symbol=candidate['symbol'], now=datetime.now(timezone.utc))
