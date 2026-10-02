from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from value_investment_agent.operations.start_criteria import (
    CLASSIFICATIONS,
    SHADOW_START_GATES,
    load_m6_start_criteria_matrix,
    m6_start_criteria_matrix_from_payload,
)


ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = ROOT / "config" / "m6-start-criteria-matrix-v1.json"


def test_daily_input_consistency_never_grants_shadow_count(tmp_path, monkeypatch):
    from datetime import datetime, date
    from types import SimpleNamespace
    import hashlib
    from value_investment_agent.operations import shadow_daily_input as module
    def bind(name, value):
        path = tmp_path / (name + '.json')
        path.write_text(json.dumps(value), encoding='utf-8')
        return dict(path=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                    observed_at='2026-09-30T15:10:00+08:00')
    bindings = {role: bind(role, dict(action='no_order', run_id='test-run',
        session_date='2026-09-30', generated_at='2026-09-30T15:10:00+08:00',
        suggested_state='NOT_READY')) for role in module.ROLES}
    original = bind('original', dict(observation='synthetic isolated fixture'))
    bindings['event'] = bind('event', dict(action='no_order', simulation_only=False,
        observed_at='2026-09-30T15:10:00+08:00', scan_as_of='2026-09-30T15:10:00+08:00',
        coverage_complete=True, symbols=['600887'], source_bindings=[original]))
    bindings['run_receipt'] = bind('run_receipt', dict(action='no_order', run_id='test-run',
        simulation_only=False, session_date='2026-09-30', node_sequence=list(module.DAG_NODES),
        input_hashes={key: bindings[key]['sha256'] for key in ('quote', 'event')},
        output_hashes={key: bindings[key]['sha256'] for key in ('research', 'model', 'decision', 'portfolio', 'product')}))
    manifest = dict(schema_version='shadow-daily-input-v1', session_date='2026-09-30',
        generated_at='2026-09-30T15:11:00+08:00', symbols=['600887'], bindings=bindings, action='no_order')
    request = bind('manifest', manifest)
    monkeypatch.setattr(module, 'quote_snapshot_from_bundle_file', lambda *a, **k:
        SimpleNamespace(status='verified_close', quote_date=date(2026, 9, 30)))
    def audit():
        return module.audit_shadow_daily_input(root=tmp_path, path=tmp_path/request['path'],
            expected_sha256=request['sha256'], now=datetime.fromisoformat('2026-09-30T15:12:00+08:00'))
    result = audit()
    assert result['input_consistency_status'] == 'SHADOW_INPUT_INCOMPLETE'
    assert 'SHARED_RESEARCH_DAILY_INPUT_CONSUMPTION_NOT_PROVEN' in result['blockers']
    assert 'DAG_EXECUTION_INCOMPLETE' in result['blockers']
    assert result['shadow_session_valid'] is False
    assert result['verified_real_session_count'] == 0
    (tmp_path / 'decision.json').write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='hash mismatch'):
        audit()


def _payload() -> dict[str, object]:
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))


def test_isolated_attempt_runs_shared_scheduler_and_seals_refusal(tmp_path):
    import shutil
    import hashlib
    from value_investment_agent.operations.shadow_daily_run import run_isolated_daily_attempt
    (tmp_path / 'config').mkdir()
    shutil.copyfile(ROOT / 'config/research-evidence-stop-ledger-v1.json',
                    tmp_path / 'config/research-evidence-stop-ledger-v1.json')
    event = tmp_path / 'event.json'
    event.write_text(json.dumps(dict(symbol='600887', action='no_order', scope='SYNTHETIC_TEST_ONLY')), encoding='utf-8')
    digest = hashlib.sha256(event.read_bytes()).hexdigest()
    output = tmp_path / 'runtime/isolated'
    result = run_isolated_daily_attempt(root=tmp_path, output=output, symbol='600887',
                                        event_path=event, event_sha256=digest)
    assert result['dag_execution_complete'] is False
    receipt = json.loads((output / 'run_receipt.json').read_text(encoding='utf-8'))
    assert receipt['node_sequence'] == ['research', 'product']
    assert receipt['verified_real_session_count'] == 0
    assert 'MISSING_DAG_ARTIFACT:quote' in result['audit']['blockers']
    research = json.loads((output / 'research.json').read_text(encoding='utf-8'))
    assert research['result']['status'] == 'BLOCKED_BY_RESEARCH_SCHEDULER'
    assert (output / 'event.json').read_bytes() == event.read_bytes()
    card = (output / 'company-card.md').read_text(encoding='utf-8')
    assert '600887' in card and 'action=no_order' in card
    assert '本次研究未形成估值结果' in card
    before = (output / 'input.json').read_bytes()
    with pytest.raises(ValueError, match='new runtime'):
        run_isolated_daily_attempt(root=tmp_path, output=output, symbol='600887',
                                  event_path=event, event_sha256=digest)
    assert (output / 'input.json').read_bytes() == before


