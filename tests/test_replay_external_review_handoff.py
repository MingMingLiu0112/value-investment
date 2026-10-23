"""Replay handoff reuses real signature contracts without granting authority."""
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from test_pending_candidate_replay import stale, prepare, publish, write, binding
from value_investment_agent.application.product import (
    publication_chain, user_research_workflow, pending_replay_publication,
    research_review_wizard as wizard, research_materiality_reviews,
)
from value_investment_agent.application.decision import value_price_policy
from value_investment_agent.application.product.common import sha256_file


def _forbid(*args, **kwargs):
    raise AssertionError('Replay handoff must not access legacy publication or write/sign')


@pytest.fixture
def registered(stale, monkeypatch):
    root, _, old = stale
    result = prepare(stale)
    publication = publish(root, result)
    write(root / value_price_policy.REVIEW_MANIFEST_PATH, dict(items={}))
    monkeypatch.setattr(publication_chain, 'load_current_chain', _forbid)
    monkeypatch.setattr(user_research_workflow, 'selected_review_candidate', _forbid)
    monkeypatch.setattr(research_materiality_reviews, 'registered_materiality_handoff', _forbid)
    monkeypatch.setattr(research_materiality_reviews, '_append_review_json', _forbid)
    monkeypatch.setattr(wizard, 'write_new_json', _forbid)
    return root, old, result, publication


def handoff(registered, **kwargs):
    root, old, _, _ = registered
    return wizard.build_external_review_handoff(root=root, symbol=old['symbol'],
        now=kwargs.get('now', datetime.now(timezone.utc)))


def _not_ready(result):
    assert result['status'] == 'NOT_READY'
    assert result['verification']['approval_changed'] is False
    assert result['verification']['research_admitted'] is False
    assert not {'commands', 'steps', 'unsigned_response'} & result.keys()


def test_replay_handoff_uses_consumed_materials_and_existing_unsigned_signature_contract(registered):
    root, old, result, publication = registered
    before = {p: sha256_file(p) for p in root.rglob('*') if p.is_file()}
    actual = handoff(registered)
    assert actual['status'] == 'EXTERNAL_SIGNATURE_REQUIRED'
    assert actual['candidate_binding'] == result['candidate_binding']
    assert actual['replay_publication_binding'] == publication['publication_binding']
    assert actual['model_context'] == old['model_context']
    packet = root / result['candidate_binding']['path']
    packet = packet.parent / 'consumed-review.json'
    assert actual['public_research_materials'] == json.loads(packet.read_bytes())
    assert 'current_draft_interpretation' not in actual['public_research_materials']
    assert actual['public_research_materials']['gate']['results']['G3_估值门'] is False
    draft = actual['unsigned_response']
    assert draft['candidate_binding'] == result['candidate_binding']
    assert draft['reviewer_id'] is draft['reviewed_at'] is draft['whole_model_approval'] is None
    assert all(group['response'] is None for group in draft['groups'])
    assert actual['authorization'] == dict(pinned_root_count=0, status='AUTHORIZED_IDENTITY_REQUIRED')
    assert actual['verification']['policy_confirmation_is_not_g3'] is True
    assert actual['verification']['approval_changed'] is actual['verification']['research_admitted'] is False
    assert actual['position_guidance'] is None
    assert result['candidate_binding']['path'] in actual['commands']['draft_preview']
    assert result['candidate_binding']['sha256'] in actual['commands']['consume_signed_response']
    assert publication['publication_binding'] in actual['source_bindings']
    assert binding(root, packet) in actual['source_bindings']
    assert actual['materiality_handoff']['status'] == 'MATERIALITY_HANDOFF_BLOCKED'
    assert {p: sha256_file(p) for p in root.rglob('*') if p.is_file()} == before


