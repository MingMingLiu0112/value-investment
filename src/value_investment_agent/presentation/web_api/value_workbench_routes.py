"""Public read-only value workbench and locally authorized explicit task controls."""
from __future__ import annotations

import ast
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from itertools import islice
import re

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import JSONResponse, Response

from ...application.product.common import require_inside
from .local_auth import authorize, LocalAuthorizationError, AUTHORIZATION_REQUIRED

BASE = '/api/v1/value-workbench'
MODULES = frozenset(('A', 'B', 'C', 'D1', 'D2', 'E1', 'E2', 'F1', 'F2', 'G1', 'G2'))
CONTROLS = frozenset(('cancel', 'retry', 'resume'))
OPERATION_MODULES = {'REPLAY_SELECTION': 'B', 'FRESH_PUBLIC_SCAN': 'B',
    'VERIFY_EVIDENCE': 'A', 'RECALCULATE_MAIN': 'F1', 'SIMULATE_ASSUMPTIONS': 'F1',
    'REVIEW_NOTE': 'G2'}
MAX_BODY = 16_384
MAX_DOWNLOAD = 50_000_000


def _read_workbench(project, symbol):
    from ...application.product.value_transparent_workbench_v1 import read_value_transparent_workbench
    value = read_value_transparent_workbench(root=project, symbol=symbol, now=datetime.now(timezone.utc))
    if value.get('action') != 'no_order' or value.get('formal_eligibility') is not False:
        raise ValueError('WORKBENCH_PUBLIC_BOUNDARY_MISMATCH')
    # Only the aggregator's evidence section supplies downloadable bindings.
    bindings = []
    for section in value.get('sections', []):
        if section.get('id') == 'evidence' and section.get('data') is not None:
            bindings.extend(section['data'].get('source_bindings', []))
    downloads = []
    for binding in bindings:
        ident = sha256((binding['path'] + '\0' + binding['sha256']).encode('utf-8')).hexdigest()
        downloads.append(dict(id=ident, binding=binding,
            url=BASE + '/evidence/' + ident + '?symbol=' + symbol))
    return dict(value, evidence_downloads=downloads,
        portfolio_entry=dict(href='/portfolio', workflow='EXISTING_PREPARE_CONFIRM',
                             scope='NO_TRADE_RECORDED_BY_WORKBENCH'))


def _reply(value, status=200):
    return JSONResponse(value, status_code=status, headers={'Cache-Control': 'no-store'})


def _task_service(project):
    from ...application.research.transparent_task_v1 import TransparentTaskService
    return TransparentTaskService(project)


def _task_inputs(project, symbol):
    """Native preparation owns registered source selection; this is UI projection only."""
    try:
        service = _task_service(project)
        prepare = getattr(service, 'prepare', None)
        if prepare is None:
            raise ValueError('TASK_INPUT_PREPARATION_NOT_AVAILABLE')
        prepared = prepare(symbol=symbol)
        if (not isinstance(prepared, dict) or prepared.get('action') != 'no_order'
                or prepared.get('symbol') != symbol or not isinstance(prepared.get('operations'), list)):
            raise ValueError('TASK_PREPARATION_CONTRACT_MISMATCH')
        rows = {row['operation']: row for row in prepared['operations']}
        if len(rows) != len(prepared['operations']) or set(rows) - set(OPERATION_MODULES):
            raise ValueError('TASK_PREPARATION_OPERATION_MISMATCH')
        operations = []
        for operation, module_id in OPERATION_MODULES.items():
            row = deepcopy(rows.get(operation, {}))
            enabled = row.get('enabled') is True and isinstance(row.get('payload'), dict)
            payload = row.get('payload') if enabled else None
            if enabled and operation == 'FRESH_PUBLIC_SCAN':
                payload['network_authorized'] = False  # only a subsequent explicit checkbox authorizes POST
            operations.append(dict(row, operation=operation, module_id=module_id, enabled=enabled,
                reason=row.get('reason') or (None if enabled else 'VERIFIED_TASK_INPUT_UNAVAILABLE'),
                payload=payload, prepared_payload=payload, user_fields=row.get('user_fields', []),
                network_authorization_required=operation == 'FRESH_PUBLIC_SCAN'))
        capabilities = service.capabilities() if hasattr(service, 'capabilities') else {}
        return dict(action='no_order', formal_eligibility=False, symbol=symbol,
            status='PREPARED' if any(row['enabled'] for row in operations) else 'DISABLED',
            operations=operations, tasks_started=0,
            simulation_fields=capabilities.get('simulation_fields', []))
    except (ImportError, ValueError, OSError, KeyError, TypeError, RuntimeError) as error:
        return dict(action='no_order', formal_eligibility=False, symbol=symbol, status='DISABLED',
            operations=[dict(operation=operation, module_id=module_id, enabled=False,
                reason=str(error), prepared_payload=None, user_fields=[],
                network_authorization_required=operation == 'FRESH_PUBLIC_SCAN')
                for operation, module_id in OPERATION_MODULES.items()], tasks_started=0)