def test_isolated_normal_result_preserves_models_without_promoting_missing_decision(tmp_path, monkeypatch):
    import hashlib
    from value_investment_agent.operations import shadow_daily_run as module
    event = tmp_path / 'event.json'
    event.write_text('{"symbol":"600887"}', encoding='utf-8')
    monkeypatch.setattr(module, 'run_company_research_for_symbol', lambda **kwargs:
        dict(result=dict(symbol='600887', action='no_order', status='COMPLETED_WITH_BLOCKERS',
            run_id='shared-run', blockers=['not approved'],
            model_validity=dict(status='UNKNOWN'), price_bridge=dict(bridge_status='PENDING_EXTERNAL_DATA'),
            valuation=dict(base_value='11'), pre_decision_eligibility=None), receipt={}))
    output = tmp_path / 'runtime/normal'
    result = module.run_isolated_daily_attempt(root=tmp_path, output=output, symbol='600887',
        event_path=event, event_sha256=hashlib.sha256(event.read_bytes()).hexdigest())
    model = json.loads((output/'model.json').read_text(encoding='utf-8'))
    assert model['valuation_result']['base_value'] == '11'
    assert model['model_validity']['status'] == 'UNKNOWN'
    decision = json.loads((output/'decision.json').read_text(encoding='utf-8'))
    assert decision['blockers'] == ['PREDECISION_INPUT_NOT_ESTABLISHED']
    assert decision['suggested_state'] == 'NOT_READY'
    assert result['audit']['verified_real_session_count'] == 0


