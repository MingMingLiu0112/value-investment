"""Direct native-task tests; synthetic mechanisms and opt-in real sources are separate."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import threading
from uuid import uuid4

import pytest

from value_investment_agent.application.research import transparent_task_v1 as mod
from test_operating_profit_cash_path_v1 import inputs as compiler_inputs


def put(root, name, value):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(mod.base._bytes(value))
    return dict(path=name, sha256=hashlib.sha256(path.read_bytes()).hexdigest())


@pytest.fixture
def case(tmp_path):
    service = mod.TransparentTaskService(tmp_path)
    ref = put(tmp_path, 'runtime/public-evidence/test/bundle.json', {'synthetic': True})
    return service, dict(symbol='600519', operation='VERIFY_EVIDENCE',
                        payload={'bundle_binding': ref}, request_key='synthetic')


def create(case, **changes):
    service, kwargs = case
    return service.create(**dict(kwargs, **changes))


def native(outcome='SUCCESS'):
    return dict(outcome=outcome, action='no_order', formal_eligibility=False,
                result={'synthetic': True}, artifact_bindings=[])


@pytest.mark.parametrize('outcome,api,native_status', [
    ('SUCCESS', 'SUCCESS', 'SUCCEEDED'), ('PARTIAL', 'PARTIAL', 'SUCCEEDED'),
    ('BLOCKED', 'BLOCKED', 'WAITING_EVIDENCE'), ('FAILED', 'FAILED', 'FAILED')])
def test_api_projection_keeps_native_state_and_parent_cancel(case, monkeypatch, outcome, api, native_status):
    service, _ = case
    monkeypatch.setattr(service, '_execute', lambda *args: native(outcome))
    task = create(case)
    assert task['progress'] is None and task['completed_steps'] == 0
    done = service.run(task['task_id'])
    assert done['status'] == api and done['native_status'] == native_status
    assert service._load(task['task_id'])[1]['status'] == native_status
    assert done['completed_steps'] == 3 and done['progress'] is None
    assert not done['formal_eligibility']
    if native_status == 'SUCCEEDED':
        assert service.cancel(task['task_id'])['native_status'] == 'SUCCEEDED'
    assert service.list(symbol='600519')[0]['task_id'] == task['task_id']


def test_input_deepcopy_idempotence_conflict(case):
    service, kwargs = case
    task = create(case)
    assert create(case)['record_binding'] == task['record_binding']
    kwargs['payload']['bundle_binding']['sha256'] = '0' * 64
    assert service._load(task['task_id'])[0]['payload']['bundle_binding']['sha256'] != '0' * 64
    with pytest.raises(ValueError):
        create(case)
    _, state, _ = service._load(task['task_id'])
    assert state['status'] == 'QUEUED'


def test_restart_requires_explicit_resume_does_not_execute(case, monkeypatch):
    service, _ = case
    task = create(case)
    monkeypatch.setattr(mod, '_SESSION', 'new-process')
    restored = mod.TransparentTaskService(service.root)
    monkeypatch.setattr(restored, '_execute', lambda *args: pytest.fail('resume must not execute'))
    view = restored.read(task['task_id'])
    assert view['status'] == 'BLOCKED' and view['native_status'] == 'QUEUED'
    assert view['resume_required']
    assert restored.run(task['task_id'])['status'] == 'BLOCKED'
    assert restored.resume(task['task_id'])['status'] == 'QUEUED'


def test_interrupted_running_retains_attempt_and_resume(case, monkeypatch):
    service, _ = case
    task = create(case)
    monkeypatch.setattr(service, '_execute', lambda *args: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        service.run(task['task_id'])
    assert service.read(task['task_id'])['native_status'] == 'RUNNING'
    assert service.resume(task['task_id'])['status'] == 'QUEUED'
    monkeypatch.setattr(service, '_execute', lambda *args: native())
    done = service.run(task['task_id'])
    assert done['attempts'] == 2 and done['status'] == 'SUCCESS'
    assert (service._directory(task['task_id']) / 'attempts/0001').is_dir()


def test_cancel_during_native_io_cannot_be_overwritten(case, monkeypatch):
    service, _ = case
    task = create(case)
    entered, release = threading.Event(), threading.Event()
    result = {}
    def execute(*args):
        entered.set()
        assert release.wait(5)
        return native()
    monkeypatch.setattr(service, '_execute', execute)
    thread = threading.Thread(target=lambda: result.update(service.run(task['task_id'])))
    thread.start()
    assert entered.wait(5)
    assert service.cancel(task['task_id'])['status'] == 'CANCELLED'
    release.set()
    thread.join(5)
    assert not thread.is_alive()
    assert result['status'] == 'CANCELLED' and result['output_manifest'] is None
    attempt = service._directory(task['task_id']) / 'attempts/0001/attempt-record.json'
    assert json.loads(attempt.read_bytes())['cancelled'] is True


def test_timeout_raw_retained_retry_new_id_parent_unchanged(case, monkeypatch):
    service, _ = case
    def execute(spec, attempt):
        (attempt / 'raw.json').write_text('{"partial":true}', encoding='utf-8')
        raise TimeoutError()
    monkeypatch.setattr(service, '_execute', execute)
    task = create(case)
    failed = service.run(task['task_id'])
    assert failed['error_code'] == 'TIMEOUT' and failed['status'] == 'FAILED'
    assert (service.root / failed['attempt_path'] / 'raw.json').exists()
    retried = service.retry(task['task_id'])
    assert retried['task_id'] != task['task_id']
    assert retried['parent']['state_binding'] == failed['record_binding']
    assert service.read(task['task_id'])['record_binding'] == failed['record_binding']
    with pytest.raises(ValueError, match='NEW_ID'):
        service.retry(task['task_id'], request_key='synthetic')


def test_source_changed_after_create_no_native_execution(case, monkeypatch):
    service, kwargs = case
    task = create(case)
    (service.root / kwargs['payload']['bundle_binding']['path']).write_bytes(b'{}')
    monkeypatch.setattr(service, '_execute', lambda *args: pytest.fail('changed input dispatched'))
    assert service.run(task['task_id'])['status'] == 'FAILED'


def test_source_changed_during_native_no_success(case, monkeypatch):
    service, kwargs = case
    task = create(case)
    def execute(*args):
        (service.root / kwargs['payload']['bundle_binding']['path']).write_bytes(b'{}')
        return native()
    monkeypatch.setattr(service, '_execute', execute)
    assert service.run(task['task_id'])['error_code'] == 'OUTPUT_OR_SOURCE_VALIDATION_FAILED'


def test_output_tamper_rejected_on_read(case, monkeypatch):
    service, _ = case
    monkeypatch.setattr(service, '_execute', lambda *args: native())
    task = create(case)
    done = service.run(task['task_id'])
    manifest = service._bound(done['output_manifest'])
    (service.root / manifest['artifacts'][0]['path']).write_bytes(b'{}')
    view = service.read(task['task_id'])
    assert view['status'] == 'FAILED' and view['native_status'] == 'SUCCEEDED'


def test_head_recovery_is_explicit(case):
    service, _ = case
    task = create(case)
    head = service._directory(task['task_id']) / 'current.json'
    head.unlink()
    with pytest.raises(ValueError, match='RESUME'):
        service.read(task['task_id'])
    assert service.resume(task['task_id'])['status'] == 'QUEUED'


@pytest.mark.parametrize('field,value', [
    ('opening.cash_cny', '1'), ('annual.1.commitment_cash_cny', '0'),
    ('annual.0.reserve_ratio', '0'), ('terminal.profit_scale', 1),
    ('cost_of_equity', 'NaN'), ('annual.1.target_payout_ratio', '.5')])
def test_simulation_unknown_or_nonexplicit_inputs_rejected(field, value):
    with pytest.raises(ValueError):
        mod._changes([dict(field=field, value=value)])


def test_simulation_changes_are_bounded_and_unique():
    mod._changes([dict(field='annual.1.target_payout_ratio', value='0.5')])
    with pytest.raises(ValueError):
        mod._changes([dict(field='cost_of_equity', value='0.1')] * 2)


def test_fresh_requires_explicit_network_authorization(case):
    service, _ = case
    with pytest.raises(ValueError, match='AUTHORIZATION'):
        service.create(symbol='600519', operation='FRESH_PUBLIC_SCAN',
            payload=dict(network_authorized=False, max_per_channel=1), request_key='fresh')
    with pytest.raises(ValueError, match='UNSUPPORTED'):
        service.create(symbol='600519', operation='SCREEN_REPLAY', payload={}, request_key='bad')


def test_no_base_model_and_real_subprocess_failure_retained(case, monkeypatch):
    service, _ = case
    monkeypatch.setattr(mod.base.ResearchTaskService, '_drive',
                        lambda *a, **kw: pytest.fail('frozen saved/mock path called'))
    task = create(case)
    result = service.run(task['task_id'])  # actual child rejects synthetic non-bundle
    assert result['status'] == 'FAILED'
    error = (service.root / result['attempt_path'] / 'stderr.log').read_text(encoding='utf-8')
    assert 'BUNDLE_SCOPE_INVALID' in error
    assert not (service.root / 'runtime/public-evidence/current.json').exists()


def test_actual_native_evidence_dispatch_with_synthetic_native_fixture(tmp_path, monkeypatch):
    from test_public_evidence_consumer import bundle
    args, packet, _ = bundle(tmp_path, monkeypatch)
    service = mod.TransparentTaskService(tmp_path)
    ref = dict(path=args['bundle_path'].relative_to(tmp_path).as_posix(), sha256=args['bundle_sha256'])
    # Synthetic native loader fixture only; orchestration/closure code really executes.
    spec = dict(symbol=packet['requests'][0]['symbol'], operation='VERIFY_EVIDENCE',
                payload=dict(bundle_binding=ref))
    result = mod._dispatch(service, spec, tmp_path)
    assert result['outcome'] in {'SUCCESS', 'PARTIAL'}
    assert len(result['artifact_bindings']) >= 3


def main_fingerprint_metadata():
    from value_investment_agent.application.research.main_valuation_revalidation_v1 import (
        implementation_fingerprints, implementation_fingerprint_basis)
    return dict(implementation_sha256=implementation_fingerprints(),
                implementation_fingerprint_basis=implementation_fingerprint_basis())


def test_main_registry_binding_cannot_switch_source(tmp_path):
    service = mod.TransparentTaskService(tmp_path)
    spec_ref = put(tmp_path, 'artifacts/current/test/spec.json',
                   dict(symbol='000568', action='no_order', **main_fingerprint_metadata()))
    reg_ref = put(tmp_path, 'config/current-operating-research-sources-v1.json',
                  dict(cases={'000568': {'main_revalidation': spec_ref}}))
    task = service.create(symbol='000568', operation='RECALCULATE_MAIN',
        payload=dict(registry_binding=reg_ref, spec_binding=spec_ref), request_key='main')
    (tmp_path / reg_ref['path']).write_bytes(b'{}')
    assert service.run(task['task_id'])['status'] == 'FAILED'


@pytest.mark.parametrize('symbol', ['600519', '600887'])
def test_real_source_task_requires_explicit_fixture_env(symbol):
    root_value = os.environ.get('TRANSPARENT_TASK_REAL_ROOT')
    ref_value = os.environ.get('TRANSPARENT_TASK_REAL_BUNDLE')
    if not root_value or not ref_value:
        pytest.skip('Set TRANSPARENT_TASK_REAL_ROOT and TRANSPARENT_TASK_REAL_BUNDLE for native PDF verification')
    root = Path(root_value).resolve()
    service = mod.TransparentTaskService(root)
    ref = service._binding(root / ref_value)
    before = (root / ref_value).read_bytes()
    task = service.create(symbol=symbol, operation='VERIFY_EVIDENCE',
        payload=dict(bundle_binding=ref), request_key='real-' + uuid4().hex)
    result = service.run(task['task_id'])
    assert result['status'] in {'SUCCESS', 'PARTIAL'}, result
    assert result['completed_steps'] == 3
    assert (root / ref_value).read_bytes() == before
    assert result['native_metadata']['new_llm_calls'] == 0


def test_source_bound_simulation_reconstructs_and_calls_real_v4(tmp_path, compiler_inputs, monkeypatch):
    from value_investment_agent.domain.valuation.operating_profit_cash_path_v1 import compile_operating_profit_cash_path
    from value_investment_agent.application.research.main_valuation_revalidation_v1 import SUCCESS
    from value_investment_agent.valuation_models import residual_income_path_v4 as v4
    compiled = mod._json({k: v for k, v in compile_operating_profit_cash_path(**compiler_inputs).items()
                         if k != 'typed_scenario'})
    spec_ref = put(tmp_path, 'artifacts/current/test/spec.json', dict(
        hypotheses={'scenarios': {'base': {
            'terminal_policy': compiler_inputs['terminal_policy'], 'cost_of_equity': '0.1'}}}))
    baseline = dict(status=SUCCESS, annual_ledgers={'base': compiled},
        period_assembly={'scenarios': {'base': {'model_years': [
            {'annual_row': {k: v for k, v in row.items() if k != 'cash_policy'}}
            for row in compiler_inputs['annual_rows']]}}},
        input_descriptor_sha256='a' * 64, source_bindings=[spec_ref])
    untouched = deepcopy(baseline)
    monkeypatch.setattr(mod, '_main_baseline', lambda *args: deepcopy(baseline))
    calls, calculate = [], v4.scenario_calculation
    def traced(*args):
        calls.append(True)
        return calculate(*args)
    monkeypatch.setattr(v4, 'scenario_calculation', traced)
    result = mod._simulate(mod.TransparentTaskService(tmp_path), dict(symbol='000568',
        payload=dict(spec_binding=spec_ref, scenario='base',
            changes=[dict(field='annual.1.target_payout_ratio', value='0.5')],
            rationale='TEST_ONLY explicit lower distribution assumption')))
    assert calls == [True]
    assert mod.Decimal(result['ledger']['rows'][0]['distribution']) == 10
    assert result['inputs']['opening_state'] == compiler_inputs['opening_state']
    assert result['inputs']['annual_rows'][0]['cash_policy']['commitment_cash_cny'] == '0'
    assert baseline == untouched and not result['main_range_adopted']
    assert result['calculation']['per_share_value']


def test_fresh_dispatch_reuses_actual_run_once_contract_newdir_only(case, monkeypatch):
    import types
    service, _ = case
    task = service.create(symbol='600519', operation='FRESH_PUBLIC_SCAN',
        payload=dict(network_authorized=True, max_per_channel=1), request_key='fresh')
    spec = service._load(task['task_id'])[0]
    calls = []
    def run_once(**kwargs):
        calls.append(kwargs)
        ref = put(service.root, (kwargs['output_dir'] / 'raw.json').relative_to(service.root).as_posix(),
                  {'synthetic_public': True})
        put(service.root, (kwargs['output_dir'] / 'manifest.json').relative_to(service.root).as_posix(),
            dict(files={'raw': ref}))
        return dict(input_mode='LIVE_COLLECTION', current_publication_eligible=False)
    monkeypatch.setattr(mod.importlib.util, 'module_from_spec',
                        lambda spec: types.SimpleNamespace(run_once=run_once,
                            build_financial_input=lambda: None, _collect_official=lambda: None,
                            fetch_tencent_board_rank=lambda: None, fetch_sina_industry_quotes=lambda: None,
                            fetch_eastmoney_dividends=lambda: None))
    monkeypatch.setattr(mod.importlib.util, 'spec_from_file_location',
                        lambda *args: types.SimpleNamespace(loader=types.SimpleNamespace(exec_module=lambda _: None)))
    result = mod._dispatch(service, spec, service._directory(task['task_id']) / 'attempts/0001')
    assert calls[0]['reuse_inputs'] is False
    assert calls[0]['skip_workbook'] is True and calls[0]['wps_dir'] is None
    assert calls[0]['collect_public_financials'] is True
    assert result['operation'] == 'FRESH_PUBLIC_SCAN' and result['outcome'] == 'PARTIAL'
    with pytest.raises(FileExistsError):
        mod._dispatch(service, spec, service._directory(task['task_id']) / 'attempts/0001')


def test_cancel_blocks_next_collector_keeps_completed_raw(case):
    import types
    service, _ = case
    task = create(case)
    spec, state, binding = service._load(task['task_id'])
    service._save(spec, state, binding, mod.base._now(), status='RUNNING', attempts=1)
    calls = []
    def collected():
        calls.append('first')
        return b'raw retained by run_once before next collector'
    module = types.SimpleNamespace(build_financial_input=collected,
        _collect_official=lambda: calls.append('second'),
        fetch_tencent_board_rank=lambda: None, fetch_sina_industry_quotes=lambda: None,
        fetch_eastmoney_dividends=lambda: None)
    mod._guard_public_io(service, spec, Path('0001'), module)
    assert module.build_financial_input().startswith(b'raw retained')
    service.cancel(task['task_id'])
    with pytest.raises(mod.base._Cancelled):
        module._collect_official()
    assert calls == ['first']


@pytest.fixture
def note_case(tmp_path):
    service = mod.TransparentTaskService(tmp_path)
    ref = put(tmp_path, 'artifacts/current/note/spec.json',
              dict(symbol='000568', action='no_order', scope='CONDITIONAL_RESEARCH_ONLY'))
    args = dict(symbol='000568', operation='REVIEW_NOTE',
        payload=dict(target_binding=ref, opinion='工程交互验收记录，不代表投资判断'),
        actor_context=deepcopy(mod.REVIEW_ACTOR_CONTEXT), request_key='note')
    return service, args


def test_review_note_real_worker_same_task_artifacts_no_approval(note_case):
    service, args = note_case
    target_before = (service.root / args['payload']['target_binding']['path']).read_bytes()
    task = service.create(**args)
    args['actor_context']['actor'] = 'mutated-caller'
    result = service.run(task['task_id'])
    assert result['status'] == 'SUCCESS'
    note = result['result']['result']
    assert note['scope'] == 'COMMENT_NOT_G3_APPROVAL'
    assert note['opinion'] == '工程交互验收记录，不代表投资判断'
    assert note['actor_context'] == mod.REVIEW_ACTOR_CONTEXT
    assert note['approval_changed'] is note['formal_eligibility'] is note['signed'] is False
    assert note['main_range_adopted'] is False and note['action'] == 'no_order'
    assert (service.root / args['payload']['target_binding']['path']).read_bytes() == target_before
    assert result['output_manifest']['path'].startswith(
        service._directory(task['task_id']).relative_to(service.root).as_posix())
    assert service.read(task['task_id'])['result'] == result['result']


@pytest.mark.parametrize('extra', ['actor', 'actor_context', 'approved', 'formal_eligibility', 'scope'])
def test_review_note_payload_cannot_claim_identity_or_approval(note_case, extra):
    service, args = note_case
    args['payload'][extra] = 'G3_APPROVED'
    with pytest.raises(ValueError, match='EXACT_NATIVE_INPUT'):
        service.create(**args)
    assert not service.base.exists()


@pytest.mark.parametrize('context', [None, {}, {'actor': 'USER_APPROVED'},
    {'actor': 'LOCAL_AUTHORIZED_OPERATOR', 'authorization_basis': 'CLIENT_ASSERTION'}])
def test_review_note_requires_route_actor_context(note_case, context):
    service, args = note_case
    args['actor_context'] = context
    with pytest.raises(ValueError, match='ROUTE_AUTHORIZED'):
        service.create(**args)


@pytest.mark.parametrize('damage', ['symbol', 'hash', 'opinion', 'private'])
def test_review_note_rejects_unbound_or_wrong_target(note_case, damage):
    service, args = note_case
    if damage == 'symbol':
        args['symbol'] = '600519'
    elif damage == 'hash':
        args['payload']['target_binding']['sha256'] = '0' * 64
    elif damage == 'opinion':
        args['payload']['opinion'] = ' '
    else:
        args['payload']['target_binding']['path'] = 'config/current-research-drafts.json'
    with pytest.raises(ValueError):
        service.create(**args)


def test_review_note_source_changed_before_run_fails_closed(note_case):
    service, args = note_case
    task = service.create(**args)
    (service.root / args['payload']['target_binding']['path']).write_bytes(b'{}')
    assert service.run(task['task_id'])['status'] == 'FAILED'


def test_actual_owned_subprocess_cancel_is_reaped_and_logs_retained(case, monkeypatch):
    import sys
    import time
    service, _ = case
    real_popen = mod.subprocess.Popen
    children = []
    def child(*args, **kwargs):
        process = real_popen([sys.executable, '-u', '-c',
            "import time; print('TEST_ONLY_NATIVE_BLOCKING_IO', flush=True); time.sleep(60)"], **kwargs)
        children.append(process)
        return process
    monkeypatch.setattr(mod.subprocess, 'Popen', child)
    task = create(case, timeout_seconds=30)
    answer = {}
    thread = threading.Thread(target=lambda: answer.update(service.run(task['task_id'])))
    thread.start()
    log = service._directory(task['task_id']) / 'attempts/0001/stdout.log'
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and (not log.exists() or not log.read_bytes()):
        time.sleep(0.02)
    try:
        assert log.exists() and b'TEST_ONLY_NATIVE_BLOCKING_IO' in log.read_bytes()
        service.cancel(task['task_id'])
        thread.join(5)
        assert not thread.is_alive(), 'cancel left the owned worker running'
        assert len(children) == 1 and children[0].poll() is not None
        assert answer['status'] == 'CANCELLED' and answer['output_manifest'] is None
        assert json.loads((log.parent / 'attempt-record.json').read_bytes())['cancelled']
        assert b'TEST_ONLY_NATIVE_BLOCKING_IO' in log.read_bytes()
    finally:
        # Test-only cleanup also owns this exact handle, never enumerates PIDs.
        for process in children:
            if process.poll() is None:
                process.kill()
                process.wait()
        thread.join(5)


def test_prepare_missing_inputs_is_independent_readonly_and_fresh_not_authorized(tmp_path):
    service = mod.TransparentTaskService(tmp_path)
    prepared = service.prepare(symbol='000568')
    rows = {x['operation']: x for x in prepared['operations']}
    assert set(rows) == set(mod.OPERATIONS)
    assert rows['FRESH_PUBLIC_SCAN']['enabled']
    assert rows['FRESH_PUBLIC_SCAN']['payload']['network_authorized'] is False
    assert rows['RECALCULATE_MAIN']['reason'] == 'MAIN_BASELINE_MISSING'
    assert rows['SIMULATE_ASSUMPTIONS']['enabled'] is False
    assert rows['REVIEW_NOTE']['enabled'] is False
    assert list(tmp_path.iterdir()) == []
    with pytest.raises(ValueError):
        service.create(symbol='000568', operation='FRESH_PUBLIC_SCAN',
            payload=rows['FRESH_PUBLIC_SCAN']['payload'], request_key='no-network-consent')


def register_main_for_prepare(root):
    source = put(root, 'runtime/value-test/native.json', {'TEST_ONLY': True})
    ref = put(root, 'artifacts/current/test/main.json', dict(
        schema_version='main-valuation-revalidation-v1', symbol='000568', action='no_order',
        bindings={'native': source}, hypotheses={'scenarios': {'bear': {}, 'base': {}, 'bull': {}}},
        **main_fingerprint_metadata()))
    put(root, 'config/current-operating-research-sources-v1.json', dict(
        schema_version='current-operating-research-sources-v1', action='no_order',
        cases={'000568': {'main_revalidation': ref}}))
    return ref, source


def test_prepare_registered_main_source_hash_and_note_binding(tmp_path):
    service = mod.TransparentTaskService(tmp_path)
    ref, source = register_main_for_prepare(tmp_path)
    before = {str(p): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    rows = {x['operation']: x for x in service.prepare(symbol='000568')['operations']}
    assert rows['RECALCULATE_MAIN']['payload']['spec_binding'] == ref
    assert rows['SIMULATE_ASSUMPTIONS']['payload']['changes'] == []
    assert rows['SIMULATE_ASSUMPTIONS']['user_fields'] == ['scenario', 'changes', 'rationale']
    assert rows['REVIEW_NOTE']['payload'] == dict(target_binding=ref, opinion='')
    assert before == {str(p): p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    (tmp_path / source['path']).write_bytes(b'{}')
    invalid = {x['operation']: x for x in service.prepare(symbol='000568')['operations']}
    assert invalid['RECALCULATE_MAIN']['reason'] == 'MAIN_BASELINE_INVALID'
    assert not invalid['SIMULATE_ASSUMPTIONS']['enabled']
    assert not invalid['REVIEW_NOTE']['enabled']


def test_prepare_actual_public_bundle_selects_source_for_note(tmp_path, monkeypatch):
    from test_public_evidence_consumer import bundle
    args, packet, _ = bundle(tmp_path, monkeypatch)
    ref = put(tmp_path, 'runtime/public-evidence/test/bundle.json', packet)
    put(tmp_path, 'runtime/public-evidence/current.json',
        dict(schema_version='public-evidence-pointer-v1', action='no_order', bundle=ref))
    service = mod.TransparentTaskService(tmp_path)
    symbol = packet['requests'][0]['symbol']
    rows = {x['operation']: x for x in service.prepare(symbol=symbol)['operations']}
    assert rows['VERIFY_EVIDENCE']['payload']['bundle_binding'] == ref
    assert rows['REVIEW_NOTE']['payload']['target_binding'] == ref
    payload = dict(rows['REVIEW_NOTE']['payload'], opinion='TEST_ONLY engineering comment')
    service._validate_payload(symbol, 'REVIEW_NOTE', payload)
    assert not service.base.exists()


def test_prepare_real_registrations_no_model_network_or_task_write():
    value = os.environ.get('TRANSPARENT_TASK_REAL_ROOT')
    if not value:
        pytest.skip('TRANSPARENT_TASK_REAL_ROOT required for actual registered bindings')
    service = mod.TransparentTaskService(Path(value))
    before = set(service.base.iterdir()) if service.base.exists() else set()
    for symbol in ('600519', '600887', '000568'):
        rows = {x['operation']: x for x in service.prepare(symbol=symbol)['operations']}
        assert rows['REPLAY_SELECTION']['enabled'], rows
        assert rows['REVIEW_NOTE']['enabled'], rows
        if symbol == '000568':
            assert rows['RECALCULATE_MAIN']['enabled'], rows
            assert rows['SIMULATE_ASSUMPTIONS']['enabled'], rows
        else:
            assert rows['VERIFY_EVIDENCE']['enabled'], rows
        assert rows['FRESH_PUBLIC_SCAN']['payload']['network_authorized'] is False
    assert (set(service.base.iterdir()) if service.base.exists() else set()) == before


def isolated_code_mirror(root, spec, monkeypatch):
    # Copy executing project sources to TEST_ONLY mirror; never edit frozen code.
    mirror = root / 'test-only-code'
    for name in spec['source_contract']['files']:
        dest = mirror / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((mod._CODE_ROOT / name).read_bytes())
    monkeypatch.setattr(mod, '_CODE_ROOT', mirror)
    return mirror


@pytest.mark.parametrize('changed', ['scripts/run_m2_opportunity_discovery.py',
    'src/value_investment_agent/m2_market_data.py',
    'src/value_investment_agent/application/discovery/official_universe_collection.py'])
def test_dynamic_scan_source_change_rejects_frozen_task_without_repin(case, monkeypatch, changed):
    service, _ = case
    task = service.create(symbol='600519', operation='FRESH_PUBLIC_SCAN',
        payload=dict(network_authorized=True, max_per_channel=1), request_key='source-contract')
    spec = service._load(task['task_id'])[0]
    before = deepcopy(spec['source_contract'])
    mirror = isolated_code_mirror(service.root, spec, monkeypatch)
    path = mirror / changed
    path.write_bytes(path.read_bytes() + b'\n# TEST_ONLY change\n')
    monkeypatch.setattr(service, '_execute', lambda *args: pytest.fail('changed code dispatched'))
    result = service.run(task['task_id'])
    assert result['status'] == 'FAILED'
    assert result['error_code'] == 'IMPLEMENTATION_CHANGED'
    assert service._load(task['task_id'])[0]['source_contract'] == before


def test_worker_checks_same_source_contract_after_native_call(case, monkeypatch):
    service, _ = case
    task = create(case)
    spec = service._load(task['task_id'])[0]
    mirror = isolated_code_mirror(service.root, spec, monkeypatch)
    attempt = service._directory(task['task_id']) / 'attempts/0001'
    attempt.mkdir(parents=True)
    def change_during_native(*args):
        path = mirror / 'src/value_investment_agent/application/research/public_evidence.py'
        path.write_bytes(path.read_bytes() + b'\n# TEST_ONLY during dispatch\n')
        return native()
    monkeypatch.setattr(mod, '_dispatch', change_during_native)
    with pytest.raises(ValueError, match='IMPLEMENTATION_CHANGED'):
        mod._worker(service.root, service._directory(task['task_id']) / 'input.json', attempt)
    assert not (attempt / 'native-result.json').exists()


@pytest.mark.parametrize('change', ['implementation', 'input'])
def test_historical_partial_preserved_but_not_currently_consumable(case, monkeypatch, change):
    service, kwargs = case
    task = create(case)
    monkeypatch.setattr(service, '_execute', lambda *args: native('PARTIAL'))
    historical = service.run(task['task_id'])
    assert historical['status'] == 'PARTIAL' and historical['currently_consumable']
    spec, state, binding = service._load(task['task_id'])
    manifest_before = deepcopy(historical['output_manifest'])
    if change == 'implementation':
        mirror = isolated_code_mirror(service.root, spec, monkeypatch)
        path = mirror / 'src/value_investment_agent/application/research/public_evidence.py'
    else:
        path = service.root / kwargs['payload']['bundle_binding']['path']
    path.write_bytes(path.read_bytes() + b' ')
    current = service.read(task['task_id'])
    assert current['status'] == 'BLOCKED'
    assert current['native_status'] == current['persisted_status'] == 'SUCCEEDED'
    assert current['outcome'] == 'PARTIAL'
    assert current['current_validation'] == 'UNASSESSABLE'
    assert current['current_validation_reason']
    assert current['currently_consumable'] is False and 'result' not in current
    assert current['output_manifest'] == manifest_before
    assert service._load(task['task_id'])[1:] == (state, binding)


def test_main_bound_model_fingerprint_must_match_before_create(tmp_path):
    service = mod.TransparentTaskService(tmp_path)
    ref, _ = register_main_for_prepare(tmp_path)
    packet = json.loads((tmp_path / ref['path']).read_bytes())
    key = next(iter(packet['implementation_sha256']))
    packet['implementation_sha256'][key] = '0' * 64
    bad_ref = put(tmp_path, ref['path'], packet)
    registry = put(tmp_path, 'config/current-operating-research-sources-v1.json', dict(
        schema_version='current-operating-research-sources-v1', action='no_order',
        cases={'000568': {'main_revalidation': bad_ref}}))
    with pytest.raises(ValueError, match='MODEL_IMPLEMENTATION_CHANGED'):
        service.create(symbol='000568', operation='RECALCULATE_MAIN',
            payload=dict(registry_binding=registry, spec_binding=bad_ref), request_key='wrong-model')
    assert not service.base.exists()


def test_unified_receipt_queued_running_terminal_and_source_refs(case, monkeypatch):
    service, kwargs = case
    task = create(case)
    assert task['run_id'] is task['started_at'] is task['finished_at'] is None
    assert task['duration_seconds'] is None and task['current_step'] is None
    assert task['module_id'] == 'A' and task['module_version'] == mod.VERSION
    assert not task['retry_allowed']
    observed = {}
    def execute(*args):
        observed.update(service.read(task['task_id']))
        return native('PARTIAL')
    monkeypatch.setattr(service, '_execute', execute)
    done = service.run(task['task_id'])
    assert observed['run_id'] == task['task_id'] + '/attempt/0001'
    assert observed['started_at'] and observed['finished_at'] is None
    assert observed['current_step'] == 'EXECUTE_NATIVE'
    assert observed['duration_seconds'] >= 0 and not observed['retry_allowed']
    assert done['run_id'] == observed['run_id'] and done['started_at'] == observed['started_at']
    state = service._load(task['task_id'])[1]
    assert done['finished_at'] == state['updated_at']
    assert done['finished_at_basis'] == 'TERMINAL_VERSION_UPDATED_AT'
    delta = datetime.fromisoformat(done['finished_at']) - datetime.fromisoformat(done['started_at'])
    assert done['duration_seconds'] == delta.total_seconds()
    assert done['current_step'] is None and done['error'] is None
    assert done['warnings'] == ['NATIVE_PARTIAL_RESULT']
    assert done['source_refs'] == [dict(role='bundle_binding', **kwargs['payload']['bundle_binding'])]
    assert done['input_refs'] == [done['input_binding']]


def test_unknown_historical_time_is_not_reconstructed(case):
    service, _ = case
    task = create(case)
    spec, state, pin = service._load(task['task_id'])
    state, pin = service._save(spec, state, pin, mod.base._now(), status='FAILED',
        attempts=1, error_code='TEST_ONLY_HISTORICAL_FAILURE')
    before = deepcopy(state)
    view = service._view(spec, state, pin, mod.base._now())
    assert view['run_id'] is view['started_at'] is view['duration_seconds'] is None
    assert view['finished_at'] == before['updated_at']
    assert view['retry_allowed'] and view['error']['code'] == 'TEST_ONLY_HISTORICAL_FAILURE'
    assert 'HISTORICAL_STARTED_AT_UNKNOWN' in view['warnings']
    assert service._load(task['task_id'])[1] == before


def test_receipt_resume_clears_old_attempt_clock_and_new_attempt_gets_new_id(case, monkeypatch):
    service, _ = case
    task = create(case)
    monkeypatch.setattr(service, '_execute', lambda *args: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        service.run(task['task_id'])
    first = service.read(task['task_id'])
    queued = service.resume(task['task_id'])
    assert queued['run_id'] is queued['started_at'] is queued['duration_seconds'] is None
    monkeypatch.setattr(service, '_execute', lambda *args: native())
    second = service.run(task['task_id'])
    assert second['run_id'].endswith('/0002') and second['run_id'] != first['run_id']
    assert datetime.fromisoformat(second['started_at']) >= datetime.fromisoformat(first['started_at'])


def test_operation_module_mapping_is_bounded():
    assert mod.OPERATION_MODULES == {
        'VERIFY_EVIDENCE': 'A', 'REPLAY_SELECTION': 'B', 'FRESH_PUBLIC_SCAN': 'B',
        'RECALCULATE_MAIN': 'F1', 'SIMULATE_ASSUMPTIONS': 'F1', 'REVIEW_NOTE': 'G2'}


@pytest.mark.parametrize('damage', [None, 'changed', 'missing_binding'])
def test_replay_embeds_exact_bound_selection_and_keeps_run_metadata(tmp_path, monkeypatch, damage):
    from types import SimpleNamespace
    from value_investment_agent.application.discovery import value_module_adapter_v1 as adapter
    service = mod.TransparentTaskService(tmp_path)
    attempt = tmp_path / 'runtime/test-only-output'
    original = {}
    def run(**kwargs):
        directory = kwargs['output_dir']
        expected = dict(items=[{'symbol': '600519', 'name': 'TEST_ONLY'}],
                        action='no_order', formal_eligibility=False)
        ref = put(tmp_path, (directory / 'selection.json').relative_to(tmp_path).as_posix(), expected)
        record = dict(status='PARTIAL', run_id='b-test-only', module_id='B',
            source_refs=[dict(path='runtime/test-only-input.json', sha256='a' * 64)],
            output_manifest={'items': [dict(role='selection', hash_basis='RAW_BYTES', **ref)]},
            action='no_order')
        if damage == 'missing_binding':
            record['output_manifest']['items'] = []
        original.update(deepcopy(record))
        put(tmp_path, (directory / 'module-run.json').relative_to(tmp_path).as_posix(), record)
        if damage == 'changed':
            (tmp_path / ref['path']).write_bytes(b'{"items":[]}')
        return SimpleNamespace(as_dict=lambda: deepcopy(record))
    monkeypatch.setattr(adapter, 'run', run)
    spec = dict(symbol='600519', operation='REPLAY_SELECTION', payload={})
    if damage:
        with pytest.raises(ValueError):
            mod._dispatch(service, spec, attempt)
        return
    output = mod._dispatch(service, spec, attempt)
    result = output['result']
    assert result['selection']['items'][0]['symbol'] == '600519'
    assert all(result[key] == value for key, value in original.items())
    assert result['selection_binding'] in output['artifact_bindings']
    assert result['selection'] == service._bound(result['selection_binding'])
    assert not output['current_published'] and not output['formal_eligibility']


def test_real_replay_task_exposes_bound_stock_selection():
    value = os.environ.get('TRANSPARENT_TASK_REAL_ROOT')
    if not value:
        pytest.skip('TRANSPARENT_TASK_REAL_ROOT required for actual B native selection')
    service = mod.TransparentTaskService(Path(value))
    row = next(row for row in service.prepare(symbol='600519')['operations']
               if row['operation'] == 'REPLAY_SELECTION')
    assert row['enabled']
    task = service.create(symbol='600519', operation='REPLAY_SELECTION', payload=row['payload'],
                          request_key='readable-real-replay-' + uuid4().hex)
    view = service.run(task['task_id'])
    assert view['status'] in {'SUCCESS', 'PARTIAL'}, view
    result = view['result']['result']
    assert result['selection'] == service._bound(result['selection_binding'])
    assert result['selection']['items']
    assert all('symbol' in item for item in result['selection']['items'])
    assert result['source_refs'] and result['run_id'].startswith('b-')
    assert not view['result']['current_published']
