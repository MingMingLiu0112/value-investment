"""TEST_ONLY owned-child supervision; no providers, network or real task writes."""
from contextlib import contextmanager, nullcontext
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import socket
import subprocess

import pytest

from value_investment_agent.operations import live_task_controller_v1 as app

TASK = 'rt-' + 'a' * 32


class Service:
    def __init__(self, root):
        self.root = root
        self.spec = {'symbol': '123456', 'task_id': TASK, 'config': {'TEST_ONLY': True}}
        self.input_raw = json.dumps(self.spec, sort_keys=True, separators=(',', ':')).encode()
        self.state = dict(status='QUEUED', error_code=None, version=1, reserved_cost='1.75',
            input_sha256=hashlib.sha256(self.input_raw).hexdigest(),
            settled_cost='0.25', reservations={'r': {'status': 'RESERVED', 'cost': '1.75'}},
            returned_responses=[{'path': 'runtime/TEST_ONLY-response', 'sha256': 'a' * 64}],
            roles={'FUNDAMENTAL': {'sha256': 'b' * 64}}, usage={'prompt_tokens': 20})
        self.saves = []
        self.loads = []

    def _directory(self, ident):
        assert ident == TASK
        return self.root / 'TEST_ONLY-task'

    def _lock(self, directory, name='state'):
        assert name in {'state', 'controller'}
        return nullcontext()

    def _load(self, ident, *, recover=False):
        assert ident == TASK
        self.loads.append(recover)
        return deepcopy(self.spec), deepcopy(self.state), {'sha256': str(self.state['version'])}

    def _save(self, spec, state, pin, now, **changes):
        assert spec == self.spec
        self.saves.append(deepcopy(changes))
        self.state = {**deepcopy(state), **deepcopy(changes), 'version': state['version'] + 1}
        return deepcopy(self.state), {'sha256': str(self.state['version'])}

    def _view(self, *a, **k):
        raise AssertionError('No expensive view allowed')


class Child:
    pid = 999999  # TEST_ONLY, never used in OS process control.
    def __init__(self, exit_code=None):
        self.returncode = exit_code
        self.killed = 0
        self.waited = 0
    def poll(self):
        return self.returncode
    def kill(self):
        self.killed += 1
        self.returncode = -9
    def wait(self, *, timeout):
        assert timeout == app.REAP_TIMEOUT_SECONDS
        self.waited += 1
        return self.returncode


