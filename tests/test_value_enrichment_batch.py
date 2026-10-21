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
