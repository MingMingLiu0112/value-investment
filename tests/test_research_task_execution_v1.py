"""D1 durable lifecycle using real snapshot/pilot and isolated original-byte fixtures."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import threading

import pytest

from test_llm_agent_research import _inputs, _replies
from value_investment_agent.application.research.agent_review import task_execution_v1 as mod
from value_investment_agent.infrastructure.agent_runtime.provider import MockLLMProvider


@pytest.fixture
def task(tmp_path):
    workbench,digest,original = _inputs(tmp_path)
    service = mod.ResearchTaskService(tmp_path)
    args = dict(symbol='600519',workbench=workbench,workbench_sha256=digest,
                responses=_replies(),request_key='TEST_ONLY-saved')
    return service,args,original


def test_actual_saved_response_workflow_is_persistent_idempotent_and_non_admitted(task, monkeypatch):
    service,args,original = task
    before = original.read_bytes()
    created = service.create(**args)
    assert created['status'] == 'QUEUED'
    assert service.create(**args)['record_binding'] == created['record_binding']
    result = service.run(created['task_id'])
    assert result['status'] == 'SUCCEEDED' and result['checkpoint_verified']
    assert result['execution_mode'] == 'SAVED_RESPONSE' and result['new_llm_calls'] == 0
    assert result['provider_requests'] == 3 and result['finding_count'] == 3
    assert not result['formal_eligibility'] and result['action'] == 'no_order'
    assert result['usage_basis'] == 'MOCK_PROVIDER_ACCOUNTING_NOT_NEW_LLM_USAGE'
    def forbidden(*args, **kwargs):
        raise AssertionError('verified checkpoint must not repeat saved/provider calls')
    monkeypatch.setattr(MockLLMProvider,'complete',forbidden)
    fresh = mod.ResearchTaskService(service.root)
    assert fresh.run(created['task_id'])['record_binding'] == result['record_binding']
    assert fresh.resume(created['task_id'])['record_binding'] == result['record_binding']
    assert fresh.read(created['task_id'])['record_binding'] == result['record_binding']
    assert original.read_bytes() == before
    assert not (service.root/'config/current-agent-research.json').exists()


def test_mock_mode_uses_existing_three_role_runner(task):
    service,args,_ = task
    created = service.create(**dict(args,mode='MOCK'))
    result = service.run(created['task_id'])
    assert result['status'] == 'SUCCEEDED' and result['execution_mode'] == 'MOCK'


@pytest.mark.parametrize('change', [dict(symbol='600887'),dict(responses=_replies('changed')),
                                 dict(budget={'max_attempts':1})])
def test_request_key_cannot_alias_different_inputs(task, change):
    service,args,_ = task
    service.create(**args)
    with pytest.raises(ValueError,match='conflicts'):
        service.create(**dict(args,**change))


def test_live_and_invalid_budget_are_rejected_before_task_creation(task):
    service,args,_ = task
    for change in (dict(mode='live'),dict(budget={'max_attempts':True}),
                   dict(budget={'max_attempts':99}),dict(budget={'max_cost_usd':1})):
        with pytest.raises(ValueError):
            service.create(**dict(args,**change))
    assert not service.base.exists()


def test_missing_evidence_waits_and_explicit_resume_requeues_without_provider(task, monkeypatch):
    service,args,original = task
    raw = original.read_bytes()
    original.unlink()
    created = service.create(**args)
    assert created['status'] == 'WAITING_EVIDENCE'
    assert service.run(created['task_id'])['status'] == 'WAITING_EVIDENCE'
    original.write_bytes(raw)
    native = MockLLMProvider.complete
    def forbidden(*args, **kwargs):
        raise AssertionError('resume must never invoke provider')
    monkeypatch.setattr(MockLLMProvider,'complete',forbidden)
    assert service.resume(created['task_id'])['status'] == 'QUEUED'
    monkeypatch.setattr(MockLLMProvider,'complete',native)
    assert service.run(created['task_id'])['status'] == 'SUCCEEDED'


def test_completed_task_revalidates_original_before_returning_success(task):
    service,args,original = task
    task_id = service.create(**args)['task_id']
    service.run(task_id)
    original.write_bytes(b'TEST_ONLY changed source')
    result = service.read(task_id)
    assert result['status'] == 'FAILED' and result['persisted_status'] == 'SUCCEEDED'
    assert result['checkpoint_verified'] is False
    assert service.run(task_id)['status'] == 'FAILED'


def test_cancel_before_run_is_persistent_and_does_not_restart(task, monkeypatch):
    service,args,_ = task
    task_id = service.create(**args)['task_id']
    cancelled = service.cancel(task_id)
    assert cancelled['status'] == 'CANCELLED'
    def forbidden(*args, **kwargs):
        raise AssertionError('cancelled task cannot call provider')
    monkeypatch.setattr(MockLLMProvider,'complete',forbidden)
    assert service.run(task_id)['status'] == service.resume(task_id)['status'] == 'CANCELLED'
    assert service.cancel(task_id)['record_binding'] == cancelled['record_binding']


def test_running_task_exclusion_and_cooperative_cancellation(task, monkeypatch):
    service,args,_ = task
    task_id = service.create(**args)['task_id']
    entered,release = threading.Event(),threading.Event()
    native = MockLLMProvider.complete
    def blocked(self,request):
        entered.set()
        assert release.wait(5)
        return native(self,request)
    monkeypatch.setattr(MockLLMProvider,'complete',blocked)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(service.run,task_id)
        try:
            assert entered.wait(5)
            assert service.read(task_id)['status'] == 'RUNNING'
            with pytest.raises(RuntimeError,match='already active'):
                mod.ResearchTaskService(service.root).run(task_id)
            with pytest.raises(RuntimeError,match='already active'):
                service.resume(task_id)
            assert service.cancel(task_id)['status'] == 'CANCELLED'
        finally:
            release.set()
        assert pending.result(timeout=5)['status'] == 'CANCELLED'
    assert not (service._directory(task_id)/'pilot.json').exists()


def test_crash_after_complete_packet_recovers_whole_checkpoint_without_reexecution(task, monkeypatch):
    service,args,_ = task
    task_id = service.create(**args)['task_id']
    native = mod.llm_pilot.run_llm_research_pilot
    def crash(**kwargs):
        native(**kwargs)
        raise SystemExit('TEST_ONLY crash after complete packet')
    monkeypatch.setattr(mod.llm_pilot,'run_llm_research_pilot',crash)
    with pytest.raises(SystemExit):
        service.run(task_id)
    assert service.read(task_id)['status'] == 'RUNNING'
    def forbidden(*args, **kwargs):
        raise AssertionError('complete checkpoint must not call provider')
    monkeypatch.setattr(MockLLMProvider,'complete',forbidden)
    recovered = mod.ResearchTaskService(service.root).resume(task_id)
    assert recovered['status'] == 'SUCCEEDED' and recovered['attempts'] == 1
    assert recovered['role_exactly_once'] is False and recovered['provider_requests'] == 3


def test_partial_crash_does_not_auto_repeat_and_explicit_retry_is_budgeted(task, monkeypatch):
    service,args,_ = task
    task_id = service.create(**args)['task_id']
    native = mod.llm_pilot.run_llm_research_pilot
    def crash(**kwargs):
        snapshot = mod.load_research_snapshot(root=kwargs['root'],workbench=kwargs['workbench'],
            expected_sha256=kwargs['workbench_sha256'],symbol=kwargs['symbol'])
        role = next(iter(mod.llm_pilot.ROLE_TASKS))
        kwargs['provider'].complete(mod.llm_pilot._request(role,snapshot))
        raise SystemExit('TEST_ONLY partial role crash')
    monkeypatch.setattr(mod.llm_pilot,'run_llm_research_pilot',crash)
    with pytest.raises(SystemExit):
        service.run(task_id)
    state = service.run(task_id)
    assert state['status'] == 'FAILED' and state['provider_requests'] == 1
    assert state['error_code'] == 'INTERRUPTED_EXPLICIT_RESUME_REQUIRED'
    queued = service.resume(task_id)
    assert queued['status'] == 'QUEUED' and queued['provider_requests'] == 1
    monkeypatch.setattr(mod.llm_pilot,'run_llm_research_pilot',native)
    result = service.run(task_id)
    assert result['status'] == 'SUCCEEDED' and result['attempts'] == 2
    assert result['provider_requests'] == 4 and result['new_llm_calls'] == 0


@pytest.mark.parametrize('budget', [dict(max_provider_requests=2),dict(max_prompt_tokens=599),dict(max_completion_tokens=299)])
def test_budget_denial_precedes_any_saved_provider_request(task, monkeypatch, budget):
    service,args,_ = task
    task_id = service.create(**dict(args,budget=budget))['task_id']
    def forbidden(*args, **kwargs):
        raise AssertionError('budget denied before any saved/provider request')
    monkeypatch.setattr(MockLLMProvider,'complete',forbidden)
    result = service.run(task_id)
    assert result['status'] == 'FAILED' and result['error_code'] == 'TASK_BUDGET_EXHAUSTED'
    assert result['provider_requests'] == result['attempts'] == 0


def test_attempt_budget_survives_explicit_resume(task, monkeypatch):
    service,args,_ = task
    task_id = service.create(**dict(args,budget={'max_attempts':1}))['task_id']
    def failed(**kwargs):
        raise ValueError('TEST_ONLY no response')
    monkeypatch.setattr(mod.llm_pilot,'run_llm_research_pilot',failed)
    assert service.run(task_id)['status'] == 'FAILED'
    result = service.resume(task_id)
    assert result['status'] == 'FAILED' and result['error_code'] == 'ATTEMPT_BUDGET_EXHAUSTED'


def test_corrupted_checkpoint_is_not_replaced_by_another_execution(task, monkeypatch):
    service,args,_ = task
    task_id = service.create(**args)['task_id']
    result = service.run(task_id)
    (service.root/result['checkpoint']['path']).write_text('{}',encoding='utf-8')
    def forbidden(*args, **kwargs):
        raise AssertionError('tampered checkpoint must not cause reexecution')
    monkeypatch.setattr(MockLLMProvider,'complete',forbidden)
    assert service.read(task_id)['status'] == 'FAILED'
    assert service.resume(task_id)['status'] == 'FAILED'


@pytest.mark.parametrize('target', ['input.json','current.json','version'])
def test_task_hash_chain_drift_fails_closed(task, target):
    service,args,_ = task
    result = service.create(**args)
    directory = service._directory(result['task_id'])
    path = directory/target if target != 'version' else service.root/result['record_binding']['path']
    path.write_text('{}',encoding='utf-8')
    with pytest.raises((ValueError,KeyError,TypeError)):
        service.read(result['task_id'])


def test_orphan_version_needs_explicit_resume_and_no_provider(task, monkeypatch):
    service,args,_ = task
    task_id = service.create(**args)['task_id']
    native_head = service._head
    def crash(*args, **kwargs):
        raise SystemExit('TEST_ONLY crash before head publication')
    monkeypatch.setattr(service,'_head',crash)
    with pytest.raises(SystemExit):
        service.cancel(task_id)
    monkeypatch.setattr(service,'_head',native_head)
    with pytest.raises(ValueError,match='Unpublished'):
        service.read(task_id)
    assert service.resume(task_id)['status'] == 'CANCELLED'


def test_read_absent_and_path_escape_do_not_create_work(task):
    service,args,_ = task
    with pytest.raises(FileNotFoundError):
        service.read('rt-'+'0'*32)
    assert not service.base.exists()
    with pytest.raises(ValueError):
        service.create(**dict(args,workbench=Path('../outside.json')))
    with pytest.raises(ValueError):
        service.run('../other')


def test_creation_crash_recovers_input_only_without_executing_provider(task, monkeypatch):
    service,args,_ = task
    save = service._save
    def crash(*args, **kwargs):
        raise SystemExit('TEST_ONLY crash after immutable input, before first version')
    monkeypatch.setattr(service,'_save',crash)
    with pytest.raises(SystemExit):
        service.create(**args)
    task_id = 'rt-' + mod._hash(args['request_key'].encode())[:32]
    monkeypatch.setattr(service,'_save',save)
    def forbidden(*args, **kwargs):
        raise AssertionError('input-only recovery must not execute provider')
    monkeypatch.setattr(MockLLMProvider,'complete',forbidden)
    recovered = service.resume(task_id)
    assert recovered['status'] == 'QUEUED' and recovered['version'] == 1
    assert recovered['attempts'] == recovered['provider_requests'] == 0


def test_future_workbench_cannot_be_run_even_with_historical_case(task):
    service,args,_ = task
    workbench = args['workbench']
    payload = json.loads(workbench.read_bytes())
    payload['generated_at'] = '2099-01-01T00:00:00+00:00'
    workbench.write_text(json.dumps(payload),encoding='utf-8')
    changed = dict(args,workbench_sha256=mod._hash(workbench.read_bytes()))
    created = service.create(**changed)
    assert created['status'] == 'FAILED' and created['provider_requests'] == 0


def test_business_clock_does_not_reject_china_date_at_utc_previous_day(task, monkeypatch):
    from dataclasses import replace
    from datetime import date
    service,args,_ = task
    native = mod.load_research_snapshot
    def local_date_snapshot(**kwargs):
        return replace(native(**kwargs),as_of=date(2026,11,1))
    monkeypatch.setattr(mod,'load_research_snapshot',local_date_snapshot)
    created = service.create(**args,now=datetime.fromisoformat('2026-10-31T16:30:00+00:00'))
    assert created['status'] == 'QUEUED'


@pytest.mark.parametrize('prompt_cap,completion_cap,expected', [(600,300,'FAILED'),(800,400,'SUCCEEDED')])
def test_response_generated_before_meter_crash_keeps_token_reservation(task, monkeypatch, prompt_cap, completion_cap, expected):
    service,args,_ = task
    task_id = service.create(**dict(args,budget=dict(max_prompt_tokens=prompt_cap,
        max_completion_tokens=completion_cap)))['task_id']
    native = MockLLMProvider.complete
    generated = []
    def crash_after_response(self,request):
        response = native(self,request)
        generated.append(response)
        raise SystemExit('TEST_ONLY response generated before usage settlement')
    monkeypatch.setattr(MockLLMProvider,'complete',crash_after_response)
    with pytest.raises(SystemExit):
        service.run(task_id)
    interrupted = service.read(task_id)
    assert len(generated) == interrupted['provider_requests'] == 1
    assert interrupted['usage'] == dict(prompt_tokens=200,completion_tokens=100)
    assert interrupted['unsettled_usage'] == dict(prompt_tokens=200,completion_tokens=100)
    assert service.resume(task_id)['status'] == 'QUEUED'
    monkeypatch.setattr(MockLLMProvider,'complete',native)
    result = service.run(task_id)
    assert result['status'] == expected
    assert result['usage'] == dict(prompt_tokens=200 if expected=='FAILED' else 800,
                                 completion_tokens=100 if expected=='FAILED' else 400)
    assert result['provider_requests'] == (1 if expected=='FAILED' else 4)
    assert result['unsettled_usage'] == dict(prompt_tokens=200,completion_tokens=100)
    assert result['new_llm_calls'] == 0


def test_symbol_discovery_survives_new_service_and_is_read_only(task):
    service,args,original = task
    first = service.create(**args)
    second = service.create(**dict(args,request_key='TEST_ONLY-second'))
    service.cancel(second['task_id'])
    before = {p.relative_to(service.root).as_posix():p.read_bytes() for p in service.root.rglob('*') if p.is_file()}
    fresh = mod.ResearchTaskService(service.root)
    rows = fresh.list_for_symbol('600519')
    assert {row['task_id'] for row in rows} == {first['task_id'],second['task_id']}
    assert {row['status'] for row in rows} == {'QUEUED','CANCELLED'}
    assert fresh.list_for_symbol('600887') == []
    assert before == {p.relative_to(service.root).as_posix():p.read_bytes() for p in service.root.rglob('*') if p.is_file()}
    original.write_bytes(b'TEST_ONLY changed evidence')
    broken = fresh.list_for_symbol('600519')
    assert next(row for row in broken if row['task_id']==first['task_id'])['status'] == 'FAILED'


def test_symbol_discovery_missing_store_is_zero_write(task):
    service,_,_ = task
    assert service.list_for_symbol('600519') == []
    assert not service.base.exists()


def test_symbol_discovery_rejects_instead_of_silently_truncating_directories(task):
    service,_,_ = task
    for number in range(101):
        (service.base/('rt-'+f'{number:032x}')).mkdir(parents=True)
    with pytest.raises(ValueError,match='DISCOVERY_LIMIT_EXCEEDED'):
        service.list_for_symbol('600519')


def test_symbol_discovery_rejects_more_than_twenty_results(task):
    service,args,_ = task
    for number in range(21):
        service.create(**dict(args,request_key='TEST_ONLY-list-'+str(number)))
    with pytest.raises(ValueError,match='RESULT_LIMIT_EXCEEDED'):
        service.list_for_symbol('600519')


def test_corrupt_discovered_task_is_identified_and_never_hidden(task):
    service,args,_ = task
    task_id = service.create(**args)['task_id']
    (service._directory(task_id)/'current.json').write_text('{}',encoding='utf-8')
    with pytest.raises(ValueError,match='DISCOVERY_INVALID:'+task_id):
        service.list_for_symbol('600519')


def test_read_and_discovery_never_recreate_a_missing_lock_file(task):
    service,args,_ = task
    task_id = service.create(**args)['task_id']
    lock = service._directory(task_id)/'state.lock'
    lock.unlink()
    with pytest.raises(ValueError,match='state lock missing'):
        service.read(task_id)
    with pytest.raises(ValueError,match='DISCOVERY_INVALID'):
        service.list_for_symbol('600519')
    assert not lock.exists()
