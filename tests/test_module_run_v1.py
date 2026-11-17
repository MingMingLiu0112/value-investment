"""TEST_ONLY mechanism tests; no real-source or investment acceptance claims."""
import ast
import copy
from dataclasses import FrozenInstanceError
from pathlib import Path
import pytest
from value_investment_agent.domain.research.module_run_v1 import (
    ModuleRun, ModuleRunCodec, ModuleAdapter, SCHEMA_VERSION, FIELDS,
    MODULES, RUN_TYPES, STATUSES, make_manifest, canonical_sha256,
    module_run_schema, input_schema, output_schema,
)


def binding(payload=None):
    payload = {'observed': [1, {'label':'公开'}]} if payload is None else payload
    return {'role':'result','schema_id':'test-result-v1','payload':payload,
            'sha256':canonical_sha256(payload)}


def payload():
    return dict(symbol='000568',stage_events=[],warnings=[],errors=[],schema_version=SCHEMA_VERSION, action='no_order', run_id='validation-new-1',
                module_id='D2', run_type='VALIDATE', status='SUCCESS', parent_run_ids=['native-task-1'],
                created_at='2026-11-01T10:00:00+08:00', started_at='2026-11-01T02:00:01Z',
                finished_at='2026-11-01T02:00:02+00:00',
                input_manifest=make_manifest('test-input-v1',[binding()]),
                output_manifest=make_manifest('test-output-v1',[binding()]),
                source_refs=[],artifact_refs=[],
                metrics={'assurance':'TEST_ONLY','source_ref_validation':'CALLER_RESPONSIBILITY',
                         'native_task_id':'native-task-1','native_started_at':None,
                         'native_code_commit':None,'historical_not_original_run':True},
                model_version='NOT_APPLICABLE',rule_version='validation-v1',code_commit='590b13f3')


def test_codec_roundtrip_deep_immutability():
    p=payload(); original=copy.deepcopy(p); run=ModuleRun.from_payload(p)
    p['metrics']['native_task_id']='changed'
    p['output_manifest']['items'][0]['payload']['observed'].append(3)
    exported=run.as_dict();exported['metrics']['assurance']='UNVERIFIED'
    run.metrics['assurance']='UNVERIFIED'
    assert run.as_dict()==original
    assert ModuleRunCodec.from_payload(ModuleRunCodec.to_payload(run), dependencies={})==run
    assert ModuleRunCodec.artifact_type=='module_run'
    with pytest.raises((FrozenInstanceError,AttributeError,TypeError)):
        run._canonical_json='{}'
    with pytest.raises(TypeError):ModuleRunCodec.to_payload(original)


@pytest.mark.parametrize('field',FIELDS)
def test_every_field_mandatory(field):
    p=payload();del p[field]
    with pytest.raises(ValueError):ModuleRun.from_payload(p)


@pytest.mark.parametrize('module',MODULES)
def test_all_eleven_modules(module):
    p=payload();p['module_id']=module
    assert ModuleRun.from_payload(p).module_id==module


@pytest.mark.parametrize('run_type',RUN_TYPES)
def test_run_types(run_type):
    p=payload();p['run_type']=run_type
    assert ModuleRun.from_payload(p).run_type==run_type


@pytest.mark.parametrize('status',STATUSES)
def test_lifecycle_positive(status):
    p=payload();p['status']=status
    if status=='QUEUED':p.update(started_at=None,finished_at=None)
    if status=='RUNNING':p['finished_at']=None
    if status in ('CANCELLED','BLOCKED'):p['started_at']=None
    if status!='SUCCESS':p['output_manifest']=make_manifest('empty-output',[])
    assert ModuleRun.from_payload(p).status==status


@pytest.mark.parametrize('change',[
    {'status':'SUCCESS','started_at':None}, {'status':'SUCCESS','finished_at':None},
    {'status':'RUNNING'}, {'status':'RUNNING','started_at':None,'finished_at':None},
    {'status':'QUEUED'}, {'status':'FAILED','finished_at':None},
    {'started_at':'2026-11-01T01:59:59Z'}, {'finished_at':'2026-11-01T02:00:00Z'},
    {'created_at':None}, {'created_at':'2026-11-01T02:00:00'},
    {'started_at':'2026-11-01'}, {'action':'buy'}, {'status':'PASS'},
    {'module_id':'S1'}, {'run_type':'AUTO'}, {'code_commit':'unknown'},
    {'model_version':None}, {'rule_version':''}, {'parent_run_ids':['native-task-1','native-task-1']},
    {'parent_run_ids':['validation-new-1']}, {'source_refs':['unbound-source']},
    {'artifact_refs':{}}, {'unexpected':True},
])
def test_invalid_envelopes(change):
    p=payload();p.update(change)
    with pytest.raises(ValueError):ModuleRun.from_payload(p)


@pytest.mark.parametrize('value',[float('nan'),float('inf'),float('-inf'),{1:'bad'},(1,2)])
def test_non_json_anywhere_rejected(value):
    p=payload();p['metrics']['bad']=value
    with pytest.raises(ValueError):ModuleRun.from_payload(p)


def test_no_false_success_and_explicit_assurance():
    for update in ({'assurance':'APPROVED'},{'success':False},{'errors':['failed']},
                   {'source_ref_validation':'VERIFIED_BY_DOMAIN'}):
        p=payload();p['metrics'].update(update)
        with pytest.raises(ValueError):ModuleRun.from_payload(p)
    p=payload();p['output_manifest']=make_manifest('empty',[])
    with pytest.raises(ValueError):ModuleRun.from_payload(p)


