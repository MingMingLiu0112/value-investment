"""TEST_ONLY service contracts: synthetic source bytes, no provider/network access."""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import socket
from types import SimpleNamespace

import pytest

from value_investment_agent.application.research.agent_review import operating_task_v2 as mod
from value_investment_agent.application.research.agent_review import operating_draft_v1 as draft
from value_investment_agent.infrastructure.agent_runtime.provider import LLMResponse

NOW = datetime(2026, 10, 31, 8, tzinfo=timezone.utc)


def reply(role):
    statement = dict(text='TEST_ONLY interpretation, not a verified fact.', evidence_ids=['test:1'])
    if role == 'EVENT':
        return dict(seen_events=[], uncovered=[dict(text='TEST_ONLY uncovered events.', evidence_ids=[])])
    if role == 'COUNTER_EVIDENCE':
        return dict(counterevidence=[deepcopy(statement)], invalidation=[deepcopy(statement)])
    rows = [dict(dimension=dimension, period_start='2027-01-01', period_end='2027-12-31',
                 classification='UNKNOWN', lower=None, upper=None, unit='not_quantified',
                 rationale='TEST_ONLY insufficient evidence.', evidence_ids=['test:1'])
            for dimension in draft.DIMENSIONS]
    return dict(business_drivers=[statement], scenarios={name: deepcopy(rows) for name in ('bear', 'base', 'bull')})


class TestOnlyProvider:
    __test__ = False

    def __init__(self, behavior=None):
        self.calls = []
        self.requests = []
        self.behavior = behavior

    def complete(self, request):
        self.calls.append(request.role)
        self.requests.append(request)
        if self.behavior:
            response = self.behavior(request)
            if response is not None:
                return response
        return LLMResponse(json.dumps(reply(request.role)), 100, 50, 'TEST_ONLY_MODEL')


@pytest.fixture
def env(tmp_path_factory, monkeypatch):
    # Keep Windows immutable-version paths below MAX_PATH without changing storage.
    tmp_path = tmp_path_factory.mktemp('ot')
    def no_network(*args, **kwargs):
        pytest.fail('TEST_ONLY test attempted a real model/network call')

    monkeypatch.setattr(socket.socket, 'connect', no_network)
    monkeypatch.setattr(mod.OpenAICompatibleChatProvider, 'complete', no_network)
    monkeypatch.delenv('VALUE_AGENT_TEST_ONLY_KEY', raising=False)
    monkeypatch.setattr(mod, '_now', lambda value=None: value or NOW)
    cfg = dict(endpoint='https://test-only.invalid/v1/chat/completions', model_id='TEST_ONLY_MODEL',
               api_key_env='VALUE_AGENT_TEST_ONLY_KEY', timeout_seconds=1, max_completion_tokens_cap=512,
               max_run_cost='10', input_cost_per_million='1', output_cost_per_million='2',
               authorized=True, authorization_reference='TEST_ONLY_NOT_REAL_AUTHORIZATION',
               currency='CNY', daily_cost_limit='10')
    config = tmp_path / mod.CONFIG
    config.parent.mkdir(parents=True)
    source = tmp_path / 'runtime/TEST_ONLY-source.txt'
    source.parent.mkdir(parents=True)
    source.write_bytes(b'TEST_ONLY synthetic bytes, not a financial original')

    def configure(**changes):
        cfg.update(changes)
        config.write_text(json.dumps(cfg), encoding='utf-8')

    configure()

    def loader(*, root, symbol, now, binding=None):
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        pin = dict(path=source.relative_to(tmp_path).as_posix(), sha256=digest)
        if binding is not None and binding != pin:
            raise ValueError('TEST_ONLY_SOURCE_HASH_CHANGED')
        # Match the production sourcebuilder envelope, without pretending these are originals.
        value = dict(schema_version='operating-source-context-v1', symbol=symbol,
                     issuer_name='TEST_ONLY issuer', as_of=now.isoformat(),
                     financial_basis='TEST_ONLY', source_binding=pin, action='no_order',
                     limitations=['TEST_ONLY fixture, not real source acceptance'], evidence=[dict(
                         id='test:1', source_id='TEST_ONLY', pdf_sha256=digest,
                         available_at='2026-10-30T00:00:00+00:00', period='2026-06-30',
                         scope='consolidated', unit='CNY', value='10', field='cash',
                         physical_page=1, text='TEST_ONLY cash 10', kind='VERIFIED_REPORTED_FACT')])
        value['snapshot_fingerprint'] = hashlib.sha256(mod._bytes(value)).hexdigest()
        return value

    def service(provider=None):
        return mod.LiveOperatingTaskService(tmp_path, test_provider=provider or TestOnlyProvider(), source_loader=loader)

    return SimpleNamespace(root=tmp_path, cfg=cfg, configure=configure, source=source,
                           loader=loader, service=service)


