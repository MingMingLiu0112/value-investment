"""TEST_ONLY temporary task stores; no real model, DB or private source data."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pytest

from test_llm_agent_research import _inputs, _replies
from value_investment_agent.application.research import module_run_projection_v1 as mod
from value_investment_agent.infrastructure.agent_runtime import provider

COMMIT = 'a' * 40


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def denied(*a, **kw):
        raise AssertionError('Projection must not call live provider/network')
    monkeypatch.setattr(provider.OpenAICompatibleChatProvider, 'complete', denied)
    monkeypatch.setattr(provider, 'build_opener', denied)
    monkeypatch.setattr(mod, '_current_commit', lambda root: COMMIT)


@pytest.fixture
def task(tmp_path):
    workbench, digest, original = _inputs(tmp_path)
    service = mod.ResearchTaskService(tmp_path)
    args = dict(symbol='600519', workbench=workbench, workbench_sha256=digest,
                responses=_replies(), request_key='TEST_ONLY-projection')
    task_id = service.create(**args)['task_id']
    service.run(task_id)
    return service, task_id, args, original


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}


def data(service, task_id):
    projection = mod.ModuleRunProjectionService(service.root, service=service)
    verified, spec = projection._verified(task_id)
    now = datetime.now(timezone.utc)
    return mod.native_projection_data(native_summary=verified, module_id='D1',
        symbol=spec['symbol'], code_commit=COMMIT, started_at=now, finished_at=now,
        assurance='UNVERIFIED')


def test_real_saved_lifecycle_projection_new_identity_unknowns_and_no_write(task, monkeypatch):
    service, task_id, _, _ = task
    before = snapshot(service.root)
    def denied(*a, **kw):
        raise AssertionError('Projection must never execute, save, repair or call mock provider')
    monkeypatch.setattr(provider.MockLLMProvider, 'complete', denied)
    monkeypatch.setattr(service, '_save', denied)
    result = data(service, task_id)
    assert result['run_type'] == 'VALIDATE'
    assert result['run_id'].startswith('validation-' + task_id + '-' + service.read(task_id)['record_binding']['sha256'] + '-')
    assert result['run_id'] != task_id and result['code_commit'] == COMMIT
    assert result['metrics']['native_code_commit'] is None
    assert result['metrics']['native_started_at'] is None
    assert result['metrics']['native_finished_at'] is None
    assert result['metrics']['native_status'] == 'SUCCEEDED'
    assert result['metrics']['new_llm_calls'] == 0
    assert result['metrics']['derived_scope'] == 'SAVED_RESPONSE_NOT_NEW_LLM_RESEARCH'
    assert result['parent_run_ids'] == []
    assert result['metrics']['validation_of']['kind']=='NATIVE_RESEARCH_TASK'
    assert result['metrics']['validation_of']['task_id']==task_id
    assert result['metrics']['parent_relation'] == 'VALIDATION_OF_NATIVE_TASK'
    assert result['artifact_refs'][0]['role'] == 'WHOLE_PACKET'
    assert result['metrics']['formal_eligibility'] is False and result['action'] == 'no_order'
    assert snapshot(service.root) == before


def test_public_allowlist_strips_paths_payloads_and_free_text(task, monkeypatch):
    service, task_id, _, _ = task
    read = service.read
    def polluted(identifier):
        return dict(read(identifier), raw_response='PRIVATE_SECRET_MARKER',
                    endpoint='https://PRIVATE_SECRET_MARKER', config={'key':'PRIVATE_SECRET_MARKER'},
                    arbitrary_path='C:/PRIVATE_SECRET_MARKER/account.json')
    monkeypatch.setattr(service, 'read', polluted)
    result = data(service, task_id)
    serialized = json.dumps(result)
    for text in ('PRIVATE_SECRET_MARKER', 'raw_response', 'endpoint', 'workbench', 'path', 'responses'):
        assert text not in serialized


def test_source_change_never_keeps_current_success(task):
    service, task_id, _, original = task
    original.write_bytes(b'TEST_ONLY changed original')
    result = data(service, task_id)
    assert result['status'] == 'FAILED'
    assert result['metrics']['native_status'] == 'SUCCEEDED'
    assert result['metrics']['native_current_status'] == 'FAILED'
    assert result['artifact_refs'] == []


@pytest.mark.parametrize('damage', ['input', 'version', 'head', 'missing_head'])
def test_corrupt_native_binding_refuses_projection_without_repair(task, damage):
    service, task_id, _, _ = task
    directory = service._directory(task_id)
    if damage == 'input':
        (directory/'input.json').write_bytes(b'{}')
    elif damage == 'version':
        next((directory/'versions').glob('*.json')).write_bytes(b'{}')
    elif damage == 'head':
        (directory/'current.json').write_bytes(b'{}')
    else:
        (directory/'current.json').unlink()
    before = snapshot(service.root)
    with pytest.raises((ValueError, OSError, KeyError)):
        data(service, task_id)
    assert snapshot(service.root) == before


def test_mismatched_view_binding_refused(task, monkeypatch):
    service, task_id, _, _ = task
    read = service.read
    monkeypatch.setattr(service, 'read', lambda identifier: dict(read(identifier),
        record_binding={'path':'runtime/other.json', 'sha256':'0'*64}))
    with pytest.raises(ValueError, match='HEAD_CHANGED'):
        data(service, task_id)


def test_history_uses_existing_discovery_and_new_service_reads_same_tasks(task):
    service, task_id, _, _ = task
    projection = mod.ModuleRunProjectionService(service.root)
    results = projection.history('600519')
    assert len(results) == 1
    assert results[0]['metrics']['native_task_id'] == task_id
    assert projection.history('600887') == []
    diff = projection.diff(task_id, task_id)
    assert diff['changes'] == [] and diff['economic_comparability'] == 'NOT_ASSESSED_METADATA_ONLY'


def test_history_does_not_hide_discovery_limit_or_corruption(task, monkeypatch):
    service, _, _, _ = task
    def limited(symbol):
        raise ValueError('RESEARCH_TASK_DISCOVERY_LIMIT_EXCEEDED')
    monkeypatch.setattr(service, 'list_for_symbol', limited)
    with pytest.raises(ValueError, match='LIMIT_EXCEEDED'):
        mod.ModuleRunProjectionService(service.root, service=service).history('600519')


def test_diff_reports_only_metadata_changes_and_rejects_cross_symbol(task):
    service, first, args, _ = task
    second = service.create(**dict(args, request_key='TEST_ONLY-projection-two'))['task_id']
    projection = mod.ModuleRunProjectionService(service.root, service=service)
    result = projection.diff(first, second)
    assert {x['field'] for x in result['changes']} >= {'input_manifest', 'output_manifest'}
    third = service.create(**dict(args, request_key='TEST_ONLY-other-symbol', symbol='600887'))['task_id']
    with pytest.raises((ValueError, OSError)):
        projection.diff(first, third)


def test_builder_rejects_rawdict_unverified_even_with_succeeded_status(tmp_path):
    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError, match='VERIFIED_NATIVE_REQUIRED'):
        mod.build_validation_run(native_summary={'status':'SUCCEEDED'}, module_id='D1',
            symbol='600519', code_commit=COMMIT, started_at=now, finished_at=now,
            assurance='UNVERIFIED')


def test_verified_input_cannot_be_swapped_after_validation(task):
    service, task_id, _, _ = task
    projection = mod.ModuleRunProjectionService(service.root, service=service)
    native, _ = projection._verified(task_id)
    (service._directory(task_id)/'input.json').write_bytes(b'{}')
    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError, match='HASH_MISMATCH'):
        mod.native_projection_data(native_summary=native,module_id='D1',symbol='600519',
            code_commit=COMMIT,started_at=now,finished_at=now,assurance='UNVERIFIED')


def test_builder_checks_commit_time_and_validated_manifest(task):
    service, task_id, _, _ = task
    native, _ = mod.ModuleRunProjectionService(service.root, service=service)._verified(task_id)
    now = datetime.now(timezone.utc)
    args = dict(native_summary=native,module_id='D1',symbol='600519',
        code_commit=COMMIT,started_at=now,finished_at=now,assurance='UNVERIFIED')
    for change, reason in [({'code_commit':'b'*40}, 'COMMIT_MISMATCH'),
                           ({'symbol':'600887'}, 'SYMBOL_MISMATCH'),
                           ({'started_at':datetime(2026,1,1)}, 'AWARE_CLOCK'),
                           ({'input_refs':[]}, 'MANIFEST_CHANGED')]:
        with pytest.raises(ValueError, match=reason):
            mod.native_projection_data(**dict(args, **change))


def test_head_change_after_native_validation_refuses_current_projection(task):
    service, task_id, _, _ = task
    native, _ = mod.ModuleRunProjectionService(service.root,service=service)._verified(task_id)
    (service._directory(task_id)/'current.json').write_bytes(b'{}')
    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError,match='HASH_MISMATCH'):
        mod.native_projection_data(native_summary=native,module_id='D1',symbol='600519',
            code_commit=COMMIT,started_at=now,finished_at=now,assurance='UNVERIFIED')


def test_testonly_live_scope_preserved_and_no_live_research_claim(env):
    service = env.service()
    task_id = service.create(symbol='123456',request_key='TEST_ONLY_projection')['task_id']
    service.run(task_id)
    before = snapshot(env.root)
    projection = mod.ModuleRunProjectionService(env.root,backend='live',service=service)
    result = projection.get(task_id)
    assert result['metrics']['derived_scope'] == 'TEST_ONLY_LIVE_CONTRACT_NOT_REAL_RESEARCH'
    assert result['metrics']['new_llm_calls'] == 0
    assert result['metrics']['native_status'] == 'SUCCEEDED'
    assert {x['role'] for x in result['artifact_refs']} == {'FUNDAMENTAL','COUNTER_EVIDENCE','EVENT'}
    assert snapshot(env.root) == before


def test_non_task_source_only_adapter_explicitly_not_supported(tmp_path):
    source=tmp_path/'TEST_ONLY.json';source.write_bytes(b'{}')
    binding=dict(path=source.name,sha256=hashlib.sha256(source.read_bytes()).hexdigest())
    with pytest.raises(ValueError,match='NATIVE_TASK_ID_INVALID'):
        mod.verify_native_projection(root=tmp_path,input_refs=[binding],native_validator=lambda:dict(
            native_task_id='source-only-fixture',status='SUCCEEDED',symbol='600519',execution_mode='SOURCE_ONLY'))


# Import the existing TEST_ONLY live fixture, not real provider configuration.
from test_operating_task_v2 import env  # noqa: E402,F401


def test_full_shared_contract_schema_and_detached_export(task):
    from value_investment_agent.domain.research.module_run_v1 import ModuleRun, FIELDS, module_run_schema, make_manifest
    import jsonschema
    service,task_id,_,_ = task
    result = mod.ModuleRunProjectionService(service.root,service=service).get(task_id)
    assert set(result) == set(FIELDS)
    assert result['schema_version']=='module-run-v1' and result['status']=='SUCCESS'
    jsonschema.Draft202012Validator(module_run_schema()).validate(result)
    value=ModuleRun.from_payload(result)
    assert value.as_dict()==result
    exported=value.as_dict();exported['metrics']['native_status']='FORGED'
    assert value.as_dict()['metrics']['native_status']=='SUCCEEDED'
    for key in ('input_manifest','output_manifest'):
        manifest=result[key]
        assert manifest==make_manifest(manifest['schema_id'],manifest['items'])
    assert result['created_at']==result['started_at']
    assert result['model_version']=='NOT_APPLICABLE_METADATA_VALIDATION'
    assert result['metrics']['native_model_version'] is None
    assert result['metrics']['code_commit_basis']=='CURRENT_CHECKOUT_HEAD_NOT_NATIVE_EXECUTION'
    assert 'native_projection' not in result and 'NOT_CONVERTED' not in json.dumps(result)


def test_shared_new_symbol_events_warnings_errors_fields(task):
    service,task_id,_,original=task
    projection=mod.ModuleRunProjectionService(service.root,service=service)
    value=projection.get(task_id)
    assert value['symbol']=='600519'
    assert value['stage_events']==[
        {'event':'VALIDATION_STARTED','at':value['started_at']},
        {'event':'VALIDATION_FINISHED','at':value['finished_at']}]
    assert value['warnings']==['HISTORICAL_CODE_AND_EXECUTION_TIMES_NOT_RECONSTRUCTED']
    assert value['errors']==[] and value['metrics']['native_started_at'] is None
    original.write_bytes(b'TEST_ONLY source invalid')
    failed=projection.get(task_id)
    assert failed['status']=='FAILED' and failed['errors']==['NATIVE_VALIDATION_NOT_PASSED']
    assert failed['metrics']['native_status']=='SUCCEEDED'


def test_each_validation_unique_identity_with_stable_native_output_hash(task):
    service,task_id,_,_=task
    projection=mod.ModuleRunProjectionService(service.root,service=service)
    a=projection.get(task_id);b=projection.get(task_id)
    assert a['run_id']!=b['run_id']
    assert a['metrics']['native_summary_sha256']==b['metrics']['native_summary_sha256']
    assert a['input_manifest']==b['input_manifest'] and a['output_manifest']==b['output_manifest']
    assert a['parent_run_ids']==b['parent_run_ids']==[]
    assert a['metrics']['validation_of']==b['metrics']['validation_of']


@pytest.mark.parametrize('native_status',['FAILED','WAITING_EVIDENCE'])
def test_verified_metadata_does_not_upgrade_native_execution(task,native_status):
    service,task_id,_,_=task
    directory=service._directory(task_id)
    spec,state,pin=service._load(task_id)
    service._save(spec,state,pin,datetime.now(timezone.utc),status=native_status,
                  error_code='TEST_ONLY_PRIOR_EXECUTION_NOT_SUCCEEDED')
    before=snapshot(service.root)
    value=mod.ModuleRunProjectionService(service.root,service=service,module_id='G2').get(task_id)
    assert value['status']=='SUCCESS' and value['run_type']=='VALIDATE'
    assert value['metrics']['native_status']==value['metrics']['native_current_status']==native_status
    assert value['metrics']['native_execution_succeeded'] is False
    assert value['metrics']['assurance_scope']=='METADATA_ONLY_NOT_EXECUTION_APPROVAL'
    assert value['metrics']['success_semantics']=='NATIVE_METADATA_PROVENANCE_VALIDATION_ONLY'
    assert value['metrics']['formal_eligibility'] is False
    assert 'NATIVE_EXECUTION_NOT_SUCCEEDED' in value['warnings']
    assert snapshot(service.root)==before


@pytest.mark.parametrize('module_id',['A','B','C','F1'])
def test_projection_does_not_claim_generic_module_support(task,module_id):
    service,task_id,_,_=task
    with pytest.raises(ValueError,match='MODULE_ID_INVALID'):
        mod.ModuleRunProjectionService(service.root,service=service,module_id=module_id)


def test_caller_refs_summary_and_guards_are_deep_frozen(task):
    service,task_id,_,_=task
    directory=service._directory(task_id)
    inputs=[service._binding(directory/'input.json'),service.read(task_id)['record_binding']]
    spec=json.loads((directory/'input.json').read_bytes())
    sources=[spec['workbench']]
    original_input=inputs[-1]['sha256'];original_source=sources[0]['sha256']
    def validator():
        return dict(service.read(task_id),native_validation_passed=True)
    native=mod.verify_native_projection(root=service.root,native_validator=validator,
        input_refs=inputs,source_refs=sources)
    inputs[-1]['sha256']='0'*64;sources[0]['sha256']='0'*64
    native.input_refs[-1]['sha256']='0'*64
    native.summary['native_status']='FORGED'
    assert native.input_refs[-1]['sha256']==original_input
    assert native.source_refs[0]['sha256']==original_source
    assert native.summary['native_status']=='SUCCEEDED'
    assert all(type(ref) is bytes and type(raw) is bytes for ref,raw in native.guards)
    now=datetime.now(timezone.utc)
    args=dict(native_summary=native,module_id='D1',symbol='600519',code_commit=COMMIT,
        started_at=now,finished_at=now,assurance='UNVERIFIED')
    with pytest.raises(ValueError,match='MANIFEST_CHANGED'):
        mod.build_validation_run(**args,input_refs=inputs,source_refs=sources)
    value=mod.build_validation_run(**args)
    assert value['metrics']['native_record_sha256']==original_input
    assert value['source_refs'][0]['payload']['native_sha256']==original_source


def test_raw_original_change_after_proof_reenters_native_validator(task):
    service,task_id,_,original=task
    native,_=mod.ModuleRunProjectionService(service.root,service=service)._verified(task_id)
    original.write_bytes(b'TEST_ONLY raw original changed AFTER proof, workbench unchanged')
    now=datetime.now(timezone.utc)
    with pytest.raises(ValueError,match='NATIVE_VALIDATION_CHANGED'):
        mod.build_validation_run(native_summary=native,module_id='D1',symbol='600519',code_commit=COMMIT,
            started_at=now,finished_at=now,assurance='UNVERIFIED')


def test_cost_metadata_preserves_explicit_native_basis_and_labels_unknown(env,monkeypatch):
    service=env.service()
    task_id=service.create(symbol='123456',request_key='TEST_ONLY_cost_projection')['task_id']
    service.run(task_id)
    projection=mod.ModuleRunProjectionService(env.root,backend='live',service=service)
    value=projection.get(task_id)
    assert value['metrics']['usage_basis']=='CONFIGURED_RATE_ESTIMATE_NOT_PROVIDER_BILL'
    assert value['metrics']['cost_basis']=='CONFIGURED_RATE_ESTIMATE_NOT_PROVIDER_BILL'
    assert 'settled_cost' in value['metrics']
    read=service.read
    monkeypatch.setattr(service,'read',lambda identifier:dict(read(identifier),usage_basis='UNKNOWN'))
    unknown=projection.get(task_id)
    assert unknown['metrics']['cost_basis']=='UNKNOWN_NOT_PROVIDER_BILL'
    assert unknown['metrics']['settled_cost']==value['metrics']['settled_cost']
    assert 'usage_basis' not in unknown['metrics']
    def no_basis(identifier):
        item=dict(read(identifier));item.pop('usage_basis',None)
        return item
    monkeypatch.setattr(service,'read',no_basis)
    missing=projection.get(task_id)
    assert missing['metrics']['cost_basis']=='UNKNOWN_NOT_PROVIDER_BILL'
    assert missing['metrics']['settled_cost']==value['metrics']['settled_cost']
