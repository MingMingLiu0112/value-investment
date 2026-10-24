"""Isolated Root summary integration; TEST_ONLY sources never leave tmp_path."""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json

import pytest

from value_investment_agent.application.product.daily_refresh import _enrichment_execution_summary
from value_investment_agent.application.research.value_evidence_enrichment_v1 import (
    enrich_retained_company, register_enriched_research,
)
from value_investment_agent.infrastructure.screening import value_evidence_enrichment_v1 as extraction
from value_investment_agent.research_artifact_repository import InMemoryResearchArtifactRepository
from value_investment_agent.research_case import ResearchCase
from value_investment_agent.valuation_models.fcff import FinancialFacts


NOW = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)


def _write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, default=str), encoding='utf-8')


def _binding(root, path):
    return dict(path=path.relative_to(root).as_posix(), sha256=sha256(path.read_bytes()).hexdigest())


@pytest.fixture
def adoption(tmp_path, monkeypatch):
    folder = tmp_path / 'runtime/daily-marketwide/TEST_ONLY'
    folder.mkdir(parents=True)
    original = folder / 'annual.pdf'
    original.write_bytes(b'%PDF-TEST_ONLY-isolated-retained-statement')
    source = extraction.RetainedAnnualSource('600001', '2025-12-31',
        original.relative_to(tmp_path).as_posix(), sha256(original.read_bytes()).hexdigest(),
        'https://static.cninfo.com.cn/finalpage/2026-04-01/123456.PDF',
        '2026-09-01T00:00:00+00:00')
    pages = ['TEST_ONLY \u80a1\u7968\u4ee3\u7801: 600001; 2025\u5e74\u5e74\u5ea6\u62a5\u544a',
        '\u5408\u5e76\u8d44\u4ea7\u8d1f\u503a\u8868\n2025\u5e7412\u670831\u65e5 2024\u5e7412\u670831\u65e5\n'
        '\u5355\u4f4d\uff1a\u5143 \u5e01\u79cd\uff1a\u4eba\u6c11\u5e01\n'
        '\u8d44\u4ea7\u603b\u8ba1 1,000.00 900.00\n\u8d1f\u503a\u5408\u8ba1 200.00 180.00']
    # Only PDF decoding is substituted. Arithmetic, assurance, registration,
    # bound-input verification and the Root summary all execute real code.
    monkeypatch.setattr(extraction, 'extract_pages', lambda path, limit: pages[:limit])
    points = [dict(symbol=source.symbol, field_name=field, value=value, unit='CNY',
        data_point_id='TEST_ONLY:' + field, source_id='TEST_ONLY:official',
        source_url=source.source_url, sha256=source.sha256, period_label=source.period,
        validation_status='verified', created_at=source.available_at, fetched_at=source.available_at,
        metadata=dict(automatic_cross_source_verification=True,
            statement_scope='consolidated', currency='CNY'))
        for field, value in [('total_assets', '1000'), ('total_liabilities', '200')]]
    export = folder / 'financial.json'
    _write(export, {'points': points})
    result = enrich_retained_company(tmp_path, source, points, evaluation_at=NOW,
        cache_dir=tmp_path / '.tmp/extraction', name='TEST_ONLY')
    assert len(result['adopted_points']) == 1
    case = ResearchCase(symbol=source.symbol, name='TEST_ONLY', as_of=NOW.date(),
        generated_at=NOW, run_id='TEST_ONLY', research_version='test-v1', industry='TEST_ONLY',
        investment_path='UNASSESSED', thesis='TEST_ONLY', return_driver='UNASSESSED',
        mispricing_hypothesis='UNASSESSED', financial_summary={}, positives=[], counter_evidence=[],
        thesis_breakers=[], next_events=[], evidence_status='PARTIAL', valuation_status='NOT_ASSESSED',
        research_status='DATA_CHECK', blockers=['MISSING_ECONOMIC_INPUTS'], evidence_refs=[],
        quote_date=None, financial_period=date(2025, 12, 31),
        missing_date_reasons={'quote_date': 'TEST_ONLY no quote'})
    facts = FinancialFacts(source.symbol, NOW.date(), False, [], ['MISSING_ECONOMIC_INPUTS'])
    result['research_registration'] = register_enriched_research(result, root=tmp_path, points=points,
        repository=InMemoryResearchArtifactRepository(), case=case, facts=facts, run_id='TEST_ONLY')
    result['source_extraction'].pop('page_texts', None)
    result_path = folder / 'enrichment/600001.json'
    _write(result_path, result)
    queue = dict(content_sha256='a' * 64,
        evidence_enrichment_work_queue=[dict(symbol=source.symbol, company_name='TEST_ONLY')],
        inputs=dict(financial_export_path=export.relative_to(tmp_path).as_posix(),
                    financial_export_sha256=sha256(export.read_bytes()).hexdigest()))
    execution = dict(schema_version='value-enrichment-execution-v1', action='no_order',
        queue_content_sha256=queue['content_sha256'], formal_eligibility=False, new_fact_approvals=0,
        attempted_count=1, finished_at=(NOW + timedelta(seconds=1)).isoformat(),
        items=[dict(symbol=source.symbol, state='DATA_UNAVAILABLE', formal_eligibility=False,
            transitions=['ORIGINAL_HASH_VERIFIED', 'QUALITY_REEVALUATED', 'DATA_UNAVAILABLE'],
            adopted_fact_ids=[p['data_point_id'] for p in result['adopted_points']],
            research_registration_status='RESEARCH_INPUTS_UPDATED',
            extracted_candidates=2, matched_candidates=2,
            result_binding=_binding(tmp_path, result_path))])
    return dict(root=tmp_path, folder=folder, original=original, export=export,
        result=result, result_path=result_path, queue=queue, execution=execution)


