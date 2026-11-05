"""Read-only validation projections over existing tasks, never a second run store.

HTTP authentication remains the caller's responsibility. This module registers no
routes, starts no work, and never repairs heads or writes execution records.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
from itertools import islice
import json
from pathlib import Path
import re
import subprocess
import uuid
from typing import Callable

from .agent_review.task_execution_v1 import ResearchTaskService, STATES, VERSION

from ...domain.research.module_run_v1 import (
    ModuleRun, MODULES, ASSURANCE_LEVELS, SCHEMA_VERSION, make_manifest, canonical_sha256,
)
_PROOF = object()
_PROJECTION_MODULES = ('D1','D2','G2')


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def _time(value):
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError('PROJECTION_AWARE_CLOCK_REQUIRED')
    return value.isoformat()


def _native_time(value):
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.isoformat() if parsed.utcoffset() is not None else None
    except (TypeError, ValueError):
        return None


def _current_commit(root):
    value = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'],
                                    text=True, stderr=subprocess.DEVNULL).strip()
    if not re.fullmatch('[0-9a-f]{40}', value):
        raise ValueError('PROJECTION_CODE_COMMIT_UNAVAILABLE')
    return value


def _bound(root, binding):
    if (not isinstance(binding, dict) or set(binding) != {'path', 'sha256'}
            or not isinstance(binding['path'], str)
            or not isinstance(binding['sha256'], str)
            or not re.fullmatch('[0-9a-f]{64}', binding['sha256'])):
        raise ValueError('PROJECTION_EXACT_BINDING_REQUIRED')
    relative = Path(binding['path'])
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('PROJECTION_BINDING_OUTSIDE_ROOT')
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError('PROJECTION_BINDING_OUTSIDE_ROOT')
    raw = path.read_bytes()
    if _hash(raw) != binding['sha256']:
        raise ValueError('PROJECTION_BINDING_HASH_MISMATCH')
    return raw


def _safe_summary(value):
    """Only typed native metadata survives; no free text, config or raw replies."""
    task_id = value.get('native_task_id', value.get('task_id'))
    status = value.get('native_status', value.get('status'))
    if not isinstance(task_id, str) or not re.fullmatch('rt-[0-9a-f]{32}', task_id):
        raise ValueError('PROJECTION_NATIVE_TASK_ID_INVALID')
    if status not in STATES:
        raise ValueError('PROJECTION_NATIVE_STATUS_INVALID')
    mode = value.get('execution_mode')
    scopes = {'SAVED_RESPONSE': 'SAVED_RESPONSE_NOT_NEW_LLM_RESEARCH',
              'MOCK': 'MOCK_NOT_REAL_RESEARCH',
              'LIVE_OPERATING': 'LIVE_LLM_OPERATING_RESEARCH_NOT_ADMITTED',
              'TEST_ONLY_LIVE_CONTRACT': 'TEST_ONLY_LIVE_CONTRACT_NOT_REAL_RESEARCH'}
    if mode not in scopes:
        raise ValueError('PROJECTION_NATIVE_EXECUTION_MODE_INVALID')
    current_status = value.get('status', status)
    if current_status not in STATES:
        raise ValueError('PROJECTION_NATIVE_STATUS_INVALID')
    if type(value.get('native_validation_passed')) is not bool:
        raise ValueError('PROJECTION_NATIVE_VALIDATION_RESULT_REQUIRED')
    symbol = value.get('symbol')
    if not isinstance(symbol, str) or not re.fullmatch('[0-9]{6}', symbol):
        raise ValueError('PROJECTION_NATIVE_SYMBOL_INVALID')
    summary = dict(native_validation_passed=value['native_validation_passed'], native_task_id=task_id, native_symbol=symbol, native_status=status, native_current_status=current_status, execution_mode=mode,
                   derived_scope=scopes[mode], native_code_commit=None,
                   native_created_at=_native_time(value.get('created_at')),
                   native_updated_at=_native_time(value.get('updated_at')),
                   native_started_at=None, native_finished_at=None,
                   unknown_fields=['native_code_commit', 'native_started_at', 'native_finished_at'])
    for key in ('attempts', 'provider_requests', 'new_llm_calls', 'finding_count'):
        item = value.get(key)
        if type(item) is int and item >= 0:
            summary[key] = item
    usage = value.get('usage', {})
    summary['usage'] = {key: usage[key] for key in ('prompt_tokens', 'completion_tokens')
                        if type(usage.get(key)) is int and usage[key] >= 0}
    basis = value.get('usage_basis')
    if basis in {'CONFIGURED_RATE_ESTIMATE_NOT_PROVIDER_BILL', 'MOCK_PROVIDER_ACCOUNTING_NOT_NEW_LLM_USAGE'}:
        summary['usage_basis'] = basis
    native_cost_basis = value.get('cost_basis', basis)
    for key in ('reserved_cost', 'settled_cost'):
        if key not in value:
            continue
        try:
            number = Decimal(str(value[key]))
            if not number.is_finite() or number < 0:
                raise ValueError('PROJECTION_COST_INVALID')
            summary[key] = str(number)
        except InvalidOperation as error:
            raise ValueError('PROJECTION_COST_INVALID') from error
        summary['currency'] = value.get('currency') if value.get('currency') in {'CNY','USD'} else None
        # Preserve only an EXPLICIT native-view basis. A numeric cost alone says
        # nothing about estimation, billing or payment. Never infer a basis.
        summary['cost_basis'] = (native_cost_basis if native_cost_basis ==
            'CONFIGURED_RATE_ESTIMATE_NOT_PROVIDER_BILL' else 'UNKNOWN_NOT_PROVIDER_BILL')
    summary['native_artifacts'] = [dict(role=item['role'], sha256=item['sha256'])
        for item in value.get('native_artifacts', [])
        if item.get('role') in {'WHOLE_PACKET', 'FUNDAMENTAL', 'COUNTER_EVIDENCE', 'EVENT'}
        and isinstance(item.get('sha256'), str) and re.fullmatch('[0-9a-f]{64}', item['sha256'])]
    error = value.get('error_code')
    if error is not None:
        summary['native_error_present'] = True
        summary['native_error_sha256'] = _hash(str(error).encode('utf-8'))
    return summary


@dataclass(frozen=True)
class _VerifiedNative:
    root: Path
    summary_json: bytes
    input_refs_json: bytes
    source_refs_json: bytes
    guards: tuple
    native_validator: Callable[[], dict]
    proof: object

    # Every public access detaches. No caller-owned dict/list survives in proof,
    # manifests or guards; frozen dataclass alone would only be shallow freezing.
    @property
    def summary(self):
        return json.loads(self.summary_json)

    @property
    def input_refs(self):
        return tuple(json.loads(self.input_refs_json))

    @property
    def source_refs(self):
        return tuple(json.loads(self.source_refs_json))


def verify_native_projection(*, root: Path, native_validator: Callable[[], dict],
                             input_refs, source_refs=()):
    """Invoke the existing validator, bind its metadata; a raw dict is not proof.

    Limited to existing D1/D2 task metadata for the G2 projection use case.
    Not a generic source-only A/B adapter or original-research admission path.
    """
    root = Path(root).resolve()
    inputs = tuple(json.loads(_canonical(list(input_refs))))
    sources = tuple(json.loads(_canonical(list(source_refs))))
    if not inputs or len(inputs) + len(sources) > 300 or not callable(native_validator):
        raise ValueError('PROJECTION_NATIVE_VALIDATOR_AND_BOUNDED_INPUTS_REQUIRED')
    guards = tuple((_canonical(ref), _bound(root, ref)) for ref in inputs + sources)
    summary = _safe_summary(native_validator())
    if any(_bound(root, json.loads(ref)) != raw for ref, raw in guards):
        raise ValueError('PROJECTION_INPUT_CHANGED_DURING_VALIDATION')
    return _VerifiedNative(root, _canonical(summary), _canonical(list(inputs)),
                           _canonical(list(sources)), guards, native_validator, _PROOF)


def native_projection_data(*, native_summary, module_id, symbol, input_refs=None,
                           source_refs=None, code_commit, model_version=None,
                           rule_version=None, started_at, finished_at, assurance):
    """Prepare only verified public metadata; domain conversion is separate."""
    if not isinstance(native_summary, _VerifiedNative) or native_summary.proof is not _PROOF:
        raise ValueError('PROJECTION_VERIFIED_NATIVE_REQUIRED')
    native = native_summary
    if module_id not in _PROJECTION_MODULES:
        raise ValueError('PROJECTION_MODULE_ID_INVALID')
    if not isinstance(symbol, str) or not re.fullmatch('[0-9]{6}', symbol):
        raise ValueError('PROJECTION_SYMBOL_INVALID')
    if symbol != native.summary['native_symbol']:
        raise ValueError('PROJECTION_NATIVE_SYMBOL_MISMATCH')
    if code_commit != _current_commit(native.root):
        raise ValueError('PROJECTION_CURRENT_COMMIT_MISMATCH')
    _time(started_at); _time(finished_at)
    if finished_at < started_at:
        raise ValueError('PROJECTION_CLOCK_ORDER_INVALID')
    if assurance not in ASSURANCE_LEVELS:
        raise ValueError('PROJECTION_ASSURANCE_INVALID')
    for version in (model_version, rule_version):
        if version is not None and (not isinstance(version, str) or not re.fullmatch('[A-Za-z0-9_.:-]{1,128}', version)):
            raise ValueError('PROJECTION_VERSION_INVALID')
    for refs, expected in ((input_refs, native.input_refs), (source_refs, native.source_refs)):
        if refs is not None and tuple(refs) != expected:
            raise ValueError('PROJECTION_VALIDATED_MANIFEST_CHANGED')
    if any(_bound(native.root, json.loads(ref)) != raw for ref, raw in native.guards):
        raise ValueError('PROJECTION_INPUT_CHANGED_AFTER_VALIDATION')
    # Re-enter the ORIGINAL native validator immediately before conversion. This
    # covers raw originals nested in workbench/source_binding without inventing
    # a second closure parser or accepting a stale top-level manifest hash.
    if _canonical(_safe_summary(native.native_validator())) != native.summary_json:
        raise ValueError('PROJECTION_NATIVE_VALIDATION_CHANGED')
    if any(_bound(native.root, json.loads(ref)) != raw for ref, raw in native.guards):
        raise ValueError('PROJECTION_INPUT_CHANGED_DURING_VALIDATION')
    summary = json.loads(_canonical(native.summary))
    if summary['execution_mode'] in {'MOCK', 'TEST_ONLY_LIVE_CONTRACT'} and assurance != 'TEST_ONLY':
        raise ValueError('PROJECTION_TEST_ONLY_ASSURANCE_REQUIRED')
    binding_hash = native.input_refs[-1]['sha256']
    success = summary['native_validation_passed']
    def inline(role, schema_id, payload):
        return dict(role=role, schema_id=schema_id, payload=payload,
                    sha256=canonical_sha256(payload), hash_basis='CANONICAL_JSON')
    def digest_ref(role, digest):
        # Public refs describe the verified native raw hash. Their OWN sha256 is
        # canonical JSON of this description, never a fake repository artifact ID.
        return inline(role, 'native-raw-binding-digest-v1',
                      dict(native_sha256=digest, native_hash_basis='RAW_BYTES'))
    inputs = [digest_ref('native_input' if i == 0 else 'native_version', ref['sha256'])
              for i, ref in enumerate(native.input_refs)]
    sources = [digest_ref('native_source', ref['sha256']) for ref in native.source_refs]
    artifacts = [digest_ref(item['role'], item['sha256']) for item in summary['native_artifacts']]
    metrics = dict(summary, symbol=symbol, assurance=assurance,
        source_ref_validation='CALLER_RESPONSIBILITY', success=success,
        projection_scope='READ_ONLY_NATIVE_PROVENANCE_VALIDATION_NOT_EXECUTION_OR_APPROVAL',
        assurance_scope='METADATA_ONLY_NOT_EXECUTION_APPROVAL',
        success_semantics='NATIVE_METADATA_PROVENANCE_VALIDATION_ONLY',
        native_execution_succeeded=summary['native_status']=='SUCCEEDED' and summary['native_current_status']=='SUCCEEDED',
        validation_new_llm_calls=0,native_summary_sha256=canonical_sha256(summary),
        native_record_sha256=binding_hash,
        validation_of=dict(kind='NATIVE_RESEARCH_TASK',task_id=summary['native_task_id'],
                           record_sha256=binding_hash,schema_version=VERSION),
        parent_relation='VALIDATION_OF_NATIVE_TASK', formal_eligibility=False,
        code_commit_basis='CURRENT_CHECKOUT_HEAD_NOT_NATIVE_EXECUTION',
        projection_implementation_sha256=_hash(Path(__file__).read_bytes()),
        native_model_version=None, native_rule_version=None,
        events=[dict(event='VALIDATION_STARTED',at=_time(started_at)),
                dict(event='VALIDATION_FINISHED',at=_time(finished_at))],
        warnings=['HISTORICAL_CODE_AND_EXECUTION_TIMES_NOT_RECONSTRUCTED'] +
                 ([] if summary['native_current_status']=='SUCCEEDED' else ['NATIVE_EXECUTION_NOT_SUCCEEDED']),
        errors=[] if success else ['NATIVE_VALIDATION_NOT_PASSED'])
    output = inline('native_validation_summary', 'native-validation-summary-v1', summary)
    payload = dict(schema_version=SCHEMA_VERSION, action='no_order',
        run_id='validation-'+summary['native_task_id']+'-'+binding_hash+'-'+uuid.uuid4().hex,
        module_id=module_id, symbol=symbol, run_type='VALIDATE', status='SUCCESS' if success else 'FAILED',
        stage_events=metrics.pop('events'),warnings=metrics.pop('warnings'),errors=metrics.pop('errors'),
        parent_run_ids=[], created_at=_time(started_at),
        started_at=_time(started_at), finished_at=_time(finished_at),
        input_manifest=make_manifest('native-validation-input-manifest-v1',inputs),
        output_manifest=make_manifest('native-validation-output-manifest-v1',[output]),
        source_refs=sources, artifact_refs=artifacts, metrics=metrics,
        model_version=model_version or 'NOT_APPLICABLE_METADATA_VALIDATION',
        rule_version=rule_version or 'module-run-projection-v1', code_commit=code_commit)
    return ModuleRun.from_payload(payload).as_dict()


def build_validation_run(*, native_summary, module_id, symbol, input_refs=None,
                         source_refs=None, code_commit, model_version=None,
                         rule_version=None, started_at, finished_at, assurance):
    """Build the sole shared ModuleRun, only AFTER the original native validator.

    Only existing D1/D2/G2 task metadata is supported; no generic A/B claim. Unknown
    native times/commit stay null in metrics; current VALIDATE times/commit are
    never passed off as native execution metadata. No persistence occurs here.
    """
    return native_projection_data(native_summary=native_summary,module_id=module_id,
        symbol=symbol,input_refs=input_refs,source_refs=source_refs,code_commit=code_commit,
        model_version=model_version,rule_version=rule_version,started_at=started_at,
        finished_at=finished_at,assurance=assurance)


class ModuleRunProjectionService:
    def __init__(self, root: Path, *, backend='saved', service=None, module_id=None):
        self.root = Path(root).resolve()
        if backend not in {'saved', 'live'}:
            raise ValueError('PROJECTION_BACKEND_INVALID')
        if backend == 'live':
            from .agent_review.operating_task_v2 import LiveOperatingTaskService
            expected_class = LiveOperatingTaskService
        else:
            expected_class = ResearchTaskService
        self.service = service or expected_class(self.root)
        if not isinstance(self.service, expected_class) or self.service.root != self.root:
            raise ValueError('PROJECTION_EXISTING_SERVICE_REQUIRED')
        self.backend = backend
        self.module_id = module_id or ('D1' if backend == 'saved' else 'D2')
        if self.module_id not in _PROJECTION_MODULES:
            raise ValueError('PROJECTION_MODULE_ID_INVALID')

    def _verified(self, task_id):
        view = self.service.read(task_id)
        directory = self.service._directory(task_id)
        input_path = directory / 'input.json'
        raw_input = input_path.read_bytes(); spec = json.loads(raw_input)
        input_ref = dict(path=input_path.relative_to(self.root).as_posix(), sha256=_hash(raw_input))
        if spec.get('task_id') != task_id or spec.get('schema_version') != VERSION:
            raise ValueError('PROJECTION_NATIVE_IDENTITY_INVALID')
        files = sorted(islice((directory / 'versions').glob('*.json'), 257))
        if not files or len(files) > 256:
            raise ValueError('PROJECTION_VERSION_HISTORY_UNBOUNDED')
        previous = None; refs = [input_ref]; rows = []
        for number, path in enumerate(files, 1):
            raw = path.read_bytes(); row = json.loads(raw)
            ref = dict(path=path.relative_to(self.root).as_posix(), sha256=_hash(raw))
            if (path.name != f'{number:04d}-{ref["sha256"]}.json'
                    or row.get('previous') != previous or row.get('version') != number
                    or row.get('input_sha256') != input_ref['sha256'] or row.get('task_id') != task_id
                    or row.get('schema_version') != VERSION or row.get('status') not in STATES):
                raise ValueError('PROJECTION_NATIVE_VERSION_CHAIN_INVALID')
            refs.append(ref); previous = ref; rows.append(row)
        head = directory / 'current.json'; headraw = head.read_bytes()
        if json.loads(headraw) != previous or view.get('record_binding') != previous:
            raise ValueError('PROJECTION_NATIVE_HEAD_CHANGED')
        if (view.get('task_id') != task_id or view.get('symbol') != spec.get('symbol')
                or view.get('execution_mode') != spec.get('mode')):
            raise ValueError('PROJECTION_NATIVE_VIEW_IDENTITY_INVALID')
        source_refs = [spec[k] for k in ('workbench', 'source_binding') if k in spec]
        view = dict(view, native_status=rows[-1]['status'])
        artifacts = []
        output_refs = []
        if view.get('checkpoint_verified') and rows[-1].get('checkpoint'):
            output_refs.append(('WHOLE_PACKET', rows[-1]['checkpoint']))
        if self.backend == 'live' and view.get('research_draft'):
            output_refs.extend((role, ref) for role, ref in rows[-1].get('roles', {}).items())
        for role, ref in output_refs:
            _bound(self.root, ref)
            artifacts.append(dict(role=role, sha256=ref['sha256']))
        view['native_artifacts'] = artifacts
        # Preserve a source-invalid read as failed metadata, never a current success.
        if rows[-1]['status'] == 'CANCELLED':
            _, source_status, _ = self.service._check(spec, datetime.now(timezone.utc))
            if source_status:
                view = dict(view, status=source_status)
        if self.backend == 'saved':
            native_valid = view.get('snapshot_status') == 'VERIFIED'
        else:
            native_valid = view.get('error_code') not in {
                'SOURCE_OR_IMPLEMENTATION_CHANGED','LIVE_CHECKPOINT_INVALID','EVIDENCE_MISSING'}
        if rows[-1]['status'] == 'SUCCEEDED' and view['status'] != 'SUCCEEDED':
            native_valid = False
        if rows[-1]['status'] == 'CANCELLED' and source_status:
            native_valid = False
        view['native_validation_passed'] = native_valid
        # The closure reuses existing native read/source validation, not this
        # cached dict. A failed/cancelled task may still have valid provenance;
        # conversely unchanged input.json does not prove raw originals unchanged.
        baseline = {key:view.get(key) for key in (
            'record_binding','status','snapshot_status','checkpoint_verified','error_code','context_fingerprint')}
        def validate_current():
            current = self.service.read(task_id)
            comparable = {key:current.get(key) for key in baseline}
            if comparable != baseline:
                raise ValueError('PROJECTION_NATIVE_VALIDATION_CHANGED')
            if rows[-1]['status'] == 'CANCELLED':
                _, current_source_status, _ = self.service._check(spec,datetime.now(timezone.utc))
                if current_source_status != source_status:
                    raise ValueError('PROJECTION_NATIVE_VALIDATION_CHANGED')
            return view
        verified = verify_native_projection(root=self.root, native_validator=validate_current,
                                            input_refs=refs, source_refs=source_refs)
        # Returned output hashes are verified, but not a second public payload store.
        for _, ref in output_refs:
            _bound(self.root, ref)
        if head.read_bytes() != headraw:
            raise ValueError('PROJECTION_NATIVE_HEAD_CHANGED')
        extra_guards = [(_canonical(dict(path=head.relative_to(self.root).as_posix(), sha256=_hash(headraw))), headraw)]
        extra_guards.extend((_canonical(ref), _bound(self.root, ref)) for _, ref in output_refs)
        verified = replace(verified, guards=verified.guards + tuple(extra_guards))
        return verified, spec

    def get(self, task_id):
        started = datetime.now(timezone.utc)
        _time(started)
        verified, spec = self._verified(task_id)
        return build_validation_run(native_summary=verified, module_id=self.module_id,
                                    symbol=spec['symbol'], code_commit=_current_commit(self.root),
                                    started_at=started, finished_at=datetime.now(timezone.utc),
                                    assurance='TEST_ONLY' if verified.summary['execution_mode'] in {'MOCK','TEST_ONLY_LIVE_CONTRACT'} else 'UNVERIFIED')

    def history(self, symbol):
        # Existing bounded discovery revalidates every item; no directory scan/index.
        views = self.service.list_for_symbol(symbol)
        return [self.get(view['task_id']) for view in views]

    def diff(self, left_id, right_id):
        left = self.get(left_id); right = self.get(right_id)
        a, b = left, right
        if (a['module_id'], a['metrics']['symbol']) != (b['module_id'], b['metrics']['symbol']):
            raise ValueError('PROJECTION_DIFF_SCOPE_MISMATCH')
        keys = ('input_manifest', 'output_manifest', 'source_refs', 'artifact_refs', 'status')
        return dict(schema_version='module-run-projection-diff-v1',
                    left_run_id=a['run_id'], right_run_id=b['run_id'],
                    changes=[dict(field=k, before=a[k], after=b[k]) for k in keys if a[k] != b[k]],
                    economic_comparability='NOT_ASSESSED_METADATA_ONLY', action='no_order', formal_eligibility=False)