@pytest.mark.parametrize('missing_node', [None, 'price_bridge', 'decision_gate', 'portfolio_gate'])
def test_daily_execution_completeness_is_not_operational_admission(tmp_path, monkeypatch, missing_node):
    import hashlib
    from datetime import datetime, timezone, timedelta
    from value_investment_agent.operations import shadow_daily_run as module
    from value_investment_agent.pre_decision_eligibility import PreDecisionEligibility, STATUS_NOT_ELIGIBLE

    # Only the shared research result is a synthetic seam; decision/risk engines run.
    day = datetime.now(timezone(timedelta(hours=8))).date()
    predecision = PreDecisionEligibility(symbol='600887', decision_as_of=day,
        status=STATUS_NOT_ELIGIBLE, approval_status='REJECTED_NEEDS_REWORK',
        model_validity_status='NOT_ESTABLISHED', price_bridge_status='PENDING_EXTERNAL_DATA',
        event_review_watermark=day, blockers=('SYNTHETIC_RESEARCH_NOT_APPROVED',),
        evidence_refs=({'id': 'synthetic-test-only'},))
    monkeypatch.setattr(module, 'run_company_research_for_symbol', lambda **kwargs:
        dict(result=dict(symbol='600887', action='no_order', status='COMPLETED_WITH_BLOCKERS',
            run_id='synthetic-shared-run', blockers=['SYNTHETIC_RESEARCH_NOT_APPROVED'],
            model_validity=dict(status='NOT_ESTABLISHED'),
            price_bridge=None if missing_node == 'price_bridge' else dict(bridge_status='PENDING_EXTERNAL_DATA'),
            valuation=None,
            pre_decision_eligibility=None if missing_node == 'decision_gate' else predecision.as_policy()),
            receipt={}))
    event = tmp_path / 'event.json'
    event.write_text('{"symbol":"600887","scope":"SYNTHETIC_TEST_ONLY"}', encoding='utf-8')
    portfolio = tmp_path / 'simulation.json'
    portfolio.write_bytes((ROOT / 'tests/fixtures/m4_portfolio_risk_demo.json').read_bytes())
    output = tmp_path / 'runtime/completeness'
    kwargs = {} if missing_node == 'portfolio_gate' else dict(
        simulated_portfolio_path=portfolio,
        simulated_portfolio_sha256=hashlib.sha256(portfolio.read_bytes()).hexdigest())
    result = module.run_isolated_daily_attempt(root=tmp_path, output=output, symbol='600887',
        event_path=event, event_sha256=hashlib.sha256(event.read_bytes()).hexdigest(), **kwargs)
    receipt = json.loads((output / 'run_receipt.json').read_text(encoding='utf-8'))
    assert result['dag_execution_complete'] is (missing_node is None)
    assert receipt['dag_execution_complete'] is (missing_node is None)
    if missing_node is None:
        assert receipt['node_sequence'] == list(module.DAG_NODES)
        assert receipt['skipped_nodes'] == []
    else:
        assert missing_node in receipt['skipped_nodes']
    for role in ('research', 'model', 'decision', 'portfolio', 'product'):
        payload = json.loads((output / (role + '.json')).read_text(encoding='utf-8'))
        assert payload['generated_at'] == receipt['generated_at']
        assert datetime.fromisoformat(payload['generated_at']) <= datetime.fromisoformat(receipt['completed_at'])
        if role == 'decision' and 'review' in payload:
            assert datetime.fromisoformat(payload['review']['created_at']) <= datetime.fromisoformat(payload['generated_at'])
    assert receipt['verified_real_session_count'] == 0
    assert result['audit']['shadow_session_valid'] is False
    assert result['audit']['verified_real_session_count'] == 0
    assert receipt['action'] == 'no_order'


@pytest.mark.parametrize('payload', [{}, {'symbol': '000333'}, []])
def test_isolated_attempt_rejects_missing_or_foreign_event_issuer(tmp_path, payload):
    import hashlib
    from value_investment_agent.operations.shadow_daily_run import run_isolated_daily_attempt
    event = tmp_path / 'event.json'
    event.write_text(json.dumps(payload), encoding='utf-8')
    output = tmp_path / 'runtime/rejected'
    with pytest.raises(ValueError, match='issuer mismatch'):
        run_isolated_daily_attempt(root=tmp_path, output=output, symbol='600887',
            event_path=event, event_sha256=hashlib.sha256(event.read_bytes()).hexdigest())
    assert not output.exists()