def create(service, key='TEST_ONLY_request'):
    return service.create(symbol='123456', request_key=key, now=NOW)['task_id']


def daily_records(service):
    head = service.base / 'budget/2026-10-31/current.json'
    return service._bound(json.loads(head.read_bytes()))['records']


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*')
            if p.is_file() and p.suffix != '.lock'}


def test_precall_cost_rejects_without_provider_or_reservation(env):
    env.configure(max_run_cost='0.000001')
    provider = TestOnlyProvider()
    service = env.service(provider)
    result = service.run(create(service))
    assert result['status'] == 'FAILED'
    assert result['error_code'] == 'LIVE_BUDGET_EXHAUSTED_BEFORE_CALL'
    assert provider.calls == [] and result['provider_requests'] == 0
    assert Decimal(result['reserved_cost']) == Decimal(result['settled_cost']) == 0
    assert result['reservations'] == {}


def test_service_rejects_8192_completion_cap_before_task_or_call(env):
    env.configure(max_completion_tokens_cap=8192)
    provider = TestOnlyProvider()
    service = env.service(provider)
    before = snapshot(env.root)
    with pytest.raises(ValueError, match='^MODEL_COMPLETION_CAP_INVALID$'):
        mod.model_configuration(env.root)
    with pytest.raises(ValueError, match='^MODEL_COMPLETION_CAP_INVALID$'):
        create(service)
    assert provider.calls == []
    assert snapshot(env.root) == before
    assert not service.base.exists()


def test_timeout_preserves_durable_reservation(env):
    def timeout(request):
        raise TimeoutError('TEST_ONLY unknown provider outcome')
    provider = TestOnlyProvider(timeout)
    service = env.service(provider)
    task = create(service)
    result = service.run(task)
    assert result['status'] == 'FAILED' and provider.calls == ['FUNDAMENTAL']
    assert Decimal(result['reserved_cost']) > 0 and Decimal(result['settled_cost']) == 0
    assert result['usage'] == dict(prompt_tokens=0, completion_tokens=0)
    assert {r['status'] for r in result['reservations'].values()} == {'RESERVED'}
    cold = env.service().read(task)
    assert cold['reserved_cost'] == result['reserved_cost']
    records = daily_records(service)
    assert {r['status'] for r in records.values()} == {'RESERVED'}
    assert sum(Decimal(r['cost']) for r in records.values()) == Decimal(result['reserved_cost'])


def test_three_roles_settle_usage_and_remain_unapproved(env):
    provider = TestOnlyProvider()
    service = env.service(provider)
    task = create(service)
    result = service.run(task)
    assert result['status'] == 'SUCCEEDED', result.get('error_code')
    assert provider.calls == list(mod.ROLES)
    assert result['usage'] == dict(prompt_tokens=300, completion_tokens=150)
    assert Decimal(result['settled_cost']) == Decimal('0.0006')
    assert Decimal(result['reserved_cost']) == 0
    assert set(result['roles']) == set(result['research_draft']) == set(mod.ROLES)
    assert result['execution_mode'] == 'TEST_ONLY_LIVE_CONTRACT' and result['new_llm_calls'] == 0
    assert result['currency'] == 'CNY' and result['daily_cost_limit'] == '10'
    assert not result['formal_eligibility'] and not result['approval_changed']
    assert result['formal_fact_count'] == 0 and result['condition_price'] is None
    assert result['action'] == 'no_order' and not result['main_range_adopted']
    records = daily_records(service)
    assert len(records) == 3 and {r['status'] for r in records.values()} == {'SETTLED'}
    assert sum(Decimal(r['cost']) for r in records.values()) == Decimal('0.0006')


