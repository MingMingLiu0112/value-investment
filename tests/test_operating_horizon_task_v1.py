"""Offline annual task persistence, provenance and shared-budget contracts."""
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
import json
import socket
from types import SimpleNamespace

import pytest

from test_operating_horizon_draft_v1 import context, payload, NOW
from value_investment_agent.application.research.agent_review import operating_horizon_task_v1 as mod
from value_investment_agent.infrastructure.agent_runtime.provider import LLMResponse


@pytest.fixture
def env(tmp_path_factory, monkeypatch, context):
    root = tmp_path_factory.mktemp('ht')
    monkeypatch.setattr(mod, '_now', lambda value=None: value or NOW)
    def no_network(*args, **kwargs):
        pytest.fail('Real provider/network forbidden in contract tests')
    monkeypatch.setattr(socket.socket, 'connect', no_network)
    monkeypatch.setattr(mod.live.OpenAICompatibleChatProvider, 'complete', no_network)
    cfg = dict(endpoint='https://test-only.invalid/v1/chat/completions', model_id='TEST_ONLY',
        api_key_env='VALUE_AGENT_TEST_ONLY_KEY', timeout_seconds=1, max_completion_tokens_cap=4096,
        max_run_cost='10', input_cost_per_million='1', output_cost_per_million='2',
        authorized=True, authorization_reference='TEST_ONLY', currency='CNY', daily_cost_limit='10')
    config = root / mod.live.CONFIG
    config.parent.mkdir(parents=True)
    config.write_text(json.dumps(cfg), encoding='utf-8')
    original = root / 'runtime/original.json'
    original.parent.mkdir(parents=True)
    original.write_text(json.dumps(context), encoding='utf-8')
    def loader(*, root, symbol, now, binding=None):
        raw = original.read_bytes()
        pin = dict(path='runtime/original.json', sha256=mod._hash(raw))
        if binding is not None and pin != binding:
            raise ValueError('SOURCE_CHANGED')
        ctx = json.loads(raw)
        ctx.update(symbol=symbol, as_of=now.isoformat(), source_binding=pin)
        ctx['snapshot_fingerprint'] = mod._hash(mod._bytes(ctx))
        return ctx
    class Provider:
        def __init__(self):
            self.calls = []
            self.behavior = None
        def complete(self, request):
            self.calls.append(request)
            if self.behavior:
                return self.behavior(request)
            years = [int(y) for y in request.output_schema['properties']['years']['required']]
            return LLMResponse(json.dumps(payload(years)), 100, 50, 'TEST_ONLY')
    provider = Provider()
    def service():
        return mod.OperatingHorizonTaskService(root, test_provider=provider, source_loader=loader)
    return SimpleNamespace(root=root, cfg=cfg, config=config, original=original,
                           loader=loader, provider=provider, service=service)


def create(env, years=None, key='TEST_ONLY_horizon'):
    return env.service().create(symbol='123456', request_key=key,
                                years=[2026] if years is None else years, now=NOW)['task_id']


def records(env):
    live = mod.live.LiveOperatingTaskService(env.root)
    head = live.base / 'budget/2026-11-05/current.json'
    return live._bound(json.loads(head.read_bytes()))['records']


def test_round_trip_single_call_read_list_and_current_year(env):
    task = create(env)
    out = env.service().run(task)
    assert out['status'] == 'SUCCEEDED', out
    assert len(env.provider.calls) == 1
    result = out['research_result']
    assert result['years']['2026']['estimate_kind'] == 'CURRENT_FY_ESTIMATE'
    assert result['years']['2026']['calculated_paths']['base']['extrema']['growth_lower']['revenue_cny'] == '1010.00'
    assert out['review_status'] == 'PENDING' and out['d2_three_role_complete'] is False
    assert out['action'] == 'no_order' and not out['valuation_produced']
    assert not out['approval_changed'] and not out['formal_eligibility']
    for key in ('source_binding', 'research_as_of', 'context_fingerprint', 'record_binding'):
        assert out[key]
    cold = env.service()
    assert cold.read(task)['research_result'] == result
    assert cold.list_for_symbol('123456')[0]['research_result'] == result
    assert cold.list_for_symbol('654321') == []
    assert cold.run(task)['research_result'] == result
    assert cold.resume(task)['research_result'] == result
    assert len(env.provider.calls) == 1
    assert len(records(env)) == 1
    assert next(iter(records(env).values())) == dict(status='SETTLED', cost='0.0002')
    assert not (cold.base / 'budget').exists()