def test_isolated_attempt_snapshots_and_forwards_explicit_research_inputs(tmp_path, monkeypatch):
    import hashlib
    from value_investment_agent.operations import shadow_daily_run as module
    def source(name, payload):
        path = tmp_path / (name + '.json')
        path.write_text(json.dumps(payload), encoding='utf-8')
        return path, hashlib.sha256(path.read_bytes()).hexdigest()
    event, event_hash = source('event', {'symbol': '600887'})
    package, package_hash = source('package', {'symbol': '600887', 'fixture': True})
    request, request_hash = source('request', {'symbol': '600887', 'fixture': True})
    captured = {}
    def shared(**kwargs):
        captured.update(kwargs)
        assert kwargs['package_path'].read_bytes() == package.read_bytes()
        return dict(result=dict(symbol='600887', action='no_order',
            status='BLOCKED_BY_RESEARCH_SCHEDULER', blockers=['fixture refusal']), receipt={})
    monkeypatch.setattr(module, 'run_company_research_for_symbol', shared)
    output = tmp_path / 'runtime/explicit'
    result = module.run_isolated_daily_attempt(root=tmp_path, output=output, symbol='600887',
        event_path=event, event_sha256=event_hash, package_path=package,
        package_sha256=package_hash, schedule_request_path=request,
        schedule_request_sha256=request_hash)
    assert captured['package_path'] == output / 'valuation_package.json'
    assert captured['event_path'] == output / 'event.json'
    assert captured['event_sha256'] == event_hash
    assert captured['schedule_request'] == json.loads(request.read_text(encoding='utf-8'))
    assert captured['schedule_request_sha256'] == request_hash
    research = json.loads((output / 'research.json').read_text(encoding='utf-8'))
    assert research['research_input_bindings']['valuation_package']['sha256'] == package_hash
    assert research['research_input_bindings']['schedule_request']['sha256'] == request_hash
    assert research['research_input_bindings']['valuation_package']['consumption_status'] == 'SNAPSHOTTED_NOT_CONSUMED_BY_SHARED_RESEARCH'
    manifest = json.loads((output / 'input.json').read_text(encoding='utf-8'))
    assert 'schedule_request' not in manifest['bindings']
    assert result['audit']['verified_real_session_count'] == 0


def test_isolated_request_without_explicit_package_is_rejected(tmp_path):
    from value_investment_agent.operations.shadow_daily_run import run_isolated_daily_attempt
    with pytest.raises(ValueError, match='explicit source-bound package'):
        run_isolated_daily_attempt(root=tmp_path, output=tmp_path / 'runtime/rejected',
            symbol='600887', event_path=tmp_path / 'unused', event_sha256='unused',
            schedule_request_path=tmp_path / 'request', schedule_request_sha256='unused')
    assert not (tmp_path / 'runtime/rejected').exists()


@pytest.mark.parametrize('matched', [True, False])
def test_daily_company_card_keeps_source_explanation_separate_from_admission(tmp_path, monkeypatch, matched):
    import hashlib
    from value_investment_agent.operations import shadow_daily_run as module
    event = tmp_path / 'event.json'
    event.write_text('{"symbol":"600887"}', encoding='utf-8')
    event_hash = hashlib.sha256(event.read_bytes()).hexdigest()
    followup = tmp_path / 'followup.json'
    followup.write_text(json.dumps(dict(event_scan=dict(sha256=event_hash if matched else 'wrong'))), encoding='utf-8')
    followup_hash = hashlib.sha256(followup.read_bytes()).hexdigest()
    monkeypatch.setattr(module, 'read_event_followup', lambda **kwargs:
        dict(symbol='600887', rows={'测试原文事实': '已披露；原件：https://example.test/filing'},
             unresolved_questions=['仍缺支付后现金证据'], sha256=followup_hash))
    monkeypatch.setattr(module, 'run_company_research_for_symbol', lambda **kwargs:
        dict(result=dict(symbol='600887', action='no_order', status='BLOCKED_BY_RESEARCH_SCHEDULER',
                         blockers=['evidence stop']), receipt={}))
    output = tmp_path / 'runtime/explained'
    kwargs = dict(root=tmp_path, output=output, symbol='600887', event_path=event,
        event_sha256=event_hash, followup_path=followup, followup_sha256=followup_hash)
    if not matched:
        with pytest.raises(ValueError, match='acquired event scan'):
            module.run_isolated_daily_attempt(**kwargs)
        assert not output.exists()
        return
    result = module.run_isolated_daily_attempt(**kwargs)
    card = (output / 'company-card.md').read_text(encoding='utf-8')
    assert '测试原文事实' in card and '仍缺支付后现金证据' in card
    assert 'evidence stop' in card and 'NOT_READY' in card
    assert (output / 'event_followup.json').read_bytes() == followup.read_bytes()
    assert result['audit']['verified_real_session_count'] == 0


