"""Synthetic adapter contracts; tests do not confer personal eligibility."""
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from test_pending_research_candidate import candidate_inputs, run
from value_investment_agent.application.product import pending_candidate_supplement as supplement
from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.application.product.research_reviews import (
    prepare_pending_review_intake, prepare_pending_review_response,
)


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')


def bind(root, path):
    return dict(path=path.relative_to(root).as_posix(), sha256=sha256_file(path))


@pytest.fixture
def registered(tmp_path, synthetic_pending_candidate_clock):
    implementation = tmp_path / supplement.GENERATOR
    implementation.parent.mkdir(parents=True)
    implementation.write_bytes((Path(__file__).resolve().parents[1] / supplement.GENERATOR).read_bytes())
    package, policy, request = candidate_inputs(tmp_path)
    data = json.loads(policy.read_bytes())
    data['human_review_groups'] = [dict(id='ECONOMICS', question='Does profitability persist?',
        support='Synthetic inputs.', countercase='Persistence unproven.', impact='Pending only.',
        field_paths=['facts.scenario_inputs'])]
    write(policy, data)
    run(tmp_path, package, policy, request)
    candidate = tmp_path / 'runtime/pending/candidate.json'
    symbol = json.loads(candidate.read_bytes())['symbol']
    workflow = tmp_path / supplement.WORKFLOW_PATH
    write(workflow, dict(schema_version='user-research-workflow-v1', action='no_order',
        supplemental_review_candidates={symbol: bind(tmp_path, candidate)},
        review_candidates={symbol: dict(path='runtime/should-not-fallback.json', sha256='0' * 64)}))
    return tmp_path, symbol, candidate, workflow


def load(registered):
    root, symbol, _, _ = registered
    return supplement.load_current_pending_candidate_supplement(root=root, symbol=symbol)


def rebind_candidate(registered, candidate):
    root, symbol, path, workflow = registered
    write(path, candidate)
    registry = json.loads(workflow.read_bytes())
    registry['supplemental_review_candidates'][symbol] = bind(root, path)
    write(workflow, registry)


