"""Exact issuer originals consumed by pending models, without admission."""
from copy import deepcopy
import json

import pytest

pytestmark = pytest.mark.usefixtures('synthetic_pending_candidate_clock')

from test_financial_review_attachment import package, _pin
from test_financial_valuation_rebase import fixture_rebase
from test_pending_research_candidate import candidate_inputs, run
from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.application.product.pending_research_candidate import (
    verify_pending_research_candidate,
)
from value_investment_agent.application.product.decision_surface import (
    verify_current_decision_workbench,
)
from value_investment_agent.research_artifact_codecs import artifact_payload


def _write(path, value):
    path.write_text(json.dumps(value), encoding='utf-8')


@pytest.fixture
def indexed_candidate(package, monkeypatch):
    root, spec, _ = fixture_rebase(package, monkeypatch)
    _, supplement, manifest = package
    original = supplement['source_bindings'][0]
    # Retain the fixture's absolute paths, matching the actual Yili supplement.
    for number in range(12346, 12352):
        path = root / f'{number}.pdf'
        path.write_bytes(f'%PDF-1.4\nsynthetic retained original {number}\n'.encode('ascii'))
        binding = deepcopy(original)
        binding.update(id=f'cninfo:{number}', path=str(path), sha256=sha256_file(path),
            source_url=f'https://static.cninfo.com.cn/finalpage/2025-05-01/{number}.PDF')
        supplement['source_bindings'].append(binding)
    annual = supplement['source_bindings'][1]
    supplement['facts'][0].update(source_id=annual['id'], source_binding=deepcopy(annual))
    manifest['source_bindings'] = deepcopy(supplement['source_bindings'])
    spec['manifest_sha256'] = _pin(package)['manifest_sha256']
    package_path, policy_path, request = candidate_inputs(root)
    source = json.loads(package_path.read_text(encoding='utf-8'))
    rows = [dict(secCode=source['symbol'], secName=source['name'], orgId='gssh0600887',
        announcementId=binding['id'].split(':')[1],
        adjunctUrl=binding['source_url'].removeprefix('https://static.cninfo.com.cn/'))
        for binding in (original, annual)]
    index_path = root / 'issuer-index.json'
    _write(index_path, dict(announcements=rows))
    policy = json.loads(policy_path.read_text(encoding='utf-8'))
    policy.update(financial_rebase=spec,
        issuer_index_bindings=[dict(path='issuer-index.json', sha256=sha256_file(index_path))],
        scenario_conditions={name: dict(cost_of_equity='0.09', retention='0.15', terminal_growth='0')
            for name in ('bear', 'base', 'bull')})
    _write(policy_path, policy)
    return root, package_path, policy_path, request, index_path, supplement


def test_only_two_consumed_originals_replace_legacy_facts_refs(indexed_candidate):
    root, package_path, policy_path, request, _, supplement = indexed_candidate
    result = run(root, package_path, policy_path, request)
    candidate = json.loads((root / 'runtime/pending/package.json').read_text(encoding='utf-8'))
    catalog = {source['id']: source for source in candidate['sources']}
    refs = candidate['facts']['evidence_refs']
    expected = {binding['id'] for binding in supplement['source_bindings'][:2]}
    assert {ref['id'] for ref in refs} == expected | {'pending-economic-proposal'}
    assert 'facts' in catalog
    for ref in refs:
        assert ref['path'] == catalog[ref['id']]['local_path']
        assert ref['sha256'] == catalog[ref['id']]['sha256']
    for binding in supplement['source_bindings'][2:]:
        assert binding['id'] in catalog
        assert catalog[binding['id']]['issuer_identity'] is None
        assert catalog[binding['id']]['sha256'] == binding['sha256']
    work = json.loads((root / 'runtime/pending/workbench.json').read_text(encoding='utf-8'))
    objects = verify_current_decision_workbench(work).dependency_objects
    consumed = artifact_payload(objects['financial_facts'])[1]
    assert consumed['evidence_refs'] == refs
    assert consumed['operating_inputs']['start_book_equity'] == '1000'
    assert candidate['research_case']['financial_summary']['ttm_ex_nonrecurring_parent_profit_cny'] == '220'
    assert result['model_context_scope'] == 'ACTUALLY_CONSUMED'
    assert result['approval_changed'] is result['research_admitted'] is result['price_admitted'] is False
    assert candidate['quote'] is None
    assert candidate['model_validity_input']['events'] == []
    receipt = root / 'runtime/pending/candidate.json'
    verify_pending_research_candidate(root=root, path=receipt, expected_sha256=sha256_file(receipt))


