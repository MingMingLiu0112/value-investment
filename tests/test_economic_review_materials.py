"""Synthetic review materials exercise binding, never grant economic approval."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json

import pytest

from test_pending_candidate_supplement import registered
from value_investment_agent.application.product import economic_review_materials as materials
from value_investment_agent.application.product import research_review_wizard as wizard
from value_investment_agent.application.product.research_reviews import prepare_pending_review_response


NOW = datetime.now(timezone.utc) + timedelta(days=1)


def test_readable_numbers_do_not_change_full_precision_assessment(registered):
    actual = handoff(registered)
    assessment = actual['economic_review_materials']['economic_assessment']
    before = deepcopy(assessment)
    row = materials._group_material(dict(id='EARNINGS', field_paths=[]),
        assessment, actual['materiality_handoff'])
    raw = assessment['scenarios'][0]['first_year_profit_cny']
    assert materials._display(raw) in row['conditional_assumptions'][0]
    assert assessment == before
    assert materials._display('81367067677.4400000000001') == '81,367,067,677.44'
    assert materials._display('0.075', percent=True) == '7.50%'
    with pytest.raises(ValueError):
        materials._display('NaN')


def handoff(registered, now=NOW):
    root, symbol, _, _ = registered
    return wizard.build_external_review_handoff(root=root, symbol=symbol, now=now)


def test_exact_current_materials_preserve_unsigned_contract_and_all_files(registered):
    root, _, _, _ = registered
    before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
    actual = handoff(registered)
    review = actual['economic_review_materials']
    assert review['schema_version'] == materials.SCHEMA
    assert review['action'] == 'no_order'
    assert review['approval_changed'] is review['primary_valuation_usable'] is False
    for key in ('candidate_binding', 'model_context', 'valuation_artifact_sha256'):
        assert review[key] == actual[key]
    assert review['input_descriptor_sha256'] == actual['model_context']['input_descriptor_sha256']
    assert review['assessment_sha256'] == review['economic_assessment']['assessment_sha256']
    assert 'assessed_at' not in review['economic_assessment']
    assert [g['id'] for g in review['groups']] == [g['id'] for g in actual['unsigned_response']['groups']]
    assert [g['field_paths'] for g in review['groups']] == [g['field_paths'] for g in actual['unsigned_response']['groups']]
    assert all(g['response'] is None for g in actual['unsigned_response']['groups'])
    assert actual['unsigned_response']['whole_model_approval'] is None
    assert actual['unsigned_response'] == prepare_pending_review_response(root=root,
        candidate_path=root / actual['candidate_binding']['path'],
        candidate_sha256=actual['candidate_binding']['sha256'])
    assert actual['position_guidance'] is None
    later = handoff(registered, NOW + timedelta(minutes=1))
    assert later['economic_review_materials'] == review
    assert before == {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('fault', ['symbol', 'descriptor', 'candidate', 'workbench', 'context',
    'approval', 'primary', 'strategy', 'action', 'missing'])
def test_mixed_or_approved_materials_cannot_reach_existing_signing_handoff(registered, monkeypatch, fault):
    original = materials.load_current_value_economic_assessment
    def mixed(**kwargs):
        result = original(**kwargs)
        if fault == 'missing': return None
        if fault == 'symbol': result['symbol'] = '000001'
        if fault == 'descriptor': result['input_descriptor_sha256'] = '0' * 64
        if fault == 'candidate': result['review_binding']['candidate_binding']['sha256'] = '0' * 64
        if fault == 'workbench': result['review_binding']['workbench_binding']['sha256'] = '0' * 64
        if fault == 'context': result['review_binding']['model_context']['model_version'] = 'wrong'
        if fault == 'approval': result['approval_changed'] = True
        if fault == 'primary': result['primary_valuation_usable'] = True
        if fault == 'strategy': result['strategy_admitted'] = True
        if fault == 'action': result['action'] = 'order'
        return result
    monkeypatch.setattr(materials, 'load_current_value_economic_assessment', mixed)
    with pytest.raises(ValueError, match='exact pending candidate'):
        handoff(registered)


def test_registry_change_after_economic_replay_is_rejected(registered, monkeypatch):
    original = materials.build_economic_review_materials
    def changed(**kwargs):
        result = original(**kwargs)
        registry = registered[3]
        registry.write_bytes(registry.read_bytes() + b'\n')
        return result
    monkeypatch.setattr(materials, 'build_economic_review_materials', changed)
    with pytest.raises(ValueError, match='changed during economic handoff'):
        handoff(registered)


def test_original_changed_after_assessment_is_rejected(registered, monkeypatch):
    original = materials.load_current_value_economic_assessment
    def changed(**kwargs):
        result = original(**kwargs)
        source = registered[0] / 'runtime/original.md'
        source.write_bytes(source.read_bytes() + b'changed')
        return result
    monkeypatch.setattr(materials, 'load_current_value_economic_assessment', changed)
    with pytest.raises(ValueError, match='source drift|hash mismatch'):
        handoff(registered)


def test_material_groups_cannot_expand_signed_scope(registered):
    root = registered[0]
    actual = handoff(registered)
    actual['review_questions'][0]['field_paths'] = ['unreviewed.input']
    with pytest.raises(ValueError, match='signed response scope'):
        materials.build_economic_review_materials(root=root, handoff=actual,
            analysis=actual['value_research_analysis'], now=NOW)


def test_valuation_hash_must_match_existing_response_replay(registered):
    actual = handoff(registered)
    actual['valuation_artifact_sha256'] = '0' * 64
    with pytest.raises(ValueError, match='exact pending candidate'):
        materials.build_economic_review_materials(root=registered[0], handoff=actual,
            analysis=actual['value_research_analysis'], now=NOW)


def test_five_groups_distinguish_fact_arithmetic_assumption_and_event_review(registered):
    actual = handoff(registered)
    assessment = actual['economic_review_materials']['economic_assessment']
    rows = [materials._group_material(dict(id=name, question='TEST_ONLY judgment',
        support='TEST_ONLY unapproved claim', countercase='TEST_ONLY strongest countercase',
        field_paths=['facts.scenario_inputs']), assessment, actual['materiality_handoff'])
        for name in ('EARNINGS', 'DURATION', 'DISTRIBUTION', 'COST_TERMINAL', 'EVENT_MODEL')]
    assert len({row['title'] for row in rows}) == 5
    for row in rows:
        assert row['judgment_questions'] and row['evidence_refs']
        assert 'TEST_ONLY unapproved claim' in row['conditional_assumptions']
        assert 'TEST_ONLY unapproved claim' not in row['verified_observations']
        assert row['counter_evidence'] == ['TEST_ONLY strongest countercase']
    assert '\u672a\u8986\u76d6' in rows[2]['verified_observations'][0]
    assert actual['materiality_handoff']['status'] in rows[4]['verified_observations'][0]


def test_stress_only_remains_not_primary(registered, monkeypatch):
    original = materials.load_current_value_economic_assessment
    def stress(**kwargs):
        result = deepcopy(original(**kwargs))
        result['model_applicability']['assessment'] = 'STRESS_ONLY'
        return result
    monkeypatch.setattr(materials, 'load_current_value_economic_assessment', stress)
    actual = handoff(registered)
    review = actual['economic_review_materials']
    assert review['status'] == 'STRESS_ONLY_NOT_PRIMARY'
    assert review['primary_valuation_usable'] is False
    assert actual['unsigned_response']['whole_model_approval'] is None
    assert json.loads(json.dumps(actual, allow_nan=False)) == actual


@pytest.fixture
def joint_registered(tmp_path, synthetic_pending_candidate_clock):
    from test_pending_research_candidate import candidate_inputs, run
    from test_joint_capital_path import policy_inputs
    from test_pending_candidate_supplement import bind, write
    from value_investment_agent.application.product.pending_candidate_supplement import WORKFLOW_PATH
    package, policy, request = candidate_inputs(tmp_path)
    policy_inputs(tmp_path, package, policy)
    settings = json.loads(policy.read_bytes())
    settings['human_review_groups'] = [dict(id=name, question='TEST_ONLY joint judgment',
        support='Synthetic conditional path.', countercase='Cash and terminal assumptions may fail.',
        impact='No admission.', field_paths=['facts.scenario_inputs'])
        for name in ('EARNINGS', 'DURATION', 'DISTRIBUTION', 'COST_TERMINAL', 'EVENT_MODEL')]
    # Retain a funding-failure case instead of making every hypothetical path pass.
    settings['choices'][0]['joint_drivers']['bear']['parent_cash_conversion'] = '0'
    write(policy, settings)
    candidate = run(tmp_path, package, policy, request)
    path = tmp_path / 'runtime/pending/candidate.json'
    workflow = tmp_path / WORKFLOW_PATH
    write(workflow, dict(schema_version='user-research-workflow-v1', action='no_order',
        supplemental_review_candidates={candidate['symbol']: bind(tmp_path, path)}))
    return tmp_path, candidate['symbol'], path, workflow


def test_joint_materials_copy_consumed_ledger_without_calculation_or_approval(joint_registered):
    root = joint_registered[0]
    before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
    actual = handoff(joint_registered)
    review = actual['economic_review_materials']
    joint = review['joint_capital_review']
    proposal = json.loads((root / joint['proposal_binding']['path']).read_bytes())
    choice = next(row for row in proposal['choices'] if row['id'] == joint['selected_choice'])
    assert joint['schema_version'] == 'joint-capital-review-v1'
    assert joint['status'] == 'CONDITIONAL_PATH_NOT_APPROVED'
    assert joint['scope'] == 'RESEARCH_ASSUMPTIONS_NOT_NORMALIZED_FACTS'
    assert joint['action'] == 'no_order'
    assert joint['candidate_binding'] == actual['candidate_binding']
    assert joint['input_descriptor_sha256'] == actual['model_context']['input_descriptor_sha256']
    for row in joint['scenarios']:
        name = row['scenario']
        assert row['drivers'] == choice['joint_drivers'][name]
        assert row['ledger'] == choice['joint_capital_ledgers'][name]
        assert len(row['ledger']['rows']) == 5
        assert row['valuation_per_share'] == actual['value_research_analysis']['valuation'][name + '_value']
    assert joint['scenarios'][0]['ledger']['cash_funding_status'] == 'FAIL'
    assert Decimal(joint['scenarios'][0]['ledger']['rows'][-1]['cash_close']) < 0
    assert review['primary_valuation_usable'] is review['approval_changed'] is False
    assert all(g['response'] is None for g in actual['unsigned_response']['groups'])
    assert before == {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_legacy_materials_do_not_invent_a_joint_ledger(registered):
    assert 'joint_capital_review' not in handoff(registered)['economic_review_materials']


def test_joint_display_uses_consumed_policy_not_duplicate_proposal_driver_text(joint_registered, monkeypatch):
    actual = handoff(joint_registered)
    expected = deepcopy(actual['economic_review_materials']['joint_capital_review'])
    original = materials.load_json_object
    def misleading_copy(path, label):
        result = original(path, label)
        if label == 'joint review proposal':
            result = deepcopy(result)
            result['choices'][0]['joint_drivers']['base']['parent_cash_conversion'] = '.01'
        return result
    monkeypatch.setattr(materials, 'load_json_object', misleading_copy)
    projected = materials._joint_capital_review(root=joint_registered[0], handoff=actual, now=NOW)
    assert projected == expected
    assert projected['scenarios'][1]['drivers']['parent_cash_conversion'] != '.01'


@pytest.mark.parametrize('fault', ['symbol', 'context', 'changed-proposal'])
def test_joint_projection_rechecks_candidate_identity_and_proposal(joint_registered, fault):
    actual = handoff(joint_registered)
    if fault == 'symbol':
        actual['symbol'] = '000001'
    elif fault == 'context':
        actual['model_context'] = dict(actual['model_context'], input_descriptor_sha256='0' * 64)
    else:
        path = joint_registered[2].parent / 'valuation-proposal.json'
        path.write_bytes(path.read_bytes() + b'\n')
    with pytest.raises(ValueError):
        materials._joint_capital_review(root=joint_registered[0], handoff=actual, now=NOW)