@pytest.mark.parametrize('change', ['manifest', 'candidate', 'packet', 'implementation', 'foreign', 'invalid-registry', 'empty-binding'])
def test_invalid_registered_replay_never_falls_back_or_emits_signing_instructions(registered, change):
    root, old, result, publication = registered
    if change == 'manifest':
        target = root / publication['publication_binding']['path']
    elif change == 'candidate':
        target = root / result['candidate_binding']['path']
    elif change == 'packet':
        target = (root / result['candidate_binding']['path']).parent / 'consumed-review.json'
    elif change == 'implementation':
        target = root / 'src/value_investment_agent/application/product/pending_candidate_replay.py'
    else:
        target = root / pending_replay_publication.POINTER_PATH
        if change == 'empty-binding':
            write(target, dict(schema_version=pending_replay_publication.POINTER_SCHEMA,
                action='no_order', publications={old['symbol']: None}))
            _not_ready(handoff(registered))
            return
        if change == 'foreign':
            write(target, dict(schema_version=pending_replay_publication.POINTER_SCHEMA,
                action='no_order', publications={'600741': publication['publication_binding']}))
            _not_ready(wizard.build_external_review_handoff(root=root, symbol='600741',
                now=datetime.now(timezone.utc)))
            return
    target.write_bytes(target.read_bytes() + b'\nchanged\n')
    _not_ready(handoff(registered))


@pytest.mark.parametrize('timestamp', ['early', 'naive'])
def test_replay_handoff_respects_requested_aware_cutoff(registered, timestamp):
    at = datetime(2026, 10, 11, tzinfo=timezone.utc)
    if timestamp == 'naive':
        at = at.replace(tzinfo=None)
    _not_ready(handoff(registered, now=at))


@pytest.mark.parametrize('changed', ['registry', 'materials'])
def test_replay_change_while_preparing_materials_removes_commands(registered, monkeypatch, changed):
    root, _, result, _ = registered
    original = wizard.preview_pending_review_response

    def preview(**kwargs):
        value = original(**kwargs)
        if changed == 'registry':
            target = root / pending_replay_publication.POINTER_PATH
        else:
            target = (root / result['candidate_binding']['path']).parent / 'consumed-review.json'
        target.write_bytes(target.read_bytes() + b'\n')
        return value

    monkeypatch.setattr(wizard, 'preview_pending_review_response', preview)
    if changed == 'registry':
        _not_ready(handoff(registered))
    else:
        with pytest.raises(ValueError, match='materials changed'):
            handoff(registered)


@pytest.mark.parametrize('state', ['matching', 'mismatch', 'rejected-policy'])
def test_replay_keeps_applicable_current_policy_basis_checks(registered, monkeypatch, state):
    root, old, result, _ = registered
    preview = wizard.preview_pending_review_response(root=root,
        candidate_path=root / result['candidate_binding']['path'],
        candidate_sha256=result['candidate_binding']['sha256'])
    expected_hash = preview['draft']['valuation_artifact_sha256']
    write(root / value_price_policy.REVIEW_MANIFEST_PATH, dict(items={old['symbol']: {}}))
    calls = []

    def current_policy(root_arg, symbol_arg, now):
        calls.append((root_arg, symbol_arg))
        if state == 'rejected-policy':
            raise ValueError('Current research changed since review')
        return dict(draft=dict(basis=dict(valuation_input_version=(
            expected_hash if state == 'matching' else '0' * 64))),
            source_bindings=[binding(root, root / value_price_policy.REVIEW_MANIFEST_PATH)],
            model_review={'scope': 'CURRENT_POLICY_REVIEW_NOT_REPLAY_MATERIALS'})

    monkeypatch.setattr(value_price_policy, 'load_value_policy_review', current_policy)
    if state == 'matching':
        actual = handoff(registered)
        assert actual['status'] == 'EXTERNAL_SIGNATURE_REQUIRED'
        assert actual['public_research_materials']['consumed_operating_inputs']
    else:
        with pytest.raises(ValueError, match='current valuation|Current research changed'):
            handoff(registered)
    assert calls == [(root, old['symbol'])]


def test_replay_does_not_mint_reviewer_authority_when_roots_are_pinned(registered, monkeypatch):
    from value_investment_agent.infrastructure.evidence import trust_root_registry
    monkeypatch.setattr(trust_root_registry, 'pinned_trust_root_fingerprints', lambda: {'synthetic-fingerprint'})
    actual = handoff(registered)
    assert actual['authorization']['status'] == 'EXACT_REVIEWER_SCOPE_MUST_BE_VERIFIED'
    assert actual['authorization']['pinned_root_count'] == 1
    assert actual['unsigned_response']['reviewer_id'] is None
    assert actual['unsigned_response']['whole_model_approval'] is None


