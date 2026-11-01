"""Native research tasks on the existing immutable ResearchTaskService store.

No provider calls or economic admission. Browser connections do not own task
lifetime. A worker calls run; restart recovery is explicit resume, never success.
Native IO is cooperative; the isolated worker has a hard attempt timeout. Partial
files and stdout/stderr remain in the attempt directory on every terminal state.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal
import importlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from uuid import uuid4

from .agent_review import task_execution_v1 as base
from ..product.common import require_inside, write_new_bytes

VERSION = 'transparent-task-v1'
_SESSION = uuid4().hex
OPERATIONS = ('REPLAY_SELECTION', 'FRESH_PUBLIC_SCAN', 'RECALCULATE_MAIN',
              'SIMULATE_ASSUMPTIONS', 'VERIFY_EVIDENCE', 'REVIEW_NOTE')
OPERATION_MODULES = {'VERIFY_EVIDENCE': 'A', 'REPLAY_SELECTION': 'B',
    'FRESH_PUBLIC_SCAN': 'B', 'RECALCULATE_MAIN': 'F1',
    'SIMULATE_ASSUMPTIONS': 'F1', 'REVIEW_NOTE': 'G2'}
PUBLIC_STATUSES = ('IDLE', 'QUEUED', 'RUNNING', 'SUCCESS', 'PARTIAL',
                   'BLOCKED', 'FAILED', 'CANCELLED')
CASH_OVERRIDES = {'target_payout_ratio', 'accessible_profit_ratio', 'reserve_ratio',
                  'net_maintenance_cash_cny', 'operating_wc_cash_cny'}
# Source-bound liability payments/opening resources cannot be edited as hypotheses.
STEPS = ('VERIFY_INPUT', 'EXECUTE_NATIVE', 'VERIFY_OUTPUT')
# The route constructs this marker ONLY after authorize(); never use request body
# identity or persist session tokens. This identifies an access context, not a
# named investor, a signature, or financial approval.
REVIEW_ACTOR_CONTEXT = dict(actor='LOCAL_AUTHORIZED_OPERATOR',
                            authorization_basis='ROUTE_AUTHORIZED_LOCAL_SESSION')


def _actor_context(operation, context):
    if operation == 'REVIEW_NOTE':
        if context != REVIEW_ACTOR_CONTEXT:
            raise ValueError('REVIEW_NOTE_REQUIRES_ROUTE_AUTHORIZED_ACTOR_CONTEXT')
        return deepcopy(context)
    if context is not None:
        raise ValueError('ACTOR_CONTEXT_ONLY_FOR_REVIEW_NOTE')
    return None


def _identity():
    return base._hash(Path(__file__).read_bytes() + Path(base.__file__).read_bytes())


_CODE_ROOT = Path(__file__).resolve().parents[4]


def _source_contract(operation):
    """Freeze native executable source at create, never rebase a queued task."""
    package = _CODE_ROOT / 'src/value_investment_agent'
    names = {'application/research/transparent_task_v1.py',
             'application/research/agent_review/task_execution_v1.py',
             'application/portfolio/private_journal_lock.py', 'application/product/common.py'}
    script_names = set()
    if operation in {'REPLAY_SELECTION', 'FRESH_PUBLIC_SCAN'}:
        from ..discovery.value_module_adapter_v1 import _code_identity
        # Reuse the independently reviewed B dependency inventory, not Git dirty
        # state (which unrelated workers and this task's artifacts may change).
        names.update(_code_identity(_CODE_ROOT)['implementation_sha256'])
        names.update({'application/discovery/official_universe_collection.py',
            'application/discovery/scoped_screening.py',
            'infrastructure/screening/official_universe_v2.py',
            'domain/discovery/official_list_calendar.py', 'official_universe.py'})
        if operation == 'FRESH_PUBLIC_SCAN':
            script_names.add('scripts/run_m2_opportunity_discovery.py')
    if operation in {'RECALCULATE_MAIN', 'SIMULATE_ASSUMPTIONS'}:
        from .main_valuation_revalidation_v1 import implementation_fingerprints
        for module_name in implementation_fingerprints():
            module = importlib.import_module(module_name)
            names.add(Path(module.__file__).resolve().relative_to(package).as_posix())
    if operation in {'VERIFY_EVIDENCE', 'REVIEW_NOTE'}:
        names.update({'application/research/public_evidence.py',
            'application/research/value_evidence_enrichment_v1.py',
            'infrastructure/public_evidence_archive_v2.py',
            'infrastructure/filings/official_report_acquisition.py',
            'infrastructure/filings/official_pdf.py', 'infrastructure/filings/pdf_text.py',
            'infrastructure/filings/pdfium_runtime.py', 'disclosures.py',
            'infrastructure/screening/value_evidence_enrichment_v1.py',
            'infrastructure/screening/evidence_screen_v3.py', 'financial_quality.py',
            'm2_discovery_engine.py', 'm2_market_data.py', 'm2_opportunity_discovery.py'})
    paths = {('src/value_investment_agent/' + name): package / name for name in names}
    paths.update({name: _CODE_ROOT / name for name in script_names})
    return dict(schema_version='transparent-native-source-contract-v1', hash_basis='RAW_BYTES',
        files={name: base._hash(path.read_bytes()) for name, path in sorted(paths.items())})


def _verify_source_contract(contract):
    if (not isinstance(contract, dict)
            or contract.get('schema_version') != 'transparent-native-source-contract-v1'
            or contract.get('hash_basis') != 'RAW_BYTES'
            or not isinstance(contract.get('files'), dict) or not contract['files']):
        raise ValueError('IMPLEMENTATION_CONTRACT_MISSING')
    for name, digest in contract['files'].items():
        path = require_inside(_CODE_ROOT, _CODE_ROOT / name, 'native source')
        if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
            raise ValueError('IMPLEMENTATION_CONTRACT_INVALID')
        if base._hash(path.read_bytes()) != digest:
            raise ValueError('IMPLEMENTATION_CHANGED')


def _json(value):
    from dataclasses import is_dataclass, asdict
    if is_dataclass(value):
        return _json(asdict(value))
    if isinstance(value, (Decimal, date, datetime)):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json(v) for v in value]
    return value


def _changes(changes):
    if not isinstance(changes, list) or not 1 <= len(changes) <= 60:
        raise ValueError('EXPLICIT_BOUNDED_CHANGES_REQUIRED')
    seen = set()
    for change in changes:
        if not isinstance(change, dict) or set(change) != {'field', 'value'}:
            raise ValueError('INVALID_ASSUMPTION_CHANGE')
        field, value = change['field'], change['value']
        if not isinstance(field, str) or field in seen:
            raise ValueError('DUPLICATE_OR_INVALID_ASSUMPTION_FIELD')
        seen.add(field)
        annual = re.fullmatch(r'annual\.(10|[1-9])\.([a-z_]+)', field)
        allowed = (field == 'cost_of_equity'
                   or field == 'terminal.profit_scale'
                   or field.startswith('terminal.') and field[9:] in CASH_OVERRIDES
                   or annual and annual[2] in CASH_OVERRIDES)
        if not allowed:
            raise ValueError('ASSUMPTION_FIELD_NOT_WHITELISTED')
        if not isinstance(value, str) or not re.fullmatch(r'-?[0-9]+(?:\.[0-9]+)?', value):
            raise ValueError('EXPLICIT_DECIMAL_STRING_REQUIRED')
        if len(value) > 80 or not Decimal(value).is_finite():
            raise ValueError('BOUNDED_FINITE_ASSUMPTION_REQUIRED')


class TransparentTaskService(base.ResearchTaskService):
    """Subclass storage/locks/head writes; never calls base saved-model execution."""

    def __init__(self, root):
        super().__init__(root)
        self.base = self.base / 'transparent-v1'

    def capabilities(self):
        return dict(schema_version=VERSION, action='no_order', formal_eligibility=False,
                    operations=[dict(operation=x, enabled=True,
                        network_authorization_required=x == 'FRESH_PUBLIC_SCAN')
                        for x in OPERATIONS], statuses=list(PUBLIC_STATUSES),
                    simulation_fields=sorted(CASH_OVERRIDES),
                    progress_basis='COMPLETED_STEPS_NOT_TIME_PERCENT',
                    cancellation='COOPERATIVE_NATIVE_CALL_WITH_HARD_ATTEMPT_TIMEOUT')

    def prepare(self, *, symbol):
        """Read explicit registrations; no task/store writes, network or model run."""
        if not isinstance(symbol, str) or not re.fullmatch('[0-9]{6}', symbol):
            raise ValueError('INVALID_SYMBOL')
        rows = {op: dict(operation=op, enabled=False, reason='INPUT_NOT_REGISTERED',
                         payload=None, user_fields=[]) for op in OPERATIONS}

        def ready(op, payload, fields=()):
            rows[op].update(enabled=True, reason=None, payload=deepcopy(payload),
                input_version=base._hash(base._bytes(payload)), user_fields=list(fields))

        def failed(ops, prefix, error):
            # Deterministic bounded reasons, no exception path/private content.
            suffix = 'MISSING' if isinstance(error, FileNotFoundError) else 'INVALID'
            for op in ops:
                rows[op]['reason'] = prefix + '_' + suffix

        ready('FRESH_PUBLIC_SCAN', dict(network_authorized=False, max_per_channel=50),
              ('network_authorized',))
        main_ref = None
        try:
            from .main_valuation_revalidation_v1 import REGISTRY, VERSION as MAIN_VERSION
            registry_path = self.root / REGISTRY
            registry_ref = self._binding(registry_path)
            registry = self._bound(registry_ref)
            if (registry.get('schema_version') != 'current-operating-research-sources-v1'
                    or registry.get('action') != 'no_order'):
                raise ValueError('INVALID_REGISTRY')
            main_ref = registry['cases'].get(symbol, {}).get('main_revalidation')
            if main_ref is None:
                raise FileNotFoundError('MAIN_BASELINE_NOT_REGISTERED')
            payload = dict(registry_binding=registry_ref, spec_binding=main_ref)
            self._validate_payload(symbol, 'RECALCULATE_MAIN', payload)
            source = self._bound(main_ref)
            if source.get('schema_version') != MAIN_VERSION:
                raise ValueError('INVALID_MAIN_SPEC')
            for ref in source['bindings'].values():
                self._raw_binding(ref)
            if set(source['hypotheses']['scenarios']) != {'bear', 'base', 'bull'}:
                raise ValueError('MAIN_SCENARIOS_MISSING')
            self._bound(registry_ref)  # reject pointer mutation during preparation
            ready('RECALCULATE_MAIN', payload)
            ready('SIMULATE_ASSUMPTIONS',
                dict(payload, scenario='base', changes=[], rationale=''),
                ('scenario', 'changes', 'rationale'))
            ready('REVIEW_NOTE', dict(target_binding=main_ref, opinion=''), ('opinion',))
        except (ValueError, OSError, KeyError, TypeError) as error:
            main_ref = None
            failed(('RECALCULATE_MAIN', 'SIMULATE_ASSUMPTIONS'), 'MAIN_BASELINE', error)

        try:
            from .public_evidence import POINTER, load_bundle
            pointer_ref = self._binding(self.root / POINTER)
            pointer = self._bound(pointer_ref)
            if (pointer.get('schema_version') != 'public-evidence-pointer-v1'
                    or pointer.get('action') != 'no_order'):
                raise ValueError('INVALID_PUBLIC_EVIDENCE_POINTER')
            ref = pointer['bundle']
            self._validate_payload(symbol, 'VERIFY_EVIDENCE', dict(bundle_binding=ref))
            packet = load_bundle(self.root, ref)
            matches = [item for item in packet['items']
                       if item['request']['symbol'] == symbol and item.get('receipt')]
            if not matches:
                raise FileNotFoundError('NO_REGISTERED_SOURCE_FOR_SYMBOL')
            self._bound(pointer_ref)
            ready('VERIFY_EVIDENCE', dict(bundle_binding=ref))
            if main_ref is None:
                ready('REVIEW_NOTE', dict(target_binding=ref, opinion=''), ('opinion',))
        except (ValueError, OSError, KeyError, TypeError) as error:
            failed(('VERIFY_EVIDENCE',), 'PUBLIC_EVIDENCE_FOR_SYMBOL', error)
            if main_ref is None:
                failed(('REVIEW_NOTE',), 'REVIEW_TARGET', error)

        try:
            from ..discovery.value_module_adapter_v1 import validate
            pointer_path = self.root / '.tmp/daily-workbench-latest-run.json'
            raw = pointer_path.read_bytes()
            pointer = json.loads(raw.decode('utf-8-sig'))
            if (pointer.get('schema_version') != 'daily-workbench-run-v1'
                    or pointer.get('action') != 'no_order'):
                raise ValueError('INVALID_SCAN_REGISTRATION')
            # A registered restoration is explicitly historical replay, never fresh.
            entry = (pointer['marketwide_screen'] if 'marketwide_screen' in pointer
                     else pointer['retained_marketwide_screen'])
            ref = dict(path=entry['manifest_path'], sha256=entry['manifest_sha256'])
            payload = dict(manifest_binding=ref, evaluation_at=base._now().isoformat(), limit=50)
            validate(root=self.root, payload=dict(payload, symbol=symbol))
            manifest = self._bound(ref)
            for source_ref in manifest['files'].values():
                self._raw_binding(source_ref)
            if pointer_path.read_bytes() != raw:
                raise ValueError('SCAN_REGISTRATION_CHANGED')
            ready('REPLAY_SELECTION', payload)
        except (ValueError, OSError, KeyError, TypeError) as error:
            failed(('REPLAY_SELECTION',), 'REGISTERED_SCAN', error)
        return dict(schema_version=VERSION, action='no_order', formal_eligibility=False,
                    symbol=symbol, operations=[rows[op] for op in OPERATIONS], tasks_started=0)

    def _validate_payload(self, symbol, operation, payload):
        if operation not in OPERATIONS or not isinstance(payload, dict):
            raise ValueError('UNSUPPORTED_OPERATION')
        fields = {
            'REPLAY_SELECTION': {'manifest_binding', 'evaluation_at', 'limit'},
            'FRESH_PUBLIC_SCAN': {'network_authorized', 'max_per_channel'},
            'VERIFY_EVIDENCE': {'bundle_binding'},
            'REVIEW_NOTE': {'target_binding', 'opinion'},
            'RECALCULATE_MAIN': {'registry_binding', 'spec_binding'},
            'SIMULATE_ASSUMPTIONS': {'registry_binding', 'spec_binding', 'scenario',
                                     'changes', 'rationale'},
        }[operation]
        if set(payload) != fields:
            raise ValueError('EXACT_NATIVE_INPUT_FIELDS_REQUIRED')
        if operation == 'FRESH_PUBLIC_SCAN':
            if payload['network_authorized'] is not True:
                raise ValueError('EXPLICIT_PUBLIC_NETWORK_AUTHORIZATION_REQUIRED')
            if type(payload['max_per_channel']) is not int or not 1 <= payload['max_per_channel'] <= 50:
                raise ValueError('PUBLIC_SCAN_LIMIT_OUT_OF_RANGE')
        elif operation == 'REPLAY_SELECTION':
            from ..discovery.value_module_adapter_v1 import validate
            validate(root=self.root, payload=dict(payload, symbol=symbol))
            for ref in self._bound(payload['manifest_binding'])['files'].values():
                self._raw_binding(ref)
        elif operation == 'REVIEW_NOTE':
            opinion = payload['opinion']
            if not isinstance(opinion, str) or not 1 <= len(opinion.strip()) <= 4000:
                raise ValueError('BOUNDED_EXPLICIT_REVIEW_OPINION_REQUIRED')
            ref = payload['target_binding']
            if not isinstance(ref, dict) or not isinstance(ref.get('path'), str):
                raise ValueError('REVIEW_TARGET_BINDING_REQUIRED')
            name = Path(ref['path']).as_posix()
            if not name.startswith(('artifacts/current/', 'runtime/research-task-execution-v1/',
                                    'runtime/value-', 'runtime/e2-', 'runtime/public-evidence/')):
                raise ValueError('REVIEW_TARGET_MUST_BE_PUBLIC_RESEARCH_ARTIFACT')
            target = self._bound(ref)
            if name.startswith('runtime/public-evidence/'):
                from .public_evidence import load_bundle
                target = load_bundle(self.root, ref)
                matched = any(item['request']['symbol'] == symbol and item.get('receipt')
                              for item in target['items'])
            else:
                matched = isinstance(target, dict) and target.get('symbol') == symbol
            if not matched or target.get('action') != 'no_order':
                raise ValueError('REVIEW_TARGET_SYMBOL_OR_SCOPE_MISMATCH')
        elif operation == 'VERIFY_EVIDENCE':
            ref = payload['bundle_binding']
            require_inside(self.root / 'runtime/public-evidence', self.root / ref['path'],
                           'public evidence bundle')
            self._bound(ref)
        else:
            from .main_valuation_revalidation_v1 import (
                REGISTRY, implementation_fingerprints, implementation_fingerprint_basis)
            if payload['registry_binding']['path'] != REGISTRY:
                raise ValueError('EXACT_MAIN_REGISTRY_REQUIRED')
            registry = self._bound(payload['registry_binding'])
            if registry['cases'][symbol].get('main_revalidation') != payload['spec_binding']:
                raise ValueError('MAIN_REGISTRY_SPEC_BINDING_MISMATCH')
            spec = self._bound(payload['spec_binding'])
            if spec.get('symbol') != symbol or spec.get('action') != 'no_order':
                raise ValueError('MAIN_SPEC_IDENTITY_MISMATCH')
            if (spec.get('implementation_fingerprint_basis') != implementation_fingerprint_basis()
                    or spec.get('implementation_sha256') != implementation_fingerprints()):
                raise ValueError('MAIN_SPEC_MODEL_IMPLEMENTATION_CHANGED')
            for ref in spec.get('bindings', {}).values():
                self._raw_binding(ref)
            if operation == 'SIMULATE_ASSUMPTIONS':
                if payload['scenario'] not in {'bear', 'base', 'bull'}:
                    raise ValueError('EXPLICIT_BASELINE_SCENARIO_REQUIRED')
                if not isinstance(payload['rationale'], str) or not 1 <= len(payload['rationale'].strip()) <= 2000:
                    raise ValueError('EXPLICIT_USER_RATIONALE_REQUIRED')
                _changes(payload['changes'])
        return json.loads(base._bytes(payload))

    def _check(self, spec, now):
        try:
            _verify_source_contract(spec.get('source_contract'))
            if spec['implementation_sha256'] != _identity():
                raise ValueError('IMPLEMENTATION_CHANGED')
        except (ValueError, OSError, KeyError, TypeError) as error:
            reason = str(error) if isinstance(error, ValueError) else 'IMPLEMENTATION_SOURCE_MISSING'
            return None, 'FAILED', reason
        try:
            _actor_context(spec['operation'], spec.get('actor_context'))
            self._validate_payload(spec['symbol'], spec['operation'], spec['payload'])
            return True, None, None
        except FileNotFoundError:
            return None, 'WAITING_EVIDENCE', 'SOURCE_MISSING'
        except (ValueError, OSError, KeyError, TypeError):
            return None, 'FAILED', 'INPUT_VALIDATION_FAILED'

    def _load(self, task_id, *, recover=False):
        # Same native hash chain as the frozen parent, with a distinct input mode.
        directory = self._directory(task_id)
        raw = (directory / 'input.json').read_bytes()
        spec = json.loads(raw)
        if (spec.get('schema_version') != base.VERSION or spec.get('task_id') != task_id
                or spec.get('mode') != VERSION or spec.get('action') != 'no_order'):
            raise ValueError('INVALID_TRANSPARENT_TASK_INPUT')
        files = sorted((directory / 'versions').glob('*.json'))
        if not files or len(files) > 256:
            raise ValueError('TASK_CHAIN_MISSING_OR_UNBOUNDED')
        previous, chain = None, []
        for number, path in enumerate(files, 1):
            binding = self._binding(path)
            row = self._bound(binding)
            if (path.name != f'{number:04d}-{binding["sha256"]}.json'
                    or row.get('schema_version') != base.VERSION
                    or row.get('version') != number or row.get('previous') != previous
                    or row.get('task_id') != task_id or row.get('input_sha256') != base._hash(raw)
                    or row.get('status') not in base.STATES or row.get('action') != 'no_order'
                    or row.get('formal_eligibility') is not False or row.get('new_llm_calls') != 0):
                raise ValueError('TASK_CHAIN_IDENTITY_MISMATCH')
            previous = binding
            chain.append(binding)
        head_path = directory / 'current.json'
        head = json.loads(head_path.read_bytes()) if head_path.exists() else None
        if head is not None and head not in chain:
            raise ValueError('TASK_HEAD_OUTSIDE_CHAIN')
        if head != previous:
            if not recover:
                raise ValueError('EXPLICIT_RESUME_REQUIRED')
            self._head(directory, previous)
        return spec, row, previous

    def _view(self, spec, state, binding, now):
        result = deepcopy(state)
        native = state['status']
        status = {'SUCCEEDED': state.get('outcome', 'SUCCESS'),
                  'WAITING_EVIDENCE': 'BLOCKED'}.get(native, native)
        resume = native in {'QUEUED', 'RUNNING'} and state.get('worker_session') != _SESSION
        if resume:
            status = 'BLOCKED'
        _, current_failure, current_reason = self._check(spec, now)
        result.update(current_validation='UNASSESSABLE' if current_failure else 'VERIFIED',
                      current_validation_reason=current_reason, currently_consumable=False)
        if current_failure and native == 'SUCCEEDED':
            status = 'BLOCKED'
        if state.get('output_manifest') and native != 'CANCELLED' and not current_failure:
            try:
                manifest = self._verify_manifest(spec, state['output_manifest'])
                result['result_binding'] = deepcopy(manifest['artifacts'][0])
                result['result'] = self._bound(manifest['artifacts'][0])
                result['currently_consumable'] = native == 'SUCCEEDED'
            except (ValueError, OSError, KeyError, TypeError):
                status = 'FAILED'
                result['error_code'] = 'OUTPUT_MANIFEST_INVALID'
                result.update(current_validation='UNASSESSABLE',
                              current_validation_reason='OUTPUT_MANIFEST_INVALID')
        result.update(status=status, native_status=native, persisted_status=native,
            record_binding=deepcopy(binding), input_binding=self._binding(self._directory(spec['task_id']) / 'input.json'),
            operation=spec['operation'], symbol=spec['symbol'], resume_required=resume,
            progress=None, completed_steps=sum(x['status'] == 'SUCCESS' for x in state['steps']),
            total_steps=len(STEPS), native_metadata=dict(schema_version=VERSION,
                execution='NATIVE_ORIGIN_SERVICE', new_llm_calls=0, approval_changed=False),
            parent=deepcopy(spec.get('parent')), formal_eligibility=False, action='no_order')
        terminal = native in {'SUCCEEDED', 'FAILED', 'WAITING_EVIDENCE', 'CANCELLED'}
        started = state.get('started_at')
        finished = state.get('updated_at') if terminal else None
        duration, duration_basis = None, 'UNKNOWN_START_TIME'
        if started is not None:
            try:
                start_clock = datetime.fromisoformat(started)
                end_clock = datetime.fromisoformat(finished) if finished else now
                if (start_clock.utcoffset() is not None and end_clock.utcoffset() is not None
                        and end_clock >= start_clock):
                    duration = (end_clock - start_clock).total_seconds()
                    duration_basis = ('TERMINAL_VERSION_UPDATED_AT_MINUS_STARTED_AT' if terminal
                                      else 'OBSERVED_AT_MINUS_STARTED_AT')
            except (ValueError, TypeError):
                pass  # Unknown historical clocks remain unknown, not inferred.
        current_step = next((row['name'] for row in state['steps']
                             if row['status'] in {'RUNNING', 'FAILED'}), None)
        warnings = []
        if state.get('outcome') == 'PARTIAL':
            warnings.append('NATIVE_PARTIAL_RESULT')
        if result['current_validation'] == 'UNASSESSABLE':
            warnings.append('CURRENT_VALIDATION_UNASSESSABLE_HISTORY_PRESERVED')
        if started is None and state.get('attempts', 0):
            warnings.append('HISTORICAL_STARTED_AT_UNKNOWN')
        error = result.get('error_code') or result['current_validation_reason']
        source_refs = [dict(role=key, **deepcopy(value))
                       for key, value in spec['payload'].items()
                       if key.endswith('_binding') and isinstance(value, dict)
                       and set(value) == {'path', 'sha256'}]
        result.update(run_id=state.get('run_id'), module_id=OPERATION_MODULES[spec['operation']],
            module_version=spec['mode'], module_version_basis='TRANSPARENT_OPERATION_CONTRACT',
            started_at=started, finished_at=finished,
            finished_at_basis='TERMINAL_VERSION_UPDATED_AT' if terminal else None,
            duration_seconds=duration, duration_basis=duration_basis,
            current_step=current_step, error={'code': error} if error else None,
            warnings=warnings, retry_allowed=native in {'FAILED', 'WAITING_EVIDENCE', 'CANCELLED'},
            retry_basis='NEW_TASK_ID_REVALIDATES_INPUT_NOT_AUTOMATIC_SUCCESS',
            source_refs=source_refs, input_refs=[deepcopy(result['input_binding'])])
        return result

    def create(self, *, symbol, operation, payload, request_key, timeout_seconds=300,
               now=None, actor_context=None, _parent=None):
        now = base._now(now)
        if (not isinstance(symbol, str) or not re.fullmatch('[0-9]{6}', symbol)
                or not isinstance(request_key, str) or not 1 <= len(request_key) <= 128
                or type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 1800):
            raise ValueError('INVALID_TASK_IDENTITY_OR_TIMEOUT')
        source_contract = _source_contract(operation)
        actor = _actor_context(operation, actor_context)
        payload = self._validate_payload(symbol, operation, deepcopy(payload))
        task_id = 'rt-' + base._hash(request_key.encode('utf-8'))[:32]
        spec = dict(schema_version=base.VERSION, task_id=task_id, symbol=symbol,
            mode=VERSION, operation=operation, payload=payload, timeout_seconds=timeout_seconds,
            implementation_sha256=_identity(), action='no_order', parent=deepcopy(_parent),
            actor_context=actor, source_contract=source_contract)
        _verify_source_contract(source_contract)
        directory = self._directory(task_id)
        with self._lock(directory):
            if (directory / 'input.json').exists():
                old, state, binding = self._load(task_id)
                if old != spec:
                    raise ValueError('IMMUTABLE_REQUEST_KEY_CONFLICT')
                return self._view(old, state, binding, now)
            write_new_bytes(directory / 'input.json', base._bytes(spec))
            state = dict(status='QUEUED', attempts=0, created_at=now.isoformat(),
                worker_session=_SESSION, steps=[dict(name=s, status='QUEUED') for s in STEPS],
                output_manifest=None, error_code=None, new_llm_calls=0,
                action='no_order', formal_eligibility=False)
            state, binding = self._save(spec, state, None, now)
            return self._view(spec, state, binding, now)

    def list(self, *, symbol):
        return self.list_for_symbol(symbol)

    def resume(self, task_id, *, now=None):
        directory = self._directory(task_id)
        with self._lock(directory, 'execution'), self._lock(directory):
            spec, state, binding = self._load(task_id, recover=True)
            if state['status'] not in {'QUEUED', 'RUNNING'}:
                return self._view(spec, state, binding, base._now(now))
            if state['attempts'] >= 3:
                raise ValueError('RESUME_ATTEMPT_LIMIT_RETRY_NEW_ID')
            state, binding = self._save(spec, state, binding, base._now(now),
                status='QUEUED', worker_session=_SESSION, error_code=None,
                run_id=None, started_at=None,
                steps=[dict(name=s, status='QUEUED') for s in STEPS])
            return self._view(spec, state, binding, base._now(now))

    def retry(self, task_id, *, request_key=None, now=None):
        with self._lock(self._directory(task_id)):
            spec, state, binding = self._load(task_id)
            if state['status'] not in {'FAILED', 'WAITING_EVIDENCE', 'CANCELLED'}:
                raise ValueError('RETRY_REQUIRES_FAILED_BLOCKED_OR_CANCELLED_PARENT')
            parent = dict(task_id=task_id, state_binding=binding,
                          input_binding=self._binding(self._directory(task_id) / 'input.json'))
        key = request_key or uuid4().hex
        if 'rt-' + base._hash(key.encode('utf-8'))[:32] == task_id:
            raise ValueError('RETRY_REQUIRES_NEW_ID')
        return self.create(symbol=spec['symbol'], operation=spec['operation'],
            payload=spec['payload'], timeout_seconds=spec['timeout_seconds'],
            request_key=key, now=now, actor_context=spec.get('actor_context'), _parent=parent)

    def _verify_manifest(self, spec, binding):
        manifest = self._bound(binding)
        if (manifest['task_id'] != spec['task_id'] or manifest['action'] != 'no_order'
                or manifest['formal_eligibility'] is not False
                or manifest['input_sha256'] != base._hash(base._bytes(spec))):
            raise ValueError('OUTPUT_IDENTITY_MISMATCH')
        for ref in manifest['artifacts']:
            self._raw_binding(ref)
        return manifest

    def _raw_binding(self, ref):
        if (not isinstance(ref, dict) or set(ref) != {'path', 'sha256'}
                or not isinstance(ref['path'], str) or not isinstance(ref['sha256'], str)
                or Path(ref['path']).is_absolute() or '..' in Path(ref['path']).parts
                or not re.fullmatch('[0-9a-f]{64}', ref['sha256'])):
            raise ValueError('EXACT_ARTIFACT_BINDING_REQUIRED')
        path = require_inside(self.root, self.root / ref['path'], 'native artifact')
        if base._hash(path.read_bytes()) != ref['sha256']:
            raise ValueError('NATIVE_ARTIFACT_HASH_CHANGED')
        return path

    def _execute(self, spec, attempt):
        """Isolate native IO; timeout preserves raw logs/artifacts, no request cancellation."""
        input_path = self._directory(spec['task_id']) / 'input.json'
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8')
        env['PYTHONPATH'] = str(Path(__file__).resolve().parents[3]) + os.pathsep + env.get('PYTHONPATH', '')
        with (attempt / 'stdout.log').open('xb') as out, (attempt / 'stderr.log').open('xb') as err:
            process = subprocess.Popen([sys.executable, '-B', '-m', __name__,
                str(self.root), str(input_path), str(attempt)], stdout=out, stderr=err, env=env)
            deadline = time.monotonic() + spec['timeout_seconds']
            try:
                while True:
                    try:
                        with self._lock(self._directory(spec['task_id'])):
                            _, persisted, _ = self._load(spec['task_id'])
                    except base.LockTimeout:
                        persisted = None  # a concurrent read/control owns this short lock
                    if persisted is not None and persisted['status'] == 'CANCELLED':
                        raise base._Cancelled('NATIVE_CANCELLED')
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError('NATIVE_ATTEMPT_TIMEOUT')
                    try:
                        process.wait(timeout=min(0.25, remaining))
                        break
                    except subprocess.TimeoutExpired:
                        continue
            finally:
                # Only this owned child handle. Never enumerate/kill arbitrary PIDs.
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
        if process.returncode:
            raise RuntimeError('NATIVE_WORKER_FAILED')
        return json.loads((attempt / 'native-result.json').read_bytes())

    def run(self, task_id, *, now=None):
        directory = self._directory(task_id)
        with self._lock(directory, 'execution'):
            with self._lock(directory):
                spec, state, binding = self._load(task_id)
                if state['status'] != 'QUEUED' or state.get('worker_session') != _SESSION:
                    return self._view(spec, state, binding, base._now(now))
                steps = deepcopy(state['steps'])
                steps[0]['status'] = 'RUNNING'
                started = base._now(now)
                attempt_number = state['attempts'] + 1
                state, binding = self._save(spec, state, binding, started,
                    status='RUNNING', attempts=attempt_number, steps=steps,
                    run_id=f'{task_id}/attempt/{attempt_number:04d}',
                    started_at=started.isoformat())
                _, status, error = self._check(spec, base._now(now))
                if status:
                    steps[0]['status'] = 'FAILED'
                    state, binding = self._save(spec, state, binding, base._now(now),
                        status=status, error_code=error, steps=steps)
                    return self._view(spec, state, binding, base._now(now))
                attempt = directory / 'attempts' / f'{state["attempts"]:04d}'
                attempt.mkdir(parents=True, exist_ok=False)
                steps[0]['status'], steps[1]['status'] = 'SUCCESS', 'RUNNING'
                state, binding = self._save(spec, state, binding, base._now(now),
                    steps=steps, attempt_path=attempt.relative_to(self.root).as_posix(),
                    native_output_path=(
                        f'runtime/daily-marketwide/{task_id}-{attempt.name}'
                        if spec['operation'] == 'FRESH_PUBLIC_SCAN' else
                        attempt.relative_to(self.root).as_posix()))
            failure, result, started = None, None, time.monotonic()
            try:
                result = self._execute(spec, attempt)
                if time.monotonic() - started > spec['timeout_seconds']:
                    raise TimeoutError('NATIVE_ATTEMPT_TIMEOUT')
            except Exception as error:
                failure = dict(code='TIMEOUT' if isinstance(error, TimeoutError) else 'NATIVE_EXECUTION_FAILED',
                               error_type=type(error).__name__)
            # Independent of the browser request. Cancellation always wins a late completion.
            with self._lock(directory):
                spec, state, binding = self._load(task_id)
                write_new_bytes(attempt / 'attempt-record.json', base._bytes(dict(
                    task_id=task_id, finished_at=base._now().isoformat(), failure=failure,
                    cancelled=state['status'] == 'CANCELLED',
                    native_output_path=state['native_output_path'], action='no_order')))
                if state['status'] == 'CANCELLED':
                    return self._view(spec, state, binding, base._now())
                steps = deepcopy(state['steps'])
                steps[1]['status'] = 'FAILED' if failure else 'SUCCESS'
                if failure:
                    state, binding = self._save(spec, state, binding, base._now(),
                        status='FAILED', error_code=failure['code'], steps=steps)
                    return self._view(spec, state, binding, base._now())
                steps[2]['status'] = 'RUNNING'
                state, binding = self._save(spec, state, binding, base._now(), steps=steps)
                try:
                    _, invalid, _ = self._check(spec, base._now())
                    if invalid:
                        raise ValueError('SOURCE_CHANGED_DURING_RUN')
                    if (result['outcome'] not in {'SUCCESS', 'PARTIAL', 'BLOCKED', 'FAILED'}
                            or result['action'] != 'no_order' or result['formal_eligibility'] is not False):
                        raise ValueError('INVALID_NATIVE_OUTCOME')
                    result_path = attempt / 'result.json'
                    write_new_bytes(result_path, base._bytes(result))
                    artifacts = [self._binding(result_path), *result.get('artifact_bindings', [])]
                    manifest = dict(schema_version=VERSION, task_id=task_id,
                        input_sha256=base._hash(base._bytes(spec)), artifacts=artifacts,
                        action='no_order', formal_eligibility=False)
                    output = attempt / 'output-manifest.json'
                    write_new_bytes(output, base._bytes(manifest))
                    ref = self._binding(output)
                    self._verify_manifest(spec, ref)
                    outcome = result['outcome']
                    native = {'SUCCESS': 'SUCCEEDED', 'PARTIAL': 'SUCCEEDED',
                              'BLOCKED': 'WAITING_EVIDENCE', 'FAILED': 'FAILED'}[outcome]
                    steps[2]['status'] = 'SUCCESS'
                    state, binding = self._save(spec, state, binding, base._now(),
                        status=native, outcome=outcome, steps=steps, output_manifest=ref,
                        error_code=None if native == 'SUCCEEDED' else 'NATIVE_' + outcome)
                except (ValueError, OSError, KeyError, TypeError):
                    steps[2]['status'] = 'FAILED'
                    state, binding = self._save(spec, state, binding, base._now(),
                        status='FAILED', error_code='OUTPUT_OR_SOURCE_VALIDATION_FAILED', steps=steps)
                return self._view(spec, state, binding, base._now())


def _main_baseline(service, spec):
    from .main_valuation_revalidation_v1 import read_main_valuation_revalidation
    service._validate_payload(spec['symbol'], spec['operation'], spec['payload'])
    result = read_main_valuation_revalidation(root=service.root, symbol=spec['symbol'], now=base._now())
    service._validate_payload(spec['symbol'], spec['operation'], spec['payload'])
    return result


def _simulate(service, spec):
    from .main_valuation_revalidation_v1 import SUCCESS
    from ...domain.valuation.operating_profit_cash_path_v1 import compile_operating_profit_cash_path, PROFIT_BASIS
    from ...domain.valuation.joint_capital_cash_path_v4 import SCOPE
    from ...valuation_models.residual_income import QualityCompounderFacts
    from ...valuation_models.residual_income_path_v4 import scenario_calculation
    payload = spec['payload']
    baseline = _main_baseline(service, spec)
    if baseline['status'] != SUCCESS:
        raise ValueError('VERIFIED_MAIN_BASELINE_REQUIRED')
    source = service._bound(payload['spec_binding'])
    name = payload['scenario']
    ledger = baseline['annual_ledgers'][name]
    rows = []
    for assembled, actual in zip(baseline['period_assembly']['scenarios'][name]['model_years'], ledger['rows']):
        row = deepcopy(assembled['annual_row'])
        row['cash_policy'] = dict(actual['cash_policy'], scope=SCOPE, currency='CNY')
        rows.append(row)
    terminal = deepcopy(source['hypotheses']['scenarios'][name]['terminal_policy'])
    terminal.update(ledger['terminal']['cash_policy'])
    contract = ledger['terminal_economic_contract']
    capital = dict(operating_allocation=contract['operating_allocation'],
                   new_operating_return=contract['productive_marginal_return'],
                   new_liquidity_return=contract['liquidity_return'])
    inputs = dict(opening_state=ledger['opening_state'], annual_rows=rows,
        capital_policy=capital, terminal_policy=terminal,
        cost_of_equity=source['hypotheses']['scenarios'][name]['cost_of_equity'], profit_basis=PROFIT_BASIS)
    # Prove reconstruction before allowing changes: no inferred/default cash values.
    original = compile_operating_profit_cash_path(**deepcopy(inputs))
    if _json(original['rows']) != [{k: v for k, v in r.items() if k != 'cash_use_breakdown'} for r in ledger['rows']]:
        raise ValueError('BASELINE_COMPILER_INPUT_NOT_EXACT')
    for change in payload['changes']:
        field, value = change['field'], change['value']
        if field == 'cost_of_equity':
            inputs[field] = value
        elif field.startswith('terminal.'):
            inputs['terminal_policy'][field[9:]] = value
        else:
            _, year, key = field.split('.')
            inputs['annual_rows'][int(year) - 1]['cash_policy'][key] = value
    compiled = compile_operating_profit_cash_path(**inputs)
    opening = inputs['opening_state']
    facts = QualityCompounderFacts(symbol=spec['symbol'], as_of=date.fromisoformat(opening['as_of']),
        verified=False, confidence='USER_CONDITIONAL_ASSUMPTIONS', evidence_refs=[],
        blockers=['NOT_ADOPTED_MAIN_RANGE'], operating_inputs={
            'start_book_equity': Decimal(opening['book_equity_cny']),
            'ordinary_shares': Decimal(opening['ordinary_shares'])})
    calculation = scenario_calculation(facts, compiled['typed_scenario'])
    return _json(dict(scope='SOURCE_BOUND_USER_ASSUMPTION_SIMULATION_NOT_ADOPTED',
        baseline_binding=payload['spec_binding'], input_descriptor_sha256=baseline['input_descriptor_sha256'],
        changes=payload['changes'], rationale=payload['rationale'], inputs=inputs,
        source_bindings=baseline['source_bindings'],
        ledger={k: v for k, v in compiled.items() if k != 'typed_scenario'},
        calculation=calculation, action='no_order', formal_eligibility=False, main_range_adopted=False))


def _guard_public_io(service, spec, attempt, module):
    # Check between existing bounded collector calls. A completed call is allowed
    # to retain its raw output; cancellation prevents starting the next collector.
    def checkpoint():
        with service._lock(service._directory(spec['task_id'])):
            _, state, _ = service._load(spec['task_id'])
            if (state['status'] == 'CANCELLED'
                    or state['status'] != 'RUNNING'
                    or state['attempts'] != int(attempt.name)):
                raise base._Cancelled('NATIVE_CANCELLED_OR_SUPERSEDED')
    for name in ('build_financial_input', '_collect_official', 'fetch_tencent_board_rank',
                 'fetch_sina_industry_quotes', 'fetch_eastmoney_dividends'):
        original = getattr(module, name)
        def guarded(*args, _original=original, **kwargs):
            checkpoint()
            return _original(*args, **kwargs)
        setattr(module, name, guarded)


def _dispatch(service, spec, attempt):
    payload, operation = spec['payload'], spec['operation']
    artifacts, outcome = [], 'SUCCESS'
    if operation == 'REPLAY_SELECTION':
        from ..discovery.value_module_adapter_v1 import run
        result = run(root=service.root, payload=dict(payload, symbol=spec['symbol']),
                     output_dir=attempt / 'selection').as_dict()
        outcome = result['status']
        artifacts.append(service._binding(attempt / 'selection/module-run.json'))
        selection = attempt / 'selection/selection.json'
        refs = [item for item in result['output_manifest']['items'] if item['role'] == 'selection']
        if outcome in {'SUCCESS', 'PARTIAL'} and len(refs) != 1:
            raise ValueError('B_SELECTION_OUTPUT_BINDING_REQUIRED')
        if refs:
            if len(refs) != 1 or refs[0].get('hash_basis') != 'RAW_BYTES':
                raise ValueError('B_SELECTION_OUTPUT_BINDING_INVALID')
            ref = {key: refs[0][key] for key in ('path', 'sha256')}
            if (service.root / ref['path']).resolve() != selection.resolve():
                raise ValueError('B_SELECTION_OUTPUT_PATH_MISMATCH')
            # Consume the native run's ORIGINAL output pin, never hash changed bytes
            # afterwards and silently rebind a different selection.
            result['selection'] = service._bound(ref)
            result['selection_binding'] = deepcopy(ref)
            artifacts.append(ref)
    elif operation == 'REVIEW_NOTE':
        service._validate_payload(spec['symbol'], operation, payload)
        actor = _actor_context(operation, spec.get('actor_context'))
        artifacts.append(deepcopy(payload['target_binding']))
        result = dict(symbol=spec['symbol'], target_binding=deepcopy(payload['target_binding']),
            opinion=payload['opinion'], actor_context=actor,
            scope='COMMENT_NOT_G3_APPROVAL', recorded_at=base._now().isoformat(),
            action='no_order', approval_changed=False, formal_eligibility=False,
            signed=False, main_range_adopted=False)
    elif operation == 'VERIFY_EVIDENCE':
        from .public_evidence import public_evidence_closure, load_bundle
        closure = public_evidence_closure(root=service.root, bundle_binding=payload['bundle_binding'])
        packet = load_bundle(service.root, payload['bundle_binding'])
        if spec['symbol'] not in {x['request']['symbol'] for x in packet['items']}:
            raise ValueError('EVIDENCE_SYMBOL_NOT_IN_BUNDLE')
        artifacts.extend(closure)
        result = dict(bundle_status=packet['status'], source_bindings=closure,
                      scope='REQUESTED_REPORTS_ONLY_NOT_FACT_COMPLETENESS')
        outcome = ('BLOCKED' if not any(x.get('receipt') for x in packet['items']) else
                   'SUCCESS' if packet['status'] == 'VERIFIED' else 'PARTIAL')
    elif operation == 'RECALCULATE_MAIN':
        from .main_valuation_revalidation_v1 import SUCCESS
        result = _main_baseline(service, spec)
        artifacts.extend(result.get('source_bindings', []))
        outcome = ('SUCCESS' if result['status'] == SUCCESS else
                   'PARTIAL' if result['status'] == 'PARTIAL_REVALIDATION_PENDING_ECONOMIC_REVIEW'
                   else 'BLOCKED')
    elif operation == 'SIMULATE_ASSUMPTIONS':
        result = _simulate(service, spec)
        artifacts.extend(result['source_bindings'])
    elif operation == 'FRESH_PUBLIC_SCAN':
        script = Path(__file__).resolve().parents[4] / 'scripts/run_m2_opportunity_discovery.py'
        module_spec = importlib.util.spec_from_file_location('_transparent_public_m2', script)
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
        _guard_public_io(service, spec, attempt, module)
        output = service.root / 'runtime/daily-marketwide' / (spec['task_id'] + '-' + attempt.name)
        output.mkdir(parents=True, exist_ok=False)
        # No workbook/current/private/hotspot publication and no reused-input scan label.
        result = module.run_once(root=service.root, output_dir=output, wps_dir=None,
            max_per_channel=payload['max_per_channel'], skip_dividend=False, reuse_inputs=False,
            project_leads=True, skip_workbook=True, collect_public_financials=True)
        ref = service._binding(output / 'manifest.json')
        manifest = service._bound(ref)
        artifacts.append(ref)
        artifacts.extend(manifest['files'].values())
        outcome = 'PARTIAL'  # Fresh acquisition does not establish whole-market/fact completeness.
    else:
        raise ValueError('UNSUPPORTED_OPERATION')
    return _json(dict(operation=operation, outcome=outcome, result=result,
        artifact_bindings=artifacts, action='no_order', formal_eligibility=False,
        current_published=False, approval_changed=False, new_llm_calls=0))


def _worker(root, input_path, attempt):
    service = TransparentTaskService(Path(root))
    path = require_inside(service.base, Path(input_path), 'transparent input')
    spec = json.loads(path.read_bytes())
    directory = service._directory(spec['task_id'])
    attempt = require_inside(directory / 'attempts', Path(attempt), 'native attempt')
    if path != directory / 'input.json':
        raise ValueError('EXACT_TASK_INPUT_REQUIRED')
    _, invalid, _ = service._check(spec, base._now())
    if invalid:
        raise ValueError('NATIVE_INPUT_INVALID')
    result = _dispatch(service, spec, attempt)
    _, invalid, reason = service._check(spec, base._now())
    if invalid:
        raise ValueError(reason or 'NATIVE_INPUT_CHANGED_DURING_EXECUTION')
    write_new_bytes(attempt / 'native-result.json', base._bytes(result))


if __name__ == '__main__':
    _worker(*sys.argv[1:])
