"""TEST_ONLY pending v2 consumption and read-only semantic replay."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
import shutil
import subprocess
import types

import pytest

from test_joint_cash_neutral_proposal import case
from test_economic_review_materials import joint_registered
from value_investment_agent.application.product import pending_research_candidate as pending
from value_investment_agent.application.product import economic_review_materials as materials
from value_investment_agent.application.product import pending_candidate_supplement as supplement
from value_investment_agent.application.product import neutral_valuation_proposal as neutral
from value_investment_agent.application.product.common import sha256_file, encode_json_bytes
from value_investment_agent.application.product.decision_surface import verify_current_decision_workbench
from value_investment_agent.m1_valuation_package_builder import build_descriptor
from value_investment_agent.application.research.v3_input_adapter import (
    build_descriptor_for_package,
)
from value_investment_agent.research_artifact_codecs import artifact_payload

ROOT = Path(pending.__file__).resolve().parents[4]


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')


@pytest.fixture
def prepared(case):
    root, package_path, policy_path, _ = case
    package = json.loads(package_path.read_bytes())
    package['sources'][0]['issuer_identity'] = dict(venue='CNINFO',
        security_code=package['symbol'], issuer_name=package['name'], organization_id='TEST_ONLY')
    ref = package['facts']['evidence_refs'][0]
    package['research_case']['evidence_refs'] = [ref]
    for key in ('positives', 'counter_evidence', 'thesis_breakers', 'next_events'):
        for item in package['research_case'].get(key, []):
            item['evidence_refs'] = ['facts']
    save(package_path, package)
    policy = json.loads(policy_path.read_bytes())
    policy['source_package_sha256'] = sha256_file(package_path)
    save(policy_path, policy)
    (root/'config').mkdir(exist_ok=True)
    save(root/'config/research-evidence-stop-ledger-v1.json',
         dict(schema_version='research-evidence-stop-ledger-v1', stops=[]))
    for name in pending.JOINT_CASH_IMPLEMENTATIONS:
        target = root/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/name, target)
    request = dict(schema_version='research-schedule-request-v1', symbol=package['symbol'],
        source_id='CNINFO', period=package['point_in_time']['report_period'],
        research_question_id='TEST_ONLY_joint_cash', blocker_id='none',
        reopen_condition_met=False, new_evidence_ids=[])
    folder = root/'runtime/pending'
    result = pending.prepare_pending_research_candidate(root=root,
        package_path=package_path, package_sha256=sha256_file(package_path),
        policy_path=policy_path, policy_sha256=sha256_file(policy_path), choice_id='cash',
        output_dir=folder, schedule_request=request, schedule_request_sha256='a'*64)
    return root, folder, result, policy


@pytest.fixture
def prepared_v3(case):
    root, package_path, policy_path, observations_path = case
    package = json.loads(package_path.read_bytes())
    package['sources'][0]['issuer_identity'] = dict(venue='CNINFO',
        security_code=package['symbol'], issuer_name=package['name'], organization_id='gssh0600887')
    ref = package['facts']['evidence_refs'][0]
    package['research_case']['evidence_refs'] = [ref]
    for key in ('positives', 'counter_evidence', 'thesis_breakers', 'next_events'):
        for item in package['research_case'].get(key, []):
            item['evidence_refs'] = ['facts']
    save(package_path, package)
    policy = json.loads(policy_path.read_bytes())
    policy['schema_version'] = neutral.JOINT_CASH_V3_SCHEMA
    policy['source_package_sha256'] = sha256_file(package_path)
    for terminal in policy['choices'][0]['terminal_policy'].values():
        terminal.update(terminal_mechanism='recursive_capital_use_and_owner_distribution_v1',
            terminal_start_year=11, first_distribution_timing='end_of_terminal_year_1',
            legacy_profit_dynamics='constant_after_profit_scale_transition',
            commitment_occurrences=None, restricted_cash_release_cny='0',
            restricted_cash_release_year=None, convergence_tolerance_cny='0.000001',
            max_tail_years=2000)
    observations = json.loads(observations_path.read_bytes())
    for name, terminal in policy['choices'][0]['terminal_policy'].items():
        observations['scenarios'][name]['terminal_policy'] = terminal
    save(observations_path, observations)
    policy['rationale_bindings'][0]['sha256'] = sha256_file(observations_path)
    save(policy_path, policy)
    (root/'config').mkdir(exist_ok=True)
    save(root/'config/research-evidence-stop-ledger-v1.json',
         dict(schema_version='research-evidence-stop-ledger-v1', stops=[]))
    for name in pending.JOINT_CASH_V3_IMPLEMENTATIONS:
        target = root/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/name, target)
    request = dict(schema_version='research-schedule-request-v1', symbol=package['symbol'],
        source_id='CNINFO', period=package['point_in_time']['report_period'],
        research_question_id='TEST_ONLY_joint_cash_v3', blocker_id='none',
        reopen_condition_met=False, new_evidence_ids=[])
    folder = root/'runtime/pending-v3'
    result = pending.prepare_pending_research_candidate(root=root,
        package_path=package_path, package_sha256=sha256_file(package_path),
        policy_path=policy_path, policy_sha256=sha256_file(policy_path),
        choice_id='cash', output_dir=folder, schedule_request=request,
        schedule_request_sha256='b'*64)
    return root, folder, result, policy


def verify(prepared):
    root, folder, _, _ = prepared
    return pending.verify_pending_research_candidate(root=root, path=folder/'candidate.json',
        expected_sha256=sha256_file(folder/'candidate.json'))


def test_v2_ten_annual_retentions_reach_actual_shared_model(prepared, monkeypatch):
    root, folder, result, _ = prepared
    assert result['input_mode'] == pending.JOINT_CASH_SCHEMA
    assert result['action'] == 'no_order' and not result['approval_changed']
    package = json.loads((folder/'package.json').read_bytes())
    work = json.loads((folder/'workbench.json').read_bytes())
    facts = artifact_payload(verify_current_decision_workbench(work).dependency_objects['financial_facts'])[1]
    assert facts['scenario_inputs'] == package['facts']['scenario_inputs']
    assert result['candidate_valuation']['model_version'] == 'residual-income-equity-path-v2'
    assert '十年现金约束' in package['research_case']['thesis']
    assert '五年' not in package['research_case']['thesis']
    assert len(package['assumption_bindings']) == 23*3
    for values in facts['scenario_inputs'].values():
        assert len(values['forecast_roes']) == len(values['forecast_retentions']) == 10
        assert len(set(values['forecast_retentions'])) > 1
        assert 'retention' not in values
    calls = []
    original = neutral.compile_joint_cash_choice
    def tracked(**kwargs):
        calls.append(kwargs)
        return original(**kwargs)
    monkeypatch.setattr(neutral, 'compile_joint_cash_choice', tracked)
    before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
    assert verify(prepared) == result
    assert len(calls) == 1 and len(calls[0]['choice']['joint_drivers']['base']['years']) == 10
    assert before == {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_v2_candidate_is_consumed_by_registered_research_supplement(prepared):
    root, folder, receipt, _ = prepared
    pointer = root/'config/current-research-drafts.json'
    save(pointer, dict(schema_version='current-research-drafts-v1', action='no_order',
        pending_candidates={receipt['symbol']: dict(
            path=(folder/'candidate.json').relative_to(root).as_posix(),
            sha256=sha256_file(folder/'candidate.json'))}))

    material = supplement.load_current_pending_candidate_supplement(
        root=root, symbol=receipt['symbol'])

    assert material is not None
    assert material['candidate']['input_mode'] == pending.JOINT_CASH_SCHEMA
    assert material['candidate']['candidate_valuation'] == receipt['candidate_valuation']
    assert material['candidate']['action'] == 'no_order'
    assert material['candidate']['approval_changed'] is False
    assert material['approval_changed'] is False
    assert material['research_admitted'] is False
    assert material['price_admitted'] is False
    assert material['position_guidance'] is None


def test_v3_candidate_is_consumed_by_registered_research_supplement(prepared_v3):
    root, folder, receipt, _ = prepared_v3
    pointer = root/'config/current-research-drafts.json'
    save(pointer, dict(schema_version='current-research-drafts-v1', action='no_order',
        pending_candidates={receipt['symbol']: dict(
            path=(folder/'candidate.json').relative_to(root).as_posix(),
            sha256=sha256_file(folder/'candidate.json'))}))

    material = supplement.load_current_pending_candidate_supplement(
        root=root, symbol=receipt['symbol'])

    assert material is not None
    assert material['candidate']['input_mode'] == pending.JOINT_CASH_V3_SCHEMA
    assert material['candidate']['candidate_valuation'] == receipt['candidate_valuation']
    assert material['candidate']['model_context_scope'] == 'ACTUALLY_CONSUMED'
    assert material['candidate']['action'] == 'no_order'
    assert material['candidate']['approval_changed'] is False
    assert material['approval_changed'] is False
    assert material['research_admitted'] is False
    assert material['price_admitted'] is False
    assert material['position_guidance'] is None


def test_v3_terminal_contract_is_consumed_and_round_trips(prepared_v3):
    root, folder, result, _ = prepared_v3
    assert result['input_mode'] == pending.JOINT_CASH_V3_SCHEMA
    assert result['model_context_scope'] == 'ACTUALLY_CONSUMED'
    assert result['candidate_valuation']['model_version'] == 'residual-income-equity-path-v3'
    assert result['action'] == 'no_order' and result['research_admitted'] is False
    package = json.loads((folder/'package.json').read_bytes())
    descriptor = build_descriptor_for_package(package, root=root)
    assert descriptor.input_sha256 == result['model_context']['input_descriptor_sha256']
    work = json.loads((folder/'workbench.json').read_bytes())
    facts = artifact_payload(
        verify_current_decision_workbench(work).dependency_objects['financial_facts'])[1]
    for scenario in facts['scenario_inputs'].values():
        terminal = scenario['terminal_economic_contract']
        assert terminal['contract_version'] == 'terminal-economic-contract-v1'
        assert terminal['terminal_mechanism'] == 'recursive_capital_use_and_owner_distribution'


def test_v3_resealed_terminal_contract_must_match_exact_proposal(prepared_v3):
    root, folder, _, _ = prepared_v3
    package = json.loads((folder/'package.json').read_bytes())
    original = build_descriptor_for_package(package, root=root)
    package['facts']['scenario_inputs']['base']['terminal_economic_contract'][
        'productive_marginal_return'] = '0.123456'
    with pytest.raises(ValueError, match='exact proposal choice'):
        build_descriptor_for_package(package, root=root)
    assert build_descriptor_for_package(
        json.loads((folder/'package.json').read_bytes()), root=root
    ).input_sha256 == original.input_sha256


def test_v3_proposal_source_identity_must_equal_content_hash(prepared_v3):
    root, folder, _, _ = prepared_v3
    package = json.loads((folder/'package.json').read_bytes())
    source = next(row for row in package['sources']
                  if row['id'].startswith('pending-joint-proposal-'))
    source['id'] = 'pending-joint-proposal-' + '0'*64
    with pytest.raises(ValueError, match='identity must equal'):
        build_descriptor_for_package(package, root=root)


@pytest.mark.parametrize('fault', ['roe', 'retention', 'ledger', 'proposal_ledger',
                                 'proposal_retention', 'model_version', 'source_driver',
                                 'implementation_set', 'executing_implementation'])
def test_semantic_replay_rejects_resealed_economic_drift(prepared, fault):
    root, folder, receipt, policy = prepared
    data = deepcopy(receipt)
    package = json.loads((folder/'package.json').read_bytes())
    descriptor = build_descriptor(package, root=root)
    if fault == 'roe':
        package['facts']['scenario_inputs']['base']['forecast_roes'][5] = '0.01'
    elif fault == 'retention':
        package['facts']['scenario_inputs']['base']['forecast_retentions'][5] = '0.3'
    elif fault == 'ledger':
        package['research_case']['financial_summary']['pending_joint_capital_research']['ledgers']['base']['rows'][5]['distribution'] = '1'
    elif fault.startswith('proposal_'):
        path = folder/'valuation-proposal.json'
        old = sha256_file(path)
        proposal = json.loads(path.read_bytes())
        if fault == 'proposal_ledger':
            proposal['choices'][0]['joint_capital_ledgers']['base']['rows'][5]['distribution'] = '1'
        else:
            proposal['choices'][0]['actual_calculation_inputs']['scenarios']['base']['forecast_retentions'][5] = '0.3'
        save(path, proposal)
        for ref in data['source_bindings']:
            if ref['sha256'] == old:
                ref['sha256'] = sha256_file(path)
    elif fault == 'model_version':
        package['dependencies']['model_version'] = 'residual-income-equity-shared-v1'
    elif fault == 'source_driver':
        policy['choices'][0]['joint_drivers']['base']['years'][5]['target_payout_ratio'] = '0.1'
    elif fault == 'implementation_set':
        data['implementation_bindings'].pop()
    else:
        data['implementation_bindings'][0]['sha256'] = '0'*64
    with pytest.raises(ValueError, match='economic derivation|source-bound|implementation|model version'):
        pending._verify_joint_economic_inputs(root=root, path=folder/'candidate.json', data=data,
            policy=policy, package=package, descriptor=descriptor)


def test_v2_review_copies_consumed_cash_drivers_terminal_and_full_input(prepared):
    root, folder, result, policy = prepared
    review = materials.project_joint_capital_review(root=root,
        binding=dict(path=(folder/'candidate.json').relative_to(root).as_posix(),
                     sha256=sha256_file(folder/'candidate.json')),
        symbol=result['symbol'], model_context=result['model_context'], now=datetime.now(timezone.utc))
    assert review['schema_version'] == 'joint-capital-cash-review-v2'
    assert review['explicit_years'] == 10 and review['action'] == 'no_order'
    proposal = json.loads((folder/'valuation-proposal.json').read_bytes())['choices'][0]
    for row in review['scenarios']:
        name = row['scenario']
        assert row['drivers'] == policy['choices'][0]['joint_drivers'][name]
        assert row['ledger'] == proposal['joint_capital_ledgers'][name]
        assert row['actual_calculation_inputs'] == proposal['actual_calculation_inputs']['scenarios'][name]
        assert row['terminal_policy'] == policy['choices'][0]['terminal_policy'][name]


def test_v1_review_bytes_equal_original_projection(joint_registered):
    root, symbol, path, _ = joint_registered
    data = pending.verify_pending_research_candidate(root=root, path=path, expected_sha256=sha256_file(path))
    baseline = subprocess.check_output(['git', 'show',
        'HEAD:src/value_investment_agent/application/product/economic_review_materials.py'], cwd=ROOT)
    old = types.ModuleType('value_investment_agent.application.product._test_legacy_materials')
    old.__package__ = 'value_investment_agent.application.product'
    exec(compile(baseline, '<retained-v1-review>', 'exec'), old.__dict__)
    args = dict(root=root, binding=dict(path=path.relative_to(root).as_posix(), sha256=sha256_file(path)),
        symbol=symbol, model_context=data['model_context'], now=datetime.now(timezone.utc)+timedelta(days=1))
    actual, prior = materials.project_joint_capital_review(**args), old.project_joint_capital_review(**args)
    assert actual['schema_version'] == 'joint-capital-review-v1'
    assert encode_json_bytes(actual) == encode_json_bytes(prior)