@pytest.mark.parametrize('years', [[], [2026,2026], [2027,2026], [2026,2028], [2026,2027,2028,2029], [True], None])
def test_years_explicit_bounded_unique_consecutive(env, years):
    with pytest.raises(ValueError):
        env.service().create(symbol='123456', request_key='TEST_ONLY_invalid', years=years, now=NOW)
    assert not env.provider.calls


def test_three_years_one_call_not_three_roles(env):
    out = env.service().run(create(env, [2026,2027,2028]))
    assert out['status'] == 'SUCCEEDED'
    assert set(out['research_result']['years']) == {'2026','2027','2028'}
    assert len(env.provider.calls) == 1 and not out['d2_three_role_complete']


def test_idempotent_cutoff_and_conflicting_years(env):
    task = create(env)
    out = env.service().create(symbol='123456', request_key='TEST_ONLY_horizon', years=[2026], now=NOW+timedelta(days=1))
    assert out['task_id'] == task and out['research_as_of'] == NOW.isoformat()
    with pytest.raises(ValueError, match='CONFLICT'):
        create(env, [2027])
    assert not env.provider.calls


def test_legacy_budget_exhaustion_blocks_horizon_and_inverse(env):
    old = mod.live.LiveOperatingTaskService(env.root)
    old._daily_budget('2026-11-05', 'old-call', Decimal('10'), env.cfg)
    result = env.service().run(create(env))
    assert result['status'] == 'FAILED' and not env.provider.calls
    assert list(records(env)) == ['old-call']


def test_horizon_reservation_charged_to_legacy(env):
    def timeout(request):
        raise TimeoutError('secret must not be persisted')
    env.provider.behavior = timeout
    task = create(env)
    result = env.service().run(task)
    assert result['status'] == 'FAILED'
    assert Decimal(result['reserved_cost']) > 0
    assert next(iter(records(env).values()))['status'] == 'RESERVED'
    old = mod.live.LiveOperatingTaskService(env.root)
    with pytest.raises(ValueError, match='DAILY_BUDGET_EXHAUSTED'):
        old._daily_budget('2026-11-05', 'old-call', Decimal('10'), env.cfg)
    env.service().resume(task)
    env.service().run(task)
    assert len(env.provider.calls) == 1
    assert 'secret must not' not in ''.join(p.read_text(encoding='utf-8') for p in env.service()._directory(task).rglob('*.json'))


@pytest.mark.parametrize('damage', ['source', 'implementation', 'request'])
def test_pre_call_binding_fails_closed(env, monkeypatch, damage):
    task = create(env)
    if damage == 'source':
        env.original.write_bytes(b'{}')
    elif damage == 'implementation':
        monkeypatch.setattr(mod, 'implementation', lambda: {'changed': 'x'})
    else:
        original = mod.draft.build_request
        def changed(*args, **kwargs):
            from dataclasses import replace
            return replace(original(*args, **kwargs), system='changed')
        monkeypatch.setattr(mod.draft, 'build_request', changed)
    assert env.service().run(task)['status'] == 'FAILED'
    assert not env.provider.calls


def test_rejected_response_retained_without_second_call(env):
    env.provider.behavior = lambda req: LLMResponse('{"years":{}}', 10, 10, 'TEST_ONLY')
    task = create(env)
    out = env.service().run(task)
    assert out['status'] == 'FAILED' and out['response_binding']
    assert env.service()._bound(out['response_binding'])['response']['text'] == '{"years":{}}'
    assert next(iter(records(env).values()))['status'] == 'SETTLED'
    assert env.service().resume(task)['status'] == 'FAILED'
    assert len(env.provider.calls) == 1


