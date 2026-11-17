"""Direct unsigned materiality dispatch tests; real originals are read-only.

Set MATERIALITY_V4_REAL_REQUIRED=1 to require the retained 600519 window.
MATERIALITY_V4_REAL_ROOT may point at a separate retained-public-originals root;
the application imports always come from the checkout running pytest.
"""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path

import pytest

from test_d2_conditional_shared_service import synthetic_chain
from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.application.product.research_materiality_reviews import (
    build_materiality_review_descriptor, prepare_materiality_review_handoff,
)
from value_investment_agent.application.product.research_reviews import build_research_review_model_context
from value_investment_agent.application.research.v4_input_adapter import (
    RETENTION_CONTRACT, build_descriptor_for_package,
)
from value_investment_agent.m1_valuation_package_builder import build_descriptor
from value_investment_agent.research_input import build_research_run_spec
from value_investment_agent.research_run_contract import canonical_contract_payload


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = '97a83c496feab701fe3f4718d8c09535ce18226729210bc2deac5f625f930086'
WINDOW = 'runtime/value-alignment-event-observation/20261030T034906348838Z'


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def binding(root, path):
    return dict(path=path.relative_to(root).as_posix(), sha256=sha256_file(path))


def refs(value):
    if isinstance(value, dict):
        if 'path' in value and 'sha256' in value:
            yield value
        for child in value.values():
            yield from refs(child)
    elif isinstance(value, list):
        for child in value:
            yield from refs(child)


def prepare(root, package_ref, scan_ref):
    return prepare_materiality_review_handoff(
        root=root, package_path=root / package_ref['path'],
        package_sha256=package_ref['sha256'], scan_path=root / scan_ref['path'],
        scan_sha256=scan_ref['sha256'])


def assert_unsigned(handoff):
    assert handoff['action'] == 'no_order'
    assert 'signature' not in handoff
    response = handoff['unsigned_response']
    assert 'signature' not in response
    assert response['reviewer_id'] is response['reviewed_at'] is None
    assert response['model_context'] == handoff['model_context']
    draft = response['event_materiality']
    assert draft['model_context'] == handoff['model_context']
    assert draft['review_id'] is draft['reviewer_id'] is draft['reviewed_at'] is None
    assert len(draft['decisions']) == len(handoff['announcements']) > 0
    for decision in draft['decisions']:
        for key in ('human_decision', 'reviewer_id', 'reviewed_at',
                    'requires_recalculation', 'requires_model_stale', 'requires_followup'):
            assert decision[key] is None


@pytest.mark.parametrize('contract', ['annual-retention-v3', None])
def test_mixed_terminal_contract_rejected_directly(synthetic_chain, contract):
    root, package_path, *_ = synthetic_chain
    package = load(package_path)
    package['facts']['scenario_inputs'] = {
        'bear': {'retention_contract': RETENTION_CONTRACT},
        'base': {'retention_contract': contract},
        'bull': {'retention_contract': RETENTION_CONTRACT},
    }
    # Only synthetic bytes are changed; no real candidate or source is touched.
    package_path.write_text(json.dumps(package), encoding='utf-8')
    with pytest.raises(ValueError, match='mixed terminal scenario contracts'):
        prepare(root, binding(root, package_path), binding(root, root / 'synthetic-scan.json'))


def test_legacy_materiality_keeps_descriptor_and_context(synthetic_chain):
    root, package_path, *_ = synthetic_chain
    before = package_path.read_bytes()
    original = build_descriptor(load(package_path), root=root)
    package_ref = binding(root, package_path)
    scan_ref = binding(root, root / 'synthetic-scan.json')
    effective = build_materiality_review_descriptor(
        root=root, package_binding=package_ref, scan_binding=scan_ref)
    assert effective.as_policy() == original.as_policy()
    handoff = prepare(root, package_ref, scan_ref)
    assert handoff['model_context'] == build_research_review_model_context(
        descriptor=original, spec=build_research_run_spec(original))
    assert 'terminal_contract_version' not in handoff['model_context']
    assert_unsigned(handoff)
    assert package_path.read_bytes() == before


