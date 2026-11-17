"""Bound B-module execution metadata over the existing observation selector.

No current-pointer discovery, task scheduling, financial admission or publication.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
from uuid import uuid4

from ..product.common import encode_json_bytes, require_inside, write_new_bytes
from .current_scan import _bound_json, current_scan_details
from .value_candidate_selection import select_value_candidates
from ...domain.discovery.value_candidate_selection import VERSION as RULE_VERSION
from ...domain.research.module_run_v1 import ModuleRun, make_manifest, canonical_sha256, module_run_schema

VERSION = 'value-module-adapter-v1'
MODULE_ID = 'B'
INPUT_SCHEMA_REF = 'value-module-adapter-v1#/input_schema'
OUTPUT_SCHEMA_REF = 'value-module-adapter-v1#/output_schema'
input_schema = dict(type='object', additionalProperties=False,
    required=['manifest_binding', 'evaluation_at', 'limit'], properties={
        'manifest_binding': dict(type='object', additionalProperties=False,
            required=['path', 'sha256'], properties={
                'path': {'type': 'string'}, 'sha256': {'type': 'string', 'pattern': '^[0-9a-f]{64}$'}}),
        'evaluation_at': {'type': 'string', 'format': 'date-time'},
        'limit': {'type': 'integer', 'minimum': 1, 'maximum': 200},
        'symbol': {'type': ['string', 'null'], 'pattern': '^[0-9]{6}$'}})
output_schema = module_run_schema()


def _binding(root, path):
    return dict(path=path.relative_to(root).as_posix(), sha256=sha256(path.read_bytes()).hexdigest())


def _read(root, binding, *, base=None):
    if (not isinstance(binding, dict) or set(binding) != {'path', 'sha256'}
            or not isinstance(binding['path'], str) or not isinstance(binding['sha256'], str)
            or not re.fullmatch('[0-9a-f]{64}', binding['sha256'])):
        raise ValueError('B_INVALID_BINDING')
    name = Path(binding['path'])
    if name.is_absolute() or '..' in name.parts:
        raise ValueError('B_RELATIVE_BINDING_REQUIRED')
    path = require_inside(base or root, root / name, 'B binding')
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != binding['sha256']:
        raise ValueError('B_BINDING_HASH_MISMATCH')
    return json.loads(raw)


def validate(*, root, payload):
    """Validate explicit inputs only; native execution owns source validation."""
    root = Path(root).resolve()
    if (not isinstance(payload, dict)
            or not {'manifest_binding', 'evaluation_at', 'limit'} <= set(payload)
            or set(payload) - {'manifest_binding', 'evaluation_at', 'limit', 'symbol'}):
        raise ValueError('B_EXPLICIT_INPUT_REQUIRED')
    if type(payload['limit']) is not int or not 1 <= payload['limit'] <= 200:
        raise ValueError('B_LIMIT_INVALID')
    if not isinstance(payload['evaluation_at'], str):
        raise ValueError('B_AWARE_EVALUATION_REQUIRED')
    when = datetime.fromisoformat(payload['evaluation_at'])
    if when.utcoffset() is None or when > datetime.now(timezone.utc):
        raise ValueError('B_AWARE_NONFUTURE_EVALUATION_REQUIRED')
    if payload.get('symbol') is not None and (not isinstance(payload['symbol'], str)
            or not re.fullmatch('[0-9]{6}', payload['symbol'])):
        raise ValueError('B_SYMBOL_INVALID')
    _read(root, payload['manifest_binding'], base=root / 'runtime/daily-marketwide')
    return json.loads(encode_json_bytes(payload))


def _native(root, payload):
    result = select_value_candidates(root=root, manifest_binding=payload['manifest_binding'],
        now=datetime.fromisoformat(payload['evaluation_at']), limit=payload['limit'])
    manifest = _bound_json(root, payload['manifest_binding'], root / 'runtime/daily-marketwide', 512_000)
    scan = current_scan_details(root, manifest)
    if scan['status'] != 'SOURCE_REVALIDATED' or result.get('data_status') == 'SOURCE_REVALIDATION_FAILED':
        raise ValueError('B_SOURCE_REVALIDATION_FAILED')
    if result.get('action') != 'no_order' or result.get('formal_eligibility') is not False or result.get('buy_eligible') is not False:
        raise ValueError('B_NATIVE_ASSURANCE_MISMATCH')
    return result, scan


def _code_identity(root):
    # Actual HEAD plus exact executing bytes: dirty code is never labelled a clean build.
    package = Path(__file__).resolve().parents[2]
    # The loaded checkout, not the evidence root, owns the executing code.
    code_root = package.parents[1]
    def git(*args):
        return subprocess.check_output(['git', '-C', str(code_root), *args],
            stderr=subprocess.DEVNULL, text=True).strip()
    commit = git('rev-parse', 'HEAD')
    if not re.fullmatch('[0-9a-f]{40}', commit):
        raise ValueError('B_CODE_COMMIT_UNAVAILABLE')
    names = ['application/discovery/value_module_adapter_v1.py',
        'application/discovery/value_candidate_selection.py', 'application/discovery/current_scan.py',
        'application/discovery/public_financial_input.py', 'application/product/common.py',
        'application/product/value_discovery_surface.py', 'domain/discovery/value_candidate_selection.py',
        'domain/research/module_run_v1.py', 'm2_discovery_engine.py', 'm2_market_data.py',
        'm2_opportunity_discovery.py', 'financial_institutions.py',
        'infrastructure/screening/financial_export_v2.py',
        'infrastructure/screening/public_financial_snapshot.py',
        'infrastructure/screening/evidence_screen_v3.py']
    hashes = {name: sha256((package / name).read_bytes()).hexdigest() for name in names}
    return dict(code_commit=commit, workspace_dirty=bool(git('status', '--porcelain', '--untracked-files=normal')),
        implementation_sha256=hashes, adapter_version=VERSION, rule_version=RULE_VERSION)


def _new_directory(root, output_dir):
    path = require_inside(root / 'runtime', root / output_dir, 'B output directory')
    if path == root / 'runtime' or path.exists():
        raise ValueError('B_NEW_RUNTIME_DIRECTORY_REQUIRED')
    return path


def _inline(role, schema_id, payload):
    return dict(role=role, schema_id=schema_id, payload=payload,
                sha256=canonical_sha256(payload), hash_basis='CANONICAL_JSON')


def _file_ref(role, schema_id, binding):
    return dict(role=role, schema_id=schema_id,
        path=binding['path'].replace('\\', '/'), sha256=binding['sha256'], hash_basis='RAW_BYTES')


def _same_code(left, right):
    return all(left.get(key) == right.get(key) for key in
               ('code_commit', 'implementation_sha256', 'adapter_version', 'rule_version'))


def _gaps(selection, scan):
    gaps = list(selection.get('blockers', []))
    scope = selection.get('screening_scope') or {}
    if scope.get('all_a_complete') is not True:
        gaps.append('ALL_A_COVERAGE_NOT_PROVEN')
    if scan.get('financial', {}).get('status') != 'PROVIDER_OBSERVATIONS_NOT_FORMAL_FACTS':
        gaps.append('FINANCIAL_SOURCE_COVERAGE_NOT_COMPLETE')
    coverage = selection['coverage']
    if coverage['observation_company_count'] < coverage['universe_count']:
        gaps.append('FINANCIAL_OBSERVATION_COMPANY_GAPS')
    if selection.get('data_status') == 'PROVIDER_OBSERVATIONS_NOT_FORMAL_FACTS':
        gaps.append('FINANCIAL_SOURCE_ADMISSION_NOT_GRANTED')
    return list(dict.fromkeys(gaps))


def run(*, root, payload, output_dir, _parent=None):
    """Execute once into a caller-selected NEW runtime directory; return ModuleRun.

    Invalid input/source produces a bound FAILED record without an empty selection.
    No caller-supplied assurance or commit can upgrade this execution.
    """
    root = Path(root).resolve()
    directory = _new_directory(root, output_dir)
    code = _code_identity(root)
    # Only native test fixtures monkeypatch this internal identity. Never input flags.
    assurance = 'TEST_ONLY' if code.get('test_only') is True else 'REAL_PUBLIC_REPLAY'
    created = datetime.now(timezone.utc).isoformat()
    supplied = json.loads(encode_json_bytes(payload))
    inputs = make_manifest(INPUT_SCHEMA_REF, [_inline('request', INPUT_SCHEMA_REF, supplied),
        _inline('implementation', VERSION, code)])
    selection = None
    source_refs = []
    errors = []
    warnings = ['DIRTY_WORKTREE_EXACT_IMPLEMENTATION_HASHED'] if code['workspace_dirty'] else []
    started = datetime.now(timezone.utc).isoformat()
    scan = None
    try:
        checked = validate(root=root, payload=supplied)
        selection, scan = _native(root, checked)
        for index, ref in enumerate(selection['source_bindings']):
            _read(root, ref, base=root / 'runtime')
            source_refs.append(_file_ref(f'native_source_{index}', 'native-bound-source', ref))
        warnings += _gaps(selection, scan)
        status = 'PARTIAL' if warnings else 'SUCCESS'
    except (ValueError, OSError, KeyError, TypeError, AttributeError) as error:
        status = 'FAILED'
        selection = None
        source_refs = []
        errors.append(dict(code='B_INPUT_OR_SOURCE_VALIDATION_FAILED',
                           error_type=type(error).__name__, reason=str(error)))
        assurance = 'TEST_ONLY' if assurance == 'TEST_ONLY' else 'UNVERIFIED'
    if not _same_code(code, _code_identity(root)):
        raise ValueError('B_IMPLEMENTATION_CHANGED_DURING_RUN')
    outputs = []
    raw_selection = encode_json_bytes(selection) if selection is not None else None
    if raw_selection is not None:
        outputs.append(_file_ref('selection', RULE_VERSION, dict(
            path=(directory / 'selection.json').relative_to(root).as_posix(),
            sha256=sha256(raw_selection).hexdigest())))
    metrics = dict(assurance=assurance, source_ref_validation='CALLER_RESPONSIBILITY',
        native_source_validation='SOURCE_REVALIDATED' if selection is not None else 'FAILED',
        engineering_status='COMPLETED' if selection is not None else 'FAILED',
        source_scope_status='PARTIAL' if warnings else 'VERIFIED',
        financial_source_admitted=False, formal_eligibility=False, buy_eligible=False,
        new_llm_calls=0, network_calls=0, current_pointer_used=False,
        requested_symbol=supplied.get('symbol'), execution_scope='BATCH',
        workspace_dirty=code['workspace_dirty'],
        coverage=selection['coverage'] if selection is not None else None,
        input_schema_ref=INPUT_SCHEMA_REF, output_schema_ref=OUTPUT_SCHEMA_REF)
    if selection is None:
        metrics['source_scope_status'] = 'UNVERIFIED'
    finished = datetime.now(timezone.utc).isoformat()
    record = ModuleRun.from_payload(dict(schema_version='module-run-v1', action='no_order',
        run_id='b-' + uuid4().hex, module_id=MODULE_ID,
        run_type='REPLAY' if _parent else 'FULL', status=status,
        parent_run_ids=[_parent] if _parent else [], created_at=created,
        started_at=started, finished_at=finished, input_manifest=inputs,
        output_manifest=make_manifest(OUTPUT_SCHEMA_REF, outputs), source_refs=source_refs,
        artifact_refs=outputs, metrics=metrics, model_version=VERSION, rule_version=RULE_VERSION,
        code_commit=code['code_commit'], symbol=None,
        stage_events=[dict(stage='NATIVE_SOURCE_REPLAY', started_at=started, finished_at=finished,
                           status='FAILED' if selection is None else 'COMPLETED')],
        warnings=warnings, errors=errors))
    # Claim the NEW directory atomically. No existing directory, even empty, is reused.
    directory.parent.mkdir(parents=True, exist_ok=True)
    directory.mkdir(exist_ok=False)
    if raw_selection is not None:
        write_new_bytes(directory / 'selection.json', raw_selection)
    write_new_bytes(directory / 'module-run.json', encode_json_bytes(record.as_dict()))
    return record


def get_run(*, root, binding):
    """Read a known immutable record and its bound outputs, without scanning history."""
    root = Path(root).resolve()
    record = ModuleRun.from_payload(_read(root, binding, base=root / 'runtime'))
    if record.module_id != MODULE_ID or record.model_version != VERSION:
        raise ValueError('B_RECORD_MODULE_OR_VERSION_MISMATCH')
    for item in record.output_manifest['items']:
        if item['role'] != 'selection' or item.get('hash_basis') != 'RAW_BYTES':
            raise ValueError('B_UNSUPPORTED_OUTPUT_BINDING')
        _read(root, {k: item[k] for k in ('path', 'sha256')}, base=root / 'runtime')
    return record


def _request_and_code(record):
    items = record.input_manifest['items']
    if len(items) != 2 or [item['role'] for item in items] != ['request', 'implementation']:
        raise ValueError('B_REPLAY_INPUT_CONTRACT_MISMATCH')
    return items[0]['payload'], items[1]['payload']


def replay(*, root, binding, output_dir):
    record = get_run(root=root, binding=binding)
    payload, original_code = _request_and_code(record)
    if record.rule_version != RULE_VERSION or not _same_code(original_code, _code_identity(Path(root).resolve())):
        raise ValueError('B_REPLAY_CODE_OR_RULE_VERSION_MISMATCH')
    return run(root=root, payload=payload, output_dir=output_dir, _parent=record.run_id)


def explain(*, root, binding, symbol=None):
    record = get_run(root=root, binding=binding)
    payload, code = _request_and_code(record)
    symbol = symbol if symbol is not None else payload.get('symbol')
    if symbol is not None and (not isinstance(symbol, str) or not re.fullmatch('[0-9]{6}', symbol)):
        raise ValueError('B_SYMBOL_INVALID')
    rows = []
    selected = []
    for item in record.output_manifest['items']:
        native = _read(Path(root).resolve(), {k: item[k] for k in ('path', 'sha256')},
                       base=Path(root).resolve() / 'runtime')
        rows = native['items'] if symbol is None else [row for row in native['items'] if row['symbol'] == symbol]
        selected = [row['symbol'] for row in native['shortlist']]
    return dict(action='no_order', run_id=record.run_id, status=record.status,
        evaluation_at=payload['evaluation_at'], limit=payload['limit'], symbol=symbol,
        symbol_status='BATCH' if symbol is None else 'IN_OBSERVED_SCOPE' if rows else 'NOT_IN_OBSERVED_SCOPE',
        items=rows, shortlist_symbols=selected, warnings=record.warnings, errors=record.errors,
        execution_scope='BATCH', symbol_filter_only=symbol is not None,
        formal_eligibility=False, buy_eligible=False, interpretation='RESEARCH_SCHEDULING_ONLY',
        source_check='RECORDED_RUN_NOT_A_NEW_SOURCE_REPLAY')


def health_check(*, root):
    """Implementation readiness only, never evidence availability or market coverage."""
    try:
        code = _code_identity(Path(root).resolve())
        return dict(status='READY', action='no_order', code_identity=code,
            source_status='NOT_CHECKED', formal_eligibility=False, buy_eligible=False)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        return dict(status='BLOCKED', action='no_order', reason=str(error),
            source_status='NOT_CHECKED', formal_eligibility=False, buy_eligible=False)


class ValueModuleAdapter:
    """Eight-interface facade; output directories and record bindings stay explicit."""
    input_schema = input_schema
    output_schema = output_schema

    def __init__(self, root):
        self.root = Path(root).resolve()

    def validate(self, payload):
        return validate(root=self.root, payload=payload)

    def run(self, payload, *, output_dir):
        return run(root=self.root, payload=payload, output_dir=output_dir)

    def get_run(self, binding):
        return get_run(root=self.root, binding=binding)

    def replay(self, binding, *, output_dir):
        return replay(root=self.root, binding=binding, output_dir=output_dir)

    def explain(self, binding, *, symbol=None):
        return explain(root=self.root, binding=binding, symbol=symbol)

    def health_check(self):
        return health_check(root=self.root)