def test_cancel_before_and_during_provider(env):
    first = create(env)
    assert env.service().cancel(first)['status'] == 'CANCELLED'
    assert env.service().run(first)['status'] == 'CANCELLED'
    assert not env.provider.calls
    second = create(env, key='TEST_ONLY_cancel')
    def cancelled(request):
        env.service().cancel(second)
        return LLMResponse(json.dumps(payload([2026])), 100, 50, 'TEST_ONLY')
    env.provider.behavior = cancelled
    out = env.service().run(second)
    assert out['status'] == 'CANCELLED' and out['response_binding']
    assert env.service().resume(second)['status'] == 'CANCELLED'


def test_head_recovery_and_checkpoint_tamper(env):
    task = create(env)
    out = env.service().run(task)
    directory = env.service()._directory(task)
    (directory / 'current.json').unlink()
    with pytest.raises(ValueError, match='HEAD_MISSING'):
        env.service().read(task)
    assert env.service().resume(task)['research_result'] == out['research_result']
    (directory / 'response.json').write_bytes(b'{}')
    assert env.service().read(task)['status'] == 'FAILED'
    assert len(env.provider.calls) == 1


def test_recovery_after_response_published_before_completion(env, monkeypatch):
    task = create(env)
    service = env.service()
    save = service._save
    def crash(spec, state, pin, now, **changes):
        if changes.get('status') == 'SUCCEEDED':
            raise KeyboardInterrupt('TEST_ONLY simulated process death')
        return save(spec, state, pin, now, **changes)
    monkeypatch.setattr(service, '_save', crash)
    with pytest.raises(KeyboardInterrupt):
        service.run(task)
    assert env.service().read(task)['persisted_status'] == 'RUNNING'
    assert env.service().resume(task)['status'] == 'SUCCEEDED'
    assert len(env.provider.calls) == 1


def test_model_authorization_changed_before_call(env):
    task = create(env)
    cfg = deepcopy(env.cfg)
    cfg['authorized'] = False
    env.config.write_text(json.dumps(cfg), encoding='utf-8')
    assert env.service().run(task)['status'] == 'FAILED'
    assert not env.provider.calls


def test_new_implementation_does_not_enter_legacy_hash(env):
    old = mod.live.implementation()
    assert mod.__name__ not in old and mod.draft.__name__ not in old
    assert set(old) < set(mod.implementation())

@pytest.mark.parametrize('counts', [(-1, 5), (True, 5), (100, 4097)])
def test_invalid_usage_retains_response_and_reservation(env, counts):
    env.provider.behavior = lambda req: LLMResponse(json.dumps(payload([2026])), *counts, 'TEST_ONLY')
    task = create(env)
    out = env.service().run(task)
    assert out['status'] == 'FAILED' and out['response_binding']
    assert next(iter(records(env).values()))['status'] == 'RESERVED'
    assert env.service().resume(task)['status'] == 'FAILED'
    assert len(env.provider.calls) == 1


def test_execution_lock_and_immutable_chain(env):
    task = create(env)
    service = env.service()
    directory = service._directory(task)
    with service._lock(directory, 'execution'):
        with pytest.raises(Exception):
            env.service().run(task)
    assert not env.provider.calls
    spec = directory / 'input.json'
    spec.write_bytes(spec.read_bytes() + b' ')
    with pytest.raises(ValueError, match='CHAIN_INVALID'):
        env.service().read(task)


def test_source_changed_during_call_cannot_publish_success(env):
    task = create(env)
    def changed(req):
        env.original.write_bytes(b'{}')
        return LLMResponse(json.dumps(payload([2026])), 100, 50, 'TEST_ONLY')
    env.provider.behavior = changed
    out = env.service().run(task)
    assert out['status'] == 'FAILED' and out['response_binding']
    assert out['research_result'] is None
    assert len(env.provider.calls) == 1


def test_wrong_model_rejected_and_reservation_retained(env):
    env.provider.behavior = lambda req: LLMResponse(json.dumps(payload([2026])), 100, 50, 'OTHER_MODEL')
    task = create(env)
    out = env.service().run(task)
    assert out['status'] == 'FAILED'
    assert out['error_code'] == 'HORIZON_PROVIDER_MODEL_MISMATCH'
    assert out['response_binding'] and out['research_result'] is None
    assert next(iter(records(env).values()))['status'] == 'RESERVED'
    assert env.service().resume(task)['error_code'] == 'HORIZON_PROVIDER_MODEL_MISMATCH'
    assert len(env.provider.calls) == 1


