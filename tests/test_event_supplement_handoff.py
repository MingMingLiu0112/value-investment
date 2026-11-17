"""Separate event handoff uses actual isolated source replay, never old G3."""
from datetime import datetime, timedelta, timezone

import pytest

from test_event_scan_supplement import source_package, inputs, consumed, read, save
from materiality_transport_helpers import authenticated_materiality_packet
from value_investment_agent.application.product import event_supplement_handoff as loader
from value_investment_agent.application.product.event_scan_supplement import _binding


@pytest.fixture
def registered(consumed):
    root, _, result = consumed
    binding = _binding(root, root / 'runtime/consumed/consumption.json')
    workflow = dict(schema_version='user-research-workflow-v1', action='no_order',
        review_candidates={result['symbol']: dict(path='OLD_G3_NOT_TO_BE_READ', sha256='0'*64)},
        supplemental_event_consumptions={result['symbol']: binding})
    save(root, root / loader.WORKFLOW, workflow)
    return root, result, workflow


def load(root, symbol, now=None):
    return loader.load_current_event_supplement_handoff(root, symbol, now or datetime.now(timezone.utc))


def test_explicit_context_is_readonly_separate_and_has_usable_existing_commands(registered):
    root, consumed_result, _ = registered
    before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
    result = load(root, consumed_result['symbol'])
    assert result['status'] == 'EXTERNAL_SIGNATURE_REQUIRED'
    assert result['scope'] == 'SEPARATE_UNADMITTED_EVENT_CONTEXT_NOT_CURRENT_G3'
    assert result['model_context'] == consumed_result['model_context']
    assert len(result['announcements']) == len(result['unsigned_response']['event_materiality']['decisions']) == 1
    assert all(result[key] is False for key in ('approval_granted', 'g3_approval_granted', 'research_admitted', 'price_admitted'))
    assert result['unsigned_response']['reviewer_id'] is None
    assert 'candidate_binding' not in result and 'valuation_artifact_sha256' not in result
    command = result['commands']['consume_signed_response']
    assert 'scripts/current/review_materiality.py consume ' in command
    assert result['handoff_binding']['path'] in command and result['handoff_binding']['sha256'] in command
    recompute = result['commands']['recompute']
    assert 'scripts/current/run_company_research.py' in recompute
    assert '--schedule-request ' in recompute and '--research-reviews ' in recompute
    assert '--event ' not in recompute and 'recheck --symbol' not in recompute
    assert {p: p.read_bytes() for p in root.rglob('*') if p.is_file()} == before


@pytest.mark.parametrize('kind', ['no_file', 'no_field', 'other_symbol'])
def test_absent_optional_registration_returns_none_even_in_legacy_root(tmp_path, kind):
    if kind != 'no_file':
        payload = dict(schema_version='user-research-workflow-v1', action='no_order')
        if kind == 'other_symbol':
            payload['supplemental_event_consumptions'] = {'000001': {'INVALID_OTHER_SYMBOL': True}}
        save(tmp_path, tmp_path / loader.WORKFLOW, payload)
    assert load(tmp_path, '600519') is None
    assert loader.load_current_event_supplement_handoff(tmp_path, '600519', None) is None


@pytest.mark.parametrize('mutation', ['issuer', 'hash', 'context', 'handoff', 'null', 'traversal', 'schema', 'mapping'])
def test_invalid_explicit_registration_never_falls_back_to_old_g3(registered, mutation):
    root, result, workflow = registered
    symbol = result['symbol']
    binding = workflow['supplemental_event_consumptions'][symbol]
    if mutation == 'issuer':
        workflow['supplemental_event_consumptions']['000001'] = binding
        symbol = '000001'
    elif mutation == 'hash':
        binding['sha256'] = '0' * 64
    elif mutation == 'null':
        workflow['supplemental_event_consumptions'][symbol] = None
    elif mutation == 'traversal':
        binding['path'] = '../outside.json'
    elif mutation == 'schema':
        workflow['schema_version'] = 'foreign-workflow'
    elif mutation == 'mapping':
        workflow['supplemental_event_consumptions'] = []
    else:
        path = root / binding['path']
        payload = read(path)
        if mutation == 'context':
            payload['model_context']['input_descriptor_sha256'] = '0' * 64
        else:
            payload['handoff_binding'] = payload['review_packet_binding']
        workflow['supplemental_event_consumptions'][symbol] = save(root, path, payload)
    save(root, root / loader.WORKFLOW, workflow)
    with pytest.raises(ValueError):
        load(root, symbol)


@pytest.mark.parametrize('clock', ['naive', 'before_construction', 'before_consumption'])
def test_context_and_consumed_materials_must_be_available_at_read_clock(registered, clock):
    root, result, _ = registered
    work = read(root / result['workbench_binding']['path'])
    if clock == 'naive':
        now = datetime.now()
    elif clock == 'before_consumption':
        now = datetime.fromisoformat(work['generated_at']) - timedelta(microseconds=1)
    else:
        now = datetime(2026, 9, 21, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match='time|available|elapsed'):
        load(root, result['symbol'], now)


