"""TEST_ONLY transport with real correlation, PDF replay and typed registration."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json

import pytest
import requests

from test_value_evidence_enrichment_v1 import source, balance_inputs, income_inputs
from test_value_enrichment_batch import registered_context, flow
from test_value_research_priority_v2 import _inputs
from value_investment_agent.application.research import value_enrichment_batch as batch
from value_investment_agent.application.research.value_evidence_enrichment_v1 import verify_enrichment_adoption
from value_investment_agent.application.research.value_research_priority_v2 import reuse_durable_income_export
from value_investment_agent.application.product.value_discovery_surface import publish_value_discovery_report
from value_investment_agent.infrastructure.screening import sina_income_original as collector
from value_investment_agent.infrastructure.screening import value_evidence_enrichment_v1 as adapter


def reports():
    return dict(result=dict(data=dict(report_list={period: dict(rCurrency='CNY',
        rType='\u5408\u5e76\u671f\u672b', publish_date='20260420', data=[
            dict(item_field='BIZINCO', item_value=revenue, item_source='lrb'),
            dict(item_field='PARENETP', item_value=profit, item_source='lrb')])
        for period, revenue, profit in [('20251231', '120.00', '24.00'), ('20241231', '100.00', '20.00')]})))


@pytest.fixture
def http(monkeypatch):
    state = dict(raw=json.dumps(reports()).encode(), status=200,
                 headers={'Content-Type': 'application/json; charset=UTF-8'}, calls=[])
    class Response:
        def __init__(self, url):
            self.url = state.get('response_url', url)
            self.status_code = state['status']
            self.headers = state['headers']
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def raise_for_status(self):
            if self.status_code >= 400:
                raise requests.HTTPError('TEST_ONLY HTTP error', response=self)
        def iter_content(self, size):
            for offset in range(0, len(state['raw']), size):
                yield state['raw'][offset:offset + size]
    class Session:
        trust_env = True
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def get(self, url, **kwargs):
            state['calls'].append(dict(url=url, trust_env=self.trust_env, **kwargs))
            if state.get('timeout'):
                raise requests.Timeout('TEST_ONLY timeout')
            return Response(url)
    monkeypatch.setattr(collector.requests, 'Session', Session)
    return state


def collect(root, **kwargs):
    return collector.collect_sina_income_original(root=root, symbol='600001',
        output_dir=root / 'runtime/income', **kwargs)


def test_collector_direct_streamed_immutable_receipt(tmp_path, http):
    descriptor = collect(tmp_path, allow_network=True)
    call = http['calls'][0]
    assert call == dict(url=collector.ENDPOINT + '?paperCode=sh600001&source=lrb&type=0&page=1&num=16',
        trust_env=False, stream=True, allow_redirects=False, timeout=(10, 20))
    raw = (tmp_path / descriptor['path']).read_bytes()
    receipt_path = tmp_path / descriptor['receipt']['path']
    receipt = json.loads(receipt_path.read_bytes())
    assert receipt == dict(url=descriptor['source_url'], path=descriptor['path'],
        sha256=sha256(raw).hexdigest(), acquired_at=descriptor['acquired_at'], bytes=len(raw), action='no_order')
    assert descriptor['receipt']['sha256'] == sha256(receipt_path.read_bytes()).hexdigest()
    with pytest.raises(FileExistsError):
        collect(tmp_path, allow_network=True)
    assert len(http['calls']) == 1


def test_collector_offline_has_no_request_or_artifact(tmp_path, http):
    assert collect(tmp_path) is None
    assert http['calls'] == [] and not (tmp_path / 'runtime/income').exists()


@pytest.mark.parametrize('symbol', ['../600001', '600001&url=x', '６００００１', '800001', '60001', None])
def test_collector_rejects_non_security_identity_before_transport(tmp_path, http, symbol):
    with pytest.raises(ValueError):
        collector.collect_sina_income_original(root=tmp_path, symbol=symbol,
            output_dir=tmp_path / 'runtime/income', allow_network=True)
    assert not http['calls']


@pytest.mark.parametrize('change', ['redirect', 'url', 'html', 'declared_size', 'stream_size', 'json', 'shape', 'timeout'])
def test_collector_refuses_unbounded_or_non_json_responses(tmp_path, http, change):
    if change == 'redirect':
        http['status'] = 302
    elif change == 'url':
        http['response_url'] = 'https://evil.example/income'
    elif change == 'html':
        http['headers']['Content-Type'] = 'text/html'
    elif change == 'declared_size':
        http['headers']['Content-Length'] = str(collector.MAX_BYTES + 1)
    elif change == 'stream_size':
        http['raw'] = b' ' * (collector.MAX_BYTES + 1)
    elif change == 'json':
        http['raw'] = b'<html>error</html>'
    elif change == 'shape':
        http['raw'] = b'{"result":{"data":{"report_list":[]}}}'
    else:
        http['timeout'] = True
    with pytest.raises((ValueError, requests.Timeout)):
        collect(tmp_path, allow_network=True)
    if change in {'json', 'shape'}:
        assert (tmp_path / 'runtime/income/sina-income.json').read_bytes() == http['raw']
        assert (tmp_path / 'runtime/income/acquisition.json').is_file()


def test_collector_path_escape_refused_before_request(tmp_path, http):
    with pytest.raises(ValueError, match='inside runtime'):
        collector.collect_sina_income_original(root=tmp_path, symbol='000001',
            output_dir=tmp_path / 'runtime/../../escape', allow_network=True)
    assert not http['calls']


@pytest.fixture
def queue_args(tmp_path):
    return _inputs(tmp_path, pending=True)


@pytest.fixture
def automatic(queue_args, income_inputs, registered_context, tmp_path, monkeypatch):
    official, points, pages = income_inputs
    official = replace(official, symbol='600001')
    pages[:] = [page.replace('600887', '600001') for page in pages]
    monkeypatch.setattr(adapter, 'extract_pages', lambda path, limit: pages[:limit])
    monkeypatch.setattr(batch, '_original', lambda *a, **kw:
        (tmp_path / official.path, datetime.fromisoformat(official.available_at), True))
    current = [dict(deepcopy(p), symbol='600001', source_name='CNINFO statutory disclosure')
               for p in points if p['period_label'] == official.period]
    current.append(dict(deepcopy(current[0]), field_name='interest_bearing_debt', value='80',
                        data_point_id='pending-debt', validation_status='pending'))
    base = tmp_path / 'runtime/automatic-base.json'
    base.write_text(json.dumps(dict(points=[], annual_points=current)), encoding='utf-8')
    args = dict(queue_args, financial_export_path=base, financial_export_sha256=sha256(base.read_bytes()).hexdigest())
    receipt = json.loads(args['receipt_path'].read_bytes())
    receipt['generated_at'] = datetime.now(timezone.utc).isoformat()
    args['receipt_path'].write_text(json.dumps(receipt), encoding='utf-8')
    args['receipt_sha256'] = sha256(args['receipt_path'].read_bytes()).hexdigest()
    args['report_path'] = tmp_path / 'runtime/automatic-report.json'
    publish_value_discovery_report(root=tmp_path, receipt_path=args['receipt_path'],
        receipt_sha256=args['receipt_sha256'], output_path=args['report_path'])
    args['report_sha256'] = sha256(args['report_path'].read_bytes()).hexdigest()
    queue = batch.build_value_research_priority_v2(**args)
    return args, queue, base.read_bytes()


def execute(automatic, *, allow_network=True):
    args, queue, _ = automatic
    repo, contexts, _ = batch.load_enrichment_research_contexts(root=args['root'], symbols=['600001'],
        evaluation_at=datetime.now(timezone.utc))
    return batch.execute_value_enrichment_batch(root=args['root'], queue=queue,
        financial_export_path=args['financial_export_path'], financial_export_sha256=args['financial_export_sha256'],
        output_dir=args['root'] / 'runtime/automatic-run', allow_network=allow_network, budget=1,
        repository=repo, research_contexts=contexts)


def test_worker_collects_prior_inputs_registers_and_replays(automatic, http):
    args, queue, original = automatic
    result = execute(automatic)
    item = result['items'][0]
    assert item['symbol'] == '600001' and len(http['calls']) == 1
    assert item['income_collection'] == dict(status='SOURCE_REPLAYED', added_input_count=2)
    assert len(item['adopted_fact_ids']) == 3
    binding = item['financial_export']
    payload = json.loads((args['root'] / binding['path']).read_bytes())
    assert payload['points'] == [] and len(payload['annual_points']) == 7
    assert args['financial_export_path'].read_bytes() == original
    summary = verify_enrichment_adoption(root=args['root'], result_binding=item['result_binding'],
        financial_export_path=args['root'] / binding['path'], financial_export_sha256=binding['sha256'],
        evaluation_at=datetime.now(timezone.utc))
    assert summary['adopted_fact_count'] == 3 and summary['research_inputs_updated']
    assert summary['quality_coverage_after'] == '0.3333'
    assert summary['new_fact_approvals'] == 0 and not summary['formal_eligibility']
    public = batch.read_verified_enrichment_progress(args['root'], '600001', datetime.now(timezone.utc))
    assert public['adopted_fact_count'] == 3
    _, contexts, diagnostics = batch.load_enrichment_research_contexts(root=args['root'], symbols=['600001'],
        evaluation_at=datetime.now(timezone.utc))
    assert diagnostics['600001']['status'] == 'VERIFIED_ENRICHMENT_CONTEXT_RESTORED'
    assert not contexts['600001']['facts'].verified
    assert contexts['600001']['case'].valuation_status == 'NOT_ASSESSED'
    consumption = json.loads((args['root'] / result['lawful_consumption_export']['path']).read_bytes())
    assert consumption['annual_points'] == payload['annual_points']
    base_points, _ = batch.load_retained_financial_export(args['financial_export_path'],
        evaluation_at=datetime.now(timezone.utc))
    _, _, restored, reuse = reuse_durable_income_export(root=args['root'],
        export=args['financial_export_path'], export_sha256=args['financial_export_sha256'],
        points=base_points, sources=payload['value_enrichment_sources'], symbols={'600001'},
        evaluation_at=datetime.now(timezone.utc))
    assert len(restored) == len(base_points) + 2 and len(reuse) == 1
    assert len(http['calls']) == 1
    secondary = next(p for p in payload['annual_points'] if p.get('metadata', {}).get('income_secondary'))
    raw = args['root'] / secondary['metadata']['income_secondary']['path']
    raw.write_bytes(raw.read_bytes() + b' ')
    assert batch.read_verified_enrichment_progress(args['root'], '600001', datetime.now(timezone.utc)) is None


@pytest.mark.parametrize('failure', ['offline', 'conflict', 'timeout'])
def test_worker_income_failure_keeps_only_official_adoption(automatic, http, failure):
    if failure == 'conflict':
        payload = reports()
        payload['result']['data']['report_list']['20241231']['data'][0]['item_value'] = '99'
        http['raw'] = json.dumps(payload).encode()
    elif failure == 'timeout':
        http['timeout'] = True
    result = execute(automatic, allow_network=failure != 'offline')
    item = result['items'][0]
    assert len(item['adopted_fact_ids']) == 1 and 'financial_export' not in item
    if failure == 'offline':
        assert not http['calls'] and 'income_collection' not in item
    else:
        assert item['income_collection']['status'] == 'UNAVAILABLE'
    assert result['new_fact_approvals'] == 0 and not result['formal_eligibility']


@pytest.mark.parametrize('budget', [1, 2, 3])
def test_worker_total_network_collection_respects_three_candidate_budget(flow, http, monkeypatch, budget):
    original = batch.enrich_retained_company
    discovery_calls = []
    def unavailable_original(**kwargs):
        discovery_calls.append(kwargs['symbol'])
        raise ValueError('TEST_ONLY_OFFICIAL_DISCOVERY_UNAVAILABLE')
    monkeypatch.setattr(batch, 'acquire_official_report', unavailable_original)
    def pending(*args, **kwargs):
        packet = original(*args, **kwargs)
        packet['sourced_arithmetic_points'] = [dict(field_name='revenue_yoy')]
        return packet
    monkeypatch.setattr(batch, 'enrich_retained_company', pending)
    args, queue, _ = flow
    result = batch.execute_value_enrichment_batch(root=args['root'], queue=queue,
        financial_export_path=args['financial_export_path'], financial_export_sha256=args['financial_export_sha256'],
        output_dir=args['root'] / 'runtime/bounded-three', allow_network=True, budget=budget)
    assert result['attempted_count'] == min(budget, len(queue['evidence_enrichment_work_queue']))
    # Missing URLs now trigger explicit bounded discovery, never real CI IO.
    assert len(http['calls']) == 1 <= result['attempted_count'] <= 3
    assert len(discovery_calls) + len(http['calls']) == result['attempted_count']
    assert result['items'][0]['income_collection']['status'] == 'UNAVAILABLE'
    assert all('TEST_ONLY_OFFICIAL_DISCOVERY_UNAVAILABLE' in item['reason']
               for item in result['items'][1:])


def test_default_context_reload_preserves_backoff_and_three_attempt_limit(automatic, http, monkeypatch):
    args, queue, _ = automatic
    root = args['root']
    clock = datetime.now(timezone.utc)
    http['timeout'] = True
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock
    monkeypatch.setattr(batch, 'datetime', Clock)
    restored_statuses = []
    def run(name):
        repository, contexts, diagnostics = batch.load_enrichment_research_contexts(root=root,
            symbols=['600001'], evaluation_at=clock)
        restored_statuses.append(diagnostics['600001']['status'])
        return batch.execute_value_enrichment_batch(root=root, queue=queue,
            financial_export_path=args['financial_export_path'], financial_export_sha256=args['financial_export_sha256'],
            output_dir=root / 'runtime' / name, allow_network=True, budget=1,
            repository=repository, research_contexts=contexts)
    attempts = []
    for cycle in range(6):
        outcome = run('reload-' + str(cycle))
        rows = [row for row in outcome['items'] if row['symbol'] == '600001']
        if cycle < 3:
            # Unattempted companies have a fair acquisition turn before retry.
            for peer in range(len(queue['evidence_enrichment_work_queue'])):
                if rows:
                    break
                outcome = run(f'reload-{cycle}-peer-{peer}')
                rows = [row for row in outcome['items'] if row['symbol'] == '600001']
            assert len(rows) == 1
            attempts.append(rows[0]['attempt'])
            assert rows[0]['retryable'] and len(rows[0]['adopted_fact_ids']) == 1
            assert rows[0]['research_registration_status'] == 'RESEARCH_INPUTS_UPDATED'
            public = batch.read_verified_enrichment_progress(root, '600001', clock)
            assert public['adopted_fact_count'] == 1 and not public['formal_eligibility']
        else:
            assert rows == []
            assert any(row['symbol'] == '600001' and row['attempt'] == 3
                       for row in outcome['skipped_unchanged'])
        call_count = len(http['calls'])
        clock += timedelta(seconds=1)
        immediate = run('backoff-' + str(cycle))
        assert all(row['symbol'] != '600001' for row in immediate['items'])
        assert len(http['calls']) == call_count
        clock += timedelta(minutes=10)
        if cycle == 2:
            clock += timedelta(days=1)
    assert attempts == [1, 2, 3] and len(http['calls']) == 3
    assert restored_statuses[0] == 'REGISTERED_CONTEXT_LOADED'
    assert all(status == 'VERIFIED_ENRICHMENT_CONTEXT_RESTORED' for status in restored_statuses[1:])
    checkpoints = [json.loads(path.read_bytes())['payload'] for path in
        (root / 'runtime/value-evidence-enrichment/progress-v1').glob('*.json')]
    adopted = [row for row in checkpoints if row.get('registered_adoption')]
    assert len({row['key'] for row in adopted}) == 1
    assert sorted(row['attempt'] for row in adopted) == [1, 2, 3]
    # A genuinely rebound registered input must reopen, unlike worker output.
    workbench = root / 'runtime/workbench.json'
    payload = json.loads(workbench.read_bytes())
    payload['registered_model_revision'] = 'TEST_ONLY new registered source version'
    workbench.write_text(json.dumps(payload), encoding='utf-8')
    registry = root / 'config/current-agent-research.json'
    payload = json.loads(registry.read_bytes())
    payload['cases']['600001']['workflows']['financial']['workbench']['sha256'] = sha256(workbench.read_bytes()).hexdigest()
    registry.write_text(json.dumps(payload), encoding='utf-8')
    reopened = run('registered-baseline-changed')
    row = next(row for row in reopened['items'] if row['symbol'] == '600001')
    assert row['attempt'] == 1 and len(http['calls']) == 4


def test_caller_context_drift_cannot_reopen_or_supply_registration(automatic, http):
    args, queue, _ = automatic
    root = args['root']
    repository, contexts, _ = batch.load_enrichment_research_contexts(root=root,
        symbols=['600001'], evaluation_at=datetime.now(timezone.utc))
    contexts['600001']['case'] = replace(contexts['600001']['case'], thesis='UNREGISTERED CALLER DRIFT')
    with pytest.raises(ValueError, match='differs from verified registered inputs'):
        batch.execute_value_enrichment_batch(root=root, queue=queue,
            financial_export_path=args['financial_export_path'], financial_export_sha256=args['financial_export_sha256'],
            output_dir=root / 'runtime/caller-drift', allow_network=True, budget=1,
            repository=repository, research_contexts=contexts)
    assert not http['calls'] and not (root / 'runtime/caller-drift').exists()
