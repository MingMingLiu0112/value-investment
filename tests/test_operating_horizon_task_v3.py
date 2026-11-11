"""One-shot JSON repair tests; synthetic providers only, never network."""
from dataclasses import replace
import json
from types import SimpleNamespace

import pytest

from test_operating_horizon_task_v2 import env, source_env, context, NOW
from value_investment_agent.application.research.agent_review import operating_horizon_task_v3 as mod
from value_investment_agent.infrastructure.agent_runtime.provider import LLMResponse


@pytest.fixture
def repair(env, monkeypatch):
    monkeypatch.setattr(mod, '_now', lambda value=None: value or NOW)
    old = env.service()
    complete = old.test_provider.complete
    # Capture a single original call; do not count fixture rendering as a call.
    def malformed(req):
        response = complete(req)
        return replace(response, text=response.text + '}')
    old.test_provider = SimpleNamespace(complete=malformed)
    task = old.create(symbol='123456',request_key='TEST_ONLY_original',years=[2026],now=NOW)['task_id']
    out = old.run(task)
    assert out['persisted_status'] == 'FAILED' and out['response_binding']
    calls = []
    def fix(req):
        calls.append(req)
        return LLMResponse(req.user.rstrip()[:-1],100,50,'TEST_ONLY')
    provider = SimpleNamespace(complete=fix)
    def service():
        return mod.OperatingHorizonTaskService(env.root,test_provider=provider)
    return SimpleNamespace(env=env,old=old,source_task_id=task,original=out,
        calls=calls,provider=provider,service=service)


def create(repair, **kwargs):
    return repair.service().create(source_task_id=repair.source_task_id,
        request_key='TEST_ONLY_repair',now=NOW,**kwargs)['task_id']


def test_single_call_exact_semantics_original_unchanged_and_pending(repair):
    old_dir=repair.old._directory(repair.source_task_id)
    before={str(p):p.read_bytes() for p in old_dir.rglob('*.json')}
    task=create(repair)
    service=repair.service()
    result=service.run(task)
    assert result['status']=='SUCCEEDED',result
    assert len(repair.calls)==1
    assert result['semantic_preservation']=='VERIFIED'
    assert result['original_response_binding']==repair.original['response_binding']
    assert result['repair_requested_at']==NOW.isoformat()
    assert result['research_as_of']==repair.original['research_as_of']
    assert result['research_result']['quantification_status']=='CONDITIONAL_SENSITIVITY_NOT_EMPIRICALLY_PROVEN_BOUNDS'
    assert result['review_status']=='PENDING' and not result['d2_three_role_complete']
    assert not result['approval_changed'] and not result['valuation_produced']
    assert result['action']=='no_order' and not result['formal_eligibility']
    assert {str(p):p.read_bytes() for p in old_dir.rglob('*.json')}==before
    assert service.read(task)['research_result']==result['research_result']
    assert service.list_for_symbol('123456')[0]['task_id']==task
    assert service.resume(task)['status']=='SUCCEEDED'
    assert service.run(task)['status']=='SUCCEEDED' and len(repair.calls)==1
    with pytest.raises(ValueError,match='AUTHORIZATION_ALREADY_USED'):
        service.create(source_task_id=repair.source_task_id,request_key='TEST_ONLY_another',now=NOW)
    assert not (service.base/'budget').exists()
    head=service._budget_service.base/'budget/2026-11-05/current.json'
    records=service._bound(json.loads(head.read_bytes()))['records']
    assert len(records)==2 and all(r['status']=='SETTLED' for r in records.values())


@pytest.mark.parametrize('original',[
    'prefix {"x":1}}','```json\n{"x":1}}\n```','{"x":1} {"y":2}',
    '{"x":1}}}','{"x":1}','{"x":1} garbage','{"x":1,"x":2}}',
    '{"x":NaN}}','[1]}','{"x":1} } {"x":1}',
])
def test_ambiguous_or_not_exactly_one_extra_brace_rejected(original):
    with pytest.raises(ValueError):mod.verify_same_semantics(original,'{"x":1}')


@pytest.mark.parametrize('repaired',[
    '{"x":2,"s":"文本","a":[1,2]}',
    '{"x":true,"s":"文本","a":[1,2]}',
    '{"x":1,"s":"文本改","a":[1,2]}',
    '{"x":1,"s":"文本","a":[2,1]}',
    '{"x":1,"s":"文本","a":[1,2],"extra":null}',
    '{"x":1,"s":"文本","a":[1,2]}}',
    '{"x":1,"x":1,"s":"文本","a":[1,2]}',
])
def test_any_semantic_mutation_or_non_strict_json_rejected(repaired):
    with pytest.raises(ValueError):
        mod.verify_same_semantics('{"x":1,"s":"文本","a":[1,2]}}',repaired)


