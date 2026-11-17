"""Independent v10 cash-policy task store for the fixed Q3 OCR supplement.

The v10 corpus has no v8 approved-plan anchors. V3's stable-source duplicate
guard is retained; v1's policy request/validator is used without inventing a
plan, CFO, or parent cash. Old task contracts and stores are untouched.
"""
from datetime import datetime
from copy import deepcopy
import json
import os
from pathlib import Path
import re

from . import operating_cash_policy_task_v1 as cash_v1
from .operating_cash_policy_task_v3 import OperatingCashPolicyTaskServiceV3
from . import operating_cash_policy_task_v3 as cash_v3
from . import operating_cash_policy_task_v2 as cash_v2
from . import operating_horizon_sources_v10_q3_ocr as sources
from . import operating_task_v2 as live
from .task_execution_v1 import VERSION, _bytes, _hash, _now
from ...product.common import require_inside

CONTRACT = 'operating-cash-policy-task-v4-q3-ocr'
STORE = 'cp4q3'
CONFIG = 'config/current-operating-q3-ocr-task-v1.json'


def implementation():
    return {**cash_v1.implementation(), **sources.implementation(),
            cash_v2.__name__: _hash(Path(cash_v2.__file__).read_bytes()),
            cash_v3.__name__: _hash(Path(cash_v3.__file__).read_bytes()),
            __name__: _hash(Path(__file__).read_bytes())}