def _summary(fixture):
    path = fixture['folder'] / 'enrichment/execution.json'
    _write(path, fixture['execution'])
    return _enrichment_execution_summary(fixture['root'], fixture['folder'],
        _binding(fixture['root'], path), fixture['queue'])


def _rebind_result(fixture):
    _write(fixture['result_path'], fixture['result'])
    fixture['execution']['items'][0]['result_binding'] = _binding(fixture['root'], fixture['result_path'])


def test_verified_adoption_reaches_root_summary_without_economic_promotion(adoption):
    first = _summary(adoption)
    assert first['status'] == 'VERIFIED_RESEARCH_EXECUTION'
    assert first['verified_adopted_fact_count'] == first['research_inputs_updated_count'] == 1
    assert first['attempted_count'] == first['reevaluated_count'] == first['data_gap_count'] == 1
    verified = first['items'][0]['adoption']
    assert verified['status'] == 'VERIFIED_FACT_ADOPTION'
    assert verified['adopted_fact_ids'] == adoption['execution']['items'][0]['adopted_fact_ids']
    assert verified['research_inputs_updated'] is True
    assert verified['new_fact_approvals'] == 0
    assert not verified['complete_debt_verified'] and not verified['formal_eligibility']
    assert first['action'] == 'no_order' and not first['formal_eligibility']
    assert _summary(adoption) == first  # Warm extraction-cache read is equivalent.


def test_root_counts_verified_consumption_not_declared_registration_status(adoption):
    adoption['result'].pop('research_registration')
    _rebind_result(adoption)
    row = adoption['execution']['items'][0]
    row.update(research_registration_status='RESEARCH_INPUTS_UPDATED',
        adopted_fact_count=999, research_inputs_updated=True)
    summary = _summary(adoption)
    assert summary['status'] == 'VERIFIED_RESEARCH_EXECUTION'
    assert summary['verified_adopted_fact_count'] == 1
    assert summary['research_inputs_updated_count'] == 0
    assert summary['items'][0]['adoption']['research_inputs_updated'] is False


@pytest.mark.parametrize('declared', ['missing', 'empty'])
def test_no_declared_adoption_is_only_scheduling_and_needs_no_result_binding(adoption, declared):
    row = adoption['execution']['items'][0]
    if declared == 'missing':
        row.pop('adopted_fact_ids')
    else:
        row['adopted_fact_ids'] = []
    row.pop('result_binding')
    summary = _summary(adoption)
    assert summary['status'] == 'VERIFIED_RESEARCH_EXECUTION'
    assert summary['verified_adopted_fact_count'] == summary['research_inputs_updated_count'] == 0
    assert summary['items'][0]['adoption'] is None
    assert not summary['formal_eligibility']


