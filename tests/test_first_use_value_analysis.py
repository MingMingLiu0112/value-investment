"""Synthetic replay boundaries; no test result is an economic approval."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json

import pytest

from test_pending_candidate_supplement import registered
from test_economic_review_materials import joint_registered
from value_investment_agent.application.product.research_draft import load_current_research_analysis
from value_investment_agent.application.research.value_research_analysis import (
    load_current_value_research_analysis, project_value_research_analysis,
)


NOW = datetime.now(timezone.utc) + timedelta(days=1)


@pytest.mark.parametrize('changed', ['input_descriptor_sha256', 'review_binding'])
def test_economic_assessment_cannot_mix_current_research_versions(registered, monkeypatch, changed):
    from value_investment_agent.application.research import value_economic_assessment
    root, symbol, _, _ = registered
    original = value_economic_assessment.load_current_value_economic_assessment
    def mixed(**kwargs):
        result = original(**kwargs)
        result[changed] = 'b' * 64 if changed == 'input_descriptor_sha256' else {}
        return result
    monkeypatch.setattr(value_economic_assessment, 'load_current_value_economic_assessment', mixed)
    result = load_current_research_analysis(root, symbol, now=NOW)
    assert result['status'] == 'SOURCE_OR_REPLAY_UNAVAILABLE'
    assert result['scenarios'] == []
    assert result['action_admitted'] is False


def test_source_to_scenarios_sensitivity_and_review_preserves_bytes(registered):
    root, symbol, candidate, _ = registered
    before = {path: path.read_bytes() for path in root.rglob('*') if path.is_file()}
    analysis = load_current_value_research_analysis(root=root, symbol=symbol, now=NOW)
    workbench = json.loads((candidate.parent / 'workbench.json').read_bytes())
    assert analysis['schema_version'] == 'value-research-analysis-v1'
    assert analysis['arithmetic_complete'] is True
    assert analysis['valuation'] == workbench['valuation']
    assert analysis['economic_assumptions_reviewed'] is False
    assert analysis['strategy_admitted'] is analysis['action_admitted'] is False
    assert analysis['price_comparison_eligible'] is False
    assert analysis['action'] == 'no_order'
    assert analysis['joint_capital_review'] is None
    assert analysis['review_binding']['candidate_binding']['path'].endswith('candidate.json')
    assert analysis['source_catalog']
    assert all(source['sha256'] for source in analysis['source_catalog'])
    assert analysis['counter_evidence'] and analysis['thesis_breakers']
    assert analysis['model_applicability']['route']['selected_model'] == 'residual_income_or_equity_value'
    assert analysis['model_applicability']['status'] == 'CONDITIONAL_NOT_ECONOMICALLY_APPROVED'
    assert analysis['sensitivity']['economic_consistency_reviewed'] is False
    assert analysis['human_review_groups']
    base = Decimal(analysis['valuation']['base_value'])
    for row in analysis['sensitivity']['rows']:
        assert row['basis'] and row['evidence_refs']
        point = next(item for item in row['points'] if item['bound'] == 'base')
        assert Decimal(point['per_share_value']) == base
        assert Decimal(point['delta_from_base']) == 0
    terminal = next(row for row in analysis['sensitivity']['rows'] if row['field_path'] == 'terminal_roe')
    ordered = sorted(terminal['points'], key=lambda point: Decimal(point['input_value']))
    assert Decimal(ordered[0]['per_share_value']) < Decimal(ordered[-1]['per_share_value'])
    assert before == {path: path.read_bytes() for path in root.rglob('*') if path.is_file()}


@pytest.mark.parametrize('target', ['package.json', 'workbench.json', 'candidate.json',
                                    'consumed-review.json', 'original.md'])
def test_missing_or_changed_source_never_returns_cached_numbers(registered, target):
    root, symbol, candidate, _ = registered
    path = root / 'runtime/original.md' if target == 'original.md' else candidate.parent / target
    path.write_bytes(path.read_bytes() + b'\nSOURCE_CHANGED')
    analysis = load_current_research_analysis(root, symbol, now=NOW)
    assert analysis['status'] == 'SOURCE_OR_REPLAY_UNAVAILABLE'
    assert analysis['arithmetic_complete'] is False
    assert analysis['scenarios'] == []
    assert 'valuation' not in analysis
    assert analysis['action_admitted'] is False


def test_requested_cutoff_rejects_later_consumed_inputs(registered):
    root, symbol, candidate, _ = registered
    stamp = datetime.fromisoformat(json.loads(candidate.read_bytes())['generated_at'])
    analysis = load_current_research_analysis(root, symbol, now=stamp - timedelta(seconds=1))
    assert analysis['arithmetic_complete'] is False
    assert 'cutoff' in analysis['blockers'][0]


def test_missing_registration_is_not_a_search_for_unregistered_files(registered):
    root, symbol, _, workflow = registered
    data = json.loads(workflow.read_bytes())
    data['supplemental_review_candidates'] = {}
    workflow.write_text(json.dumps(data), encoding='utf-8')
    assert load_current_research_analysis(root, symbol, now=NOW) is None


def test_invalid_current_registration_does_not_fall_back(registered):
    root, symbol, _, workflow = registered
    data = json.loads(workflow.read_bytes())
    data['supplemental_review_candidates'][symbol]['sha256'] = '0' * 64
    workflow.write_text(json.dumps(data), encoding='utf-8')
    result = load_current_research_analysis(root, symbol, now=NOW)
    assert result['arithmetic_complete'] is False
    assert result['scenarios'] == []


def test_analysis_can_exist_without_formal_publication(registered, monkeypatch):
    from value_investment_agent.application.decision import current_value_plan
    root, symbol, _, _ = registered
    result = current_value_plan.load_current_value_action_plans(root, now=NOW)
    assert len(result['items']) == 1
    plan = result['items'][0]
    assert plan['symbol'] == symbol
    assert plan['research_analysis']['arithmetic_complete'] is True
    assert Decimal(plan['base']) > 0
    assert plan['formal_eligibility'] is False
    assert plan['price_comparison_eligible'] is False
    assert plan['action_intent'] is None
    assert plan['position_guidance'] is None
    assert plan['action'] == 'no_order'
    assert all(plan[action + '_trigger_price'] is None for action in ('entry', 'add', 'reduce', 'exit'))
    assert result['blockers'][0].startswith('VALUE_PUBLICATION_CHAIN_UNAVAILABLE:')


def test_existing_review_contract_includes_verified_arithmetic(registered):
    from value_investment_agent.application.product.research_review_wizard import build_external_review_handoff
    root, symbol, candidate, _ = registered
    result = build_external_review_handoff(root=root, symbol=symbol, now=NOW)
    assert result['status'] == 'EXTERNAL_SIGNATURE_REQUIRED'
    analysis = result['value_research_analysis']
    assert result['public_research_materials'] == json.loads(
        (candidate.parent / 'consumed-review.json').read_bytes())
    assert analysis['arithmetic_complete'] is True
    assert analysis['review_binding']['candidate_binding'] == result['candidate_binding']
    assert result['unsigned_response']['reviewer_id'] is None
    assert result['unsigned_response']['whole_model_approval'] is None
    assert result['verification']['approval_changed'] is False


def test_read_time_invalidated_plan_discards_frozen_analysis(monkeypatch, tmp_path):
    from value_investment_agent.application.decision import current_value_plan
    frozen = dict(schema_version='value-action-plan-v1', symbol='600887', blockers=[],
        research_analysis=dict(arithmetic_complete=True, scenarios=[dict(per_share_value='42')]),
        research_analysis_status='CONDITIONAL_ANALYSIS_VERIFIED')
    monkeypatch.setattr(current_value_plan, 'load_registered_value_action_plans',
        lambda *args, **kwargs: dict(items=[], blockers=['SOURCE_MISSING'], source_bindings=[]))
    result = current_value_plan.revalidate_current_value_plan(tmp_path, frozen, now=NOW)
    assert 'research_analysis' not in result
    assert result['formal_eligibility'] is False


def test_new_descriptor_invalidates_nonreplaceable_old_price_conditions(
        registered, monkeypatch):
    from value_investment_agent.application.decision import current_value_plan
    root, symbol, _, _ = registered
    frozen = dict(
        schema_version='value-action-plan-v1', symbol=symbol,
        verification_scope='FORMAL_HISTORICAL_PLAN', candidate_action='WATCH',
        action_intent='MANUAL_REVIEW', security_review_eligible=True,
        formal_eligibility=True, scenario_validity={'status': 'ready'},
        valuation_input_version='0' * 64, research_version='OLD', blockers=[],
        source_bindings=[],
    )
    monkeypatch.setattr(
        current_value_plan, 'load_registered_value_action_plans',
        lambda *args, **kwargs: dict(
            items=[dict(frozen)], blockers=[], source_bindings=[]))

    result = current_value_plan.load_current_value_action_plans(
        root, now=NOW, symbols=[symbol])['items'][0]

    assert result['signal_state'] == 'STALE'
    assert result['formal_eligibility'] is False
    assert result['action_intent'] is None
    assert 'CURRENT_RESEARCH_DESCRIPTOR_CHANGED' in result['blockers']
    assert result['research_analysis']['input_descriptor_sha256'] != (
        frozen['valuation_input_version'])


def test_projector_rejects_binding_outside_repository(registered):
    root, _, _, _ = registered
    with pytest.raises(ValueError, match='relative'):
        project_value_research_analysis(root=root, now=NOW,
            package_binding=dict(path='../outside.json', sha256='0' * 64), workbench_binding={})


def test_source_drift_during_sensitivity_discards_all_results(registered, monkeypatch):
    from value_investment_agent.application.research import value_research_analysis
    root, symbol, _, _ = registered
    original = value_research_analysis._sensitivity
    def mutate_after_calculation(descriptor, model, **kwargs):
        result = original(descriptor, model, **kwargs)
        (root / 'runtime/original.md').write_bytes(b'CHANGED_DURING_CALCULATION')
        return result
    monkeypatch.setattr(value_research_analysis, '_sensitivity', mutate_after_calculation)
    result = load_current_research_analysis(root, symbol, now=NOW)
    assert result['arithmetic_complete'] is False
    assert result['scenarios'] == []
    assert 'hash mismatch' in result['blockers'][0]


def test_public_joint_review_matches_handoff_without_calling_signing_or_private_paths(joint_registered, monkeypatch):
    from value_investment_agent.application.product import economic_review_materials as materials
    from value_investment_agent.application.product import research_review_wizard as wizard
    import io
    import socket

    root, symbol, _, _ = joint_registered
    expected = wizard.build_external_review_handoff(root=root, symbol=symbol, now=NOW)[
        'economic_review_materials']['joint_capital_review']
    before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
    original_open = io.open

    def readonly_open(file, mode='r', *args, **kwargs):
        assert not any(flag in mode for flag in 'wax+'), 'public projection tried to write'
        assert 'private' not in str(file).lower(), 'public projection tried to read private state'
        return original_open(file, mode, *args, **kwargs)

    def forbidden(*args, **kwargs):
        pytest.fail('Public analysis must not invoke handoff/signing/network')

    monkeypatch.setattr(io, 'open', readonly_open)
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(materials, 'prepare_pending_review_response', forbidden)
    monkeypatch.setattr(wizard, 'build_external_review_handoff', forbidden)
    first = load_current_value_research_analysis(root=root, symbol=symbol, now=NOW)
    second = load_current_value_research_analysis(root=root, symbol=symbol, now=NOW + timedelta(minutes=1))
    assert first['joint_capital_review'] == second['joint_capital_review'] == expected
    joint = first['joint_capital_review']
    assert set(joint) == {'schema_version', 'symbol', 'action', 'status', 'scope', 'candidate_binding',
        'proposal_binding', 'policy_binding', 'input_descriptor_sha256', 'selected_choice', 'date_scope',
        'basis_at', 'valuation_at', 'scenarios'}
    assert first['approval_changed'] is first['economic_assumptions_reviewed'] is False
    assert first['strategy_admitted'] is first['action_admitted'] is False
    assert joint['scenarios'][0]['ledger']['cash_funding_status'] == 'FAIL'
    assert before == {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('target', ['candidate.json', 'valuation-proposal.json', 'policy'])
def test_public_joint_drift_never_falls_back_to_prior_ledger(joint_registered, monkeypatch, target):
    from value_investment_agent.application.research import value_research_analysis as service
    root, symbol, candidate_path, _ = joint_registered
    candidate = json.loads(candidate_path.read_bytes())
    path = root / candidate['economic_policy_binding']['path'] if target == 'policy' else candidate_path.parent / target
    path.write_bytes(path.read_bytes() + b'\nCHANGED')
    monkeypatch.setattr(service, 'load_current_pending_replay', lambda **kwargs: pytest.fail('stale fallback'))
    with pytest.raises(ValueError):
        service.load_current_value_research_analysis(root=root, symbol=symbol, now=NOW)


def test_public_joint_selector_change_during_projection_is_rejected(joint_registered, monkeypatch):
    from value_investment_agent.application.product import economic_review_materials as materials
    root, symbol, _, registry = joint_registered
    original = materials.project_joint_capital_review

    def changed(**kwargs):
        result = original(**kwargs)
        registry.write_bytes(registry.read_bytes() + b'\n')
        return result

    monkeypatch.setattr(materials, 'project_joint_capital_review', changed)
    with pytest.raises(ValueError, match='hash mismatch'):
        load_current_value_research_analysis(root=root, symbol=symbol, now=NOW)


def test_public_joint_source_change_at_projection_end_is_rejected(joint_registered, monkeypatch):
    from value_investment_agent.application.product import economic_review_materials as materials
    root, symbol, candidate_path, _ = joint_registered
    original = materials.project_joint_capital_review

    def changed(**kwargs):
        result = original(**kwargs)
        candidate = json.loads(candidate_path.read_bytes())
        source = root / candidate['economic_policy_binding']['path']
        source.write_bytes(source.read_bytes() + b'\n')
        return result

    monkeypatch.setattr(materials, 'project_joint_capital_review', changed)
    with pytest.raises(ValueError, match='hash mismatch'):
        load_current_value_research_analysis(root=root, symbol=symbol, now=NOW)


@pytest.mark.parametrize('naive', [False, True])
def test_public_joint_projection_respects_requested_clock(joint_registered, naive):
    root, symbol, candidate_path, _ = joint_registered
    generated = datetime.fromisoformat(json.loads(candidate_path.read_bytes())['generated_at'])
    now = generated.replace(tzinfo=None) if naive else generated - timedelta(seconds=1)
    with pytest.raises(ValueError):
        load_current_value_research_analysis(root=root, symbol=symbol, now=now)


def test_real_public_cc1_and_nonjoint_companion_readback(monkeypatch):
    """Opt-in read-only public originals, never construct/register a new candidate."""
    import os
    import io
    import socket
    from pathlib import Path
    from value_investment_agent.application.product import economic_review_materials as materials
    location = os.environ.get('VALUE_PUBLIC_JOINT_REAL_ROOT')
    if not location:
        pytest.skip('Explicit public fixture root not supplied')
    root = Path(location)
    original_open = io.open

    def readonly_open(file, mode='r', *args, **kwargs):
        assert not any(flag in mode for flag in 'wax+'), 'real readback tried to write'
        assert 'private' not in str(file).lower(), 'real readback tried to read private data'
        return original_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(io, 'open', readonly_open)
    monkeypatch.setattr(socket, 'create_connection', lambda *args, **kwargs: pytest.fail('no HTTP'))
    monkeypatch.setattr(socket.socket, 'connect', lambda *args, **kwargs: pytest.fail('no HTTP'))
    monkeypatch.setattr(materials, 'prepare_pending_review_response',
        lambda **kwargs: pytest.fail('Real public read must not construct signing response'))
    now = datetime.now(timezone.utc)
    joint = load_current_value_research_analysis(root=root, symbol='600519', now=now)
    companion = load_current_value_research_analysis(root=root, symbol='600887', now=now)
    assert joint['joint_capital_review']['schema_version'] == 'joint-capital-review-v1'
    assert joint['joint_capital_review']['status'] == 'CONDITIONAL_PATH_NOT_APPROVED'
    assert len(joint['joint_capital_review']['scenarios']) == 3
    assert all(len(row['ledger']['rows']) == 5 for row in joint['joint_capital_review']['scenarios'])
    assert companion['joint_capital_review'] is None
    assert joint['economic_assumptions_reviewed'] is joint['approval_changed'] is False
    assert joint['action'] == companion['action'] == 'no_order'
