"""Sealed synthetic owned entries with the production source loader; no private data."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
from hashlib import sha256

import pytest

from test_advisory_decision_recommendation_v3 import _entry
from test_hotspot_current_price_case import capture, NOW
from value_investment_agent import research_artifact_repository as repositories
from value_investment_agent.application.decision.artifact_bundle import (
    export_artifact_bundle, ReadOnlyArtifactBundleRepository,
)
from value_investment_agent.application.hotspot.price_action_case import project_current_price_action_plan
from value_investment_agent.application.portfolio import owned_hotspot_lifecycle as subject
from value_investment_agent.domain.portfolio.dual_sleeve_records import canonical_bytes
from value_investment_agent.research_artifact_codecs import artifact_payload
from value_investment_agent.research_artifacts import ResearchArtifactIdentity


def seal(value, key):
    value[key] = sha256(canonical_bytes({k: v for k, v in value.items() if k != key})).hexdigest()
    return value


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW if tz is None else NOW.astimezone(tz)

    monkeypatch.setattr(repositories, 'datetime', Clock)
    case = capture(tmp_path)
    plan = project_current_price_action_plan(case)
    plan.update(case_path=case['case_path'], case_sha256=case['case_sha256'],
                research_version='TEST_ONLY-original', evaluated_at=NOW.isoformat())
    entry = replace(_entry(), symbol=case['symbol'], entry_date=NOW.date(),
                    entry_price=Decimal('18'), confirmed_at=NOW, created_at=NOW)
    kind, payload = artifact_payload(entry)
    ref = dict(id='TEST_ONLY-original-case', role=subject.ORIGINAL_CASE_ROLE,
               path=case['case_path'], sha256=case['case_sha256'],
               evaluated_at=NOW.isoformat(), rule_version=plan['model_or_rule_version'])
    artifact = repositories.InMemoryResearchArtifactRepository().save_object(entry,
        identity=ResearchArtifactIdentity(scope_type='security', scope_key=case['symbol'],
            artifact_type=kind, schema_version=payload['schema_version'],
            as_of=NOW.date(), available_at=NOW), evidence_refs=[ref], run_id='TEST_ONLY-owned')
    snapshot = seal(dict(schema_version='private-recording-time-judgment-snapshot-v1',
        decision_id='hotspot-' + case['symbol'], research_version=plan['research_version'],
        publication_id='TEST_ONLY-publication', public_packet_content_sha256='a' * 64,
        recorded_at=NOW.isoformat(), action='no_order',
        scope='IMMUTABLE_PUBLICATION_AT_RECORDING_TIME_NOT_PROVEN_PRETRADE_KNOWLEDGE',
        trade_time_availability_proven=False, current_source_reverified=False,
        plan=deepcopy(plan)), 'snapshot_sha256')
    fill = dict(transaction_id='TEST_ONLY-fill', symbol=case['symbol'], side='BUY',
        exchange='SSE', sleeve='HOTSPOT_SATELLITE', trade_date=NOW.date().isoformat(),
        price_cny='18', quantity='100', decision_id=snapshot['decision_id'],
        research_version=plan['research_version'], judgment_snapshot=snapshot)
    record = seal(dict(kind='FILL_CONFIRMED', sequence=3, recorded_at=NOW.isoformat(),
        body=dict(fill=fill, confirmation=dict(confirmed_at=NOW.isoformat()))), 'record_sha256')
    contract = dict(action='no_order', account_scope='TEST_ONLY-owned',
        fill_record_sha256=record['record_sha256'], symbol=fill['symbol'],
        exchange=fill['exchange'], sleeve=fill['sleeve'], transaction_id=fill['transaction_id'],
        confirmation=dict(confirmed_at=NOW.isoformat()), entry_ref=dict(
            artifact_id=artifact.artifact_id, payload_sha256=artifact.envelope.payload_sha256,
            available_at=NOW.isoformat()))
    binding = dict(provenance='REGISTERED_ARTIFACT_BINDING', binding_mode='CONTEMPORANEOUS',
        confirmed_at=NOW.isoformat(), artifact_bundle=export_artifact_bundle([artifact]),
        binding_contract=contract, **{k: contract[k] for k in
            ('fill_record_sha256', 'symbol', 'exchange', 'sleeve', 'transaction_id')})
    context = dict(action='no_order', ownership_verified=True, account_scope='TEST_ONLY-owned',
        symbol=fill['symbol'], sleeve=fill['sleeve'], bindings=[binding],
        entry_artifact=artifact, entry_thesis=entry)
    return dict(root=tmp_path, context=context, confirmed_fill_records=[record],
                current_plan=plan, now=NOW), case


def test_production_loader_replays_research_but_never_claims_trade_time(inputs):
    args, _ = inputs
    before = deepcopy(args)
    result = subject.resolve_owned_hotspot_lifecycle(**args)
    item = result['items'][0]
    assert result['ownership_verified'] is True
    assert item['source_reference_status'] == 'SOURCE_REPLAYED'
    assert item['research_reference']['entry_case_binding'] == item['original_case_binding']
    assert item['execution_at'] is None
    assert item['research_reference']['price_comparability']['status'] != 'CONFIRMED'
    assert item['scope'] == 'ORIGINAL_RESEARCH_REFERENCE_NOT_EXECUTION_CONTINUITY'
    assert result['status'] == 'NOT_ASSESSABLE'
    assert result['personal_add_permission'] is result['pretrade_proven'] is False
    assert args == before


@pytest.mark.parametrize('fault', ['wrong_fill', 'wrong_symbol', 'other_case', 'hash',
    'future', 'late_recording', 'rule', 'no_ref', 'two_refs', 'no_entry',
    'snapshot_hash', 'context_artifact', 'fake_execution'])
def test_adversarial_sealed_inputs_fail_closed(inputs, fault):
    args, case = inputs
    binding = args['context']['bindings'][0]
    record = args['confirmed_fill_records'][0]
    row = binding['artifact_bundle']['artifacts'][0]
    ref = row['evidence_refs'][0]
    snap = record['body']['fill']['judgment_snapshot']
    if fault == 'wrong_fill':
        binding['fill_record_sha256'] = binding['binding_contract']['fill_record_sha256'] = '0' * 64
    elif fault == 'wrong_symbol':
        args['context']['symbol'] = '000333'
    elif fault == 'other_case':
        ref['path'] = 'runtime/other-case.json'
    elif fault == 'hash':
        (args['root'] / case['case_path']).write_bytes(b'{}')
    elif fault == 'future':
        ref['evaluated_at'] = (NOW + timedelta(days=1)).isoformat()
    elif fault == 'late_recording':
        snap['recorded_at'] = (NOW + timedelta(days=1)).isoformat()
    elif fault == 'rule':
        ref['rule_version'] = 'changed'
    elif fault == 'no_ref':
        row['evidence_refs'] = []
    elif fault == 'two_refs':
        row['evidence_refs'].append({**ref, 'id': 'second'})
    elif fault == 'no_entry':
        args['context']['bindings'] = []
    elif fault == 'snapshot_hash':
        snap['snapshot_sha256'] = '0' * 64
    elif fault == 'context_artifact':
        args['context']['entry_artifact'] = 'different'
    else:
        record['body']['fill']['executed_at'] = NOW.isoformat()
    # Keep outer record hashes valid: semantic contradictions must still fail.
    if fault in ('late_recording', 'fake_execution'):
        seal(snap, 'snapshot_sha256')
        seal(record, 'record_sha256')
        binding['fill_record_sha256'] = binding['binding_contract']['fill_record_sha256'] = record['record_sha256']
    if fault != 'context_artifact':
        args['context']['entry_artifact'] = ReadOnlyArtifactBundleRepository(
            binding['artifact_bundle']).load_by_id(row['artifact_id'])
    result = subject.resolve_owned_hotspot_lifecycle(**args)
    assert result['personal_add_permission'] is result['pretrade_proven'] is False
    if fault != 'fake_execution':
        assert not result['items'] or result['items'][0]['research_reference'] is None


def test_current_rule_change_retains_only_unapproved_reference(inputs):
    args, _ = inputs
    # A caller-supplied changed version cannot replace the source-replayed rule.
    args['current_plan']['model_or_rule_version'] = 'wrong'
    result = subject.resolve_owned_hotspot_lifecycle(**args)
    assert result['personal_add_permission'] is False
    assert result['items'][0]['research_reference'] is None
    assert result['items'][0]['blockers'] == ['CURRENT_RULE_MISMATCH']


def test_multiple_entries_are_evaluated_per_fill_not_latest_candidate(inputs):
    args, _ = inputs
    second = deepcopy(args['context'])
    args['context']['entry_contexts'] = [deepcopy(second), second]
    result = subject.resolve_owned_hotspot_lifecycle(**args)
    assert result['items'] == []
    assert result['blockers'] == ['DUPLICATE_OWNED_FILL']


def test_distinct_fills_are_not_collapsed_to_latest(inputs):
    args, _ = inputs
    second = deepcopy(args['context']['bindings'][0])
    record = deepcopy(args['confirmed_fill_records'][0])
    record['body']['fill']['transaction_id'] = 'TEST_ONLY-second-fill'
    seal(record, 'record_sha256')
    second['transaction_id'] = second['binding_contract']['transaction_id'] = 'TEST_ONLY-second-fill'
    second['fill_record_sha256'] = second['binding_contract']['fill_record_sha256'] = record['record_sha256']
    args['confirmed_fill_records'].append(record)
    args['context']['bindings'].append(second)
    result = subject.resolve_owned_hotspot_lifecycle(**args)
    assert len(result['items']) == 2
    assert len({item['fill_record_sha256'] for item in result['items']}) == 2
    assert all(item['source_reference_status'] == 'SOURCE_REPLAYED' for item in result['items'])
    assert not result['personal_add_permission']


def test_original_sources_cannot_be_used_before_acquisition(inputs):
    args, _ = inputs
    binding = args['context']['bindings'][0]
    row = binding['artifact_bundle']['artifacts'][0]
    earlier = (NOW - timedelta(days=1)).isoformat()
    row['evidence_refs'][0]['evaluated_at'] = earlier
    args['context']['entry_artifact'] = ReadOnlyArtifactBundleRepository(
        binding['artifact_bundle']).load_by_id(row['artifact_id'])
    record = args['confirmed_fill_records'][0]
    snap = record['body']['fill']['judgment_snapshot']
    snap['plan']['evaluated_at'] = earlier
    seal(snap, 'snapshot_sha256')
    seal(record, 'record_sha256')
    binding['fill_record_sha256'] = binding['binding_contract']['fill_record_sha256'] = record['record_sha256']
    result = subject.resolve_owned_hotspot_lifecycle(**args)
    assert result['items'][0]['blockers'] == ['ORIGINAL_SOURCE_NOT_REPLAYABLE']
    assert result['items'][0]['research_reference'] is None


def test_cross_version_context_cannot_borrow_sealed_entry(inputs):
    args, _ = inputs
    args['context']['entry_thesis'] = replace(args['context']['entry_thesis'], thesis='different')
    result = subject.resolve_owned_hotspot_lifecycle(**args)
    assert result['items'][0]['blockers'] == ['CONTEXT_ENTRY_MISMATCH']


def test_ref_role_is_required_even_when_untyped_reference_has_matching_hash(inputs):
    args, _ = inputs
    binding = args['context']['bindings'][0]
    row = binding['artifact_bundle']['artifacts'][0]
    row['evidence_refs'][0].pop('role')
    args['context']['entry_artifact'] = ReadOnlyArtifactBundleRepository(
        binding['artifact_bundle']).load_by_id(row['artifact_id'])
    result = subject.resolve_owned_hotspot_lifecycle(**args)
    assert result['ownership_verified'] is True
    assert result['items'][0]['blockers'] == ['UNIQUE_ORIGINAL_CASE_REFERENCE_REQUIRED']
    assert not result['personal_add_permission']


def test_raw_source_tampering_is_rejected_by_production_loader(inputs):
    args, case = inputs
    source = args['root'] / case['source_bindings']['60m']['path']
    source.write_bytes(source.read_bytes() + b' ')
    result = subject.resolve_owned_hotspot_lifecycle(**args)
    assert result['items'][0]['blockers'] == ['ORIGINAL_SOURCE_NOT_REPLAYABLE']


@pytest.mark.parametrize('field,value', [('case_path', 'runtime/different.json'),
    ('case_sha256', '0' * 64), ('symbol', '000333'), ('model_or_rule_version', 'different')])
def test_same_fill_snapshot_semantics_cannot_be_hidden_by_valid_hash(inputs, field, value):
    args, _ = inputs
    record = args['confirmed_fill_records'][0]
    snapshot = record['body']['fill']['judgment_snapshot']
    snapshot['plan'][field] = value
    seal(snapshot, 'snapshot_sha256')
    seal(record, 'record_sha256')
    binding = args['context']['bindings'][0]
    binding['fill_record_sha256'] = binding['binding_contract']['fill_record_sha256'] = record['record_sha256']
    result = subject.resolve_owned_hotspot_lifecycle(**args)
    assert result['items'][0]['research_reference'] is None
    assert not result['personal_add_permission']