def test_consumed_packet_exact_bindings_and_existing_unsigned_signature_contract(registered):
    root, symbol, path, workflow = registered
    before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
    result = load(registered)
    assert result['mode'] == 'REGISTERED_NEW_INPUT_CANDIDATE'
    assert result['scope'] == 'UNADMITTED_WEB_RESEARCH_SUPPLEMENT_ONLY'
    assert result['registry_binding'] == bind(root, workflow)
    assert result['candidate_binding'] == bind(root, path)
    assert result['candidate'] == json.loads(path.read_bytes())
    assert result['model_context'] == result['candidate']['model_context']
    for role, name in (('package', 'package.json'), ('workbench', 'workbench.json'),
                       ('review_packet', 'consumed-review.json')):
        assert result[role + '_binding'] == bind(root, path.parent / name)
    assert not {'publication', 'publication_binding', 'replay_publication_binding'}.intersection(result)
    intake = prepare_pending_review_intake(root=root, candidate_path=path,
        candidate_sha256=result['candidate_binding']['sha256'])
    response = prepare_pending_review_response(root=root, candidate_path=path,
        candidate_sha256=result['candidate_binding']['sha256'])
    assert intake['status'] == 'AWAITING_HUMAN_RESPONSES'
    assert response['candidate_binding'] == result['candidate_binding']
    assert response['model_context'] == result['model_context']
    assert response['reviewer_id'] is response['whole_model_approval'] is None
    assert all(row['response'] is None for row in response['groups'])
    for key in ('approval_changed', 'research_admitted', 'price_admitted',
                'canonical_written', 'registered_current_case_changed'):
        assert result[key] is False
    assert result['position_guidance'] is None
    assert before == {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('case', ['missing-file', 'missing-field', 'missing-symbol'])
def test_absent_is_none_without_looking_up_old_candidates(tmp_path, case):
    if case != 'missing-file':
        workflow = dict(schema_version='user-research-workflow-v1', action='no_order',
            review_candidates={'600887': dict(path='runtime/old.json', sha256='0' * 64)})
        if case == 'missing-symbol':
            workflow['supplemental_review_candidates'] = {}
        write(tmp_path / supplement.WORKFLOW_PATH, workflow)
    assert supplement.load_current_pending_candidate_supplement(root=tmp_path, symbol='600887') is None


@pytest.mark.parametrize('case', ['null-map', 'null-entry', 'extra-mode', 'bad-hash',
                                'missing-candidate', 'outside', 'schema', 'action', 'issuer'])
def test_invalid_registration_raises_without_fallback(registered, case):
    root, symbol, _, workflow = registered
    registry = json.loads(workflow.read_bytes())
    binding = registry['supplemental_review_candidates'][symbol]
    if case == 'null-map':
        registry['supplemental_review_candidates'] = None
    elif case == 'null-entry':
        registry['supplemental_review_candidates'][symbol] = None
    elif case == 'extra-mode':
        binding['mode'] = 'IMMUTABLE_CURRENT_IMPLEMENTATION_EXACT_INPUT_REPLAY_V1'
    elif case == 'bad-hash':
        binding['sha256'] = '0' * 64
    elif case == 'missing-candidate':
        binding['path'] = 'runtime/missing.json'
    elif case == 'outside':
        binding['path'] = '../outside.json'
    elif case in ('schema', 'action'):
        registry['schema_version' if case == 'schema' else 'action'] = 'wrong'
    else:
        symbol = '000002' if symbol != '000002' else '000003'
        registry['supplemental_review_candidates'][symbol] = binding
    write(workflow, registry)
    with pytest.raises((ValueError, OSError)):
        supplement.load_current_pending_candidate_supplement(root=root, symbol=symbol)


@pytest.mark.parametrize('case', ['mode', 'bound-mode', 'producer', 'context', 'admission',
                                'future', 'source', 'packet-missing', 'packet-rehashed', 'workbench-rehashed'])
def test_rehashed_mutations_cannot_supply_consumed_or_approved_material(registered, case):
    root, _, path, _ = registered
    candidate = json.loads(path.read_bytes())
    if case == 'mode':
        candidate['preparation_mode'] = 'IMMUTABLE_CURRENT_IMPLEMENTATION_EXACT_INPUT_REPLAY_V1'
    elif case == 'bound-mode':
        candidate['bound_draft_inputs'] = {}
    elif case == 'producer':
        candidate['implementation_bindings'] = []
    elif case == 'context':
        candidate['model_context']['model_id'] = 'wrong-model'
    elif case == 'admission':
        candidate['approval_changed'] = True
    elif case == 'future':
        candidate['generated_at'] = datetime(2099, 1, 1, tzinfo=timezone.utc).isoformat()
    elif case == 'source':
        (root / 'runtime/original.md').write_bytes(b'drift')
    elif case == 'packet-missing':
        (path.parent / 'consumed-review.json').unlink()
    else:
        target = path.parent / ('consumed-review.json' if case == 'packet-rehashed' else 'workbench.json')
        data = json.loads(target.read_bytes())
        if case == 'packet-rehashed':
            data['consumed_operating_inputs']['start_book_equity'] = '999999'
        else:
            data['artifact_bundle']['artifacts'][0]['identity']['input_sha256'] = '0' * 64
        write(target, data)
        for binding in candidate['source_bindings']:
            if binding['path'] == target.relative_to(root).as_posix():
                binding['sha256'] = sha256_file(target)
    rebind_candidate(registered, candidate)
    with pytest.raises((ValueError, KeyError, OSError)):
        load(registered)


def test_registry_change_during_projection_is_rejected(registered, monkeypatch):
    _, _, _, workflow = registered
    project = supplement.project_research_review_packet

    def changing(**kwargs):
        result = project(**kwargs)
        workflow.write_bytes(workflow.read_bytes() + b'\n')
        return result

    monkeypatch.setattr(supplement, 'project_research_review_packet', changing)
    with pytest.raises(ValueError, match='binding drift'):
        load(registered)