@pytest.fixture
def case(tmp_path, monkeypatch):
    service = Service(tmp_path)
    child = Child()
    clock = [0.0]
    spawns = []
    on_sleep = [lambda: None]
    def sleep(seconds):
        assert 0 <= seconds <= .2
        clock[0] += seconds
        on_sleep[0]()
    def spawn(args, **kw):
        spawns.append((args, kw))
        return child
    monkeypatch.setattr(app, '_service', lambda root: service)
    monkeypatch.setattr(app, '_identity', lambda: {'controller_sha256': 'c' * 64, 'code_commit': 'd' * 40})
    monkeypatch.setattr(app.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(app.time, 'sleep', sleep)
    monkeypatch.setattr(app.subprocess, 'Popen', spawn)
    monkeypatch.setattr(socket.socket, 'connect', lambda *a: pytest.fail('No network'))
    return tmp_path, service, child, clock, spawns, on_sleep


def assert_retained(before, after):
    for k in ('reserved_cost', 'settled_cost', 'reservations', 'returned_responses', 'roles', 'usage', 'input_sha256'):
        assert after[k] == before[k]


def test_deadline_kills_only_owned_child_and_retains_budget_responses(case, monkeypatch):
    root, service, child, clock, spawns, _ = case
    monkeypatch.setenv('VALUE_AGENT_TEST_ONLY', 'SECRET_NOT_IN_COMMAND')
    before = deepcopy(service.state)
    result = app.supervise_live_task(root, TASK, timeout_seconds=.4)
    assert result['status'] == 'FAILED' and result['error_code'] == app.DEADLINE_ERROR
    assert child.killed == 1 and child.waited >= 1
    assert_retained(before, result)
    assert service.spec['config'] == {'TEST_ONLY': True}
    receipt = result['live_controller']
    assert receipt['controller_sha256'] == 'c' * 64 and receipt['code_commit'] == 'd' * 40
    assert receipt['deadline_at'] > receipt['started_at']
    assert receipt['result'] == 'TOTAL_DEADLINE_EXCEEDED'
    args, kw = spawns[0]
    assert args[1:] == ['-B', '-m', app.MODULE, '--worker', str(root), TASK]
    assert kw['cwd'] == root and kw['stdout'] == kw['stderr'] == kw['stdin'] == subprocess.DEVNULL
    assert 'SECRET' not in str(args) and any(service.loads)


def test_cancel_observed_kills_reaps_and_does_not_overwrite_cancel(case):
    root, service, child, _, _, on_sleep = case
    before = deepcopy(service.state)
    on_sleep[0] = lambda: service.state.update(status='CANCELLED', error_code='USER_CANCELLED')
    r = app.supervise_live_task(root, TASK, timeout_seconds=1)
    assert r['status'] == 'CANCELLED' and r['error_code'] == 'USER_CANCELLED'
    assert child.killed == 1 and child.waited >= 1
    assert_retained(before, r)


@pytest.mark.parametrize('status', ['SUCCEEDED', 'CANCELLED'])
def test_terminal_idempotence_no_new_record_or_child(case, status):
    root, service, child, _, spawns, _ = case
    service.state['status'] = status
    before = deepcopy(service.state)
    r = app.supervise_live_task(root, TASK)
    assert r['status'] == status and service.state == before
    assert not service.saves and not spawns and not child.killed


@pytest.mark.parametrize('code', [1, 0])
def test_early_exit_without_native_terminal_is_explicit_failure(case, code):
    root, service, child, _, _, _ = case
    child.returncode = code
    before = deepcopy(service.state)
    r = app.supervise_live_task(root, TASK)
    assert r['status'] == 'FAILED' and 'LIVE_WORKER_EXIT_' in r['error_code']
    assert r['live_controller']['worker_exit_code'] == code
    assert child.killed == 0 and child.waited >= 1
    assert_retained(before, r)


def test_native_success_preserved_even_worker_still_in_expensive_view(case):
    root, service, child, _, _, on_sleep = case
    on_sleep[0] = lambda: service.state.update(status='SUCCEEDED', error_code=None)
    r = app.supervise_live_task(root, TASK)
    assert r['status'] == 'SUCCEEDED' and r['error_code'] is None
    assert child.killed == 1 and r['live_controller']['result'] == 'NATIVE_SUCCEEDED'


def test_spawn_failure_safe_and_preserves_state(case, monkeypatch):
    root, service, _, _, _, _ = case
    before = deepcopy(service.state)
    def fail(*a, **k):
        raise OSError('SECRET raw endpoint/config')
    monkeypatch.setattr(app.subprocess, 'Popen', fail)
    r = app.supervise_live_task(root, TASK)
    assert r['status'] == 'FAILED' and r['error_code'] == 'LIVE_WORKER_START_FAILED'
    assert 'SECRET' not in str(r)
    assert_retained(before, r)


def test_worker_calls_only_original_service_run(monkeypatch, tmp_path):
    calls = []
    class Original:
        def run(self, task_id):
            calls.append(task_id)
    monkeypatch.setattr(app, '_service', lambda root: Original())
    assert app._worker_main(['--worker', str(tmp_path), TASK]) == 0
    assert calls == [TASK]
    assert app._worker_main(['--worker', str(tmp_path), 'bad']) == 2


@pytest.mark.parametrize('value', [0, -1, True, float('nan'), 3601])
def test_invalid_deadline_does_not_spawn(case, value):
    root, service, _, _, spawns, _ = case
    with pytest.raises(ValueError):
        app.supervise_live_task(root, TASK, value)
    assert not spawns and not service.saves


def test_existing_running_task_not_owned_is_not_relaunched(case):
    root, service, _, _, spawns, _ = case
    service.state['status'] = 'RUNNING'
    with pytest.raises(ValueError, match='REQUIRES_QUEUED'):
        app.supervise_live_task(root, TASK)
    assert not spawns and not service.saves


def test_failed_kill_and_bounded_wait_never_claims_termination(case, monkeypatch):
    root, service, child, _, _, _ = case
    before = deepcopy(service.state)
    def failed_kill():
        child.killed += 1
        raise OSError('TEST_ONLY kill failed')
    def blocked_wait(*, timeout):
        assert timeout == 5
        child.waited += 1
        raise subprocess.TimeoutExpired('TEST_ONLY owned child', timeout)
    monkeypatch.setattr(child, 'kill', failed_kill)
    monkeypatch.setattr(child, 'wait', blocked_wait)
    with pytest.raises(RuntimeError, match='^LIVE_CONTROLLER_CHILD_TERMINATION_UNCONFIRMED$'):
        app.supervise_live_task(root, TASK, timeout_seconds=.2)
    assert child.killed == child.waited == 1  # finally does not repeat a five-second wait.
    assert service.state['status'] == before['status']
    assert service.state['live_controller']['result'] == 'STARTING'
    assert_retained(before, service.state)


def test_kill_exit_race_accepts_only_confirmed_exit(case, monkeypatch):
    _, _, child, _, _, _ = case
    def exited_during_kill():
        child.returncode = 0
        raise ProcessLookupError('TEST_ONLY already exited')
    monkeypatch.setattr(child, 'kill', exited_during_kill)
    app._reap(child)
    assert child.waited == 1 and child.poll() == 0


def test_terminal_state_lock_race_retries_then_persists_failure(case, monkeypatch):
    root, service, child, clock, _, on_sleep = case
    before = deepcopy(service.state)
    @contextmanager
    def lock(directory, name='state'):
        if name == 'state' and .2 <= clock[0] < .8:
            raise app.LockTimeout('TEST_ONLY UI _view holds state lock')
        yield
    monkeypatch.setattr(service, '_lock', lock)
    on_sleep[0] = lambda: service.state.update(status='RUNNING')
    r = app.supervise_live_task(root, TASK, timeout_seconds=.2)
    assert clock[0] >= .8 and child.killed == 1
    assert r['status'] == 'FAILED' and r['error_code'] == app.DEADLINE_ERROR
    assert_retained(before, r)


def pending_case(case, monkeypatch):
    root, service, child, clock, _, on_sleep = case
    directory = service._directory(TASK)
    directory.mkdir()
    (directory / 'input.json').write_bytes(service.input_raw)
    busy = [True]
    @contextmanager
    def lock(directory, name='state'):
        if name == 'state' and busy[0] and clock[0] >= .2:
            raise app.LockTimeout('TEST_ONLY long UI read')
        yield
    monkeypatch.setattr(service, '_lock', lock)
    monkeypatch.setattr(app, 'FINALIZE_LOCK_RETRY_SECONDS', .4)
    on_sleep[0] = lambda: service.state.update(status='RUNNING')
    before = deepcopy(service.state)
    r = app.supervise_live_task(root, TASK, timeout_seconds=.2)
    return root, service, child, busy, before, r


def test_lock_exhaustion_durable_pending_then_explicit_idempotent_finalization(case, monkeypatch):
    root, service, child, busy, before, r = pending_case(case, monkeypatch)
    assert child.killed == 1 and r['status'] == 'FINALIZATION_PENDING'
    assert r['persisted_task_status'] is None and service.state['status'] == 'RUNNING'
    assert service.state['live_controller']['result'] == 'STARTING'
    binding = r['pending_bindings'][0]
    path = root / binding['path']
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == binding['sha256']
    assert path.name == app.PENDING_PREFIX + binding['sha256'] + '.json'
    assert json.loads(raw)['input_sha256'] == before['input_sha256']
    assert len(raw) <= app.MAX_PENDING_BYTES
    count = len(service.saves)
    assert app.read_pending_live_task(root, TASK)['status'] == 'FINALIZATION_PENDING'
    assert len(service.saves) == count  # Detection is read-only, even under lock contention.
    busy[0] = False
    final = app.finalize_pending_live_task(root, TASK)
    assert final['status'] == 'FAILED' and final['error_code'] == app.DEADLINE_ERROR
    assert_retained(before, final)
    assert path.read_bytes() == raw
    count = len(service.saves)
    assert app.finalize_pending_live_task(root, TASK)['status'] == 'FAILED'
    assert len(service.saves) == count
    assert app.read_pending_live_task(root, TASK)['status'] == 'NO_PENDING_FINALIZATION'


@pytest.mark.parametrize('damage', ['artifact', 'input', 'controller'])
def test_pending_finalization_refuses_tamper_or_new_controller(case, monkeypatch, damage):
    root, service, _, busy, _, r = pending_case(case, monkeypatch)
    busy[0] = False
    if damage == 'artifact':
        path = root / r['pending_bindings'][0]['path']
        path.write_bytes(path.read_bytes() + b' ')
    elif damage == 'input':
        (service._directory(TASK) / 'input.json').write_bytes(b'CHANGED_TEST_ONLY')
    else:
        service.state['live_controller']['started_at'] = '2099-01-01T00:00:00+00:00'
    count = len(service.saves)
    with pytest.raises(ValueError):
        app.finalize_pending_live_task(root, TASK)
    assert len(service.saves) == count and service.state['status'] == 'RUNNING'


def test_pending_cancelled_state_preserved_and_finalizer_has_no_model_calls(case, monkeypatch):
    root, service, _, busy, _, _ = pending_case(case, monkeypatch)
    busy[0] = False
    service.state.update(status='CANCELLED', error_code='USER_CANCELLED')
    def forbidden(*a, **k):
        raise AssertionError('Finalization must never start a worker or model')
    monkeypatch.setattr(app.subprocess, 'Popen', forbidden)
    r = app.finalize_pending_live_task(root, TASK)
    assert r['status'] == 'CANCELLED' and r['error_code'] == 'USER_CANCELLED'