@pytest.mark.parametrize('unsafe', [False, True])
def test_partial_daily_audit_checks_present_outputs_even_without_quote(tmp_path, unsafe):
    import hashlib
    from datetime import datetime
    from value_investment_agent.operations.shadow_daily_input import audit_shadow_daily_input
    decision = dict(action='no_order', run_id='partial', session_date='2026-10-02',
        generated_at='2026-10-02T10:00:00+08:00', suggested_state='NOT_READY',
        orders=[{'symbol': '600887'}] if unsafe else [])
    path = tmp_path / 'decision.json'
    path.write_text(json.dumps(decision), encoding='utf-8')
    binding = dict(path=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                   observed_at='2026-10-02T10:00:00+08:00')
    manifest = tmp_path / 'input.json'
    manifest.write_text(json.dumps(dict(schema_version='shadow-daily-input-v1',
        action='no_order', symbols=['600887'], session_date='2026-10-02',
        generated_at='2026-10-02T10:01:00+08:00', bindings={'decision': binding})), encoding='utf-8')
    kwargs = dict(root=tmp_path, path=manifest,
        expected_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
        now=datetime.fromisoformat('2026-10-02T10:02:00+08:00'))
    if unsafe:
        with pytest.raises(ValueError, match='must not produce orders'):
            audit_shadow_daily_input(**kwargs)
        return
    result = audit_shadow_daily_input(**kwargs)
    assert 'MISSING_DAG_ARTIFACT:quote' in result['blockers']
    assert 'DECISION_RUN_ID_MISMATCH' in result['blockers']
    assert result['binding_hashes']['decision'] == binding['sha256']
    assert result['verified_real_session_count'] == 0


def test_daily_event_projection_preserves_missing_watermark_and_verifies_originals(tmp_path):
    import hashlib
    from datetime import datetime
    from value_investment_agent.application.product.daily_event_input import project_daily_event_input
    original = tmp_path / 'index.json'
    original.write_text('{}', encoding='utf-8')
    original_hash = hashlib.sha256(original.read_bytes()).hexdigest()
    raw = dict(schema_version='m1-event-scan-v1', symbol='600887', provider='CNINFO',
        scan_from='2026-10-02', scan_to='2026-10-02', validity_from='2026-10-02',
        validity_to='2026-10-02', status='COMPLETE_NO_MATERIAL_EVENT_IN_VALIDITY_WINDOW',
        coverage_status='COMPLETE', pre_model_review_status='NONE', announcements=[],
        blockers=[], evidence_refs=[dict(id='index', path='index.json', sha256=original_hash)],
        retrieved_at='2026-10-02T16:00:00+08:00', parser_version='test-only')
    path = tmp_path / 'scan.json'
    path.write_text(json.dumps(raw), encoding='utf-8')
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    def project():
        return project_daily_event_input(root=tmp_path, path=path, expected_sha256=digest,
            symbol='600887', now=datetime.fromisoformat('2026-10-02T16:01:00+08:00'))
    result = project()
    assert result['coverage_status'] == 'COMPLETE'
    assert result['coverage_complete'] is False
    assert result['scan_cutoff_basis'] == 'ACQUISITION_ONLY_NOT_COVERAGE_CUTOFF'
    assert result['materiality_approved'] is False
    assert result['source_bindings'][1]['sha256'] == original_hash
    original.write_text('{"changed":true}', encoding='utf-8')
    with pytest.raises(ValueError, match='original hash mismatch'):
        project()


def test_daily_risk_rehearsal_uses_existing_engine_and_rejects_actual_namespace(tmp_path):
    import hashlib
    from datetime import datetime
    from value_investment_agent.application.portfolio.daily_risk_rehearsal import evaluate_daily_risk_rehearsal
    payload = json.loads((ROOT / 'tests/fixtures/m4_portfolio_risk_demo.json').read_text(encoding='utf-8'))
    path = tmp_path / 'simulation.json'
    def run():
        path.write_text(json.dumps(payload), encoding='utf-8')
        return evaluate_daily_risk_rehearsal(root=tmp_path, path=path,
            expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            now=datetime.fromisoformat('2026-10-02T14:00:00+08:00'), assessment_id='test-simulated-risk')
    result = run()
    assert result['simulation_only'] is True
    assert result['personal_capacity_confirmed'] is False
    assert result['position_guidance'] is None
    assert result['input_as_of'] == '2026-09-22'
    assert result['risk_assessment']['findings']
    assert result['risk_assessment']['assessment_namespace'] == 'SIMULATED'
    payload['snapshot']['namespace'] = 'ACTUAL'
    with pytest.raises(ValueError, match='SIMULATED risk demos only'):
        run()


