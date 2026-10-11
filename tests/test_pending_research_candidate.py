"""Shared candidate contracts use synthetic inputs, never issuer approval."""
from datetime import datetime, timezone
from decimal import Decimal
import json

import pytest

pytestmark = pytest.mark.usefixtures('synthetic_pending_candidate_clock')

from test_neutral_valuation_proposal import proposal_inputs
from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.application.product.pending_research_candidate import (
    prepare_pending_research_candidate, verify_pending_research_candidate,
)
from value_investment_agent.application.product.decision_surface import verify_current_decision_workbench
from value_investment_agent.research_artifact_codecs import artifact_payload


def candidate_inputs(root):
    package_path, policy_path = proposal_inputs(root)
    package = json.loads(package_path.read_text(encoding='utf-8'))
    package['sources'][0]['issuer_identity'] = dict(venue='CNINFO',
        security_code=package['symbol'], issuer_name=package['name'], organization_id='gssh0600887')
    ref = package['facts']['evidence_refs'][0]
    package['research_case']['evidence_refs'] = [ref]
    for field in ('positives', 'counter_evidence', 'thesis_breakers', 'next_events'):
        for item in package['research_case'].get(field, []):
            item['evidence_refs'] = ['facts']
    package_path.write_text(json.dumps(package), encoding='utf-8')
    policy = json.loads(policy_path.read_text(encoding='utf-8'))
    policy['source_package_sha256'] = sha256_file(package_path)
    policy_path.write_text(json.dumps(policy), encoding='utf-8')
    (root / 'config').mkdir()
    (root / 'config/research-evidence-stop-ledger-v1.json').write_text(
        json.dumps({'schema_version': 'research-evidence-stop-ledger-v1', 'stops': []}), encoding='utf-8')
    request = dict(schema_version='research-schedule-request-v1', symbol=package['symbol'],
        source_id='CNINFO', period=package['point_in_time']['report_period'],
        research_question_id='pending-finite-research', blocker_id='no-active-evidence-stop',
        reopen_condition_met=False, new_evidence_ids=[])
    return package_path, policy_path, request


def run(root, package, policy, request, **kwargs):
    return prepare_pending_research_candidate(root=root, package_path=package,
        package_sha256=sha256_file(package), policy_path=policy, policy_sha256=sha256_file(policy),
        choice_id='continuity', output_dir=root / 'runtime/pending',
        schedule_request=request, schedule_request_sha256='a' * 64,
        **kwargs)


def test_selected_inputs_are_consumed_by_actual_application_without_admission(
        tmp_path, synthetic_pending_candidate_clock):
    package, policy, request = candidate_inputs(tmp_path)
    before = package.read_bytes()
    result = run(tmp_path, package, policy, request)
    assert package.read_bytes() == before
    assert result['status'] == 'PENDING_REVIEW'
    from zoneinfo import ZoneInfo
    assert result['candidate_research_as_of'] == synthetic_pending_candidate_clock.astimezone(
        ZoneInfo('Asia/Shanghai')).date().isoformat()
    assert result['prior_research_as_of'] == '2026-09-22'
    assert result['price_admitted'] is result['registered_current_case_changed'] is False
    assert result['position_guidance'] is None
    work = json.loads((tmp_path / 'runtime/pending/workbench.json').read_text(encoding='utf-8'))
    objects = verify_current_decision_workbench(work).dependency_objects
    facts = artifact_payload(objects['financial_facts'])[1]
    candidate = json.loads((tmp_path / 'runtime/pending/package.json').read_text(encoding='utf-8'))
    assert len(candidate['facts']['scenario_inputs']['base']['forecast_roes']) == 15
    assert len(candidate['assumption_bindings']) == 19 * 3
    assert facts['operating_inputs'] == candidate['facts']['operating_inputs']
    assert facts['scenario_inputs']['base']['forecast_roes'] == candidate['facts']['scenario_inputs']['base']['forecast_roes']
    assert work['suggested_state'] == 'NO_ACTION'
    assert work['valuation']['status'] == 'conditional_research_only', work['valuation']['blockers']
    assert candidate['quote'] is None
    assert candidate['model_validity_input']['blockers']
    assert candidate['source_contract']['strict_contemporaneous_pit'] == 'NOT_PROVEN'
    assert (tmp_path / 'runtime/pending/consumed-review.json').is_file()
    assert Decimal(result['candidate_valuation']['base_value']) > 0


@pytest.mark.parametrize('change', ['choice', 'future-source', 'wrong-schedule', 'original-drift'])
def test_invalid_candidates_do_not_publish_or_write_a_candidate(tmp_path, change):
    package, policy, request = candidate_inputs(tmp_path)
    if change == 'choice':
        data = json.loads(policy.read_text(encoding='utf-8'))
        data['choices'][0]['id'] = 'not-continuity'
        policy.write_text(json.dumps(data), encoding='utf-8')
    elif change == 'future-source':
        data = json.loads(package.read_text(encoding='utf-8'))
        data['sources'][0]['source_available_at'] = '2099-09-24T00:00:00+08:00'
        data['sources'][0]['availability_basis'] = 'synthetic'
        package.write_text(json.dumps(data), encoding='utf-8')
        data = json.loads(policy.read_text(encoding='utf-8'))
        data['source_package_sha256'] = sha256_file(package)
        policy.write_text(json.dumps(data), encoding='utf-8')
    elif change == 'wrong-schedule':
        request['symbol'] = '000001'
    else:
        (tmp_path / 'runtime/original.md').write_text('drift', encoding='utf-8')
    with pytest.raises(ValueError):
        run(tmp_path, package, policy, request)
    assert not (tmp_path / 'runtime/pending/candidate.json').exists()