@pytest.mark.parametrize('change', ['invented_id', 'extra_id', 'duplicate_id', 'string_ids',
    'missing_result_binding', 'missing_result_file', 'stale_result_hash', 'result_path_escape',
    'result_value_rehashed', 'result_quality_rehashed', 'result_symbol_rehashed',
    'original_bytes', 'export_bytes', 'export_amount_rehashed', 'registration_payload_rehashed',
    'registration_link_rehashed', 'finish_before_result'])
def test_nonempty_declarations_fail_closed_when_proof_or_binding_is_tampered(adoption, change):
    row = adoption['execution']['items'][0]
    if change == 'invented_id':
        row['adopted_fact_ids'] = ['TEST_ONLY:invented']
    elif change == 'extra_id':
        row['adopted_fact_ids'].append('TEST_ONLY:extra')
    elif change == 'duplicate_id':
        row['adopted_fact_ids'] *= 2
    elif change == 'string_ids':
        row['adopted_fact_ids'] = row['adopted_fact_ids'][0]
    elif change == 'missing_result_binding':
        row.pop('result_binding')
    elif change == 'missing_result_file':
        adoption['result_path'].unlink()
    elif change == 'stale_result_hash':
        adoption['result_path'].write_text('{}', encoding='utf-8')
    elif change == 'result_path_escape':
        row['result_binding']['path'] = '../outside/result.json'
    elif change == 'result_value_rehashed':
        adoption['result']['adopted_points'][0]['value'] = '0'
        _rebind_result(adoption)
    elif change == 'result_quality_rehashed':
        adoption['result']['after']['coverage_ratio'] = '1.0000'
        _rebind_result(adoption)
    elif change == 'result_symbol_rehashed':
        adoption['result']['source_extraction']['identity']['source']['symbol'] = '600002'
        _rebind_result(adoption)
    elif change == 'original_bytes':
        adoption['original'].write_bytes(b'%PDF-TEST_ONLY-tampered-original')
    elif change in {'export_bytes', 'export_amount_rehashed'}:
        payload = json.loads(adoption['export'].read_bytes())
        payload['points'][0]['value'] = '2000'
        _write(adoption['export'], payload)
        if change == 'export_amount_rehashed':
            adoption['queue']['inputs']['financial_export_sha256'] = sha256(adoption['export'].read_bytes()).hexdigest()
    elif change == 'registration_payload_rehashed':
        adoption['result']['research_registration']['artifacts'][0]['envelope']['canonical_payload'] = '{"forged":true}'
        _rebind_result(adoption)
    elif change == 'registration_link_rehashed':
        adoption['result']['research_registration']['financial_facts_artifact_id'] = 'TEST_ONLY:wrong-version'
        _rebind_result(adoption)
    else:
        adoption['execution']['finished_at'] = (NOW - timedelta(seconds=1)).isoformat()
    assert _summary(adoption) == {'status': 'UNVERIFIED'}


@pytest.mark.parametrize('change', ['queue_binding', 'unknown_candidate', 'duplicate_candidate',
    'new_approval', 'formal_eligibility', 'item_eligibility', 'attempt_count'])
def test_valid_fact_proof_cannot_override_execution_contract(adoption, change):
    execution = adoption['execution']
    if change == 'queue_binding':
        execution['queue_content_sha256'] = 'b' * 64
    elif change == 'unknown_candidate':
        adoption['queue']['evidence_enrichment_work_queue'] = []
    elif change == 'duplicate_candidate':
        execution['items'].append(deepcopy(execution['items'][0]))
        execution['attempted_count'] = 2
    elif change == 'new_approval':
        execution['new_fact_approvals'] = 1
    elif change == 'formal_eligibility':
        execution['formal_eligibility'] = True
    elif change == 'item_eligibility':
        execution['items'][0]['formal_eligibility'] = True
    else:
        execution['attempted_count'] = 0
    assert _summary(adoption) == {'status': 'UNVERIFIED'}


def test_execution_outer_hash_is_checked_before_adoption(adoption):
    path = adoption['folder'] / 'enrichment/execution.json'
    _write(path, adoption['execution'])
    binding = _binding(adoption['root'], path)
    modified = deepcopy(adoption['execution'])
    modified['items'][0]['adopted_fact_ids'] = ['TEST_ONLY:forged']
    _write(path, modified)
    assert _enrichment_execution_summary(adoption['root'], adoption['folder'], binding,
        adoption['queue']) == {'status': 'UNVERIFIED'}
