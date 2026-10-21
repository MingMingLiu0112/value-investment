"""Real source replay in an isolated queue, never synthetic candidate insertion."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json

import pytest

from test_value_evidence_enrichment_v1 import source, balance_inputs, income_inputs
from test_value_enrichment_batch import registered_context
from test_value_research_priority_v2 import _inputs
from value_investment_agent.application.research import value_enrichment_batch as batch
from value_investment_agent.application.research.value_research_priority_v2 import build_value_research_priority_v2, reuse_durable_income_export
from value_investment_agent.application.research.income_source_correlation import correlate_income_inputs
from value_investment_agent.application.research.value_evidence_enrichment_v1 import enrich_retained_company, verify_enrichment_adoption
from value_investment_agent.application.product.value_discovery_surface import publish_value_discovery_report
from value_investment_agent.infrastructure.screening import value_evidence_enrichment_v1 as adapter
from value_investment_agent.infrastructure.screening.value_enrichment_progress import ValueEnrichmentProgress


CLOCK = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, default=str), encoding='utf-8')


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


@pytest.fixture(autouse=True)
def queue_args(tmp_path):
    return _inputs(tmp_path, pending=True)


@pytest.fixture
def durable_income(queue_args, income_inputs, registered_context, tmp_path, monkeypatch):
    official, points, pages = income_inputs
    official = replace(official, symbol='600001')
    pages[:] = [page.replace('600887', '600001') for page in pages]
    monkeypatch.setattr(adapter, 'extract_pages', lambda path, limit: pages[:limit])
    current = [dict(deepcopy(p), symbol='600001', source_name='CNINFO statutory disclosure')
               for p in points if p['period_label'] == official.period]
    base = tmp_path / 'runtime/current-base.json'
    payload = dict(points=[], annual_points=current)
    write(base, payload)
    args = dict(queue_args, financial_export_path=base, financial_export_sha256=digest(base))
    receipt = json.loads(args['receipt_path'].read_bytes())
    receipt['generated_at'] = CLOCK.isoformat()
    write(args['receipt_path'], receipt)
    args['receipt_sha256'] = digest(args['receipt_path'])
    args['report_path'] = tmp_path / 'runtime/current-report.json'
    publish_value_discovery_report(root=tmp_path, receipt_path=args['receipt_path'],
        receipt_sha256=args['receipt_sha256'], output_path=args['report_path'])
    args['report_sha256'] = digest(args['report_path'])
    reports = {period: dict(rCurrency='CNY', rType='\u5408\u5e76\u671f\u672b', publish_date='20260420', data=[
        dict(item_field='BIZINCO', item_value=revenue, item_source='lrb'),
        dict(item_field='PARENETP', item_value=profit, item_source='lrb')])
        for period, revenue, profit in [('20251231', '120.00', '24.00'), ('20241231', '100.00', '20.00')]}
    raw = tmp_path / 'runtime/income.json'
    write(raw, dict(result=dict(data=dict(report_list=reports))))
    descriptor = dict(path='runtime/income.json', sha256=digest(raw),
        acquired_at=(CLOCK - timedelta(hours=1)).isoformat(),
        source_url='https://quotes.sina.cn/cn/api/openapi.php/CompanyFinanceService.getFinanceReport2022?paperCode=sh600001&source=lrb&type=0')
    acquisition = tmp_path / 'runtime/acquisition.json'
    write(acquisition, dict(url=descriptor['source_url'], path=descriptor['path'], sha256=descriptor['sha256'],
        acquired_at=descriptor['acquired_at'], bytes=len(raw.read_bytes()), action='no_order'))
    descriptor['receipt'] = dict(path='runtime/acquisition.json', sha256=digest(acquisition))
    correlated = correlate_income_inputs(tmp_path, official, descriptor, evaluation_at=CLOCK)
    prior = [p for p in correlated if p['period_label'] == '2024-12-31']
    full = [*current, *prior]
    saved = tmp_path / 'runtime/saved-income-financial.json'
    write(saved, dict(points=[], annual_points=full))
    before = build_value_research_priority_v2(**args)
    result = enrich_retained_company(tmp_path, official, full,
        evaluation_at=CLOCK - timedelta(minutes=10), cache_dir=tmp_path / '.tmp/value-enrichment-extraction')
    class ReceiptClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return CLOCK - timedelta(minutes=5)
    with monkeypatch.context() as patch:
        patch.setattr(batch, 'datetime', ReceiptClock)
        persisted = batch.persist_verified_enrichment_adoption(root=tmp_path, result=result,
            financial_export_path=saved, financial_export_sha256=digest(saved),
            output_dir=tmp_path / 'runtime/durable-income')
    return dict(args=args, official=official, raw=raw, receipt=acquisition, saved=saved,
        before=before, persisted=persisted, base_bytes=base.read_bytes())


def company(queue):
    return next(row for row in queue['evidence_enrichment_work_queue'] if row['symbol'] == '600001')


def test_default_queue_and_batch_reuse_both_income_denominators(durable_income):
    data, args = durable_income, durable_income['args']
    root = args['root']
    queue = build_value_research_priority_v2(**args)
    assert company(data['before'])['evidence_completeness']['coverage_ratio'] == '0.0000'
    assert company(queue)['evidence_completeness']['coverage_ratio'] == '0.3333'
    assert len(queue['durable_income_reuse']) == 1
    assert len(queue['durable_income_reuse'][0]['input_fact_ids']) == 2
    assert queue['inputs']['base_financial_export']['path'] == 'runtime/current-base.json'
    assert queue == build_value_research_priority_v2(**args)
    assert queue == build_value_research_priority_v2(**dict(args,
        financial_export_path=root / queue['inputs']['financial_export_path'],
        financial_export_sha256=queue['inputs']['financial_export_sha256']))
    repo, contexts, _ = batch.load_enrichment_research_contexts(root=root, symbols=['600001'], evaluation_at=CLOCK)
    execution = batch.execute_value_enrichment_batch(root=root, queue=queue,
        financial_export_path=args['financial_export_path'], financial_export_sha256=args['financial_export_sha256'],
        output_dir=root / 'runtime/automatic-reuse', budget=1, repository=repo, research_contexts=contexts)
    row = execution['items'][0]
    assert row['symbol'] == '600001' and len(row['adopted_fact_ids']) == 3, row
    summary = verify_enrichment_adoption(root=root, result_binding=row['result_binding'],
        financial_export_path=root / queue['inputs']['financial_export_path'],
        financial_export_sha256=queue['inputs']['financial_export_sha256'], evaluation_at=datetime.now(timezone.utc))
    assert summary['adopted_fact_count'] == 3 and summary['research_inputs_updated']
    assert summary['quality_coverage_after'] == '0.3333'
    assert summary['new_fact_approvals'] == 0 and not summary['formal_eligibility']
    public = batch.read_verified_enrichment_progress(root, '600001', datetime.now(timezone.utc))
    assert public['adopted_fact_count'] == 3
    assert args['financial_export_path'].read_bytes() == data['base_bytes']
    all_symbols = lambda q: {row['symbol'] for name in ('deep_research_priority', 'evidence_enrichment_work_queue') for row in q[name]}
    assert all_symbols(queue) == all_symbols(data['before'])


@pytest.mark.parametrize('change', ['secondary', 'receipt', 'official', 'export', 'cache', 'base', 'deleted_base'])
def test_saved_assurance_cannot_replace_source_and_base_replay(durable_income, change):
    data, args = durable_income, durable_income['args']
    root = args['root']
    queue = build_value_research_priority_v2(**args)
    if change == 'cache':
        path = next((root / '.tmp/value-enrichment-extraction').glob('*.json'))
        value = json.loads(path.read_bytes())
        value['packet']['income_comparatives'][0]['prior_value'] = '99'
        value['packet_sha256'] = sha256(json.dumps(value['packet'], sort_keys=True).encode()).hexdigest()
        write(path, value)
    elif change in ('base', 'deleted_base'):
        payload = json.loads(args['financial_export_path'].read_bytes())
        if change == 'deleted_base':
            payload['annual_points'].pop(0)
        else:
            payload['annual_points'][0]['value'] = '1001'
        write(args['financial_export_path'], payload)
        args['financial_export_sha256'] = digest(args['financial_export_path'])
    else:
        path = dict(secondary=data['raw'], receipt=data['receipt'], official=root / data['official'].path,
                    export=data['saved'])[change]
        path.write_bytes(path.read_bytes() + b' ')
    with pytest.raises(ValueError):
        build_value_research_priority_v2(**args)
    with pytest.raises(ValueError):
        batch.execute_value_enrichment_batch(root=root, queue=queue,
            financial_export_path=args['financial_export_path'], financial_export_sha256=args['financial_export_sha256'],
            output_dir=root / 'runtime/refused', budget=1)
    assert not (root / 'runtime/refused').exists()


@pytest.mark.parametrize('conflicting', [False, True])
def test_duplicate_source_declarations_are_deduplicated_or_refused(durable_income, conflicting):
    data, args = durable_income, durable_income['args']
    expected = build_value_research_priority_v2(**args)
    declaration = expected['durable_income_reuse'][0]['source']
    duplicate = deepcopy(declaration)
    if conflicting:
        duplicate['sha256'] = '0' * 64
    payload = json.loads(args['financial_export_path'].read_bytes())
    payload['value_enrichment_sources'] = [declaration, duplicate]
    write(args['financial_export_path'], payload)
    args['financial_export_sha256'] = digest(args['financial_export_path'])
    if conflicting:
        with pytest.raises(ValueError, match='conflicting declared and completed enrichment source'):
            build_value_research_priority_v2(**args)
    else:
        queue = build_value_research_priority_v2(**args)
        assert queue['durable_income_reuse'] == expected['durable_income_reuse']
        assert queue['retained_enrichment_adoption'] == expected['retained_enrichment_adoption']
        assert company(queue) == company(expected)
        overlay = json.loads((args['root'] / queue['inputs']['financial_export_path']).read_bytes())
        assert len(overlay['value_enrichment_sources']) == 1


@pytest.mark.parametrize('declared', [False, True])
def test_non_candidate_source_cannot_block_remaining_queue(durable_income, monkeypatch, declared):
    data, args = durable_income, durable_income['args']
    expected = build_value_research_priority_v2(**args)
    foreign = dict(expected['durable_income_reuse'][0]['source'],
                   symbol='600519', path='runtime/absent-non-candidate.pdf', sha256='0' * 64)
    if declared:
        payload = json.loads(args['financial_export_path'].read_bytes())
        payload['value_enrichment_sources'] = [foreign]
        write(args['financial_export_path'], payload)
        args['financial_export_sha256'] = digest(args['financial_export_path'])
    else:
        completed = ValueEnrichmentProgress.completed_sources
        monkeypatch.setattr(ValueEnrichmentProgress, 'completed_sources',
            lambda self, **kwargs: [*completed(self, **kwargs), foreign])
    registered = ValueEnrichmentProgress.registered_adoption
    def candidate_only(self, symbol, **kwargs):
        assert symbol != '600519', 'Non-candidate registration must not be loaded'
        return registered(self, symbol, **kwargs)
    monkeypatch.setattr(ValueEnrichmentProgress, 'registered_adoption', candidate_only)
    queue = build_value_research_priority_v2(**args)
    for name in ('deep_research_priority', 'evidence_enrichment_work_queue',
                 'durable_income_reuse', 'retained_enrichment_adoption'):
        assert queue[name] == expected[name]
    assert all(row['symbol'] != '600519' for name in
        ('deep_research_priority', 'evidence_enrichment_work_queue') for row in queue[name])


def test_empty_candidate_set_never_loads_registered_income(durable_income, monkeypatch):
    data, args = durable_income, durable_income['args']
    def unexpected(*args, **kwargs):
        pytest.fail('Empty candidate set must not load registered adoption')
    monkeypatch.setattr(ValueEnrichmentProgress, 'registered_adoption', unexpected)
    export, digest_value, points, reused = reuse_durable_income_export(
        root=args['root'], export=args['financial_export_path'], export_sha256=args['financial_export_sha256'],
        points=[], sources=[data['official'].__dict__], symbols=set(), evaluation_at=CLOCK)
    assert export == args['financial_export_path']
    assert digest_value == args['financial_export_sha256']
    assert points == [] and reused == []
    assert export.read_bytes() == data['base_bytes']