def test_candidate_keeps_active_scheduler_stop(tmp_path):
    package, policy, request = candidate_inputs(tmp_path)
    request['blocker_id'] = 'synthetic-stop'
    stop = dict(stop_id='synthetic-stop', symbol=request['symbol'], source_id='CNINFO',
        period=request['period'], research_question_id=request['research_question_id'],
        blocker_id='synthetic-stop', reviewed_evidence_ids=['facts'], reopen_condition='new official fact')
    (tmp_path / 'config/research-evidence-stop-ledger-v1.json').write_text(json.dumps(
        {'schema_version':'research-evidence-stop-ledger-v1', 'stops':[stop]}), encoding='utf-8')
    result = run(tmp_path, package, policy, request)
    assert result['candidate_valuation'] is None
    assert result['recommendation_type'] == 'NOT_READY'
    assert result['model_context_scope'] == 'PREPARED_NOT_CONSUMED'
    assert result['research_blockers']
    assert result['decision_blockers']
    assert result['schedule_gate']
    assert not (tmp_path / 'runtime/pending/consumed-review.json').exists()


@pytest.mark.parametrize('year', [2026, 2099])
def test_actual_candidate_rejects_backdated_or_future_injected_clock(tmp_path, year):
    package, policy, request = candidate_inputs(tmp_path)
    with pytest.raises(ValueError, match='injected computation time'):
        run(tmp_path, package, policy, request,
            computed_at=datetime(year, 9, 23, 12, tzinfo=timezone.utc))
    assert not (tmp_path / 'runtime/pending').exists()


def test_grouped_economic_review_is_pinned_visible_and_not_approval(tmp_path):
    from value_investment_agent.presentation.daily_trade_assistant import _render_pending_candidate_review
    package, policy, request = candidate_inputs(tmp_path)
    data = json.loads(policy.read_text(encoding='utf-8'))
    data['human_review_groups'] = [dict(id='earnings', question='Can historical earnings persist?',
        support='Synthetic disclosed historical profit.', countercase='Synthetic impairment risk.',
        impact='Pending forecast changes, not an admitted buy price.',
        field_paths=['facts.scenario_inputs', 'research_case.financial_summary'])]
    policy.write_text(json.dumps(data), encoding='utf-8')
    result = run(tmp_path, package, policy, request)
    path = tmp_path / 'runtime/pending/candidate.json'
    text = _render_pending_candidate_review(result, sha256_file(path))
    assert 'Can historical earnings persist?' in text
    assert 'Synthetic impairment risk.' in text
    assert 'VERIFIED/REJECTED/INSUFFICIENT' in text
    assert result['approval_changed'] is False
    verify_pending_research_candidate(root=tmp_path, path=path, expected_sha256=sha256_file(path))
    result['review_groups'][0]['countercase'] = 'No risks.'
    path.write_text(json.dumps(result), encoding='utf-8')
    with pytest.raises(ValueError, match='review questions differ'):
        verify_pending_research_candidate(root=tmp_path, path=path, expected_sha256=sha256_file(path))


@pytest.mark.parametrize('change', [None, 'source', 'context', 'values', 'approval'])
def test_candidate_surface_requires_the_exact_consumed_inputs_and_boundary(tmp_path, change):
    from value_investment_agent.presentation.research_supplement_surface import project_research_supplements

    package, policy, request = candidate_inputs(tmp_path)
    run(tmp_path, package, policy, request)
    path = tmp_path / 'runtime/pending/candidate.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    if change == 'source':
        (tmp_path / 'runtime/original.md').write_text('drift', encoding='utf-8')
    elif change == 'context':
        data['model_context']['facts_sha256'] = '0' * 64
    elif change == 'values':
        data['candidate_valuation']['base_value'] = '999999'
    elif change == 'approval':
        data['approval_changed'] = True
    if change not in {None, 'source'}:
        path.write_text(json.dumps(data), encoding='utf-8')
    binding = dict(role='pending_research_candidate', path='runtime/pending/candidate.json',
                   sha256=sha256_file(path))
    payload = dict(as_of='2026-09-22', companies=[dict(symbol=data['symbol'], evidence_refs=[],
        valuation=dict(status='NOT_READY'), decision_status='NO_ACTION')], audit=dict(evidence=[]))
    if change:
        with pytest.raises(ValueError):
            verify_pending_research_candidate(root=tmp_path, path=path, expected_sha256=sha256_file(path))
        with pytest.raises(ValueError):
            project_research_supplements(payload, root=tmp_path, symbol=data['symbol'], bindings=[binding])
    else:
        project_research_supplements(payload, root=tmp_path, symbol=data['symbol'], bindings=[binding])
        assert payload['as_of'] == '2026-09-22'
        assert payload['companies'][0]['decision_status'] == 'NO_ACTION'
        assert payload['companies'][0]['valuation'] == dict(status='NOT_READY')
        assert payload['companies'][0]['decision_review'][0]['label'] == '完整主估值候选待审'