def _task_id(value):
    if not isinstance(value, str) or not re.fullmatch('rt-[0-9a-f]{32}', value):
        raise ValueError('INVALID_TASK_ID')
    return value


def _task_read(service, task_id):
    spec, state, binding = service._load(task_id, recover=False)
    result = service._view(spec, state, binding, datetime.now(timezone.utc))
    if service._load(task_id, recover=False)[2] != binding:
        raise ValueError('TASK_CHANGED_DURING_PUBLIC_READ')
    return result


def _task_list(service, symbol):
    if not service.base.exists():
        return []
    children = list(islice(service.base.iterdir(), 101))
    if len(children) > 100:
        raise ValueError('RESEARCH_TASK_DISCOVERY_LIMIT_EXCEEDED: max_entries=100')
    items = []
    for path in sorted(children):
        if path.is_dir() and re.fullmatch('rt-[0-9a-f]{32}', path.name):
            row = _task_read(service, path.name)
            if row['symbol'] == symbol:
                items.append(row)
                if len(items) > 20:
                    raise ValueError('RESEARCH_TASK_RESULT_LIMIT_EXCEEDED: max_results=20')
    return sorted(items, key=lambda row: (row['updated_at'], row['task_id']), reverse=True)


def _task_history(service, task_id):
    _, state, head = service._load(task_id, recover=False)
    items = []
    binding = head
    while binding is not None:
        if len(items) >= 256:
            raise ValueError('TASK_HISTORY_LIMIT_EXCEEDED')
        row = service._bound(binding)
        items.append(dict(record_binding=binding, record=row))
        binding = row['previous']
    if service._load(task_id, recover=False)[2] != head:
        raise ValueError('TASK_CHANGED_DURING_HISTORY_READ')
    return list(reversed(items))


def _failure(error, *, status=422):
    return _reply(dict(status='UNASSESSABLE', reason=str(error), detail=str(error), error_type=type(error).__name__,
                       action='no_order', formal_eligibility=False), status)


def _symbol(symbol):
    if not isinstance(symbol, str) or re.fullmatch('[0-9]{6}', symbol) is None:
        raise ValueError('INVALID_SYMBOL')
    return symbol


def _queries(request, allowed):
    pairs = list(request.query_params.multi_items())
    if set(k for k, _ in pairs) - set(allowed) or len(pairs) != len({k for k, _ in pairs}):
        raise ValueError('UNSUPPORTED_OR_DUPLICATE_QUERY')


