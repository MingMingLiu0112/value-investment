"""TEST_ONLY flow tests; fake downloads never become admitted financial facts."""
from copy import deepcopy
from hashlib import sha256
import json

import pytest

from test_value_research_priority_v2 import _inputs
from value_investment_agent.application.research import value_enrichment_batch as batch


@pytest.fixture
def flow(tmp_path, monkeypatch):
    args = _inputs(tmp_path, pending=True)
    raw = b'%PDF-TEST_ONLY-original'
    payload = json.loads(args['financial_export_path'].read_bytes())
    for row in payload['annual_points']:
        row.update(source_name='CNINFO statutory disclosure', sha256=sha256(raw).hexdigest(),
            source_url='https://static.cninfo.com.cn/finalpage/2026-03-31/123456.PDF')
    supplement = tmp_path / 'runtime/supplement.json'
    supplement.write_text(json.dumps(payload), encoding='utf-8')
    args.update(financial_export_path=supplement, financial_export_sha256=sha256(supplement.read_bytes()).hexdigest())
    queue = batch.build_value_research_priority_v2(**args)
    calls = []
    def download(url, path):
        calls.append(url)
        path.write_bytes(raw)
        return sha256(raw).hexdigest()
    monkeypatch.setattr(batch, 'download_official_pdf', download)
    monkeypatch.setattr(batch, 'validate_pdf_original', lambda path: None)
    def extract(root, source, points, **kwargs):
        return {'state': 'DATA_UNAVAILABLE', 'source_extraction': {'page_texts': ['TEST_ONLY']},
            'candidate_matches': [], 'before': {'quality_status': 'missing'},
            'after': {'quality_status': 'missing'}, 'debt_scope': {'status': 'DATA_GAP'},
            'next_action': 'VERIFY_MISSING_FACTS'}
    monkeypatch.setattr(batch, 'enrich_retained_company', extract)
    return args, queue, calls


def run(flow, folder, **kwargs):
    args, queue, _ = flow
    return batch.execute_value_enrichment_batch(root=args['root'], queue=queue,
        financial_export_path=args['financial_export_path'], financial_export_sha256=args['financial_export_sha256'],
        output_dir=args['root'] / 'runtime' / folder, budget=1, **kwargs)


def test_explicit_network_and_reuse_do_not_grant_approval(flow):
    denied = run(flow, 'offline')
    assert denied['items'][0]['state'] == 'DATA_UNAVAILABLE'
    assert 'NETWORK_NOT_AUTHORIZED' in denied['items'][0]['reason']
    assert not flow[2]
    first = run(flow, 'first', allow_network=True)
    second = run(flow, 'second')
    assert len(flow[2]) == 1
    assert not first['items'][0]['source_reused'] and second['items'][0]['source_reused']
    assert 'QUALITY_REEVALUATED' in first['items'][0]['transitions']
    assert first['new_fact_approvals'] == 0 and first['formal_eligibility'] is False
    assert (flow[0]['root'] / 'runtime/first/execution.json').is_file()


def test_tampered_financial_export_rejected_before_download(flow):
    args, _, calls = flow
    args['financial_export_path'].write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='hash mismatch'):
        run(flow, 'bad', allow_network=True)
    assert not calls


def test_rehashed_forged_queue_cannot_change_selected_company(flow):
    _, queue, calls = flow
    queue['evidence_enrichment_work_queue'][0]['company_name'] = 'FORGED'
    queue['content_sha256'] = batch._canonical_hash({k: v for k, v in queue.items() if k != 'content_sha256'})
    with pytest.raises(ValueError, match='replayed bound inputs'):
        run(flow, 'bad', allow_network=True)
    assert not calls


def test_corrupt_original_cache_is_not_silently_redownloaded(flow):
    run(flow, 'first', allow_network=True)
    cache = flow[0]['root'] / 'runtime/value-evidence-enrichment/originals'
    next(cache.glob('*.pdf')).write_bytes(b'corrupt')
    second = run(flow, 'second', allow_network=True)
    assert 'CACHE_HASH_MISMATCH' in second['items'][0]['reason']
    assert len(flow[2]) == 1


def test_same_output_and_invalid_budget_cannot_overwrite(flow):
    run(flow, 'first')
    with pytest.raises(FileExistsError):
        run(flow, 'first')
    args, queue, _ = flow
    with pytest.raises(ValueError, match='budget'):
        batch.execute_value_enrichment_batch(root=args['root'], queue=queue,
            financial_export_path=args['financial_export_path'], financial_export_sha256=args['financial_export_sha256'],
            output_dir=args['root'] / 'runtime/invalid', budget=100)


def test_restart_advances_beyond_attempted_head(flow):
    first = run(flow, 'progress-first')
    second = run(flow, 'progress-second')
    assert first['items'][0]['symbol'] != second['items'][0]['symbol']