def test_falsey_test_provider_remains_test_only_after_three_roles(env):
    class FalseyTestOnlyProvider(TestOnlyProvider):
        def __bool__(self):
            return False

    provider = FalseyTestOnlyProvider()
    # Pass directly: the fixture factory's fallback must not replace this object.
    service = mod.LiveOperatingTaskService(env.root, test_provider=provider, source_loader=env.loader)
    task = create(service)
    result = service.run(task)
    assert result['status'] == 'SUCCEEDED', result.get('error_code')
    assert provider.calls == list(mod.ROLES)
    assert result['provider_requests'] == 3
    assert result['execution_mode'] == 'TEST_ONLY_LIVE_CONTRACT'
    assert result['scope'] == 'TEST_ONLY_LIVE_CONTRACT_NOT_REAL_RESEARCH'
    assert result['new_llm_calls'] == 0
    assert result['action'] == 'no_order' and not result['formal_eligibility']
    cold = mod.LiveOperatingTaskService(env.root, test_provider=provider, source_loader=env.loader).read(task)
    assert cold['scope'] == result['scope'] and cold['new_llm_calls'] == 0
    assert provider.calls == list(mod.ROLES)


@pytest.mark.parametrize('failed_role', ['COUNTER_EVIDENCE', 'EVENT'])
def test_checkpoint_resume_new_instance_only_calls_unfinished_roles(env, failed_role):
    def timeout(request):
        if request.role == failed_role:
            raise TimeoutError('TEST_ONLY interruption')
    first = TestOnlyProvider(timeout)
    service = env.service(first)
    task = create(service)
    failed = service.run(task)
    boundary = mod.ROLES.index(failed_role)
    assert failed['status'] == 'FAILED'
    assert set(failed['roles']) == set(mod.ROLES[:boundary])
    reserved = Decimal(failed['reserved_cost'])
    assert reserved > 0
    second = TestOnlyProvider()
    restarted = env.service(second)
    assert restarted.resume(task)['status'] == 'QUEUED'
    assert second.calls == []
    result = restarted.run(task)
    assert result['status'] == 'SUCCEEDED'
    assert second.calls == list(mod.ROLES[boundary:])
    assert result['attempts'] == 2 and result['provider_requests'] == 4
    assert Decimal(result['reserved_cost']) == reserved
    assert all(result['roles'][role] == pin for role, pin in failed['roles'].items())


@pytest.mark.parametrize('inflight', [False, True])
def test_cancel_never_calls_remaining_roles(env, inflight):
    provider = TestOnlyProvider()
    service = env.service(provider)
    task = create(service)
    if inflight:
        provider.behavior = lambda request: (service.cancel(task), None)[1]
    else:
        assert service.cancel(task)['status'] == 'CANCELLED'
    result = service.run(task)
    assert result['status'] == 'CANCELLED' and result['roles'] == {}
    assert provider.calls == (['FUNDAMENTAL'] if inflight else [])
    restarted = env.service()
    assert restarted.resume(task)['status'] == 'CANCELLED'
    assert restarted.run(task)['status'] == 'CANCELLED'
    if inflight:
        assert Decimal(result['settled_cost']) == Decimal('0.0002')


@pytest.mark.parametrize('inflight', [False, True])
def test_source_hash_change_prevents_call_or_checkpoint(env, inflight):
    provider = TestOnlyProvider()
    service = env.service(provider)
    task = create(service)
    def change(request):
        env.source.write_bytes(b'TEST_ONLY changed original bytes')
    if inflight:
        provider.behavior = change
    else:
        change(None)
    result = service.run(task)
    assert result['status'] == 'FAILED' and result['roles'] == {}
    assert result['error_code'] == 'SOURCE_OR_IMPLEMENTATION_CHANGED'
    assert provider.calls == (['FUNDAMENTAL'] if inflight else [])


@pytest.mark.parametrize('change', [dict(authorized=False), dict(authorization_reference='TEST_ONLY_CHANGED')])
def test_changed_authorization_before_run_blocks_call(env, change):
    provider = TestOnlyProvider()
    service = env.service(provider)
    task = create(service)
    env.configure(**change)
    result = service.run(task)
    assert result['status'] == 'FAILED' and provider.calls == []
    assert result['error_code'] in {'MODEL_AUTHORIZATION_REQUIRED', 'MODEL_AUTHORIZATION_CHANGED'}
    assert result['roles'] == {} and result['reservations'] == {}


