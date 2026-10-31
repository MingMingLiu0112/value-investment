"""Durable bounded saved-response/Mock execution around the existing pilot.

Version records are immutable and hash chained. Only a fully verified pilot packet
is a checkpoint. Role-level exactly-once execution is deliberately not promised.
There is no live-provider or paid-call path in this service.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from itertools import islice
import json
import os
from pathlib import Path
import re
import tempfile
from zoneinfo import ZoneInfo

from ....infrastructure.agent_runtime.provider import MockLLMProvider
from ...portfolio.private_journal_lock import InterProcessLock, LockTimeout
from ...product.common import require_inside, write_new_bytes
from . import llm_pilot
from .snapshot import load_research_snapshot

VERSION = 'research-task-execution-v1'
STATES = {'QUEUED', 'RUNNING', 'WAITING_EVIDENCE', 'SUCCEEDED', 'FAILED', 'CANCELLED'}
DEFAULT_BUDGET = dict(max_attempts=2, max_provider_requests=6, max_prompt_tokens=60000,
                      max_completion_tokens=3072)
MOCK_RESERVED_USAGE = dict(prompt_tokens=200, completion_tokens=100)
HARD_CAPS = dict(max_attempts=3, max_provider_requests=9, max_prompt_tokens=90000,
                 max_completion_tokens=4608)


def _bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'),
                      allow_nan=False).encode('utf-8')


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _now(value=None):
    value = value or datetime.now(timezone.utc)
    if value.utcoffset() is None:
        raise ValueError('Research task clock must be timezone-aware')
    return value


def _implementation():
    return _hash(Path(__file__).read_bytes() + Path(llm_pilot.__file__).read_bytes())


class _Cancelled(RuntimeError):
    pass


class ResearchTaskService:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.base = require_inside(self.root, self.root / 'runtime/research-task-execution-v1', 'task store')

    def _directory(self, task_id):
        if not isinstance(task_id, str) or not re.fullmatch(r'rt-[0-9a-f]{32}', task_id):
            raise ValueError('Invalid research task id')
        return require_inside(self.base, self.base / task_id, 'research task')

    def _lock(self, directory, name='state'):
        return InterProcessLock(directory / (name + '.lock'), timeout_seconds=0.05)

    def _binding(self, path):
        return dict(path=path.relative_to(self.root).as_posix(), sha256=_hash(path.read_bytes()))

    def _bound(self, binding):
        if (not isinstance(binding, dict) or set(binding) != {'path','sha256'}
                or not isinstance(binding['path'], str) or not isinstance(binding['sha256'], str)
                or not re.fullmatch(r'[0-9a-f]{64}', binding['sha256'])
                or Path(binding['path']).is_absolute() or '..' in Path(binding['path']).parts):
            raise ValueError('Task requires an exact project-relative binding')
        path = require_inside(self.root, self.root / binding['path'], 'task binding')
        raw = path.read_bytes()
        if _hash(raw) != binding['sha256']:
            raise ValueError('Task binding hash mismatch')
        return json.loads(raw)

    def _head(self, directory, binding):
        # Mutable head publication is atomic; temporary files remain in this task directory.
        fd, temporary = tempfile.mkstemp(prefix='.head-', suffix='.tmp', dir=directory)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(_bytes(binding))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, directory / 'current.json')
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _load(self, task_id, *, recover=False):
        directory = self._directory(task_id)
        raw = (directory / 'input.json').read_bytes()
        spec, pin = json.loads(raw), _hash(raw)
        if (spec.get('schema_version') != VERSION or spec.get('task_id') != task_id
                or spec.get('mode') not in {'SAVED_RESPONSE','MOCK'} or spec.get('action') != 'no_order'):
            raise ValueError('Invalid research task input')
        files = sorted((directory / 'versions').glob('*.json'))
        if not files and recover and not (directory/'current.json').exists():
            snapshot,status,error = self._check(spec,_now())
            initial = dict(status=status or 'QUEUED', attempts=0, provider_requests=0,
                usage=dict(prompt_tokens=0,completion_tokens=0), checkpoint=None,
                snapshot_fingerprint=snapshot.input_fingerprint if snapshot else None,
                created_at=_now().isoformat(), error_code=error, new_llm_calls=0,
                action='no_order',formal_eligibility=False)
            state,binding = self._save(spec,initial,None,_now())
            return spec,state,binding
        if not files or len(files) > 256:
            raise ValueError('Task version chain missing or unbounded')
        previous = None
        chain = []
        for number, path in enumerate(files, 1):
            binding = self._binding(path)
            if path.name != f'{number:04d}-{binding["sha256"]}.json':
                raise ValueError('Task version filename/hash mismatch')
            row = self._bound(binding)
            if (row.get('schema_version') != VERSION or row.get('version') != number
                    or row.get('previous') != previous or row.get('task_id') != task_id
                    or row.get('input_sha256') != pin or row.get('status') not in STATES
                    or row.get('action') != 'no_order' or row.get('formal_eligibility') is not False
                    or row.get('new_llm_calls') != 0):
                raise ValueError('Task version chain identity mismatch')
            previous = binding
            chain.append((binding, row))
        head_path = directory / 'current.json'
        if head_path.exists():
            head = json.loads(head_path.read_bytes())
            self._bound(head)
            if head not in [binding for binding, _ in chain]:
                raise ValueError('Task head is outside verified version chain')
        elif recover:
            head = None
        else:
            raise FileNotFoundError('Task head missing; explicit resume required')
        if head != previous:
            if not recover:
                raise ValueError('Unpublished task version requires explicit resume')
            self._head(directory, previous)
        return spec, chain[-1][1], previous

    def _save(self, spec, state, previous, now, **changes):
        row = deepcopy(state)
        row.update(changes)
        row.update(schema_version=VERSION, task_id=spec['task_id'],
                   input_sha256=_hash(_bytes(spec)), previous=previous,
                   version=state.get('version',0)+1, updated_at=now.isoformat())
        raw = _bytes(row)
        directory = self._directory(spec['task_id'])
        path = directory / 'versions' / f'{row["version"]:04d}-{_hash(raw)}.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        write_new_bytes(path, raw)
        binding = self._binding(path)
        self._head(directory, binding)
        return row, binding

    def _snapshot(self, spec, now):
        if spec['implementation_sha256'] != _implementation():
            raise ValueError('Task implementation changed; a new request is required')
        snapshot = load_research_snapshot(root=self.root,
            workbench=self.root/spec['workbench']['path'],
            expected_sha256=spec['workbench']['sha256'], symbol=spec['symbol'])
        if snapshot.as_of > now.astimezone(ZoneInfo('Asia/Shanghai')).date():
            raise ValueError('Research snapshot is not available at task cutoff')
        workbench = self._bound(spec['workbench'])
        if workbench.get('generated_at'):
            generated = datetime.fromisoformat(workbench['generated_at'])
            if generated.utcoffset() is None or generated > now:
                raise ValueError('Research workbench is not available at task cutoff')
        for ref in snapshot.evidence:
            if ref.get('available_at') and datetime.fromisoformat(ref['available_at']) > now:
                raise ValueError('Research evidence is not available at task cutoff')
        return snapshot

    def _check(self, spec, now):
        try:
            return self._snapshot(spec, now), None, None
        except FileNotFoundError:
            return None, 'WAITING_EVIDENCE', 'EVIDENCE_MISSING'
        except (ValueError, OSError, KeyError, TypeError):
            return None, 'FAILED', 'SNAPSHOT_VALIDATION_FAILED'

    def _packet(self, spec, state, snapshot):
        path = self._directory(spec['task_id']) / 'pilot.json'
        if state.get('checkpoint'):
            packet = self._bound(state['checkpoint'])
        else:
            packet = json.loads(path.read_bytes())
        llm_pilot.verify_llm_packet(packet, snapshot, root=self.root)
        provider = MockLLMProvider(spec['responses'])
        if (packet['scope'] != llm_pilot.MOCK_SCOPE
                or packet['provider_input_sha256'] != provider.responses_sha256
                or packet['requested_model_id'] != provider.model_id
                or packet['workbench_sha256'] != spec['workbench']['sha256']):
            raise ValueError('Task checkpoint differs from saved/mock input')
        return packet, self._binding(path)

    def _view(self, spec, state, binding, now):
        result = deepcopy(state)
        result.update(record_binding=binding, persisted_status=state['status'],
                      workflow=spec['workflow'], symbol=spec['symbol'], execution_mode=spec['mode'],
                      checkpoint_verified=False, role_exactly_once=False,
                      recovery_boundary='VERIFIED_WHOLE_PACKET_ONLY', new_llm_calls=0,
                      usage_basis='MOCK_PROVIDER_ACCOUNTING_NOT_NEW_LLM_USAGE',
                      budget=deepcopy(spec['budget']), workbench_binding=deepcopy(spec['workbench']))
        unsettled = [row for row in state.get('reservations',{}).values() if row['status']=='RESERVED']
        result['unsettled_usage'] = {key:sum(row[key] for row in unsettled) for key in MOCK_RESERVED_USAGE}
        result['token_accounting'] = 'PRECALL_RESERVATION_UNSETTLED_USAGE_REMAINS_CHARGED'
        snapshot, status, error = self._check(spec, now)
        result['snapshot_status'] = 'VERIFIED' if snapshot else error
        if status and state['status'] != 'CANCELLED':
            result.update(status=status, error_code=error)
        elif state['status'] == 'SUCCEEDED':
            try:
                packet, _ = self._packet(spec, state, snapshot)
                result.update(checkpoint_verified=True, finding_count=len(packet['findings']))
            except (ValueError, OSError, KeyError, TypeError):
                result.update(status='FAILED', error_code='CHECKPOINT_VALIDATION_FAILED')
        return result

    def create(self, *, symbol, workbench, workbench_sha256, responses, request_key,
               workflow='company_research', mode='SAVED_RESPONSE', budget=None, now=None):
        now = _now(now)
        if (not isinstance(symbol,str) or not re.fullmatch(r'[0-9]{6}',symbol)
                or not isinstance(request_key,str) or not 1 <= len(request_key) <= 128
                or not isinstance(workflow,str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,31}',workflow)
                or mode not in {'SAVED_RESPONSE','MOCK'}):
            raise ValueError('Invalid task identity or unsupported execution mode')
        limits = dict(DEFAULT_BUDGET)
        if budget is not None:
            if not isinstance(budget,dict) or set(budget)-set(limits):
                raise ValueError('Unknown research task budget')
            limits.update(budget)
        if any(type(v) is not int or not 0 <= v <= HARD_CAPS[k] for k,v in limits.items()) or not limits['max_attempts']:
            raise ValueError('Task budget exceeds bounded policy')
        path = require_inside(self.root/'runtime', self.root/Path(workbench), 'task workbench')
        if not isinstance(workbench_sha256,str) or not re.fullmatch(r'[0-9a-f]{64}',workbench_sha256):
            raise ValueError('Task workbench requires a SHA256 pin')
        if (not isinstance(responses,dict) or any(type(v) is not str or len(v)>16000 for v in responses.values())):
            raise ValueError('Task requires bounded saved role responses')
        MockLLMProvider(responses)  # existing strict three-role contract, no call
        task_id = 'rt-' + _hash(request_key.encode('utf-8'))[:32]
        spec = dict(schema_version=VERSION, task_id=task_id, symbol=symbol, workflow=workflow,
            request_key_sha256=_hash(request_key.encode('utf-8')), mode=mode,
            workbench=dict(path=path.relative_to(self.root).as_posix(),sha256=workbench_sha256),
            responses=deepcopy(responses), budget=limits, implementation_sha256=_implementation(), action='no_order')
        directory = self._directory(task_id)
        with self._lock(directory):
            if (directory/'input.json').exists():
                existing,state,binding = self._load(task_id)
                if existing != spec:
                    raise ValueError('Research task request_key conflicts with its immutable input')
                return self._view(existing,state,binding,now)
            snapshot,status,error = self._check(spec,now)
            write_new_bytes(directory/'input.json',_bytes(spec))
            state = dict(status=status or 'QUEUED', attempts=0, provider_requests=0,
                usage=dict(prompt_tokens=0,completion_tokens=0), checkpoint=None,
                snapshot_fingerprint=snapshot.input_fingerprint if snapshot else None,
                created_at=now.isoformat(), error_code=error, new_llm_calls=0,
                action='no_order',formal_eligibility=False)
            state,binding = self._save(spec,state,None,now)
            return self._view(spec,state,binding,now)

    def read(self, task_id):
        directory = self._directory(task_id)
        if not (directory/'input.json').is_file():
            raise FileNotFoundError(task_id)
        if not (directory/'state.lock').is_file():
            raise ValueError('Task state lock missing; explicit recovery required')
        with self._lock(directory):
            spec,state,binding = self._load(task_id)
            return self._view(spec,state,binding,_now())

    def list_for_symbol(self, symbol):
        """Read existing tasks only; explicit limits never masquerade as full coverage."""
        if not isinstance(symbol,str) or not re.fullmatch(r'[0-9]{6}',symbol):
            raise ValueError('Task discovery requires a six-digit symbol')
        if not self.base.exists():
            return []
        children = list(islice(self.base.iterdir(),101))
        if len(children)>100:
            raise ValueError('RESEARCH_TASK_DISCOVERY_LIMIT_EXCEEDED: max_entries=100')
        results = []
        for path in sorted(children):
            if not path.is_dir() or not path.name.startswith('rt-'):
                continue
            try:
                view = self.read(path.name)
            except LockTimeout as error:
                raise RuntimeError('RESEARCH_TASK_DISCOVERY_BUSY:' + path.name) from error
            except (ValueError,OSError,KeyError,TypeError) as error:
                raise ValueError('RESEARCH_TASK_DISCOVERY_INVALID:' + path.name) from error
            if view['symbol'] == symbol:
                results.append(view)
                if len(results)>20:
                    raise ValueError('RESEARCH_TASK_RESULT_LIMIT_EXCEEDED: max_results=20')
        return sorted(results,key=lambda row:(row['updated_at'],row['task_id']),reverse=True)

    def cancel(self, task_id, *, reason='USER_CANCELLED', now=None):
        now = _now(now)
        if not isinstance(reason,str) or not 1 <= len(reason) <= 200:
            raise ValueError('Cancellation requires a bounded reason')
        directory = self._directory(task_id)
        if not (directory/'input.json').exists():
            raise FileNotFoundError(task_id)
        with self._lock(directory):
            spec,state,binding = self._load(task_id)
            self._check(spec,now)  # cancellation remains possible even with damaged evidence
            if state['status'] not in {'SUCCEEDED','CANCELLED'}:
                state,binding = self._save(spec,state,binding,now,status='CANCELLED',error_code=reason)
            return self._view(spec,state,binding,now)

    def _meter(self, task_id, response=None, *, reservation_id=None):
        directory = self._directory(task_id)
        with self._lock(directory):
            spec,state,binding = self._load(task_id)
            if state['status'] == 'CANCELLED':
                raise _Cancelled('Task cancelled')
            self._snapshot(spec,_now())
            if state['status'] != 'RUNNING':
                raise ValueError('Task is not running')
            usage = dict(state['usage'])
            requests = state['provider_requests']
            reservations = deepcopy(state.get('reservations',{}))
            if response is None:
                requests += 1
                reservation_id = str(requests)
                # MockLLMProvider has an exact fixed 200/100 response contract.
                # Persist the conservative charge atomically WITH the request intent.
                reservations[reservation_id] = dict(MOCK_RESERVED_USAGE,status='RESERVED')
                for key,value in MOCK_RESERVED_USAGE.items():
                    usage[key] += value
            else:
                reserved = reservations.get(reservation_id)
                if not reserved or reserved['status'] != 'RESERVED':
                    raise ValueError('Missing or already settled task usage reservation')
                actual = dict(prompt_tokens=response.prompt_tokens,completion_tokens=response.completion_tokens)
                if any(type(value) is not int or value<0 for value in actual.values()):
                    raise ValueError('Invalid saved-response usage')
                for key,value in actual.items():
                    usage[key] += value-reserved[key]
                reservations[reservation_id] = dict(actual,status='SETTLED')
            if (requests > spec['budget']['max_provider_requests']
                    or usage['prompt_tokens'] > spec['budget']['max_prompt_tokens']
                    or usage['completion_tokens'] > spec['budget']['max_completion_tokens']):
                raise ValueError('Task budget exhausted')
            self._save(spec,state,binding,_now(),provider_requests=requests,usage=usage,reservations=reservations)
            return reservation_id

    def _complete(self, spec, state, binding, snapshot, now):
        _, checkpoint = self._packet(spec,state,snapshot)
        return self._save(spec,state,binding,now,status='SUCCEEDED',checkpoint=checkpoint,error_code=None)

    def _drive(self, task_id, now, *, resume):
        directory = self._directory(task_id)
        if not (directory/'input.json').exists():
            raise FileNotFoundError(task_id)
        try:
            with self._lock(directory,'execution'):
                with self._lock(directory):
                    spec,state,binding = self._load(task_id,recover=resume)
                    snapshot,status,error = self._check(spec,now)
                    if state['status'] == 'CANCELLED':
                        return self._view(spec,state,binding,now)
                    if status:
                        state,binding = self._save(spec,state,binding,now,status=status,error_code=error)
                        return self._view(spec,state,binding,now)
                    output = directory/'pilot.json'
                    if output.exists():
                        try:
                            if state['status'] == 'SUCCEEDED':
                                self._packet(spec,state,snapshot)
                                return self._view(spec,state,binding,now)
                            state,binding = self._complete(spec,state,binding,snapshot,now)
                        except (ValueError,OSError,KeyError,TypeError):
                            state,binding = self._save(spec,state,binding,now,status='FAILED',error_code='CHECKPOINT_VALIDATION_FAILED')
                        return self._view(spec,state,binding,now)
                    if state['status'] == 'SUCCEEDED':
                        state,binding = self._save(spec,state,binding,now,status='FAILED',error_code='CHECKPOINT_MISSING')
                        return self._view(spec,state,binding,now)
                    if resume:
                        if state['status'] == 'QUEUED':
                            return self._view(spec,state,binding,now)
                        if state['attempts'] >= spec['budget']['max_attempts']:
                            status,error = 'FAILED','ATTEMPT_BUDGET_EXHAUSTED'
                        else:
                            status,error = 'QUEUED',None
                        state,binding = self._save(spec,state,binding,now,status=status,error_code=error,
                            snapshot_fingerprint=snapshot.input_fingerprint)
                        return self._view(spec,state,binding,now)
                    if state['status'] == 'RUNNING':
                        state,binding = self._save(spec,state,binding,now,status='FAILED',error_code='INTERRUPTED_EXPLICIT_RESUME_REQUIRED')
                        return self._view(spec,state,binding,now)
                    if state['status'] != 'QUEUED':
                        return self._view(spec,state,binding,now)
                    limits,usage = spec['budget'],state['usage']
                    if (state['attempts'] >= limits['max_attempts']
                            or state['provider_requests']+3 > limits['max_provider_requests']
                            or usage['prompt_tokens']+600 > limits['max_prompt_tokens']
                            or usage['completion_tokens']+300 > limits['max_completion_tokens']):
                        state,binding = self._save(spec,state,binding,now,status='FAILED',error_code='TASK_BUDGET_EXHAUSTED')
                        return self._view(spec,state,binding,now)
                    state,binding = self._save(spec,state,binding,now,status='RUNNING',
                        attempts=state['attempts']+1,error_code=None,snapshot_fingerprint=snapshot.input_fingerprint)
                service = self
                inner = MockLLMProvider(spec['responses'])
                class SavedProvider:
                    model_id = inner.model_id
                    responses_sha256 = inner.responses_sha256
                    def complete(self, request):
                        reservation_id = service._meter(task_id)
                        response = inner.complete(request)
                        service._meter(task_id,response,reservation_id=reservation_id)
                        return response
                try:
                    llm_pilot.run_llm_research_pilot(root=self.root,
                        workbench=self.root/spec['workbench']['path'],
                        workbench_sha256=spec['workbench']['sha256'],symbol=spec['symbol'],
                        output=output,provider=SavedProvider(),mode='mock')
                    failure = None
                except _Cancelled:
                    failure = 'USER_CANCELLED'
                except Exception:
                    failure = 'PILOT_EXECUTION_FAILED'
                # BaseException intentionally leaves durable RUNNING for explicit recovery.
                with self._lock(directory):
                    spec,state,binding = self._load(task_id)
                    if state['status'] != 'CANCELLED':
                        snapshot,status,error = self._check(spec,_now())
                        if failure or status:
                            state,binding = self._save(spec,state,binding,_now(),status=status or 'FAILED',error_code=error or failure)
                        else:
                            try:
                                state,binding = self._complete(spec,state,binding,snapshot,_now())
                            except (ValueError,OSError,KeyError,TypeError):
                                state,binding = self._save(spec,state,binding,_now(),status='FAILED',error_code='CHECKPOINT_VALIDATION_FAILED')
                    return self._view(spec,state,binding,_now())
        except LockTimeout as error:
            raise RuntimeError('Research task execution is already active') from error

    def run(self, task_id, *, now=None):
        return self._drive(task_id,_now(now),resume=False)

    def resume(self, task_id, *, now=None):
        """Explicit whole-packet recovery/requeue; never invokes a provider."""
        return self._drive(task_id,_now(now),resume=True)