def test_unchanged_exhausted_queue_is_idempotent(flow):
    seen = []
    for index in range(len(flow[1]['evidence_enrichment_work_queue']) + 1):
        result = run(flow, 'exhaust-' + str(index))
        seen.extend(row['symbol'] for row in result['items'])
    assert len(seen) == len(set(seen))
    assert result['attempted_count'] == 0
    assert result['status'] == 'COMPLETED_WITH_GAPS'
    assert all(row['last_state'] == 'DATA_UNAVAILABLE' and row['next_action']
               for row in result['skipped_unchanged'])


def test_explicit_reopen_preserves_previous_receipt(flow):
    first = run(flow, 'reopen-first')
    original = (flow[0]['root'] / 'runtime/reopen-first/execution.json').read_bytes()
    reopened = run(flow, 'reopen-second', retry_token='official-source-review-corrected-v2')
    assert reopened['items'][0]['symbol'] == first['items'][0]['symbol']
    assert original == (flow[0]['root'] / 'runtime/reopen-first/execution.json').read_bytes()


def test_transient_failure_retries_with_backoff_and_stops_at_three(flow, monkeypatch):
    from datetime import datetime, timedelta, timezone
    clock = datetime.now(timezone.utc)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock
    monkeypatch.setattr(batch, 'datetime', Clock)
    monkeypatch.setattr(batch, '_original', lambda *a, **kw: (_ for _ in ()).throw(TimeoutError('TEST_ONLY timeout')))
    first = run(flow, 'retry-first')
    assert first['items'][0]['retryable'] is True
    immediate = run(flow, 'retry-immediate')
    assert immediate['items'][0]['symbol'] != first['items'][0]['symbol']
    for attempt in (2, 3):
        clock += timedelta(minutes=10)
        result = run(flow, 'retry-' + str(attempt))
        assert result['items'][0]['symbol'] == first['items'][0]['symbol']
        assert result['items'][0]['attempt'] == attempt
    clock += timedelta(minutes=10)
    exhausted = run(flow, 'retry-exhausted')
    assert all(row['symbol'] != first['items'][0]['symbol'] for row in exhausted['items'])


def test_checkpoint_tampering_fails_closed(flow):
    run(flow, 'checkpoint-first')
    path = next((flow[0]['root'] / 'runtime/value-evidence-enrichment/progress-v1').glob('*.json'))
    envelope = json.loads(path.read_bytes())
    envelope['payload']['retryable'] = True
    path.write_text(json.dumps(envelope), encoding='utf-8')
    with pytest.raises(ValueError, match='integrity mismatch'):
        run(flow, 'checkpoint-tampered')


def test_evidence_revision_reopens(flow):
    args, _, _ = flow
    first = run(flow, 'revision-first')
    payload = json.loads(args['financial_export_path'].read_bytes())
    for row in payload['annual_points']:
        if row['symbol'] == first['items'][0]['symbol']:
            row['metadata']['review_revision'] = 'new-source-review'
    args['financial_export_path'].write_text(json.dumps(payload), encoding='utf-8')
    args['financial_export_sha256'] = sha256(args['financial_export_path'].read_bytes()).hexdigest()
    queue = batch.build_value_research_priority_v2(**args)
    revised = (args, queue, flow[2])
    result = run(revised, 'revision-second')
    assert result['items'][0]['symbol'] == first['items'][0]['symbol']


def test_interruption_after_checkpoint_resumes_next_company(flow, monkeypatch):
    write = batch.write_new_json
    def interrupt(path, payload):
        if path.name == 'execution.json':
            raise KeyboardInterrupt('TEST_ONLY crash after issuer checkpoint')
        write(path, payload)
    monkeypatch.setattr(batch, 'write_new_json', interrupt)
    with pytest.raises(KeyboardInterrupt):
        run(flow, 'crashed')
    monkeypatch.setattr(batch, 'write_new_json', write)
    resumed = run(flow, 'resumed')
    attempted = json.loads(next((flow[0]['root'] / 'runtime/crashed').glob('*-attempt.json')).read_bytes())
    assert resumed['items'][0]['symbol'] != attempted['symbol']


def test_progress_lock_rejects_concurrent_writer_and_releases(flow):
    from value_investment_agent.infrastructure.screening.value_enrichment_progress import ValueEnrichmentProgress
    progress = ValueEnrichmentProgress(flow[0]['root'])
    with progress.locked():
        with pytest.raises(OSError):
            run(flow, 'concurrent')
    assert run(flow, 'after-release')['attempted_count'] == 1


def test_changed_original_reopens_previously_completed_evidence(flow):
    run(flow, 'cached-first', allow_network=True)
    run(flow, 'cached-offline')
    cache = flow[0]['root'] / 'runtime/value-evidence-enrichment/originals'
    next(cache.glob('*.pdf')).write_bytes(b'changed original')
    result = run(flow, 'cached-changed')
    assert 'CACHE_HASH_MISMATCH' in result['items'][0]['reason']
    assert len(flow[2]) == 1


def test_research_context_requires_repository_before_any_acquisition(flow):
    with pytest.raises(ValueError, match='explicit artifact repository'):
        run(flow, 'no-repository', allow_network=True,
            research_contexts={'600001': {'case': None, 'facts': None}})
    assert not flow[2]