def test_authorization_revoked_during_first_response_stops_later_calls(env):
    def revoke(request):
        env.configure(authorized=False)
    provider = TestOnlyProvider(revoke)
    service = env.service(provider)
    result = service.run(create(service))
    assert provider.calls == ['FUNDAMENTAL']
    assert result['status'] == 'FAILED'
    assert result['error_code'] in {'MODEL_AUTHORIZATION_REQUIRED', 'MODEL_AUTHORIZATION_CHANGED'}
    assert Decimal(result['settled_cost']) == Decimal('0.0002')


@pytest.mark.parametrize('bad', ['invalid_json', 'invented_evidence'])
def test_invalid_output_rejected_but_actual_usage_settled(env, bad):
    def response(request):
        payload = reply(request.role)
        payload['business_drivers'][0]['evidence_ids'] = ['TEST_ONLY_NONEXISTENT_EVIDENCE']
        text = 'not JSON' if bad == 'invalid_json' else json.dumps(payload)
        return LLMResponse(text, 100, 50, 'TEST_ONLY_MODEL')
    provider = TestOnlyProvider(response)
    service = env.service(provider)
    result = service.run(create(service))
    assert result['status'] == 'FAILED' and result['roles'] == {}
    assert provider.calls == ['FUNDAMENTAL']
    assert result['usage'] == dict(prompt_tokens=100, completion_tokens=50)
    assert Decimal(result['reserved_cost']) == 0
    assert Decimal(result['settled_cost']) == Decimal('0.0002')
    assert {r['status'] for r in daily_records(service).values()} == {'SETTLED'}


def test_create_and_run_idempotent_and_read_get_path_has_zero_calls(env):
    provider = TestOnlyProvider()
    service = env.service(provider)
    task = create(service)
    before = snapshot(env.root)
    assert create(service) == task
    assert service.read(task)['status'] == 'QUEUED'
    assert service.list_for_symbol('123456')[0]['task_id'] == task
    assert provider.calls == [] and snapshot(env.root) == before
    assert service.run(task)['status'] == 'SUCCEEDED'
    before = snapshot(env.root)
    assert service.run(task)['status'] == 'SUCCEEDED'
    assert service.read(task)['status'] == 'SUCCEEDED'
    assert create(service) == task
    assert len(provider.calls) == 3 and snapshot(env.root) == before
    env.configure(authorization_reference='TEST_ONLY_CHANGED')
    with pytest.raises(ValueError, match='LIVE_REQUEST_KEY_CONFLICT'):
        create(service)


@pytest.mark.parametrize('outcome', ['timeout', 'settled'])
def test_cross_task_daily_cap_survives_new_service_instance(env, outcome):
    # One request fits; its persisted charge plus another full reservation does not.
    env.configure(input_cost_per_million='100', output_cost_per_million='100')
    context = env.loader(root=env.root, symbol='123456', now=NOW)
    request = draft.build_request('FUNDAMENTAL', mod.research_context(context), max_completion_tokens=512)
    prompt_cap = len(mod._bytes(request.__dict__)) + 4096
    reservation = Decimal(prompt_cap + 512) / Decimal(10000)
    limit = reservation * Decimal('1.5')
    assert limit < 10
    env.configure(daily_cost_limit=str(limit), max_run_cost=str(limit))
    def response(request):
        if outcome == 'timeout':
            raise TimeoutError('TEST_ONLY unknown billing')
        # Full-cap usage, invalid JSON: settle charge without advancing the role.
        return LLMResponse('invalid JSON', prompt_cap, 512, 'TEST_ONLY_MODEL')
    first = TestOnlyProvider(response)
    service = env.service(first)
    failed = service.run(create(service, 'TEST_ONLY_daily_first'))
    assert failed['status'] == 'FAILED' and first.calls == ['FUNDAMENTAL']
    records_before = daily_records(service)
    assert sum(Decimal(r['cost']) for r in records_before.values()) == reservation
    second = TestOnlyProvider()
    restarted = env.service(second)
    result = restarted.run(create(restarted, 'TEST_ONLY_daily_second'))
    assert result['status'] == 'FAILED'
    assert result['error_code'] == 'DAILY_BUDGET_EXHAUSTED_BEFORE_CALL'
    assert second.calls == [] and result['provider_requests'] == 0
    assert daily_records(restarted) == records_before


