"""New consumed research is reviewable without inheriting an old price policy."""
from datetime import datetime, timezone
import json

import pytest

from test_pending_candidate_supplement import registered, bind
from value_investment_agent.application.product import research_review_wizard as wizard
from value_investment_agent.application.product import (
    pending_candidate_supplement, pending_replay_publication, publication_chain,
    user_research_workflow,
)
from value_investment_agent.application.decision import value_price_policy


def forbidden(*args, **kwargs):
    raise AssertionError('New-input materials cannot borrow old publication, policy or replay')


@pytest.fixture
def isolated(registered, monkeypatch):
    for module, method in (
        (publication_chain, 'load_current_chain'),
        (pending_replay_publication, 'load_current_pending_replay'),
        (user_research_workflow, 'selected_review_candidate'),
        (value_price_policy, 'load_value_policy_review'),
        (value_price_policy, 'review_manifest_binding'),
    ):
        monkeypatch.setattr(module, method, forbidden)
    return registered


def handoff(registered, now=None):
    root, symbol, _, _ = registered
    return wizard.build_external_review_handoff(root=root, symbol=symbol,
        now=now or datetime.now(timezone.utc))


def test_new_research_materials_use_actual_consumed_packet_and_unsigned_contract(isolated):
    root, symbol, candidate, registry = isolated
    before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
    actual = handoff(isolated)
    assert actual['status'] == 'EXTERNAL_SIGNATURE_REQUIRED'
    assert actual['candidate_binding'] == bind(root, candidate)
    assert actual['candidate_preparation_mode'] == 'REGISTERED_NEW_INPUT_CANDIDATE'
    assert actual['current_public_price_policy_changed'] is False
    assert actual['public_research_materials'] == json.loads((candidate.parent / 'consumed-review.json').read_bytes())
    assert actual['public_research_materials']['gate']['results']['G3_估值门'] is False
    assert actual['unsigned_response']['reviewer_id'] is actual['unsigned_response']['whole_model_approval'] is None
    assert all(row['response'] is None for row in actual['unsigned_response']['groups'])
    assert actual['verification']['approval_changed'] is actual['verification']['research_admitted'] is False
    assert actual['position_guidance'] is None
    assert 'replay_publication_binding' not in actual
    assert bind(root, registry) in actual['source_bindings']
    assert candidate.relative_to(root).as_posix() in actual['commands']['consume_signed_response']
    assert {p: p.read_bytes() for p in root.rglob('*') if p.is_file()} == before


@pytest.mark.parametrize('part', ['candidate', 'packet', 'registry'])
def test_invalid_supplement_is_not_ready_without_legacy_fallback(isolated, part):
    _, _, candidate, registry = isolated
    path = candidate if part == 'candidate' else registry if part == 'registry' else candidate.parent / 'consumed-review.json'
    path.write_bytes(path.read_bytes() + b'changed')
    result = handoff(isolated)
    assert result['status'] == 'NOT_READY'
    assert 'commands' not in result
    assert result['verification']['approval_changed'] is False


def test_supplement_not_available_at_earlier_requested_cutoff(isolated):
    result = handoff(isolated, datetime(2020, 1, 1, tzinfo=timezone.utc))
    assert result['status'] == 'NOT_READY'
    assert 'unsigned_response' not in result


def test_change_during_preparation_cannot_deliver_stale_signing_instructions(isolated, monkeypatch):
    _, _, _, registry = isolated
    original = wizard.preview_pending_review_response

    def changing(**kwargs):
        result = original(**kwargs)
        registry.write_bytes(registry.read_bytes() + b'\n')
        return result

    monkeypatch.setattr(wizard, 'preview_pending_review_response', changing)
    with pytest.raises(ValueError, match='changed during handoff'):
        handoff(isolated)


@pytest.mark.parametrize('invalid_event', [False, True])
def test_independent_event_status_does_not_borrow_or_depend_on_g3_materials(tmp_path, monkeypatch, invalid_event):
    from value_investment_agent.application.product import event_supplement_handoff

    def event(**kwargs):
        if invalid_event:
            raise ValueError('TEST_ONLY wrong event source')
        return dict(status='EXTERNAL_SIGNATURE_REQUIRED', action='no_order',
            model_context={'input_descriptor_sha256': 'TEST_ONLY-separate-event-context'},
            approval_granted=False, g3_approval_granted=False)

    def g3(**kwargs):
        raise ValueError('TEST_ONLY old G3 material no longer available')

    monkeypatch.setattr(event_supplement_handoff, 'load_current_event_supplement_handoff', event)
    monkeypatch.setattr(wizard, '_build_external_review_handoff', g3)
    result = wizard.build_external_review_handoff(root=tmp_path, symbol='600519', now=datetime.now(timezone.utc))
    assert result['status'] == 'NOT_READY'
    assert 'unsigned_response' not in result
    assert 'commands' not in result
    assert 'model_context' not in result
    separate = result['supplemental_materiality_handoff']
    assert separate['status'] == ('MATERIALITY_HANDOFF_BLOCKED' if invalid_event else 'EXTERNAL_SIGNATURE_REQUIRED')
    assert separate['approval_granted'] is separate['g3_approval_granted'] is False


@pytest.mark.parametrize('change', ['revoked', 'new-context', 'removed'])
def test_independent_event_rechecked_after_current_g3_materials(tmp_path, monkeypatch, change):
    from value_investment_agent.application.product import event_supplement_handoff
    changed = False

    def event(**kwargs):
        if changed:
            if change == 'removed':
                return None
            if change == 'revoked':
                raise ValueError('TEST_ONLY revoked authorization')
        return dict(status='AUTHENTICATED_RESPONSE_IMPORTED', action='no_order',
            model_context={'input_descriptor_sha256': 'new' if changed else 'old'},
            approval_granted=False, g3_approval_granted=False)

    def g3(**kwargs):
        nonlocal changed
        changed = True
        return dict(status='NOT_READY', action='no_order', blockers=['TEST_ONLY'],
            verification=dict(approval_changed=False, research_admitted=False))

    monkeypatch.setattr(event_supplement_handoff, 'load_current_event_supplement_handoff', event)
    monkeypatch.setattr(wizard, '_build_external_review_handoff', g3)
    result = wizard.build_external_review_handoff(root=tmp_path, symbol='600519', now=datetime.now(timezone.utc))
    separate = result['supplemental_materiality_handoff']
    assert separate['status'] == 'MATERIALITY_HANDOFF_BLOCKED'
    assert not {'commands', 'unsigned_response', 'model_context'} & separate.keys()
