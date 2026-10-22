"""Synthetic replay boundaries; no test result is an economic approval."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json

import pytest

from test_pending_candidate_supplement import registered
from value_investment_agent.application.product.research_draft import load_current_research_analysis
from value_investment_agent.application.research.value_research_analysis import (
    load_current_value_research_analysis, project_value_research_analysis,
)


NOW = datetime(2026, 10, 22, 12, tzinfo=timezone.utc)


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
        lambda *args, **kwargs: dict(items=[], blockers=['SOURCE_MISSING']))
    result = current_value_plan.revalidate_current_value_plan(tmp_path, frozen, now=NOW)
    assert 'research_analysis' not in result
    assert result['formal_eligibility'] is False


def test_projector_rejects_binding_outside_repository(registered):
    root, _, _, _ = registered
    with pytest.raises(ValueError, match='relative'):
        project_value_research_analysis(root=root, now=NOW,
            package_binding=dict(path='../outside.json', sha256='0' * 64), workbench_binding={})


def test_source_drift_during_sensitivity_discards_all_results(registered, monkeypatch):
    from value_investment_agent.application.research import value_research_analysis
    root, symbol, _, _ = registered
    original = value_research_analysis._sensitivity
    def mutate_after_calculation(descriptor, model):
        result = original(descriptor, model)
        (root / 'runtime/original.md').write_bytes(b'CHANGED_DURING_CALCULATION')
        return result
    monkeypatch.setattr(value_research_analysis, '_sensitivity', mutate_after_calculation)
    result = load_current_research_analysis(root, symbol, now=NOW)
    assert result['arithmetic_complete'] is False
    assert result['scenarios'] == []
    assert 'hash mismatch' in result['blockers'][0]