def test_crash_after_daily_reserve_before_task_save_still_charges_next_task(env, monkeypatch):
    env.configure(input_cost_per_million='100', output_cost_per_million='100')
    context = env.loader(root=env.root, symbol='123456', now=NOW)
    request = draft.build_request('FUNDAMENTAL', mod.research_context(context), max_completion_tokens=512)
    reservation = Decimal(len(mod._bytes(request.__dict__)) + 4096 + 512) / Decimal(10000)
    limit = reservation * Decimal('1.5')
    env.configure(daily_cost_limit=str(limit), max_run_cost=str(limit))
    provider = TestOnlyProvider()
    service = env.service(provider)
    task = create(service, 'TEST_ONLY_crash_first')
    original_save = service._save

    class TestOnlyCrash(BaseException):
        pass

    def interrupted_save(*args, **kwargs):
        if kwargs.get('provider_requests') == 1:
            raise TestOnlyCrash('TEST_ONLY after durable daily reserve')
        return original_save(*args, **kwargs)

    monkeypatch.setattr(service, '_save', interrupted_save)
    with pytest.raises(TestOnlyCrash):
        service.run(task)
    assert provider.calls == []
    records = daily_records(service)
    assert len(records) == 1
    assert next(iter(records.values())) == dict(status='RESERVED', cost=str(reservation))
    second = TestOnlyProvider()
    restarted = env.service(second)
    interrupted = restarted.read(task)
    assert interrupted['status'] == 'RUNNING' and interrupted['provider_requests'] == 0
    assert Decimal(interrupted['reserved_cost']) == 0
    result = restarted.run(create(restarted, 'TEST_ONLY_crash_second'))
    assert result['error_code'] == 'DAILY_BUDGET_EXHAUSTED_BEFORE_CALL'
    assert second.calls == [] and daily_records(restarted) == records


@pytest.mark.parametrize('checkpoint_count', [1, 2])
def test_new_proposal_checkpoint_resume_preserves_requests_without_duplicate_roles(env, monkeypatch, checkpoint_count):
    marker = 'TEST_ONLY_THIS_RUN_FUNDAMENTAL_ASSUMPTION_7319'
    payload = reply('FUNDAMENTAL')
    payload['scenarios']['base'][0]['rationale'] = marker

    def fresh_fundamental(request):
        if request.role == 'FUNDAMENTAL':
            return LLMResponse(json.dumps(payload), 100, 50, 'TEST_ONLY_MODEL')

    first = TestOnlyProvider(fresh_fundamental)
    service = env.service(first)
    task = create(service)
    save = service._save

    class TestOnlyCheckpointCrash(BaseException):
        pass

    def stop_after_published_checkpoint(*args, **kwargs):
        result = save(*args, **kwargs)
        if len(kwargs.get('roles', {})) == checkpoint_count:
            raise TestOnlyCheckpointCrash()
        return result

    monkeypatch.setattr(service, '_save', stop_after_published_checkpoint)
    with pytest.raises(TestOnlyCheckpointCrash):
        service.run(task)
    assert first.calls == list(mod.ROLES[:checkpoint_count])
    second = TestOnlyProvider()
    restarted = env.service(second)
    saved = restarted.read(task)
    assert saved['status'] == 'RUNNING'
    assert saved['research_draft']['FUNDAMENTAL']['draft'] == payload
    assert restarted.resume(task)['status'] == 'QUEUED'
    assert second.calls == []
    result = restarted.run(task)
    assert result['status'] == 'SUCCEEDED', result.get('error_code')
    assert first.calls + second.calls == list(mod.ROLES)
    assert result['provider_requests'] == 3
    assert all(result['roles'][role] == pin for role, pin in saved['roles'].items())
    context = mod.research_context(env.loader(root=env.root, symbol='123456', now=NOW))
    for request in first.requests + second.requests:
        fundamental = result['research_draft']['FUNDAMENTAL'] if request.role != 'FUNDAMENTAL' else None
        rebuilt = draft.build_request(request.role, context, max_completion_tokens=512,
                                      fundamental_draft=fundamental)
        assert rebuilt == request
        packet = restarted._bound(result['roles'][request.role])
        assert packet['request_sha256'] == mod._hash(mod._bytes(rebuilt.__dict__))
        if request.role == 'FUNDAMENTAL':
            assert 'UNTRUSTED_NEW_PROPOSAL' not in request.user and marker not in request.user
        else:
            assert 'UNTRUSTED_NEW_PROPOSAL' in request.user
            assert marker in request.user
    # Cold read reconstructs the same bound requests without any extra provider call.
    assert env.service(second).read(task)['status'] == 'SUCCEEDED'
    assert first.calls + second.calls == list(mod.ROLES)