@pytest.fixture
def real_inputs():
    if os.environ.get('MATERIALITY_V4_REAL_REQUIRED') != '1':
        pytest.skip('opt in with MATERIALITY_V4_REAL_REQUIRED=1; retained runtime required')
    root = Path(os.environ.get('MATERIALITY_V4_REAL_ROOT', str(ROOT))).resolve()
    config_path = root / f'config/pending-candidate-alignments-v1/{CANDIDATE}.json'
    assert config_path.is_file(), f'required real materiality config unavailable: {config_path}'
    config = load(config_path)
    candidate_ref = config['candidate_binding']
    assert candidate_ref['sha256'] == CANDIDATE
    candidate_path = root / candidate_ref['path']
    assert sha256_file(candidate_path) == CANDIDATE
    candidate = load(candidate_path)
    package_name = (Path(candidate_ref['path']).parent / 'package.json').as_posix()
    package_refs = [ref for ref in refs(candidate) if ref['path'] == package_name]
    assert package_refs and all(ref == package_refs[0] for ref in package_refs)
    package_ref = package_refs[0]
    observation_refs = [ref for ref in config['event_observation_bindings']
                        if ref['path'] == WINDOW + '/observation.json']
    assert len(observation_refs) == 1
    observation = load(root / observation_refs[0]['path'])
    assert observation['full_calendar_window_elapsed'] is True
    assert observation['pagination_complete'] is True
    assert observation['materiality_approved'] is False
    package = load(root / package_ref['path'])
    scan_ref = observation['scan_binding']
    scan = load(root / scan_ref['path'])
    originals = [candidate_ref, package_ref, observation_refs[0], scan_ref,
                 *observation['source_bindings'], *refs(scan)]
    originals += [dict(path=s['local_path'], sha256=s['sha256']) for s in package['sources']]
    snapshot = {ref['path']: ref['sha256'] for ref in originals}
    snapshot[config_path.relative_to(root).as_posix()] = sha256_file(config_path)
    for path, digest in snapshot.items():
        assert sha256_file(root / path) == digest
    try:
        yield root, package_ref, scan_ref, package, observation
    finally:
        for path, digest in snapshot.items():
            assert sha256_file(root / path) == digest, f'original modified: {path}'


def test_real_600519_full_window_unsigned_v4_and_source_isolation(real_inputs):
    root, package_ref, scan_ref, package, observation = real_inputs
    original = build_descriptor_for_package(deepcopy(package), root=root)
    effective = build_materiality_review_descriptor(
        root=root, package_binding=package_ref, scan_binding=scan_ref)
    old, new = original.as_policy(), effective.as_policy()
    for key in old.keys() - {'input_sha256', 'model_validity_input'}:
        assert new[key] == old[key], key
    assert effective.point_in_time == original.point_in_time
    assert effective.input_sha256 != original.input_sha256
    assert effective.sources == original.sources
    event_paths = {ref['path'] for ref in observation['source_bindings']}
    old_paths = {source['local_path'] for source in package['sources']}
    fresh_paths = event_paths - old_paths
    assert fresh_paths, 'window must contain genuinely new retained sources'
    for path in fresh_paths:
        assert path not in canonical_contract_payload(new['facts'])
        assert path not in canonical_contract_payload({'sources': new['sources']})
    handoff = prepare(root, package_ref, scan_ref)
    assert_unsigned(handoff)
    assert handoff['symbol'] == '600519'
    assert handoff['package_binding'] == package_ref
    assert handoff['scan_binding'] == scan_ref
    assert handoff['scan_window']['scan_from'] == '2026-06-30'
    assert handoff['scan_window']['scan_to'] == '2026-10-29'
    assert len(handoff['announcements']) == observation['announcement_count'] == 7
    context = handoff['model_context']
    assert context['model_version'] == 'residual-income-equity-path-v4'
    assert context['terminal_contract_version'] == 'terminal-economic-contract-v2'
    assert context['research_as_of'] == package['point_in_time']['research_as_of']
    assert context['input_descriptor_sha256'] == effective.input_sha256
    facts = deepcopy(new['facts'])
    assert context['facts_sha256'] == sha256(canonical_contract_payload(facts).encode('utf-8')).hexdigest()
    for scenario in facts['scenario_inputs'].values():
        assert scenario['terminal_economic_contract']['contract_version'] == 'terminal-economic-contract-v2'
    facts['scenario_inputs']['base']['terminal_economic_contract']['rationale'] += ' TEST_ONLY'
    assert context['facts_sha256'] != sha256(canonical_contract_payload(facts).encode('utf-8')).hexdigest()