@pytest.mark.parametrize('kind,code', [
    ('citation', 'UNKNOWN_MISSING_DUPLICATE_HORIZON_CITATION'),
    ('fields', 'HORIZON_EXACT_FIELDS_REQUIRED'),
    ('incomplete', 'HORIZON_PROVIDER_RESPONSE_INCOMPLETE'),
    ('unknown', 'HORIZON_STRUCTURED_RESPONSE_OR_SOURCE_REJECTED'),
])
def test_safe_error_classification(env, kind, code):
    def response(req):
        if kind == 'incomplete':
            raise ValueError('LLM response is truncated, filtered, refused or incomplete')
        if kind == 'unknown':
            raise ValueError('SECRET_PROVIDER_TEXT_MUST_NOT_BE_PERSISTED')
        value = payload([2026])
        if kind == 'fields':
            value['extra'] = 'not_allowed'
        else:
            value['years']['2026']['operating_paths']['base']['drivers']['volume_change']['evidence_ids'] = ['missing']
        return LLMResponse(json.dumps(value), 100, 50, 'TEST_ONLY')
    env.provider.behavior = response
    task = create(env)
    out = env.service().run(task)
    assert out['status'] == 'FAILED' and out['error_code'] == code
    assert env.service().read(task)['error_code'] == code
    assert 'SECRET_PROVIDER_TEXT' not in ''.join(p.read_text(encoding='utf-8') for p in env.service()._directory(task).rglob('*.json'))


def test_response_published_but_budget_settlement_failure_never_recovers_success(env, monkeypatch):
    task = create(env)
    service = env.service()
    daily_budget = service._daily_budget
    def fail_settlement(*args, **kwargs):
        if kwargs.get('settle'):
            raise ValueError('DAILY_BUDGET_HEAD_UNPUBLISHED_FAIL_CLOSED')
        return daily_budget(*args, **kwargs)
    monkeypatch.setattr(service, '_daily_budget', fail_settlement)
    out = service.run(task)
    assert out['persisted_status'] == 'FAILED' and out['response_binding']
    assert out['research_result'] is None
    assert out['error_code'] == 'DAILY_BUDGET_HEAD_UNPUBLISHED_FAIL_CLOSED'
    assert next(iter(records(env).values()))['status'] == 'RESERVED'
    for operation in ('read', 'resume', 'run'):
        recovered = getattr(env.service(), operation)(task)
        assert recovered['status'] == 'FAILED'
        assert recovered['research_result'] is None
    assert len(env.provider.calls) == 1
    assert next(iter(records(env).values()))['status'] == 'RESERVED'


def test_ledger_settled_local_save_crash_remains_failed(env, monkeypatch):
    task = create(env)
    service = env.service()
    save = service._save
    def crash(spec, state, pin, now, **changes):
        if changes.get('settled_cost'):
            raise KeyboardInterrupt('TEST_ONLY crash between ledger and task settlement')
        return save(spec, state, pin, now, **changes)
    monkeypatch.setattr(service, '_save', crash)
    with pytest.raises(KeyboardInterrupt):
        service.run(task)
    assert next(iter(records(env).values()))['status'] == 'SETTLED'
    for operation in ('read', 'resume', 'run'):
        out = getattr(env.service(), operation)(task)
        assert out['status'] == 'FAILED' and out['research_result'] is None
        assert out['error_code'] == 'HORIZON_SETTLEMENT_UNVERIFIED'
    assert len(env.provider.calls) == 1


def test_success_requires_intact_shared_settlement_ledger(env):
    task = create(env)
    assert env.service().run(task)['status'] == 'SUCCEEDED'
    old = mod.live.LiveOperatingTaskService(env.root)
    head = old.base / 'budget/2026-11-05/current.json'
    head.write_bytes(b'{}')
    for operation in ('read', 'resume', 'run'):
        out = getattr(env.service(), operation)(task)
        assert out['status'] == 'FAILED' and out['research_result'] is None
        assert out['error_code'] == 'DAILY_BUDGET_HEAD_UNPUBLISHED_FAIL_CLOSED'
    assert len(env.provider.calls) == 1