def _unique_json(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('DUPLICATE_JSON_FIELD')
        value[key] = item
    return value


async def _body(request):
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > MAX_BODY:
            raise ValueError('WORKBENCH_BODY_TOO_LARGE')
    def invalid_constant(value):
        raise ValueError('NONFINITE_JSON')
    result = json.loads(raw, object_pairs_hook=_unique_json, parse_constant=invalid_constant)
    if not isinstance(result, dict):
        raise ValueError('WORKBENCH_OBJECT_BODY_REQUIRED')
    return result


def _catalog(project):
    path = require_inside(project, project / 'config/value-mainline-modules-v1.json', 'module catalog')
    raw = path.read_bytes()
    if len(raw) > 2_000_000:
        raise ValueError('MODULE_CATALOG_TOO_LARGE')
    catalog = json.loads(raw, object_pairs_hook=_unique_json)
    if catalog['schema_version'] != 'value-mainline-modules-v1' or catalog['action'] != 'no_order':
        raise ValueError('MODULE_CATALOG_CONTRACT_MISMATCH')
    seen = set()
    items = []
    for item in catalog['modules']:
        module = item['module_id']
        if module not in MODULES or module in seen:
            raise ValueError('MODULE_CATALOG_ID_INVALID_OR_DUPLICATE')
        seen.add(module)
        metadata = []
        for ref in item.get('entrypoints', []):
            name = ref.get('path', '')
            info = dict(ref, inspection='NOT_INSPECTED', runtime_status='NOT_READ')
            relative = Path(name)
            if (not isinstance(name, str) or relative.is_absolute() or '..' in relative.parts
                    or not name.startswith(('src/', 'scripts/')) or relative.suffix != '.py'):
                info['inspection'] = 'NOT_A_LOCAL_PYTHON_ENTRYPOINT'
            else:
                target = require_inside(project, project / relative, 'native entrypoint')
                try:
                    content = target.read_bytes()
                    if len(content) > 2_000_000:
                        raise ValueError('ENTRYPOINT_SOURCE_TOO_LARGE')
                    tree = ast.parse(content.decode('utf-8-sig'))
                    nodes = tree.body
                    found = None
                    for part in ref.get('entrypoint', '').split('(')[0].split('.'):
                        found = next((node for node in nodes if isinstance(node,
                            (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == part), None)
                        if found is None:
                            break
                        nodes = found.body
                    info.update(inspection='SOURCE_DEFINITION_PRESENT' if found is not None else 'SOURCE_DEFINITION_NOT_FOUND',
                        sha256=sha256(content).hexdigest())
                except FileNotFoundError:
                    info['inspection'] = 'SOURCE_FILE_MISSING'
                except (SyntaxError, UnicodeError, ValueError) as error:
                    info.update(inspection='SOURCE_NOT_INSPECTABLE', reason=str(error))
            metadata.append(info)
        items.append(dict(item, native_source_metadata=metadata, runtime_status='NOT_READ'))
    if path.read_bytes() != raw:
        raise ValueError('MODULE_CATALOG_CHANGED_DURING_READ')
    return dict(schema_version='value-workbench-module-catalog-v1', action='no_order',
        formal_eligibility=False, modules=items, runtime_status='NOT_READ',
        task_operations=[dict(module_id=module, operation=operation,
            network_authorization_required=operation == 'FRESH_PUBLIC_SCAN')
            for operation, module in OPERATION_MODULES.items()],
        catalog_binding=dict(path=path.relative_to(project).as_posix(), sha256=sha256(raw).hexdigest()),
        review_note_status='COMMENT_TASK_ONLY_NOT_G3_APPROVAL')


def _companies(project):
    """Registration discovery only: do not open/revalidate the registered research."""
    registered = {}
    sources = []
    for name, schema, field in (
        ('config/current-research-drafts.json', 'current-research-drafts-v1', 'pending_candidates'),
        ('config/current-operating-research-sources-v1.json', 'current-operating-research-sources-v1', 'cases'),
    ):
        try:
            path = require_inside(project, project / name, 'public company registry')
            if path.stat().st_size > 2_000_000:
                raise ValueError('COMPANY_REGISTRY_TOO_LARGE')
            raw = path.read_bytes()
            if len(raw) > 2_000_000:
                raise ValueError('COMPANY_REGISTRY_TOO_LARGE')
            value = json.loads(raw, object_pairs_hook=_unique_json)
            if (not isinstance(value, dict) or value.get('schema_version') != schema
                    or value.get('action') != 'no_order' or not isinstance(value.get(field), dict)):
                raise ValueError('COMPANY_REGISTRY_SCHEMA_OR_ACTION_MISMATCH')
            symbols = []
            for symbol, entry in value[field].items():
                _symbol(symbol)
                if not isinstance(entry, dict):
                    raise ValueError('COMPANY_REGISTRY_ENTRY_MUST_BE_OBJECT')
                symbols.append(symbol)
            if path.read_bytes() != raw:
                raise ValueError('COMPANY_REGISTRY_CHANGED_DURING_READ')
            binding = dict(path=name, sha256=sha256(raw).hexdigest())
            sources.append(dict(status='REGISTRY_ENUMERATED_NOT_RESEARCH_VERIFIED', binding=binding))
            for symbol in symbols:
                registered.setdefault(symbol, []).append(binding)
        except (ValueError, OSError, KeyError, TypeError) as error:
            sources.append(dict(path=name, status='UNASSESSABLE', reason=str(error),
                                error_type=type(error).__name__))
    failed = sum(row['status'] == 'UNASSESSABLE' for row in sources)
    return dict(action='no_order', formal_eligibility=False,
        status='UNASSESSABLE' if failed == len(sources) else 'PARTIAL' if failed else 'REGISTERED_ENTRIES',
        scope='REGISTERED_RESEARCH_ENTRIES_NOT_CURRENT_SHORTLIST', sources=sources,
        items=[dict(symbol=symbol, name=None, status='REGISTERED_NOT_YET_REVALIDATED',
            current_candidate=None, research_verified=False, source_registries=bindings,
            action='no_order', formal_eligibility=False,
            url=BASE + '?symbol=' + symbol) for symbol, bindings in sorted(registered.items())])


def register_value_workbench_routes(api: FastAPI, *, project, sessions, port):
    project = Path(project).resolve()

    def denied(request):
        try:
            authorize(request, session=sessions, port=port)
        except LocalAuthorizationError as error:
            return _reply(dict(status=error.code, reason=error.detail, action='no_order', formal_eligibility=False),
                          401 if error.code == AUTHORIZATION_REQUIRED else 403)
        return None

    @api.get(BASE)
    def workbench(request: Request, symbol: str | None = None):
        try:
            _queries(request, {'symbol'})
            return _reply(_read_workbench(project, _symbol(symbol)))
        except ImportError as error:
            return _failure(error, status=503)
        except (ValueError, OSError, KeyError, TypeError) as error:
            return _failure(error)

    @api.get(BASE + '/modules')
    def modules(request: Request, symbol: str | None = None):
        try:
            _queries(request, {'symbol'})
            catalog = _catalog(project)
            if symbol is not None:
                catalog['task_inputs'] = _task_inputs(project, _symbol(symbol))
            return _reply(catalog)
        except (ValueError, OSError, KeyError, TypeError) as error:
            return _failure(error)

    @api.get(BASE + '/task-inputs')
    def task_inputs(request: Request, symbol: str | None = None):
        try:
            _queries(request, {'symbol'})
            return _reply(_task_inputs(project, _symbol(symbol)))
        except (ValueError, OSError, KeyError, TypeError) as error:
            return _failure(error)

    @api.get(BASE + '/companies')
    def companies(request: Request):
        try:
            _queries(request, set())
            return _reply(_companies(project))
        except (ValueError, OSError, KeyError, TypeError) as error:
            return _failure(error)

    @api.post(BASE + '/tasks')
    async def create(request: Request, background: BackgroundTasks):
        error = denied(request)
        if error is not None:
            return error
        try:
            _queries(request, set())
            body = await _body(request)
            if not {'module_id', 'operation', 'symbol', 'request_key', 'payload'} <= set(body) or set(body) - {
                    'module_id', 'operation', 'symbol', 'request_key', 'payload', 'timeout_seconds'}:
                raise ValueError('INVALID_TASK_CREATE_FIELDS')
            if body['module_id'] not in MODULES or OPERATION_MODULES.get(body['operation']) != body['module_id']:
                raise ValueError('UNSUPPORTED_MODULE_OR_OPERATION')
            _symbol(body['symbol'])
            if (not isinstance(body['request_key'], str)
                    or not re.fullmatch('[A-Za-z0-9_-]{8,80}', body['request_key'])
                    or not isinstance(body['payload'], dict)):
                raise ValueError('INVALID_TASK_REQUEST_KEY_OR_INPUTS')
            if 'timeout_seconds' in body and (type(body['timeout_seconds']) is not int
                    or not 1 <= body['timeout_seconds'] <= 1800):
                raise ValueError('INVALID_TASK_TIMEOUT')
            service = _task_service(project)
            kwargs = {key: value for key, value in body.items() if key != 'module_id'}
            if body['operation'] == 'REVIEW_NOTE':
                from ...application.research.transparent_task_v1 import REVIEW_ACTOR_CONTEXT
                kwargs['actor_context'] = deepcopy(REVIEW_ACTOR_CONTEXT)
            task = service.create(**kwargs)
            if task['status'] == 'QUEUED':
                background.add_task(service.run, task['task_id'])
            return _reply(task, 202)
        except ImportError as error:
            return _failure(error, status=503)
        except PermissionError as error:
            return _failure(error, status=403)
        except (ValueError, OSError, KeyError, TypeError, RuntimeError) as error:
            return _failure(error)

    @api.get(BASE + '/tasks')
    def tasks(request: Request, symbol: str | None = None):
        error = denied(request)
        if error is not None:
            return error
        try:
            _queries(request, {'symbol'})
            _symbol(symbol)
            items = _task_list(_task_service(project), symbol)
            return _reply(dict(action='no_order', formal_eligibility=False, symbol=symbol, items=items))
        except ImportError as error:
            return _failure(error, status=503)
        except (ValueError, OSError, KeyError, TypeError, RuntimeError) as error:
            return _failure(error)

    @api.get(BASE + '/tasks/{task_id}')
    def read_task(task_id: str, request: Request):
        error = denied(request)
        if error is not None:
            return error
        try:
            _queries(request, set())
            _task_id(task_id)
            return _reply(_task_read(_task_service(project), task_id))
        except ImportError as error:
            return _failure(error, status=503)
        except (ValueError, OSError, KeyError, TypeError, RuntimeError) as error:
            return _failure(error, status=404)

    @api.get(BASE + '/tasks/{task_id}/history')
    @api.get(BASE + '/tasks/history/{task_id}')
    def history(task_id: str, request: Request):
        error = denied(request)
        if error is not None:
            return error
        try:
            _queries(request, set())
            _task_id(task_id)
            value = _task_history(_task_service(project), task_id)
            return _reply(dict(action='no_order', formal_eligibility=False, task_id=task_id, history=value))
        except ImportError as error:
            return _failure(error, status=503)
        except (ValueError, OSError, KeyError, TypeError, RuntimeError) as error:
            return _failure(error, status=404)

    @api.post(BASE + '/tasks/{task_id}/{operation}')
    async def control(task_id: str, operation: str, request: Request, background: BackgroundTasks):
        error = denied(request)
        if error is not None:
            return error
        try:
            _queries(request, set())
            if operation not in CONTROLS:
                raise ValueError('UNSUPPORTED_TASK_CONTROL')
            _task_id(task_id)
            if await _body(request) != {}:
                raise ValueError('TASK_CONTROL_REQUIRES_EMPTY_OBJECT')
            service = _task_service(project)
            task = getattr(service, operation)(task_id)
            if operation != 'cancel' and task['status'] == 'QUEUED':
                background.add_task(service.run, task['task_id'])
            return _reply(task)
        except ImportError as error:
            return _failure(error, status=503)
        except PermissionError as error:
            return _failure(error, status=403)
        except (ValueError, OSError, KeyError, TypeError, RuntimeError) as error:
            return _failure(error, status=409)

    @api.get(BASE + '/evidence/{evidence_id}')
    def evidence(evidence_id: str, request: Request, symbol: str | None = None):
        try:
            _queries(request, {'symbol'})
            if not re.fullmatch('[A-Za-z0-9_-]{1,128}', evidence_id):
                raise ValueError('INVALID_EVIDENCE_ID')
            view = _read_workbench(project, _symbol(symbol))
            entries = view.get('evidence_downloads', [])
            matches = [entry for entry in entries if entry.get('id') == evidence_id]
            if len(matches) != 1:
                raise ValueError('EVIDENCE_NOT_IN_AGGREGATED_ALLOWLIST')
            binding = matches[0]['binding']
            if set(binding) != {'path', 'sha256'} or not re.fullmatch('[0-9a-f]{64}', binding['sha256']):
                raise ValueError('INVALID_EVIDENCE_BINDING')
            name = Path(binding['path'])
            if name.is_absolute() or '..' in name.parts:
                raise ValueError('EVIDENCE_PATH_NOT_RELATIVE')
            path = require_inside(project, project / name, 'aggregated evidence')
            if path.stat().st_size > MAX_DOWNLOAD:
                raise ValueError('EVIDENCE_DOWNLOAD_TOO_LARGE')
            raw = path.read_bytes()
            if len(raw) > MAX_DOWNLOAD or sha256(raw).hexdigest() != binding['sha256']:
                raise ValueError('EVIDENCE_HASH_MISMATCH')
            # Serve the verified bytes, not a FileResponse that would reopen a changed file.
            return Response(raw, media_type='application/octet-stream', headers={
                'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
                'Content-Disposition': f'attachment; filename="{evidence_id}.bin"'})
        except ImportError as error:
            return _failure(error, status=503)
        except (ValueError, OSError, KeyError, TypeError) as error:
            return _failure(error, status=404)
