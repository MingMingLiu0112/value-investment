"""Operational owned-process deadline over the unchanged live task service/store."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from ..application.portfolio.private_journal_lock import LockTimeout
from ..application.product.common import write_new_bytes

MODULE = 'value_investment_agent.operations.live_task_controller_v1'
VERSION = 'live-task-controller-v1'
DEADLINE_ERROR = 'LIVE_TOTAL_DEADLINE_UNSETTLED_RESERVATION_RETAINED'
POLL_SECONDS = 0.2
REAP_TIMEOUT_SECONDS = 5
FINALIZE_LOCK_RETRY_SECONDS = 60
PENDING_VERSION = 'live-task-pending-finalization-v1'
PENDING_PREFIX = 'live-controller-pending-'
MAX_PENDING = 16
MAX_PENDING_BYTES = 16_384
TERMINAL = {'SUCCEEDED', 'CANCELLED', 'FAILED', 'WAITING_EVIDENCE'}


def _service(root):
    from ..application.research.agent_review.operating_task_v2 import LiveOperatingTaskService
    return LiveOperatingTaskService(root)


def _now():
    return datetime.now(timezone.utc)


def _identity():
    source = Path(__file__).resolve()
    commit = subprocess.check_output(['git', '-C', str(source.parents[3]), 'rev-parse', 'HEAD'],
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


def _retry_lock(operation, exhausted):
    deadline = time.monotonic() + FINALIZE_LOCK_RETRY_SECONDS
    while True:
        try:
            return operation()
        except LockTimeout:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return exhausted()
            time.sleep(min(POLL_SECONDS, remaining))


def _input_hash(service, task_id):
    return hashlib.sha256((service._directory(task_id) / 'input.json').read_bytes()).hexdigest()


def _pending_records(service, task_id):
    directory = service._directory(task_id)
    files = sorted(directory.glob(PENDING_PREFIX + '*.json'))
    if len(files) > MAX_PENDING:
        raise ValueError('LIVE_PENDING_FINALIZATION_LIMIT')
    result = []
    for path in files:
        if path.is_symlink() or path.resolve().parent != directory.resolve() or path.stat().st_size > MAX_PENDING_BYTES:
            raise ValueError('LIVE_PENDING_FINALIZATION_PATH_OR_SIZE_INVALID')
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if len(raw) > MAX_PENDING_BYTES or path.name != PENDING_PREFIX + digest + '.json':
            raise ValueError('LIVE_PENDING_FINALIZATION_HASH_INVALID')
        packet = json.loads(raw)
        fields = {'schema_version', 'action', 'task_id', 'input_sha256', 'metadata',
                  'failure', 'result', 'exit_code', 'recorded_at'}
        if (not isinstance(packet, dict) or set(packet) != fields
                or packet['schema_version'] != PENDING_VERSION or packet['action'] != 'no_order'
                or packet['task_id'] != task_id or packet['input_sha256'] != _input_hash(service, task_id)
                or not isinstance(packet['metadata'], dict)
                or packet['metadata'].get('schema_version') != VERSION
                or packet['metadata'].get('input_sha256') != packet['input_sha256']
                or (packet['failure'] is not None and (not isinstance(packet['failure'], str)
                    or re.fullmatch('[A-Z0-9_]{1,160}', packet['failure']) is None))
                or not isinstance(packet['result'], str)
                or len(packet['result']) > 160
                or (packet['exit_code'] is not None and type(packet['exit_code']) is not int)):
            raise ValueError('LIVE_PENDING_FINALIZATION_BINDING_INVALID')
        result.append((packet, dict(path=path.relative_to(service.root).as_posix(), sha256=digest)))
    return result


def _pending_view(task_id, records, applied=(), *, state_verified=True):
    bindings = [ref for _, ref in records if ref['sha256'] not in applied]
    return dict(schema_version=PENDING_VERSION, action='no_order', task_id=task_id,
        status=('FINALIZATION_PENDING' if bindings and state_verified else
                'FINALIZATION_STATE_UNCONFIRMED' if bindings else 'NO_PENDING_FINALIZATION'),
        pending_bindings=bindings, persisted_task_status=None,
        state_verified=state_verified, model_calls=0)


def read_pending_live_task(root, task_id):
    """Read-only detection; pending metadata never replaces the native task state."""
    service = _service(Path(root).resolve())
    records = _pending_records(service, task_id)
    if not records:
        return _pending_view(task_id, records)
    try:
        _, state, _ = service._load(task_id, recover=False)  # No lock file, view or recovery writes.
        applied = state.get('live_controller_pending_applied', [])
        if not isinstance(applied, list):
            raise ValueError('LIVE_PENDING_APPLIED_LIST_INVALID')
    except (ValueError, OSError, KeyError, TypeError):
        return _pending_view(task_id, records, state_verified=False)
    return _pending_view(task_id, records, applied)


def _write_pending(service, task_id, metadata, failure, result, exit_code):
    if metadata['input_sha256'] != _input_hash(service, task_id):
        raise ValueError('LIVE_PENDING_INPUT_CHANGED')
    if len(_pending_records(service, task_id)) >= MAX_PENDING:
        raise ValueError('LIVE_PENDING_FINALIZATION_LIMIT')
    packet = dict(schema_version=PENDING_VERSION, action='no_order', task_id=task_id,
        input_sha256=metadata['input_sha256'], metadata=metadata, failure=failure,
        result=result, exit_code=exit_code, recorded_at=_now().isoformat())
    raw = json.dumps(packet, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    if len(raw) > MAX_PENDING_BYTES:
        raise ValueError('LIVE_PENDING_FINALIZATION_SIZE_INVALID')
    digest = hashlib.sha256(raw).hexdigest()
    path = service._directory(task_id) / (PENDING_PREFIX + digest + '.json')
    write_new_bytes(path, raw)  # Atomic, fsynced publication inside the SAME task directory.
    return _pending_view(task_id, [(packet, dict(path=path.relative_to(service.root).as_posix(), sha256=digest))])


def _apply_finish(service, task_id, metadata, failure, result, exit_code, pending_digest=None):
    # Caller holds the existing state lock. Native recovery validates interrupted head publication.
    spec, state, pin = service._load(task_id, recover=True)
    if state['input_sha256'] != metadata['input_sha256']:
        raise ValueError('LIVE_PENDING_INPUT_CHANGED')
    applied = list(state.get('live_controller_pending_applied', []))
    if pending_digest is not None:
        if pending_digest in applied:
            return _view(spec, state, pin)
        current = state.get('live_controller') or {}
        if any(current.get(k) != metadata.get(k) for k in
               ('input_sha256', 'started_at', 'deadline_at', 'controller_sha256', 'code_commit')):
            raise ValueError('LIVE_PENDING_CONTROLLER_VERSION_MISMATCH')
        applied.append(pending_digest)
    receipt = dict(metadata, result=result, finished_at=_now().isoformat(), worker_exit_code=exit_code)
    changes = dict(live_controller=receipt)
    if pending_digest is not None:
        changes['live_controller_pending_applied'] = applied
    if result == 'WORKER_EXITED' and state['status'] in TERMINAL:
        failure = None  # Preserve the native error/status if its final write raced poll.
    if failure is not None and state['status'] not in {'SUCCEEDED', 'CANCELLED'}:
        changes.update(status='FAILED', error_code=failure)
    state, pin = service._save(spec, state, pin, _now(), **changes)
    return _view(spec, state, pin)


def _finish(service, task_id, metadata, *, failure=None, result, exit_code=None):
    def save():
        with service._lock(service._directory(task_id)):
            return _apply_finish(service, task_id, metadata, failure, result, exit_code)
    return _retry_lock(save, lambda: _write_pending(service, task_id, metadata, failure, result, exit_code))


def finalize_pending_live_task(root, task_id):
    """Explicitly apply validated pending operations once; no model or native.resume."""
    service = _service(Path(root).resolve())
    records = _pending_records(service, task_id)
    if not records:
        return _pending_view(task_id, records)
    def save():
        with service._lock(service._directory(task_id)):
            latest = None
            # Re-read/hash each artifact under lock before using its contents.
            for packet, ref in _pending_records(service, task_id):
                latest = _apply_finish(service, task_id, packet['metadata'], packet['failure'],
                    packet['result'], packet['exit_code'], pending_digest=ref['sha256'])
            return latest
    return _retry_lock(save, lambda: read_pending_live_task(root, task_id))


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
            input_sha256=state['input_sha256'],
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
        source_root = str(Path(__file__).resolve().parents[2])
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
                    # _finish re-reads under its bounded retry lock. Never let an
                    # extra single-shot state read strand the already-reaped worker.
                    failure = ('LIVE_WORKER_EXIT_NONZERO_UNSETTLED_RESERVATION_RETAINED' if code else
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
