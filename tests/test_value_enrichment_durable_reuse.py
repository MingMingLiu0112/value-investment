"""Restart and adversarial checks use isolated TEST_ONLY official inputs."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
import json

import pytest

from test_daily_refresh_value_adoption_integration import adoption
from test_value_enrichment_batch import registered_context
from value_investment_agent.application.research import value_enrichment_batch as batch
from value_investment_agent.infrastructure.screening.value_enrichment_progress import digest


@pytest.fixture
def durable(adoption, registered_context):
    root = adoption['root']
    summary = batch.persist_verified_enrichment_adoption(root=root, result=adoption['result'],
        financial_export_path=adoption['export'],
        financial_export_sha256=sha256(adoption['export'].read_bytes()).hexdigest(),
        output_dir=root / 'runtime/durable')
    assert summary['research_inputs_updated'] and summary['new_fact_approvals'] == 0
    return adoption


def test_restart_default_loader_and_safe_public_contract(durable):
    root = durable['root']
    now = datetime.now(timezone.utc)
    for _ in range(2):
        repository, contexts, diagnostics = batch.load_enrichment_research_contexts(
            root=root, symbols=['600001'], evaluation_at=now)
        assert diagnostics['600001']['status'] == 'VERIFIED_ENRICHMENT_CONTEXT_RESTORED'
        facts, case = contexts['600001']['facts'], contexts['600001']['case']
        assert facts.operating_inputs['debt_ratio'] == Decimal('20')
        assert not facts.verified and facts.scenario_inputs is None
        assert getattr(facts, 'valuation_timing', None) is None
        assert 'ECONOMIC_REVIEW_NOT_GRANTED_BY_ENRICHMENT' in facts.blockers
        assert case.research_status == 'DATA_CHECK' and case.valuation_status == 'NOT_ASSESSED'
        versions = repository.list_versions('security', '600001', 'financial_facts')
        assert len(versions) == 1
    public = batch.read_verified_enrichment_progress(root, '600001', now)
    assert public == dict(status='VERIFIED_FACT_ADOPTION', symbol='600001', adopted_fact_count=1,
        research_inputs_updated=True, quality_coverage_before='0.0000',
        quality_coverage_after='0.1111', formal_eligibility=False, action='no_order',
        as_of=durable['result']['evaluation_at'], verified_at=now.isoformat(),
        adopted_metrics=[dict(field_name='debt_ratio', value='20.0', unit='percent', period_label='2025-12-31')])
    assert batch.read_verified_enrichment_progress(root, '000002', now) is None
    assert batch.read_verified_enrichment_progress(root, '600001', now.replace(tzinfo=None)) is None


@pytest.mark.parametrize('change', ['source', 'export', 'baseline', 'baseline_rebound',
    'result', 'checkpoint', 'typed_payload_rebound'])
def test_reuse_refuses_changed_bindings_and_payloads(durable, change):
    root = durable['root']
    if change in {'source', 'export', 'baseline'}:
        path = dict(source=durable['original'], export=durable['export'],
                    baseline=root / 'runtime/workbench.json')[change]
        path.write_bytes(path.read_bytes() + b' ')
    elif change == 'baseline_rebound':
        path = root / 'runtime/workbench.json'
        value = json.loads(path.read_bytes())
        value['new_registered_revision'] = True
        path.write_text(json.dumps(value), encoding='utf-8')
        registry = root / 'config/current-agent-research.json'
        value = json.loads(registry.read_bytes())
        value['cases']['600001']['workflows']['financial']['workbench']['sha256'] = sha256(path.read_bytes()).hexdigest()
        registry.write_text(json.dumps(value), encoding='utf-8')
    else:
        checkpoint = next((root / 'runtime/value-evidence-enrichment/progress-v1').glob('*.json'))
        envelope = json.loads(checkpoint.read_bytes())
        if change == 'checkpoint':
            envelope['payload']['registered_adoption']['baseline_sha256'] = '0' * 64
        else:
            path = root / 'runtime/durable/600001.json'
            packet = json.loads(path.read_bytes())
            if change == 'result':
                packet['adopted_points'][0]['value'] = '0'
            else:
                registration = packet['research_registration']
                artifact = registration['artifacts'][0]['envelope']
                payload = json.loads(artifact['canonical_payload'])
                payload['operating_inputs']['invented_approval_input'] = '999'
                # Rehash every binding: replay must still reject unadmitted extras.
                from value_investment_agent.research_artifacts import ResearchArtifactEnvelope, ResearchArtifactIdentity
                identity = artifact['identity']
                identity = ResearchArtifactIdentity(**dict(identity,
                    as_of=datetime.fromisoformat(identity['as_of']).date(),
                    available_at=datetime.fromisoformat(identity['available_at'])))
                forged = ResearchArtifactEnvelope.build(identity=identity, payload=payload,
                    evidence_refs=artifact['evidence_refs'], run_id=artifact['run_id'])
                artifact['canonical_payload'] = forged.canonical_payload
                artifact['payload_sha256'] = forged.payload_sha256
                registration['financial_facts_sha256'] = forged.payload_sha256
                case = registration['artifacts'][1]['envelope']
                case_payload = json.loads(case['canonical_payload'])
                case_payload['financial_summary']['value_enrichment']['financial_facts']['sha256'] = forged.payload_sha256
                for ref in case_payload['evidence_refs']:
                    if ref.get('id') == 'value-enrichment-financial-facts':
                        ref['sha256'] = forged.payload_sha256
                forged_case = ResearchArtifactEnvelope.build(identity=ResearchArtifactIdentity(
                    'security', '600001', 'research_case', 'c3-v1', identity.as_of, identity.available_at),
                    payload=case_payload, evidence_refs=case_payload['evidence_refs'], run_id=case['run_id'])
                case['canonical_payload'] = forged_case.canonical_payload
                case['payload_sha256'] = forged_case.payload_sha256
                registration['research_case_sha256'] = forged_case.payload_sha256
            path.write_text(json.dumps(packet), encoding='utf-8')
            if change == 'typed_payload_rebound':
                attempt = root / 'runtime/durable/600001-attempt.json'
                value = json.loads(attempt.read_bytes())
                value['result_binding']['sha256'] = sha256(path.read_bytes()).hexdigest()
                attempt.write_text(json.dumps(value), encoding='utf-8')
                envelope['payload']['execution_binding']['sha256'] = sha256(attempt.read_bytes()).hexdigest()
                envelope['sha256'] = digest(envelope['payload'])
                from value_investment_agent.application.research.value_evidence_enrichment_v1 import verify_enrichment_adoption
                assert verify_enrichment_adoption(root=root, result_binding=value['result_binding'],
                    financial_export_path=durable['export'],
                    financial_export_sha256=sha256(durable['export'].read_bytes()).hexdigest(),
                    evaluation_at=datetime.now(timezone.utc))['research_inputs_updated']
        checkpoint.write_text(json.dumps(envelope), encoding='utf-8')
    now = datetime.now(timezone.utc)
    assert batch.read_verified_enrichment_progress(root, '600001', now) is None
    _, contexts, _ = batch.load_enrichment_research_contexts(root=root, symbols=['600001'], evaluation_at=now)
    if '600001' in contexts:
        assert 'debt_ratio' not in contexts['600001']['facts'].operating_inputs
        assert not contexts['600001']['facts'].verified


def test_future_checkpoint_does_not_leak(durable):
    cutoff = datetime.fromisoformat(durable['result']['evaluation_at']) - timedelta(seconds=1)
    assert batch.read_verified_enrichment_progress(durable['root'], '600001', cutoff) is None


@pytest.mark.parametrize('field,value', [('complete_debt_verified', True), ('status', 'COMPLETE_SCOPE_VALIDATED')])
def test_persistence_rejects_forged_full_debt_scope(adoption, registered_context, field, value):
    from copy import deepcopy
    result = deepcopy(adoption['result'])
    assert result['debt_scope']['complete_debt_verified'] is False
    result['debt_scope'][field] = value
    with pytest.raises(ValueError, match='debt_scope'):
        batch.persist_verified_enrichment_adoption(root=adoption['root'], result=result,
            financial_export_path=adoption['export'],
            financial_export_sha256=sha256(adoption['export'].read_bytes()).hexdigest(),
            output_dir=adoption['root'] / 'runtime/forged-scope')
    assert not (adoption['root'] / 'runtime/forged-scope').exists()
    assert batch.read_verified_enrichment_progress(adoption['root'], '600001', datetime.now(timezone.utc)) is None


@pytest.mark.parametrize('change', ['scope_and_case', 'scope_status', 'case_only'])
def test_fully_rebound_debt_scope_forgery_refused_on_restart(durable, change):
    from value_investment_agent.application.research.value_evidence_enrichment_v1 import verify_enrichment_adoption
    from value_investment_agent.research_artifacts import ResearchArtifactEnvelope, ResearchArtifactIdentity
    root = durable['root']
    result_path = root / 'runtime/durable/600001.json'
    result = json.loads(result_path.read_bytes())
    if change == 'scope_and_case':
        result['debt_scope']['complete_debt_verified'] = True
    elif change == 'scope_status':
        result['debt_scope']['status'] = 'COMPLETE_SCOPE_VALIDATED'
    if change != 'scope_status':
        registration = result['research_registration']
        raw = registration['artifacts'][1]['envelope']
        payload = json.loads(raw['canonical_payload'])
        payload['financial_summary']['value_enrichment']['complete_debt_verified'] = True
        ident = raw['identity']
        identity = ResearchArtifactIdentity(**dict(ident,
            as_of=datetime.fromisoformat(ident['as_of']).date(),
            available_at=datetime.fromisoformat(ident['available_at'])))
        forged = ResearchArtifactEnvelope.build(identity=identity, payload=payload,
            evidence_refs=raw['evidence_refs'], run_id=raw['run_id'])
        raw['canonical_payload'], raw['payload_sha256'] = forged.canonical_payload, forged.payload_sha256
        registration['research_case_sha256'] = forged.payload_sha256
    result_path.write_text(json.dumps(result), encoding='utf-8')
    attempt = root / 'runtime/durable/600001-attempt.json'
    outcome = json.loads(attempt.read_bytes())
    outcome['result_binding']['sha256'] = sha256(result_path.read_bytes()).hexdigest()
    attempt.write_text(json.dumps(outcome), encoding='utf-8')
    checkpoint = next((root / 'runtime/value-evidence-enrichment/progress-v1').glob('*.json'))
    envelope = json.loads(checkpoint.read_bytes())
    envelope['payload']['execution_binding']['sha256'] = sha256(attempt.read_bytes()).hexdigest()
    envelope['sha256'] = digest(envelope['payload'])
    checkpoint.write_text(json.dumps(envelope), encoding='utf-8')
    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError, match='debt.scope|debt_scope'):
        verify_enrichment_adoption(root=root, result_binding=outcome['result_binding'],
            financial_export_path=durable['export'],
            financial_export_sha256=sha256(durable['export'].read_bytes()).hexdigest(), evaluation_at=now)
    assert batch.read_verified_enrichment_progress(root, '600001', now) is None
    _, contexts, diagnostics = batch.load_enrichment_research_contexts(root=root,
        symbols=['600001'], evaluation_at=now)
    assert diagnostics['600001']['reuse_status'] == 'UNVERIFIED'
    assert 'value_enrichment' not in contexts['600001']['case'].financial_summary
    assert not contexts['600001']['facts'].verified
