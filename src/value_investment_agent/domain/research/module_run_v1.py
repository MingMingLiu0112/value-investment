"""Pure run envelope; external bytes, identity and future-source validation belong to callers.

Assurance is descriptive evidence, never investment authority. No I/O or runner.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import math
import re
from typing import Any, Protocol, runtime_checkable

SCHEMA_VERSION = 'module-run-v1'
MODULES = ('A','B','C','D1','D2','E1','E2','F1','F2','G1','G2')
RUN_TYPES = ('FULL','INCREMENTAL','REPLAY','VALIDATE')
STATUSES = ('QUEUED','RUNNING','SUCCESS','FAILED','CANCELLED','BLOCKED','PARTIAL')
ASSURANCE_LEVELS = ('TEST_ONLY','REAL_PUBLIC_REPLAY','REAL_PUBLIC_ACQUISITION','HISTORICAL_REPLAY','UNVERIFIED')
FIELDS = ('schema_version','action','run_id','module_id','run_type','status',
          'parent_run_ids','created_at','started_at','finished_at','input_manifest',
          'output_manifest','source_refs','artifact_refs','metrics','model_version',
          'rule_version','code_commit','symbol','stage_events','warnings','errors')
_SHA = re.compile(r'[0-9a-f]{64}\Z')


def _json(value: Any) -> None:
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float and math.isfinite(value):
        return
    if type(value) is list:
        for item in value:
            _json(item)
        return
    if type(value) is dict and all(type(k) is str for k in value):
        for item in value.values():
            _json(item)
        return
    raise ValueError('Only finite JSON with string object keys is permitted')


def canonical_json(value: Any) -> str:
    _json(value)
    result = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    try:
        result.encode('utf-8')
    except UnicodeError as exc:
        raise ValueError('Invalid Unicode JSON') from exc
    return result


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode('utf-8')).hexdigest()


def _text(value: Any, name: str) -> None:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise ValueError(f'{name}: explicit nonblank string required')


def _keys(value: Any, required: set[str], optional: set[str] | None = None) -> None:
    if type(value) is not dict or not required <= value.keys() or value.keys() - required - (optional or set()):
        raise ValueError(f'Invalid fields; required={sorted(required)}')


def _binding(item: Any) -> None:
    _keys(item, {'role','schema_id','sha256'}, {'payload','path','artifact_id','hash_basis'})
    for key in ('role','schema_id'):
        _text(item[key], key)
    if type(item['sha256']) is not str or not _SHA.fullmatch(item['sha256']):
        raise ValueError('sha256 must be lowercase 64 hex')
    locations = [k for k in ('payload','path','artifact_id') if k in item]
    if len(locations) != 1:
        raise ValueError('Exactly one of payload/path/artifact_id required')
    kind = locations[0]
    basis = item.get('hash_basis', 'CANONICAL_JSON' if kind == 'payload' else 'RAW_BYTES')
    if basis not in ('CANONICAL_JSON','RAW_BYTES'):
        raise ValueError('Unsupported hash_basis')
    if kind == 'payload':
        if type(item[kind]) is not dict or basis != 'CANONICAL_JSON':
            raise ValueError('Inline payload requires dict and canonical JSON binding')
        if canonical_sha256(item[kind]) != item['sha256']:
            raise ValueError('Inline payload sha256 mismatch')
    else:
        _text(item[kind], kind)
        if kind == 'path':
            path = item[kind]
            if (path.startswith('/') or any(c in path for c in '\\:\x00')
                    or any(ord(c) < 32 for c in path)
                    or any(p in ('','.','..') or p.rstrip(' .') != p for p in path.split('/'))):
                raise ValueError('path must be normalized project-relative POSIX path')


def make_manifest(schema_id: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    """Return detached manifest, digest covers canonical body excluding sha256."""
    _text(schema_id, 'schema_id')
    if type(items) is not list:
        raise ValueError('manifest items must be list')
    for item in items:
        _binding(item)
    body = json.loads(canonical_json({'schema_id':schema_id,'items':items}))
    return {**body, 'sha256':canonical_sha256(body)}


def _manifest(value: Any) -> None:
    _keys(value, {'schema_id','items','sha256'})
    if value != make_manifest(value['schema_id'], value['items']):
        raise ValueError('Manifest sha256 mismatch')


def _time(value: Any, name: str) -> datetime | None:
    if value is None:
        return None
    _text(value, name)
    if 'T' not in value:
        raise ValueError(f'{name}: ISO datetime required')
    try:
        result = datetime.fromisoformat(value.replace('Z','+00:00'))
    except ValueError as exc:
        raise ValueError(f'{name}: invalid datetime') from exc
    if result.utcoffset() is None:
        raise ValueError(f'{name}: timezone required')
    return result


def _validate(p: Any) -> None:
    _json(p)
    _keys(p, set(FIELDS))
    if p['schema_version'] != SCHEMA_VERSION or p['action'] != 'no_order':
        raise ValueError('Unsupported schema_version/action')
    for key in ('run_id','model_version','rule_version','code_commit'):
        _text(p[key], key)
    if not re.fullmatch(r'[0-9a-f]{7,64}', p['code_commit']):
        raise ValueError('Explicit hexadecimal code_commit required')
    for key, choices in (('module_id',MODULES),('run_type',RUN_TYPES),('status',STATUSES)):
        if p[key] not in choices:
            raise ValueError(f'Invalid {key}')
    # Explicit null identifies a batch/multi-security scope, never a fake ticker.
    if p['symbol'] is not None:
        _text(p['symbol'], 'symbol')
        if not re.fullmatch(r'[0-9]{6}', p['symbol']):
            raise ValueError('symbol must be null (batch) or an explicit six-digit symbol')
    for key in ('stage_events','warnings','errors'):
        if type(p[key]) is not list:
            raise ValueError(f'{key} must be explicit JSON list')
    if p['status'] == 'SUCCESS' and p['errors']:
        raise ValueError('SUCCESS cannot contain errors')
    parents = p['parent_run_ids']
    if type(parents) is not list:
        raise ValueError('parent_run_ids must be list')
    for parent in parents:
        _text(parent, 'parent_run_id')
    if len(set(parents)) != len(parents) or p['run_id'] in parents:
        raise ValueError('Duplicate/self parent run')
    created, started, finished = [_time(p[k], k) for k in ('created_at','started_at','finished_at')]
    if created is None:
        raise ValueError('created_at required for this run')
    if (started is not None and started < created) or (finished is not None and finished < (started or created)):
        raise ValueError('Run timestamp order violated')
    status = p['status']
    if status == 'QUEUED' and (started is not None or finished is not None):
        raise ValueError('QUEUED cannot be started/finished')
    if status == 'RUNNING' and (started is None or finished is not None):
        raise ValueError('RUNNING requires start and no finish')
    if status not in ('QUEUED','RUNNING') and finished is None:
        raise ValueError('Terminal run requires finished_at')
    if status in ('SUCCESS','FAILED','PARTIAL') and started is None:
        raise ValueError('SUCCESS/FAILED/PARTIAL requires started_at')
    for key in ('input_manifest','output_manifest'):
        _manifest(p[key])
    if status == 'SUCCESS' and not p['output_manifest']['items']:
        raise ValueError('SUCCESS requires bound output')
    for key in ('source_refs','artifact_refs'):
        if type(p[key]) is not list:
            raise ValueError(f'{key} must be explicit list')
        for item in p[key]:
            _binding(item)
    metrics = p['metrics']
    if type(metrics) is not dict or metrics.get('assurance') not in ASSURANCE_LEVELS:
        raise ValueError('metrics.assurance must declare evidence assurance')
    if metrics.get('source_ref_validation') != 'CALLER_RESPONSIBILITY':
        raise ValueError('Declare metrics.source_ref_validation=CALLER_RESPONSIBILITY')
    if status == 'SUCCESS' and (metrics.get('errors') or metrics.get('success') is False):
        raise ValueError('Contradictory SUCCESS metrics')


@dataclass(frozen=True, slots=True, init=False)
class ModuleRun:
    """Validated immutable JSON value; mutable exports and properties detach."""
    _canonical_json: str

    def __init__(self, payload: dict[str, Any]) -> None:
        _validate(payload)
        object.__setattr__(self, '_canonical_json', canonical_json(payload))

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> ModuleRun:
        return cls(payload)

    def as_dict(self) -> dict[str, Any]:
        return json.loads(self._canonical_json)

    def __getattr__(self, name: str) -> Any:
        if name in FIELDS:
            return self.as_dict()[name]
        raise AttributeError(name)


class ModuleRunCodec:
    artifact_type = 'module_run'
    schema_version = SCHEMA_VERSION

    @staticmethod
    def to_payload(value: ModuleRun) -> dict[str, Any]:
        if not isinstance(value, ModuleRun):
            raise TypeError('ModuleRunCodec requires ModuleRun')
        return value.as_dict()

    @staticmethod
    def from_payload(payload: dict[str, Any], **kwargs: Any) -> ModuleRun:
        # Repository dependency injection is accepted; this codec performs no resolution.
        return ModuleRun.from_payload(payload)


def _binding_schema() -> dict[str, Any]:
    return {'type':'object','required':['role','schema_id','sha256'],'additionalProperties':False,
            'properties':{'role':{'type':'string','minLength':1},'schema_id':{'type':'string','minLength':1},
                          'sha256':{'type':'string','pattern':'^[0-9a-f]{64}$'},'payload':{'type':'object'},
                          'path':{'type':'string','minLength':1},'artifact_id':{'type':'string','minLength':1},
                          'hash_basis':{'enum':['RAW_BYTES','CANONICAL_JSON']}},
            'oneOf':[{'required':[k]} for k in ('payload','path','artifact_id')]}


def manifest_schema() -> dict[str, Any]:
    return {'$schema':'https://json-schema.org/draft/2020-12/schema','type':'object',
            'required':['schema_id','items','sha256'],'additionalProperties':False,
            'properties':{'schema_id':{'type':'string','minLength':1},
                          'items':{'type':'array','items':_binding_schema()},
                          'sha256':{'type':'string','pattern':'^[0-9a-f]{64}$'}}}


def input_schema() -> dict[str, Any]:
    return manifest_schema()


def output_schema() -> dict[str, Any]:
    return manifest_schema()


def module_run_schema() -> dict[str, Any]:
    props = {k:{'type':'string','minLength':1} for k in FIELDS}
    props.update(schema_version={'const':SCHEMA_VERSION},action={'const':'no_order'},
                 module_id={'enum':list(MODULES)},run_type={'enum':list(RUN_TYPES)},status={'enum':list(STATUSES)},
                 code_commit={'type':'string','pattern':'^[0-9a-f]{7,64}$'},
                 symbol={'type':['string','null'],'pattern':'^[0-9]{6}$',
                         'description':'null explicitly denotes batch/multi-security scope; strings are single-security codes.'},
                 stage_events={'type':'array'},warnings={'type':'array'},errors={'type':'array'},
                 parent_run_ids={'type':'array','uniqueItems':True,'items':{'type':'string','minLength':1}},
                 created_at={'type':'string','format':'date-time'},
                 started_at={'type':['string','null'],'format':'date-time'},
                 finished_at={'type':['string','null'],'format':'date-time'},
                 input_manifest=input_schema(),output_manifest=output_schema(),
                 source_refs={'type':'array','items':_binding_schema()},
                 artifact_refs={'type':'array','items':_binding_schema()},
                 metrics={'type':'object','required':['assurance','source_ref_validation'],'properties':{
                     'assurance':{'enum':list(ASSURANCE_LEVELS)},
                     'source_ref_validation':{'const':'CALLER_RESPONSIBILITY'}}})
    return {'$schema':'https://json-schema.org/draft/2020-12/schema','type':'object',
            'required':list(FIELDS),'additionalProperties':False,'properties':props,
            'allOf':[
                {'if':{'properties':{'status':{'const':'QUEUED'}}},
                 'then':{'properties':{'started_at':{'type':'null'},'finished_at':{'type':'null'}}}},
                {'if':{'properties':{'status':{'const':'RUNNING'}}},
                 'then':{'properties':{'started_at':{'type':'string'},'finished_at':{'type':'null'}}}},
                {'if':{'properties':{'status':{'enum':['SUCCESS','PARTIAL','FAILED','CANCELLED','BLOCKED']}}},
                 'then':{'properties':{'finished_at':{'type':'string'}}}},
                {'if':{'properties':{'status':{'enum':['SUCCESS','PARTIAL','FAILED']}}},
                 'then':{'properties':{'started_at':{'type':'string'}}}},
                {'if':{'properties':{'status':{'const':'SUCCESS'}}},
                 'then':{'properties':{'errors':{'maxItems':0},
                                      'output_manifest':{'properties':{'items':{'minItems':1}}}}}},
            ],
            '$comment':'from_payload also enforces hashes, finite JSON, lifecycle and time order. Assurance grants no investment authority.'}


@runtime_checkable
class ModuleAdapter(Protocol):
    @property
    def input_schema(self) -> dict[str, Any]: ...
    @property
    def output_schema(self) -> dict[str, Any]: ...
    def validate(self, payload: dict[str, Any]) -> dict[str, Any]: ...
    def run(self, payload: dict[str, Any]) -> ModuleRun: ...
    def get_run(self, run_id: str) -> ModuleRun | None: ...
    def replay(self, run_id: str) -> ModuleRun: ...
    def explain(self, run_id: str) -> dict[str, Any]: ...
    def health_check(self) -> dict[str, Any]: ...