def test_comparison_preserves_large_numbers_and_allows_only_equivalent_json_spelling():
    mod.verify_same_semantics('{"n":123456789012345678901234567890,"s":"文本"}}',
        '{ "s":"\\u6587\\u672c", "n":123456789012345678901234567890.0 }')
    with pytest.raises(ValueError,match='SEMANTICS_CHANGED'):
        mod.verify_same_semantics('{"n":123456789012345678901234567890}}',
                                  '{"n":123456789012345678901234567891}')


def test_semantic_rewrite_fails_even_when_economic_schema_valid(repair):
    def rewrite(req):
        repair.calls.append(req)
        value=json.loads(req.user.rstrip()[:-1])
        value['years']['2026']['counter_evidence']='changed economic claim'
        return LLMResponse(json.dumps(value),100,50,'TEST_ONLY')
    repair.provider.complete=rewrite
    task=create(repair)
    result=repair.service().run(task)
    assert result['status']=='FAILED' and result['research_result'] is None
    assert result['response_binding'] and result['semantic_preservation']=='NOT_ADMITTED'
    assert repair.service().resume(task)['status']=='FAILED'
    assert repair.service().run(task)['status']=='FAILED' and len(repair.calls)==1


def test_timeout_retains_reservation_never_second_call(repair):
    def timeout(req):
        repair.calls.append(req)
        raise TimeoutError('SECRET_RAW_PROVIDER_DETAIL')
    repair.provider.complete=timeout
    task=create(repair)
    result=repair.service().run(task)
    assert result['status']=='FAILED' and result['reserved_cost']!='0'
    assert repair.service().resume(task)['status']=='FAILED'
    assert repair.service().run(task)['status']=='FAILED' and len(repair.calls)==1
    assert 'SECRET_RAW' not in json.dumps(result)


def test_settlement_failure_cannot_recover_success(repair,monkeypatch):
    task=create(repair); service=repair.service(); daily=service._daily_budget
    def fail(*args,**kwargs):
        if kwargs.get('settle'):raise ValueError('DAILY_BUDGET_CHAIN_INVALID')
        return daily(*args,**kwargs)
    monkeypatch.setattr(service,'_daily_budget',fail)
    assert service.run(task)['status']=='FAILED'
    assert repair.service().resume(task)['status']=='FAILED' and len(repair.calls)==1


def test_original_response_tamper_blocks_call(repair):
    task=create(repair)
    path=repair.env.root/repair.original['response_binding']['path']
    path.write_bytes(path.read_bytes()+b' ')
    assert repair.service().run(task)['status']=='FAILED' and not repair.calls


def test_repair_clock_distinct_from_research_cutoff(repair):
    from datetime import timedelta
    requested=NOW+timedelta(hours=2)
    result=repair.service().create(source_task_id=repair.source_task_id,
        request_key='TEST_ONLY_repair',now=requested)
    assert result['repair_requested_at']==requested.isoformat()
    assert result['research_as_of']==NOW.isoformat()


def test_v3_does_not_enter_frozen_implementation_map():
    assert mod.__name__ not in mod.v2.implementation()
    assert mod.__name__ in mod.implementation()



def test_identical_semantics_still_requires_original_v2_economic_validation(repair):
    old=repair.env.service()
    good=old.test_provider.complete
    def bad_anchor(req):
        response=good(req)
        value=json.loads(response.text)
        value['years']['2026']['operating_paths']['base']['drivers']['other_pretax_cny']['evidence_ids']=['test:revenue']
        return replace(response,text=json.dumps(value)+'}')
    old.test_provider=SimpleNamespace(complete=bad_anchor)
    source=old.create(symbol='123456',request_key='TEST_ONLY_bad_anchor',years=[2026],now=NOW)['task_id']
    assert old.run(source)['persisted_status']=='FAILED'
    task=repair.service().create(source_task_id=source,request_key='TEST_ONLY_repair',now=NOW)['task_id']
    result=repair.service().run(task)
    assert result['status']=='FAILED' and result['research_result'] is None
    assert result['response_binding'] and len(repair.calls)==1
    assert repair.service().resume(task)['status']=='FAILED' and len(repair.calls)==1