def _write_new(path, raw):
    """Exclusive publication; pinned hashes reject a partial interrupted file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


class OperatingCashPolicyTaskServiceV4(OperatingCashPolicyTaskServiceV3):
    def __init__(self, root, *, test_provider=None):
        super().__init__(root, test_provider=test_provider, source_loader=self._source)
        self.base = require_inside(self.root, self.base.parent / STORE, 'v10 cash task store')

    def _source(self, *, root, symbol, now, binding=None):
        if binding is not None:
            return sources.build_operating_horizon_source_context(
                root=root, symbol=symbol, now=now, binding=binding)
        path = require_inside(self.root, self.root / CONFIG, 'v10 cash source selection')
        raw = path.read_bytes()
        registry = json.loads(raw)
        if (set(registry) != {'schema_version', 'action', 'cases'} or
                registry['schema_version'] != 'operating-q3-ocr-task-selection-v1' or
                registry['action'] != 'no_order' or
                set(registry['cases']) != {sources.SUPPORTED_SYMBOL}):
            raise ValueError('V10_CASH_SELECTION_INVALID')
        selected = registry['cases'][symbol]
        if set(selected) != {'base_binding'}:
            raise ValueError('V10_CASH_BASE_BINDING_REQUIRED')
        result = sources.build_operating_horizon_source_context(
            root=root, symbol=symbol, now=now, base_binding=selected['base_binding'])
        if path.read_bytes() != raw:
            raise ValueError('V10_CASH_SELECTION_CHANGED')
        return result

    def _stable_source_identity(self, binding, seen=None):
        manifest = self._bound(binding)
        if (manifest.get('schema_version') != sources.VERSION or
                manifest.get('symbol') != sources.SUPPORTED_SYMBOL or
                manifest.get('action') != 'no_order'):
            raise ValueError('V10_CASH_SOURCE_IDENTITY_INVALID')
        return {key: manifest[key] for key in
                ('schema_version', 'symbol', 'base_binding', 'q3_source_bindings',
                 'implementation_sha256', 'action')}

    def _load(self, task_id, *, recover=False):
        spec, state, pin = live.LiveOperatingTaskService._load(self, task_id, recover=recover)
        if spec.get('task_contract') != CONTRACT or spec.get('symbol') != sources.SUPPORTED_SYMBOL:
            raise ValueError('INVALID_V10_CASH_TASK')
        cash_v1.v2.v1._years(spec['years'])
        return spec, state, pin

    def _save(self, spec, state, previous, now, **changes):
        row = deepcopy(state)
        row.update(changes)
        row.update(schema_version=VERSION, task_id=spec['task_id'],
                   input_sha256=_hash(_bytes(spec)), previous=previous,
                   version=state.get('version', 0) + 1, updated_at=now.isoformat())
        raw = _bytes(row)
        path = self._directory(spec['task_id']) / 'versions' / f'{row["version"]:04d}-{_hash(raw)}.json'
        _write_new(path, raw)
        pin = self._binding(path)
        self._head(self._directory(spec['task_id']), pin)
        return row, pin

    def _request(self, spec, context):
        return cash_v1.OperatingCashPolicyTaskService._request(self, spec, context)

    def _result(self, spec, state, context):
        return cash_v1.OperatingCashPolicyTaskService._result(self, spec, state, context)

    def _context(self, spec):
        if spec['implementation_sha256'] != implementation():
            raise ValueError('V10_CASH_IMPLEMENTATION_CHANGED')
        context = self._source(root=self.root, symbol=spec['symbol'],
                               binding=spec['source_binding'],
                               now=datetime.fromisoformat(spec['created_at']))
        if (context.get('source_binding') != spec['source_binding'] or
                context.get('snapshot_fingerprint') != spec['context_fingerprint'] or
                _hash(_bytes(context)) != spec['context_sha256'] or
                context.get('valuation_admitted') is not False):
            raise ValueError('V10_CASH_CONTEXT_CHANGED')
        if _hash(_bytes(self._request(spec, context).__dict__)) != spec['request_sha256']:
            raise ValueError('V10_CASH_REQUEST_CHANGED')
        return context

    def create(self, *, symbol, request_key, years, now=None):
        now = _now(now)
        years = cash_v1.v2.v1._years(years)
        if (symbol != sources.SUPPORTED_SYMBOL or not isinstance(request_key, str) or
                re.fullmatch(r'[A-Za-z0-9_-]{8,80}', request_key) is None):
            raise ValueError('V10_CASH_IDENTITY_INVALID')
        cfg = live.model_configuration(self.root)
        if self.test_provider is None and not os.environ.get(cfg['api_key_env']):
            raise PermissionError('MODEL_CREDENTIAL_REQUIRED')
        task_id = 'rt-' + _hash((CONTRACT + ':' + request_key).encode('utf-8'))[:32]
        directory = self._directory(task_id)
        with self._lock(self.base, name='admission'), self._lock(directory):
            if (directory / 'input.json').exists():
                spec, state, pin = self._load(task_id)
                mode = 'TEST_ONLY_LIVE_CONTRACT' if self.test_provider is not None else 'LIVE_OPERATING'
                if (spec['symbol'] != symbol or spec['years'] != years or
                        spec['config'] != cfg or spec['mode'] != mode or
                        spec['implementation_sha256'] != implementation()):
                    raise ValueError('V10_CASH_REQUEST_KEY_CONFLICT')
                return self._view(spec, state, pin, now)
            context = self._source(root=self.root, symbol=symbol, now=now)
            if self._prior_schema_failure(symbol=symbol, source_binding=context['source_binding'], config=cfg):
                raise PermissionError('V10_CASH_PRIOR_SCHEMA_FAILURE')
            mode = 'TEST_ONLY_LIVE_CONTRACT' if self.test_provider is not None else 'LIVE_OPERATING'
            if self._prior_equivalent_research(symbol=symbol, years=years, context=context,
                                               config=cfg, mode=mode):
                raise PermissionError('V10_CASH_EQUIVALENT_SOURCE_ALREADY_RESEARCHED')
            spec = dict(schema_version=VERSION, task_id=task_id, workflow='operating_research',
                        task_contract=CONTRACT, mode=mode, symbol=symbol, years=years,
                        request_key_sha256=_hash(request_key.encode('utf-8')),
                        created_at=now.isoformat(), source_binding=context['source_binding'],
                        context_fingerprint=context['snapshot_fingerprint'],
                        context_sha256=_hash(_bytes(context)), config=cfg,
                        implementation_sha256=implementation(), action='no_order')
            spec['request_sha256'] = _hash(_bytes(self._request(spec, context).__dict__))
            self._context(spec)
            _write_new(directory / 'input.json', _bytes(spec))
            state = dict(status='QUEUED', attempts=0, provider_requests=0, new_llm_calls=0,
                         usage=dict(prompt_tokens=0, completion_tokens=0),
                         reserved_cost='0', settled_cost='0', reservations={},
                         response_binding=None, created_at=now.isoformat(), action='no_order',
                         formal_eligibility=False, error_code=None)
            state, pin = self._save(spec, state, None, now)
            return self._view(spec, state, pin, now)

    def _view(self, spec, state, binding, now):
        value = super()._view(spec, state, binding, now)
        value['workflow'] = CONTRACT
        value['scope'] = 'Q3_OCR_TWO_FIELDS_CASH_POLICY_RESEARCH_NOT_ADMITTED'
        return value