def test_manifest_digest_binds_exact_body_and_inline_payload():
    b=binding();m=make_manifest('test',[b])
    assert m['sha256']==canonical_sha256({'schema_id':'test','items':[b]})
    b['payload']['observed'].append(4)
    assert len(m['items'][0]['payload']['observed'])==2
    with pytest.raises(ValueError):make_manifest('test',[b])
    p=payload();p['input_manifest']['schema_id']='tampered'
    with pytest.raises(ValueError):ModuleRun.from_payload(p)


@pytest.mark.parametrize('change',[
    {'path':'runtime/a.json'}, {'artifact_id':'x'}, {'payload':[]}, {'sha256':'0'*64},
    {'hash_basis':'RAW_BYTES'}, {'role':''}, {'schema_id':''}, {'extra':'x'},
])
def test_invalid_inline_binding(change):
    b=binding();b.update(change)
    with pytest.raises(ValueError):make_manifest('test',[b])


@pytest.mark.parametrize('path',['../x','/x','C:/x','a/../b','a//b','a/./b','a\\b','a:stream','a./b','a /b','a\x00b'])
def test_project_relative_paths(path):
    with pytest.raises(ValueError):
        make_manifest('test',[{'role':'source','schema_id':'pdf-v1','path':path,'sha256':'a'*64}])


def test_external_hashes_are_bindings_not_io_validation(monkeypatch):
    def forbidden(*a,**k):raise AssertionError('No filesystem/network resolution in domain')
    import builtins,socket
    monkeypatch.setattr(builtins,'open',forbidden)
    monkeypatch.setattr(socket,'socket',forbidden)
    items=[{'role':'source','schema_id':'pdf-v1','path':'runtime/not-present.pdf','sha256':'a'*64,'hash_basis':'RAW_BYTES'},
           {'role':'artifact','schema_id':'artifact-v1','artifact_id':'id-1','sha256':'b'*64,'hash_basis':'CANONICAL_JSON'}]
    p=payload();p['source_refs']=items;p['input_manifest']=make_manifest('inputs',items)
    assert ModuleRun.from_payload(p).source_refs==items


def test_schema_factories_fresh_and_required_contract():
    s=module_run_schema();assert set(s['required'])==set(FIELDS)
    assert len(s['properties']['module_id']['enum'])==11
    s['properties']['module_id']['enum'].clear()
    assert len(module_run_schema()['properties']['module_id']['enum'])==11
    assert input_schema()==output_schema()
    assert ModuleAdapter._is_protocol


def test_historical_unknown_times_do_not_require_fabrication():
    run=ModuleRun.from_payload(payload())
    assert run.metrics['native_started_at'] is None
    assert run.parent_run_ids==['native-task-1']
    assert run.run_id!='native-task-1'


def test_domain_imports_stdlib_only():
    import value_investment_agent.domain.research.module_run_v1 as mod
    tree=ast.parse(Path(mod.__file__).read_text(encoding='utf-8-sig'))
    imports={n.module.split('.')[0] for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)}
    imports.update(a.name.split('.')[0] for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names)
    assert imports <= {'__future__','dataclasses','datetime','hashlib','json','math','re','typing'}


def test_partial_is_not_skipped_and_errors_prevent_success():
    assert 'PARTIAL' in STATUSES and 'SKIPPED' not in STATUSES
    p=payload();p['status']='PARTIAL';p['errors']=[{'code':'SOURCE_MISSING'}]
    assert ModuleRun.from_payload(p).status=='PARTIAL'
    p['status']='SUCCESS'
    with pytest.raises(ValueError):ModuleRun.from_payload(p)
    for field in ('stage_events','warnings','errors'):
        p=payload();p[field]={}
        with pytest.raises(ValueError):ModuleRun.from_payload(p)
    p=payload();p['status']='SKIPPED'
    with pytest.raises(ValueError):ModuleRun.from_payload(p)


@pytest.mark.parametrize('field',['symbol','stage_events','warnings','errors'])
def test_required_fields_roundtrip_and_detach(field):
    p=payload()
    if field!='symbol':p[field]=[{'message':'TEST_ONLY', 'details':{'historical_at':None}}]
    if field=='errors':p['status']='PARTIAL'
    run=ModuleRun.from_payload(p)
    assert run.as_dict()[field]==p[field]
    if field!='symbol':
        run.as_dict()[field][0]['details']['historical_at']='changed'
        assert run.as_dict()[field][0]['details']['historical_at'] is None


def test_json_schema_lifecycle_conditions_present():
    schema=module_run_schema()
    assert len(schema['allOf'])==5
    assert schema['properties']['symbol']['pattern']=='^[0-9]{6}$'
    assert 'PARTIAL' in schema['properties']['status']['enum']
    assert 'SKIPPED' not in schema['properties']['status']['enum']


@pytest.mark.parametrize('module',['A','B'])
def test_explicit_null_batch_symbol_roundtrip(module):
    p=payload();p.update(module_id=module,symbol=None)
    run=ModuleRunCodec.from_payload(p,dependencies={})
    assert run.symbol is None
    assert ModuleRunCodec.to_payload(run)['symbol'] is None
    assert module_run_schema()['properties']['symbol']['type']==['string','null']


@pytest.mark.parametrize('symbol',['ALL','BATCH','', '000568.SZ','00568','0005680',568,False,[],{},' 000568','０００５６８'])
def test_invalid_symbol_scope_rejected(symbol):
    p=payload();p['symbol']=symbol
    with pytest.raises(ValueError):ModuleRun.from_payload(p)
