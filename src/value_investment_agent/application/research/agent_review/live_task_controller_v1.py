"""Operational owned-process deadline over the unchanged live task service/store."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from ...portfolio.private_journal_lock import LockTimeout

MODULE = 'value_investment_agent.application.research.agent_review.live_task_controller_v1'
VERSION = 'live-task-controller-v1'
DEADLINE_ERROR = 'LIVE_TOTAL_DEADLINE_UNSETTLED_RESERVATION_RETAINED'
POLL_SECONDS = 0.2
REAP_TIMEOUT_SECONDS = 5
TERMINAL = {'SUCCEEDED', 'CANCELLED', 'FAILED', 'WAITING_EVIDENCE'}


def _service(root):
    from .operating_task_v2 import LiveOperatingTaskService
    return LiveOperatingTaskService(root)


def _now():
    return datetime.now(timezone.utc)


def _identity():
    source = Path(__file__).resolve()
    commit = subprocess.check_output(['git', '-C', str(source.parents[5]), 'rev-parse', 'HEAD'],
        stderr=subprocess.DEVNULL, text=True, timeout=5).strip()
    if re.fullmatch('[0-9a-f]{40}', commit) is None:
        raise ValueError('LIVE_CONTROLLER_CODE_COMMIT_UNAVAILABLE')
    return dict(controller_sha256=hashlib.sha256(source.read_bytes()).hexdigest(), code_commit=commit)


def _load(service, task_id, *, recover=False):
    with service._lock(service._directory(task_id)):
        return service._load(task_id, recover=recover)


def _view(spec, state, pin):
    # Operational result only: never call expensive/economic service._view here.
    return dict(deepcopy(state), symbol=spec['symbol'], record_binding=deepcopy(pin))


def _reap(child):
    if child.poll() is None:
        try:
            child.kill()
        except OSError:
            pass  # It may have exited between poll and kill.
    try:
        code = child.wait(timeout=REAP_TIMEOUT_SECONDS)
    except (subprocess.TimeoutExpired, OSError):
        raise RuntimeError('LIVE_CONTROLLER_CHILD_TERMINATION_UNCONFIRMED') from None
    if code is None or child.poll() is None:
        raise RuntimeError('LIVE_CONTROLLER_CHILD_TERMINATION_UNCONFIRMED')


def _finish(service, task_id, metadata, *, failure=None, result, exit_code=None):
    with service._lock(service._directory(task_id)):
        # After owned-worker termination, recover a fully written version whose
        # head publish was interrupted. Native recovery validates the whole chain.
        spec, state, pin = service._load(task_id, recover=True)
        receipt = dict(metadata, result=result, finished_at=_now().isoformat(), worker_exit_code=exit_code)
        changes = dict(live_controller=receipt)
        if failure is not None and state['status'] not in {'SUCCEEDED', 'CANCELLED'}:
            changes.update(status='FAILED', error_code=failure)
        state, pin = service._save(spec, state, pin, _now(), **changes)
        return _view(spec, state, pin)


def supervise_live_task(root, task_id, timeout_seconds=300):
    """Run one existing QUEUED live task; no prompt/provider/input modifications.

    Routes select this only for the exact real service, not injected test providers.
    All durable operational metadata uses the existing append-only state mechanism.
    """
    if (type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds)
            or not 0 < timeout_seconds <= 3600):
        raise ValueError('LIVE_CONTROLLER_BOUNDED_TIMEOUT_REQUIRED')
    if not isinstance(task_id, str) or re.fullmatch('rt-[0-9a-f]{32}', task_id) is None:
        raise ValueError('LIVE_CONTROLLER_TASK_ID_INVALID')
    root = Path(root).resolve()
    service = _service(root)
    directory = service._directory(task_id)
    # Separate from the native execution lock: that lock belongs to the worker.
    with service._lock(directory, 'controller'):
        spec, state, pin = _load(service, task_id)
        if state['status'] in {'SUCCEEDED', 'CANCELLED'}:
            return _view(spec, state, pin)
        if state['status'] != 'QUEUED':
            raise ValueError('LIVE_CONTROLLER_REQUIRES_QUEUED_TASK')
        started = _now()
        deadline = time.monotonic() + timeout_seconds
        metadata = dict(schema_version=VERSION, **_identity(), started_at=started.isoformat(),
            deadline_at=(started + timedelta(seconds=timeout_seconds)).isoformat(),
            timeout_seconds=timeout_seconds, scope='OPERATIONAL_ENVELOPE_NOT_RESEARCH_INPUT',
            action='no_order', result='STARTING')
        with service._lock(directory):
            spec, state, pin = service._load(task_id, recover=False)
            if state['status'] in {'SUCCEEDED', 'CANCELLED'}:
                return _view(spec, state, pin)
            if state['status'] != 'QUEUED':
                raise ValueError('LIVE_CONTROLLER_REQUIRES_QUEUED_TASK')
            service._save(spec, state, pin, _now(), live_controller=metadata)
        env = os.environ.copy()  # Credential is inherited, never argv/stdin/logged.
        source_root = str(Path(__file__).resolve().parents[4])
        env['PYTHONPATH'] = source_root + (os.pathsep + env['PYTHONPATH'] if env.get('PYTHONPATH') else '')
        env['PYTHONIOENCODING'] = 'utf-8'
        child = None
        cleanup_attempted = False
        def stop_owned_child():
            nonlocal cleanup_attempted
            cleanup_attempted = True
            _reap(child)
        try:
            try:
                child = subprocess.Popen([sys.executable, '-B', '-m', MODULE, '--worker',
                    str(root), task_id], cwd=root, stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            except (OSError, ValueError):
                return _finish(service, task_id, metadata, failure='LIVE_WORKER_START_FAILED', result='START_FAILED')
            metadata['owned_pid'] = child.pid
            while True:
                if time.monotonic() >= deadline:
                    stop_owned_child()
                    return _finish(service, task_id, metadata, failure=DEADLINE_ERROR,
                                   result='TOTAL_DEADLINE_EXCEEDED', exit_code=child.returncode)
                try:
                    spec, state, pin = _load(service, task_id)
                except LockTimeout:
                    state = None  # Native write in progress: do not invent failure/refund.
                if state is not None and state['status'] in TERMINAL:
                    stop_owned_child()
                    return _finish(service, task_id, metadata, result='NATIVE_' + state['status'],
                                   exit_code=child.returncode)
                code = child.poll()
                if code is not None:
                    stop_owned_child()
                    # A terminal write may have raced the last state poll.
                    spec, state, pin = _load(service, task_id, recover=True)
                    failure = None if state['status'] in TERMINAL else (
                        'LIVE_WORKER_EXIT_NONZERO_UNSETTLED_RESERVATION_RETAINED' if code else
                        'LIVE_WORKER_EXIT_WITHOUT_TERMINAL_STATE_UNSETTLED_RESERVATION_RETAINED')
                    return _finish(service, task_id, metadata, failure=failure,
                                   result='WORKER_EXITED', exit_code=code)
                time.sleep(min(POLL_SECONDS, max(0, deadline - time.monotonic())))
        finally:
            if child is not None and not cleanup_attempted:
                stop_owned_child()


def _worker_main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 3 or args[0] != '--worker' or re.fullmatch('rt-[0-9a-f]{32}', args[2]) is None:
        return 2
    try:
        _service(Path(args[1]).resolve()).run(args[2])  # Original service.run unchanged.
        return 0
    except Exception:
        return 1  # stdout/stderr are DEVNULL; no raw request/config/secret errors.


if __name__ == '__main__':
    raise SystemExit(_worker_main())