@pytest.mark.parametrize('matched', [True, False])
def test_daily_consumer_intersects_existing_admission_with_exact_artifact(tmp_path, monkeypatch, matched):
    import hashlib
    from datetime import datetime
    from value_investment_agent.operations import shadow_daily_input as module
    from value_investment_agent import m6_shadow_admission
    def store(name, value):
        path = tmp_path / (name + '.json')
        path.write_text(json.dumps(value), encoding='utf-8')
        return dict(path=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    receipt = store('receipt', {'run_id': 'run'})
    daily = store('daily', dict(bindings={'run_receipt': receipt},
        generated_at='2026-10-02T16:00:00+08:00'))
    day = '2026-10-02'
    monkeypatch.setattr(module, 'audit_shadow_daily_input', lambda **kwargs:
        dict(session_date=day, blockers=[], input_consistency_status='PASS', action='no_order'))
    verified_calls = []
    def verify(*args, **kwargs):
        verified_calls.append(kwargs)
        return {day: 'synthetic-signature-verifier-result'}
    monkeypatch.setattr(m6_shadow_admission, 'verify_operational_shadow_bundle', verify)
    refs = {
        'bundle': store('bundle', dict(candidate_bundle=dict(sessions=[dict(session=dict(payload=dict(
            session_date=day, run_id='run', artifact_sha256=daily['sha256'] if matched else 'wrong',
            started_at='2026-10-02T15:50:00+08:00', completed_at='2026-10-02T16:01:00+08:00')))]))),
        'trust_root': store('trust', {}), 'schedule': store('schedule', {}),
    }
    request = store('request', dict(schema_version='shadow-daily-consumer-inputs-v1', action='no_order', bindings=refs))
    result = module.consume_shadow_daily_input(root=tmp_path, path=tmp_path/daily['path'],
        expected_sha256=daily['sha256'], now=datetime.fromisoformat('2026-10-02T16:02:00+08:00'),
        operational_inputs=tmp_path/request['path'], operational_inputs_sha256=request['sha256'])
    assert verified_calls == [{'required_sessions': 20, 'required_events': 1}]
    assert result['verified_real_session_count'] == (1 if matched else 0)
    assert result['daily_consumer_status'] == ('ADMITTED' if matched else 'NOT_ADMITTED')
    # All inputs and the signature verifier above are synthetic test fixtures only.


def test_daily_attempt_seals_known_input_rejection_without_swallowing_programming_errors(tmp_path, monkeypatch):
    import hashlib
    from value_investment_agent.operations import shadow_daily_run as module
    event = tmp_path / 'event.json'
    event.write_text('{"symbol":"600887"}', encoding='utf-8')
    kwargs = dict(root=tmp_path, symbol='600887', event_path=event,
                  event_sha256=hashlib.sha256(event.read_bytes()).hexdigest())
    def rejected(**kwargs):
        raise module.ResearchInputValidationError('Quote date cannot follow research as-of')
    monkeypatch.setattr(module, 'run_company_research_for_symbol', rejected)
    output = tmp_path / 'runtime/rejected-input'
    result = module.run_isolated_daily_attempt(output=output, **kwargs)
    research = json.loads((output / 'research.json').read_text(encoding='utf-8'))
    assert research['result']['status'] == 'REJECTED_BY_INPUT_VALIDATION'
    assert research['application_receipt']['reopen_consumed'] is False
    assert 'Quote date cannot follow research as-of' in (output / 'company-card.md').read_text(encoding='utf-8')
    assert result['audit']['verified_real_session_count'] == 0
    assert (output / 'run_receipt.json').exists()
    def programming_error(**kwargs):
        raise RuntimeError('unexpected bug')
    monkeypatch.setattr(module, 'run_company_research_for_symbol', programming_error)
    with pytest.raises(RuntimeError, match='unexpected bug'):
        module.run_isolated_daily_attempt(output=tmp_path / 'runtime/bug', **kwargs)
    assert not (tmp_path / 'runtime/bug/run_receipt.json').exists()


def test_daily_projection_rejects_model_or_product_from_different_research():
    from value_investment_agent.operations.shadow_daily_input import _research_projection_blockers
    result = dict(symbol='600887', action='no_order', model_validity={'status': 'UNKNOWN'},
                  price_bridge={'bridge_status': 'PENDING_EXTERNAL_DATA'}, valuation={'base_value': '10'})
    artifacts = dict(research=dict(result=result, application_receipt=dict(action='no_order',
        input_sha256=dict(valuation_package='package', quote='quote', event='raw-event'))),
        event=dict(raw_scan=dict(sha256='raw-event')),
        model=dict(model_validity=result['model_validity'], price_bridge=result['price_bridge'],
                   valuation_result=result['valuation']),
        decision=dict(suggested_state='NOT_READY', blockers=['not ready']),
        product=dict(symbol='600887', suggested_state='NOT_READY', blockers=['not ready']))
    def check():
        return _research_projection_blockers(artifacts, {'quote': 'quote', 'event': 'projection'},
                                              ['600887'], '2026-10-02')
    assert 'SHARED_RESEARCH_DAILY_INPUT_CONSUMPTION_NOT_PROVEN' not in check()
    assert not any(item.startswith('MODEL_RESEARCH_PROJECTION_MISMATCH') for item in check())
    artifacts['model']['valuation_result'] = {'base_value': '20'}
    artifacts['product']['suggested_state'] = 'MANUAL_BUY_REVIEW'
    assert 'MODEL_RESEARCH_PROJECTION_MISMATCH:valuation_result' in check()
    assert 'PRODUCT_DECISION_PROJECTION_MISMATCH' in check()


def _criteria_by_id():
    matrix = load_m6_start_criteria_matrix(MATRIX_PATH, root=ROOT)
    return {item.criterion_id: item for item in matrix.criteria}


def test_m6_matrix_uses_exact_enums_and_remains_not_started_without_authorization():
    payload = _payload()
    matrix = load_m6_start_criteria_matrix(MATRIX_PATH, root=ROOT)
    policy = matrix.as_policy()

    assert set(payload["classification_legend"]) == CLASSIFICATIONS
    assert set(payload["shadow_start_gate_legend"]) == SHADOW_START_GATES
    assert {item.classification for item in matrix.criteria} == CLASSIFICATIONS
    assert {item.shadow_start_gate for item in matrix.criteria} == SHADOW_START_GATES
    assert policy["M6_OPERATIONAL"] == "NOT_STARTED"
    assert policy["production_authorization_requested"] is False
    assert policy["production_authorization_granted"] is False
    assert policy["shadow_start_allowed"] is False
    assert policy["decision"] == "BLOCKED_PENDING_HARD_START_GATES"
    assert policy["action"] == "no_order"
    hard = [item for item in matrix.criteria if item.shadow_start_gate == "HARD_START_GATE"]
    assert hard
    assert all(item.current_satisfied is False for item in hard)


def test_m6_matrix_separates_hard_product_gates_from_research_and_natural_time():
    criteria = _criteria_by_id()

    assert criteria["m3_strict_contemporaneous_pit"].shadow_start_gate == "HARD_START_GATE"
    assert criteria["m4_confirmed_private_portfolio"].shadow_start_gate == "HARD_START_GATE"
    assert criteria["m5_product_event_loop"].shadow_start_gate == "HARD_START_GATE"
    assert criteria["m6c5_twenty_real_sessions"].shadow_start_gate == "NATURAL_TIME_GATE"
    assert criteria["m6c14_one_real_event"].shadow_start_gate == "NATURAL_TIME_GATE"
    assert criteria["m6c15_operational_acceptance"].shadow_start_gate == "NATURAL_TIME_GATE"
    assert criteria["m7_product_ux_candidate"].shadow_start_gate == "SOFT_PRODUCT_GAP"

    issuer_evidence = criteria["moutai_600519_scenario_evidence"]
    issuer_history = criteria["moutai_600519_historical_validation"]
    assert issuer_evidence.classification == "RESEARCH_EVIDENCE_REQUIRED"
    assert issuer_evidence.shadow_start_gate == "NOT_RELEVANT_TO_SHADOW_START"
    assert issuer_history.classification == "RESEARCH_EVIDENCE_REQUIRED"
    assert issuer_history.shadow_start_gate == "NOT_RELEVANT_TO_SHADOW_START"


def test_m6_matrix_rejects_authorization_request_or_unknown_classification():
    request = _payload()
    request["production_authorization_requested"] = True
    with pytest.raises(ValueError, match="must not request"):
        m6_start_criteria_matrix_from_payload(request)

    unknown = _payload()
    unknown["criteria"][0]["classification"] = "UNKNOWN"
    with pytest.raises(ValueError, match="Unknown M6 criterion classification"):
        m6_start_criteria_matrix_from_payload(unknown)


def test_m6_start_criteria_cli_is_read_only_and_prints_the_matrix():
    script = ROOT / "scripts" / "current" / "audit_m6_start_criteria.py"
    completed = subprocess.run(
        [sys.executable, str(script)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["M6_OPERATIONAL"] == "NOT_STARTED"
    assert payload["production_authorization_requested"] is False
    assert payload["production_authorization_granted"] is False
    assert payload["shadow_start_allowed"] is False
    assert payload["action"] == "no_order"
    assert payload["state_semantics"] == "STATIC_BASELINE_NOT_CURRENT_READINESS"
    assert payload["current_status_source"] == "latest verified m6 operational preflight receipt"
    assert '"user_to_authorize":' not in completed.stdout


def test_static_matrix_declares_that_its_false_values_are_baseline_only():
    raw = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    assert raw["state_semantics"] == "STATIC_BASELINE_NOT_CURRENT_READINESS"
    assert raw["current_status_source"] == "latest verified m6 operational preflight receipt"


def _with_all_hard_gates_satisfied() -> dict[str, object]:
    payload = _payload()
    for item in payload["criteria"]:
        if item["shadow_start_gate"] == "HARD_START_GATE":
            item["current_satisfied"] = True
    return payload


def test_m6_matrix_can_represent_a_startable_shadow_decision():
    payload = _with_all_hard_gates_satisfied()
    payload["shadow_start_allowed"] = True
    payload["decision"] = "SHADOW_START_READY"

    policy = m6_start_criteria_matrix_from_payload(payload).as_policy()
    assert policy["shadow_start_allowed"] is True
    assert policy["decision"] == "SHADOW_START_READY"
    assert policy["M6_OPERATIONAL"] == "NOT_STARTED"
    assert policy["production_authorization_granted"] is False
    assert (
        policy["summary"]["hard_start_gates_satisfied"]
        == policy["summary"]["hard_start_gates"]
    )


def test_m6_matrix_rejects_a_contradictory_shadow_start_decision():
    startable = _with_all_hard_gates_satisfied()
    startable["shadow_start_allowed"] = True
    with pytest.raises(ValueError, match="SHADOW_START_READY"):
        m6_start_criteria_matrix_from_payload(startable)

    blocked = _payload()
    blocked["decision"] = "SHADOW_START_READY"
    with pytest.raises(ValueError, match="BLOCKED_PENDING_HARD_START_GATES"):
        m6_start_criteria_matrix_from_payload(blocked)