@pytest.mark.parametrize('mutation', ['registry', 'source', 'consumption'])
def test_drift_during_projection_is_rejected(registered, monkeypatch, mutation):
    root, result, workflow = registered
    original = loader.verify_consumed_event_scan_supplement
    calls = 0

    def verify(**kwargs):
        nonlocal calls
        verified = original(**kwargs)
        calls += 1
        if calls == 1:
            if mutation == 'registry':
                workflow['supplemental_event_consumptions'] = {}
                save(root, root / loader.WORKFLOW, workflow)
            elif mutation == 'source':
                # Alter a genuine retained original after the first full replay.
                handoff = read(root / result['handoff_binding']['path'])
                path = root / handoff['announcements'][0]['evidence_refs'][0]['path']
                path.write_bytes(b'TEST_ONLY source drift during read')
            else:
                path = root / workflow['supplemental_event_consumptions'][result['symbol']]['path']
                path.write_bytes(path.read_bytes() + b' ')
        return verified

    monkeypatch.setattr(loader, 'verify_consumed_event_scan_supplement', verify)
    with pytest.raises(ValueError):
        load(root, result['symbol'])


def import_signed(registered, authenticated_materiality_packet):
    """Reuse the existing isolated production signer/consumer fixture, never actual keys."""
    from copy import deepcopy
    from value_investment_agent.event_materiality import event_materiality_review_from_payload

    root, result, _ = registered
    handoff = read(root / result['handoff_binding']['path'])
    review = deepcopy(handoff['unsigned_response']['event_materiality'])
    now = datetime.now(timezone.utc)
    review.update(review_id='TEST_ONLY_supplemental_handoff', reviewed_at=now.isoformat(),
                  review_as_of=now.date().isoformat(), reviewer_id='TEST_ONLY_before_fixture_signer')
    for decision in review['decisions']:
        decision.update(event_decision_id='TEST_ONLY_' + decision['announcement_id'],
            reviewed_at=now.isoformat(), reviewer_id='TEST_ONLY_before_fixture_signer',
            human_decision='NOT_MATERIAL', requires_recalculation=False,
            requires_model_stale=False, requires_followup=False,
            review_notes=['TEST_ONLY synthetic source classification, no actual issuer approval'])
    packet, _, _, _, _ = authenticated_materiality_packet(
        root / handoff['package_binding']['path'], event_materiality_review_from_payload(review))
    return packet


def test_signed_import_changes_only_supplemental_status_and_binds_real_packet(registered, authenticated_materiality_packet):
    root, consumed_result, _ = registered
    before = load(root, consumed_result['symbol'])
    assert before['status'] == 'EXTERNAL_SIGNATURE_REQUIRED'
    packet = import_signed(registered, authenticated_materiality_packet)
    files = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
    result = load(root, consumed_result['symbol'])
    assert result['status'] == 'AUTHENTICATED_RESPONSE_IMPORTED'
    assert result['consumption_binding'] == before['consumption_binding']
    assert result['model_context'] == before['model_context']
    assert result['review_packet_binding'] == _binding(root, packet)
    assert result['materiality_consumption_binding'] != result['consumption_binding']
    assert result['recompute_required'] is result['publication_required'] is True
    assert result['scope'] == 'SEPARATE_UNADMITTED_EVENT_CONTEXT_NOT_CURRENT_G3'
    assert all(result[key] is False for key in ('approval_granted', 'g3_approval_granted', 'research_admitted', 'price_admitted'))
    assert result['review_packet_binding']['path'] in result['commands']['recompute']
    assert result['review_packet_binding']['sha256'] in result['commands']['recompute']
    assert '--event ' not in result['commands']['recompute']
    assert {p: p.read_bytes() for p in root.rglob('*') if p.is_file()} == files


@pytest.mark.parametrize('mutation', ['incomplete', 'revoked', 'wrong_context', 'packet', 'signature', 'source', 'future_clock'])
def test_invalid_or_revoked_signed_import_never_becomes_pending_or_g3(registered, authenticated_materiality_packet, mutation):
    from value_investment_agent.application.product.research_materiality_reviews import _context_key
    from value_investment_agent.infrastructure.evidence import trust_root_registry

    root, consumed_result, _ = registered
    packet_path = import_signed(registered, authenticated_materiality_packet)
    journal = root / 'runtime/materiality-review-responses' / _context_key(consumed_result['model_context'])
    completion = journal / 'completion.json'
    receipt_ref = read(completion)
    receipt = read(root / receipt_ref['path'])
    now = None
    if mutation == 'incomplete':
        completion.unlink()
    elif mutation == 'revoked':
        save(root, trust_root_registry._TEST_REGISTRY_PATH,
             dict(schema_version='authorization-trust-root-registry-v1', pinned_trust_root_sha256=[]))
    elif mutation == 'wrong_context':
        receipt['model_context']['facts_sha256'] = '0' * 64
        receipt_ref = save(root, root / receipt_ref['path'], receipt)
        save(root, completion, receipt_ref)
    elif mutation == 'packet':
        packet_path.write_bytes(packet_path.read_bytes() + b' ')
    elif mutation == 'signature':
        ref = receipt['authenticated_materiality_binding']['response']
        path = root / ref['path']
        envelope = read(path)
        envelope['signature'] = '0' * 128
        # Even rehashing every transport locator cannot repair a forged signature.
        ref.update(save(root, path, envelope))
        packet = read(packet_path)
        packet['authenticated_materiality_binding'] = receipt['authenticated_materiality_binding']
        receipt['review_packet_binding'] = save(root, packet_path, packet)
        receipt_ref = save(root, root / receipt_ref['path'], receipt)
        save(root, completion, receipt_ref)
    elif mutation == 'source':
        handoff = read(root / consumed_result['handoff_binding']['path'])
        (root / handoff['announcements'][0]['evidence_refs'][0]['path']).write_bytes(b'TEST_ONLY changed original')
    else:
        packet = read(packet_path)
        review = read(root / packet['bindings']['event_materiality']['path'])
        now = datetime.fromisoformat(review['reviewed_at']) - timedelta(microseconds=1)
    with pytest.raises(ValueError):
        load(root, consumed_result['symbol'], now)