@pytest.mark.parametrize('registry', ['absent', 'other-symbol'])
def test_absent_symbol_keeps_exact_legacy_publication_selector(registered, monkeypatch, registry):
    root, old, _, publication = registered
    pointer = root / pending_replay_publication.POINTER_PATH
    if registry == 'absent':
        pointer.unlink()
    else:
        write(pointer, dict(schema_version=pending_replay_publication.POINTER_SCHEMA,
            action='no_order', publications={'600741': publication['publication_binding']}))
    marker = RuntimeError('legacy publication selected')

    def legacy(root_arg):
        assert root_arg == root
        raise marker

    monkeypatch.setattr(publication_chain, 'load_current_chain', legacy)
    with pytest.raises(RuntimeError) as caught:
        handoff(registered)
    assert caught.value is marker


def test_bound_draft_path_does_not_consult_replay_registry(monkeypatch, tmp_path):
    monkeypatch.setattr(pending_replay_publication, 'load_current_pending_replay', _forbid)
    actual = wizard.build_external_review_handoff(root=tmp_path, symbol='000333',
        now=datetime.now(timezone.utc), bound_draft=True)
    assert actual['status'] == 'NOT_READY'
    assert actual['blockers'] == ['CURRENT_SOURCE_BOUND_DRAFT_UNAVAILABLE']


@pytest.mark.parametrize('replacement', ['verified-supplement', 'invalid-supplement'])
def test_new_higher_priority_candidate_during_economic_read_never_returns_old_replay(
        registered, monkeypatch, replacement):
    from value_investment_agent.application.product import (
        economic_review_materials, pending_candidate_supplement,
    )
    changed = False
    original_loader = pending_candidate_supplement.load_current_pending_candidate_supplement
    original_materials = economic_review_materials.build_economic_review_materials

    def current(**kwargs):
        if changed:
            if replacement == 'invalid-supplement':
                raise ValueError('TEST_ONLY new higher-priority candidate source drift')
            # Selector output only; the original replay/calculations remain real.
            return {'candidate_binding': {'path': 'runtime/TEST_ONLY/new.json', 'sha256': 'a' * 64}}
        return original_loader(**kwargs)

    def material(**kwargs):
        nonlocal changed
        result = original_materials(**kwargs)
        changed = True
        return result

    monkeypatch.setattr(pending_candidate_supplement, 'load_current_pending_candidate_supplement', current)
    monkeypatch.setattr(economic_review_materials, 'build_economic_review_materials', material)
    with pytest.raises(ValueError, match='changed during economic handoff|higher-priority candidate'):
        handoff(registered)


@pytest.mark.skipif(not (Path(__file__).resolve().parents[1] /
    'runtime/pending-candidate-replay-v5-final-20261021/600519/publication.json').is_file(),
    reason='Retained local real-source replay is not a public CI fixture')
def test_real_source_600519_read_only_external_handoff_without_signing(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    replay = pending_replay_publication.load_current_pending_replay(root=root, symbol='600519')
    assert replay is not None
    paths = [root / item['path'] for item in [
        replay['registry_binding'], replay['publication_binding'],
        *replay['candidate']['source_bindings'], *replay['candidate']['implementation_bindings']]]
    before = {p: sha256_file(p) for p in paths}
    watched = ('runtime/research-review-handoffs', 'runtime/research-review-responses',
               'runtime/research-review-consumptions', 'runtime/materiality-review-responses')

    def records():
        return {p: sha256_file(p) for name in watched for p in (root / name).rglob('*') if p.is_file()}

    journals = records()
    monkeypatch.setattr(wizard, 'write_new_json', _forbid)
    monkeypatch.setattr(research_materiality_reviews, '_append_review_json', _forbid)
    monkeypatch.setattr(user_research_workflow, 'selected_review_candidate', _forbid)
    actual = wizard.build_external_review_handoff(root=root, symbol='600519', now=datetime.now(timezone.utc))
    assert actual['status'] == 'EXTERNAL_SIGNATURE_REQUIRED'
    assert actual['candidate_binding'] == replay['publication']['candidate_binding']
    assert actual['replay_publication_binding'] == replay['publication_binding']
    assert actual['public_research_materials']['input_descriptor_sha256'] == replay['candidate']['model_context']['input_descriptor_sha256']
    assert actual['public_research_materials']['gate']['results']['G3_估值门'] is False
    assert actual['unsigned_response']['reviewer_id'] is actual['unsigned_response']['whole_model_approval'] is None
    assert actual['verification']['approval_changed'] is actual['verification']['research_admitted'] is False
    assert actual['position_guidance'] is None
    assert 'consume_signed_response' in actual['commands']
    assert {p: sha256_file(p) for p in paths} == before
    assert records() == journals