@pytest.fixture
def registered_context(tmp_path):
    from datetime import datetime, timezone
    from value_investment_agent.research_case import ResearchCase
    from value_investment_agent.valuation_models.fcff import FinancialFacts
    from value_investment_agent.research_artifact_repository import InMemoryResearchArtifactRepository
    from value_investment_agent.research_artifacts import ResearchArtifactIdentity
    from value_investment_agent.application.decision.artifact_bundle import export_artifact_bundle
    now = datetime(2026, 10, 20, tzinfo=timezone.utc)
    case = ResearchCase(symbol='600001', name='TEST_ONLY', as_of=now.date(),
        generated_at=now, run_id='test', research_version='test-v1', industry='TEST_ONLY',
        investment_path='UNASSESSED', thesis='TEST_ONLY', return_driver='UNASSESSED',
        mispricing_hypothesis='UNASSESSED', financial_summary={}, positives=[], counter_evidence=[],
        thesis_breakers=[], next_events=[], evidence_status='PARTIAL', valuation_status='NOT_ASSESSED',
        research_status='DATA_CHECK', blockers=['MISSING_ECONOMIC_INPUTS'], evidence_refs=[],
        quote_date=None, financial_period=now.date(),
        missing_date_reasons={'quote_date': 'TEST_ONLY'})
    facts = FinancialFacts(case.symbol, now.date(), False, [], ['MISSING_ECONOMIC_INPUTS'])
    repo = InMemoryResearchArtifactRepository()
    artifacts = [repo.save_object(obj, identity=ResearchArtifactIdentity('security', case.symbol,
        kind, 'c3-v1', now.date(), now), evidence_refs=[], run_id='test', advance_head=False)
        for obj, kind in [(case, 'research_case'), (facts, 'financial_facts')]]
    path = tmp_path / 'runtime/workbench.json'
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({'artifact_bundle': export_artifact_bundle(artifacts)}), encoding='utf-8')
    config = tmp_path / 'config'
    config.mkdir(exist_ok=True)
    registry = {'cases': {case.symbol: {'workflows': {'financial': {'workbench': {
        'path': 'runtime/workbench.json', 'sha256': sha256(path.read_bytes()).hexdigest()},
        'packet': {'path': 'NEVER_READ_MOCK_PACKET'}}}}}}
    (config / 'current-agent-research.json').write_text(json.dumps(registry), encoding='utf-8')
    return now, path


def test_context_loader_reuses_bound_types_and_fails_closed_per_symbol(tmp_path, registered_context):
    from datetime import timedelta
    now, path = registered_context
    _, contexts, diagnostics = batch.load_enrichment_research_contexts(root=tmp_path,
        symbols=['600001', '000589'], evaluation_at=now + timedelta(days=1))
    assert contexts['600001']['case'].as_of == (now + timedelta(days=1)).date()
    assert not contexts['600001']['facts'].verified
    assert diagnostics['000589']['status'] == 'NO_USABLE_REGISTERED_RESEARCH_CONTEXT'
    _, future, _ = batch.load_enrichment_research_contexts(root=tmp_path,
        symbols=['600001'], evaluation_at=now-timedelta(days=1))
    assert not future
    path.write_text('{}', encoding='utf-8')
    _, corrupt, status = batch.load_enrichment_research_contexts(root=tmp_path,
        symbols=['600001'], evaluation_at=now)
    assert not corrupt and 'hash mismatch' in status['600001']['reason']


def test_queue_cli_wires_loaded_repository_and_contexts(flow, registered_context, monkeypatch, capsys):
    import importlib.util
    from pathlib import Path
    import sys
    from value_investment_agent.application.research import value_research_priority_v2 as priority
    args, queue, _ = flow
    script = Path(__file__).resolve().parents[1] / 'scripts/current/build_value_research_queue.py'
    spec = importlib.util.spec_from_file_location('test_value_queue_cli', script)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    monkeypatch.setattr(cli, 'ROOT', args['root'])
    monkeypatch.setattr(priority, 'build_value_research_priority_v2', lambda **kw: queue)
    calls = []
    def execute(**kw):
        calls.append(kw)
        assert '600001' in kw['research_contexts'] and kw['repository'] is not None
        kw['output_dir'].mkdir()
        (kw['output_dir'] / 'execution.json').write_text('{}', encoding='utf-8')
        return dict(status='COMPLETED', attempted_count=0)
    monkeypatch.setattr(batch, 'execute_value_enrichment_batch', execute)
    monkeypatch.setattr(sys, 'argv', [str(script), '--report', 'runtime/report.json',
        '--report-sha256', 'a'*64, '--receipt', 'runtime/receipt.json', '--receipt-sha256', 'b'*64,
        '--priority-version', 'v2', '--financial-export', str(args['financial_export_path']),
        '--financial-export-sha256', args['financial_export_sha256'],
        '--execute-enrichment', '--output', 'runtime/cli-queue.json'])
    assert cli.main() == 0 and len(calls) == 1
    assert 'REGISTERED_CONTEXT_LOADED' in capsys.readouterr().out