@pytest.mark.parametrize('change', ['url', 'security-code'])
def test_wrong_index_mapping_cannot_create_candidate_admission(indexed_candidate, change):
    root, package_path, policy_path, request, index_path, _ = indexed_candidate
    index = json.loads(index_path.read_text(encoding='utf-8'))
    row = index['announcements'][0]
    if change == 'url':
        row['adjunctUrl'] = row['adjunctUrl'].replace('2025-05-01', '2025-05-02')
    else:
        row['secCode'] = '600519'
    _write(index_path, index)
    policy = json.loads(policy_path.read_text(encoding='utf-8'))
    policy['issuer_index_bindings'][0]['sha256'] = sha256_file(index_path)
    _write(policy_path, policy)
    with pytest.raises(ValueError, match='exact official issuer index bindings'):
        run(root, package_path, policy_path, request)
    assert not (root / 'runtime/pending/candidate.json').exists()


@pytest.mark.parametrize('stage', ['before', 'after'])
def test_identity_index_byte_drift_is_rejected(indexed_candidate, stage):
    root, package_path, policy_path, request, index_path, _ = indexed_candidate
    if stage == 'after':
        run(root, package_path, policy_path, request)
    index = json.loads(index_path.read_text(encoding='utf-8'))
    index['announcements'][0]['orgId'] = 'different-issuer'
    _write(index_path, index)
    if stage == 'before':
        with pytest.raises(ValueError, match='issuer index hash mismatch'):
            run(root, package_path, policy_path, request)
        assert not (root / 'runtime/pending/candidate.json').exists()
    else:
        receipt = root / 'runtime/pending/candidate.json'
        with pytest.raises(ValueError, match='source drift'):
            verify_pending_research_candidate(root=root, path=receipt,
                expected_sha256=sha256_file(receipt))


def test_unconsumed_original_remains_hash_bound_lineage(indexed_candidate):
    root, package_path, policy_path, request, _, supplement = indexed_candidate
    run(root, package_path, policy_path, request)
    from pathlib import Path
    Path(supplement['source_bindings'][-1]['path']).write_bytes(b'drift')
    receipt = root / 'runtime/pending/candidate.json'
    with pytest.raises(ValueError, match='source drift'):
        verify_pending_research_candidate(root=root, path=receipt,
            expected_sha256=sha256_file(receipt))


@pytest.mark.parametrize('identical', [True, False])
def test_legacy_alias_requires_exact_original_bytes_and_keeps_blockers(indexed_candidate, identical):
    root, package_path, policy_path, request, _, supplement = indexed_candidate
    source = json.loads(package_path.read_text(encoding='utf-8'))
    original = supplement['source_bindings'][0]
    alias_path = root / 'runtime/legacy-h1.pdf'
    from pathlib import Path
    alias_path.write_bytes(Path(original['path']).read_bytes() if identical else b'%PDF-1.4\nother\n')
    alias = dict(id='legacy-h1', kind='official_issuer_filing',
        location='runtime/legacy-h1.pdf', local_path='runtime/legacy-h1.pdf',
        sha256=sha256_file(alias_path), published_at='2025-05-01T00:00:00+08:00')
    source['sources'].append(alias)
    source['research_case']['evidence_refs'].append(dict(id=alias['id'],
        path=alias['local_path'], sha256=alias['sha256']))
    source['research_case']['next_events'].append(dict(kind='fact',
        text='Retained issuer event requires exact original identity.', evidence_refs=[alias['id']]))
    _write(package_path, source)
    before = package_path.read_bytes()
    policy = json.loads(policy_path.read_text(encoding='utf-8'))
    policy['source_package_sha256'] = sha256_file(package_path)
    _write(policy_path, policy)
    result = run(root, package_path, policy_path, request)
    candidate = json.loads((root / 'runtime/pending/package.json').read_text(encoding='utf-8'))
    actual = next(item for item in candidate['sources'] if item['id'] == 'legacy-h1')
    assert package_path.read_bytes() == before
    assert actual['sha256'] == alias['sha256']
    assert actual['local_path'] == alias['local_path']
    if identical:
        assert actual['location'] == original['source_url']
        assert actual['issuer_identity']['security_code'] == source['symbol']
        assert actual['identity_basis'] == 'exact_announcement_index_and_identical_retained_pdf_bytes'
        assert result['model_context_scope'] == 'ACTUALLY_CONSUMED'
    else:
        assert actual['location'] == alias['location']
        assert not actual.get('issuer_identity')
        assert result['candidate_valuation']['status'] == 'not_ready'
        assert result['candidate_valuation']['base_value'] is None
        assert any('event_scope' in blocker for blocker in result['research_blockers'])
    assert 'legacy-h1' not in {ref['id'] for ref in candidate['facts']['evidence_refs']}
    assert set(source['research_case']['blockers']) <= set(candidate['research_case']['blockers'])
    assert 'pending_complete_event_materiality_review' in candidate['model_validity_input']['blockers']
