"""Synthetic review preparation does not manufacture economic approvals."""
import json

import pytest

pytestmark = pytest.mark.usefixtures('synthetic_pending_candidate_clock')

from test_pending_research_candidate import candidate_inputs, run
from test_pending_candidate_daily_isolation import _daily_inputs, _run_daily
from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.application.product.research_reviews import prepare_pending_review_intake, attach_research_reviews
from value_investment_agent.application.product.research_supplement_comparison import compare_research_supplements
from value_investment_agent.presentation.daily_trade_assistant import _render_pending_candidate_review
from value_investment_agent.application.product import daily_trade_assistant as daily
from value_investment_agent.presentation import daily_trade_assistant as view


def _candidate(root, duplicate=False):
    package, policy, request = candidate_inputs(root)
    payload = json.loads(policy.read_text(encoding='utf-8'))
    group = dict(id='EARNINGS', question='Accept this conditional earnings proxy?',
        support='Synthetic disclosed basis.', countercase='Normalization unknown.',
        impact='Conditional purpose only.', field_paths=['facts.operating_inputs'])
    payload['human_review_groups'] = [group, group] if duplicate else [group]
    policy.write_text(json.dumps(payload), encoding='utf-8')
    result = run(root, package, policy, request)
    return root / 'runtime/pending/candidate.json', result


def test_intake_binds_actual_valuation_and_stable_group_without_approval(tmp_path):
    path, candidate = _candidate(tmp_path)
    result = prepare_pending_review_intake(root=tmp_path, candidate_path=path,
        candidate_sha256=sha256_file(path))
    assert result['groups'][0]['id'] == 'EARNINGS'
    assert result['groups'][0]['response'] is None
    assert result['reviewer'] is result['whole_model_decision'] is None
    assert result['model_context'] == candidate['model_context']
    assert len(result['valuation_artifact_sha256']) == 64
    assert result['valuation_artifact_sha256'] != sha256_file(path.parent / 'workbench.json')
    assert result['approval_changed'] is result['research_admitted'] is result['price_admitted'] is False
    assert '编号：EARNINGS' in _render_pending_candidate_review(candidate, sha256_file(path))
    from value_investment_agent.m1_valuation_package_builder import build_descriptor
    from value_investment_agent.research_input import build_research_run_spec
    descriptor = build_descriptor(json.loads((path.parent / 'package.json').read_text(encoding='utf-8')), root=tmp_path)
    intake_path = tmp_path / 'runtime/intake.json'
    intake_path.write_text(json.dumps(result), encoding='utf-8')
    with pytest.raises(ValueError, match='scope mismatch'):
        attach_research_reviews(root=tmp_path, descriptor=descriptor,
            spec=build_research_run_spec(descriptor), path=intake_path,
            expected_sha256=sha256_file(intake_path), event_sha256=None)


def test_intake_rejects_duplicate_group_identity(tmp_path):
    path, _ = _candidate(tmp_path, duplicate=True)
    with pytest.raises(ValueError, match='unique'):
        prepare_pending_review_intake(root=tmp_path, candidate_path=path,
            candidate_sha256=sha256_file(path))


def test_candidate_comparison_replays_actual_inputs_and_rejects_tampered_value(tmp_path):
    path, candidate = _candidate(tmp_path)
    binding = dict(path=path.relative_to(tmp_path).as_posix(), sha256=sha256_file(path))
    receipt = tmp_path / 'runtime/prior.json'
    receipt.write_text(json.dumps(dict(schema_version='daily-trade-assistant-receipt-v1',
        symbol=candidate['symbol'], action='no_order', outputs={'pending_research_candidate': binding})), encoding='utf-8')
    result = compare_research_supplements(root=tmp_path, symbol=candidate['symbol'],
        current_bindings=[dict(role='pending_research_candidate', **binding)],
        previous_receipt_path=receipt, previous_receipt_sha256=sha256_file(receipt))
    assert result['roles']['pending_research_candidate']['status'] == 'UNCHANGED'
    assert result['current_admission'] is result['approval_changed'] is False
    candidate['candidate_valuation']['base_value'] = '123456'
    path.write_text(json.dumps(candidate), encoding='utf-8')
    with pytest.raises(ValueError, match='differs'):
        compare_research_supplements(root=tmp_path, symbol=candidate['symbol'],
            current_bindings=[dict(role='pending_research_candidate', path=binding['path'], sha256=sha256_file(path))])


def test_daily_monthly_review_compares_registered_and_consumed_candidate(tmp_path):
    _, _, _, _, case = _daily_inputs(tmp_path)
    case['monthly_review'] = True
    result = _run_daily(tmp_path, case)
    binding = result['outputs']['pending_candidate_monthly_review']
    monthly = json.loads((tmp_path / binding['path']).read_text(encoding='utf-8'))
    assert monthly['previous_research_as_of'] == '2026-09-22'
    assert monthly['current_research_as_of'] != monthly['previous_research_as_of']
    assert monthly['comparison_status'] == 'COMPARED'
    assert monthly['current_admission'] is monthly['approval_changed'] is False
    assert 'pending_review_intake' in result['outputs']
    report = (tmp_path / 'runtime/daily-isolation/report.md').read_text(encoding='utf-8')
    assert '不是已经经历一个月' in report


@pytest.mark.parametrize('failure', ['duplicate-id', 'write-error'])
def test_optional_intake_failure_preserves_daily_report_and_receipt(tmp_path, monkeypatch, failure):
    _, policy, _, _, case = _daily_inputs(tmp_path)
    if failure == 'duplicate-id':
        data = json.loads(policy.read_text(encoding='utf-8'))
        group = dict(id='DUPLICATE', question='Synthetic question', support='Synthetic basis',
            countercase='Unknown', impact='Conditional only', field_paths=['facts.operating_inputs'])
        data['human_review_groups'] = [group, group]
        policy.write_text(json.dumps(data), encoding='utf-8')
        case['valuation_proposal_policy_sha256'] = sha256_file(policy)
    else:
        original = daily.write_new_json
        def fail_intake(path, payload):
            if path.name == 'review-intake.json':
                raise OSError('Synthetic intake write failure')
            return original(path, payload)
        monkeypatch.setattr(daily, 'write_new_json', fail_intake)
    result = _run_daily(tmp_path, case)
    assert 'report' in result['outputs'] and 'pending_review_intake' in result['outputs']
    error = json.loads((tmp_path / result['outputs']['pending_review_intake']['path']).read_text(encoding='utf-8'))
    assert error['status'] == 'RESEARCH_SUPPLEMENT_UNAVAILABLE'
    assert error['approval_changed'] is False
    assert '审核回答入口尚不可用' in (tmp_path / 'runtime/daily-isolation/report.md').read_text(encoding='utf-8')


def test_machine_readable_intake_does_not_require_markdown_callback(tmp_path):
    _, _, _, _, case = _daily_inputs(tmp_path)
    result = daily.run_daily_trade_assistant(root=tmp_path, symbol='600887', case=case,
        output_dir=tmp_path / 'runtime/no-renderer', agent_mode='none', report_renderer=view._render_report,
        supplement_renderer=view._render_supplements)
    assert 'pending_review_intake' in result['outputs']
    assert 'pending_candidate_review_report' not in result['outputs']
