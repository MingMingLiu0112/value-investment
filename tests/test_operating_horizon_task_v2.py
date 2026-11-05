"""V2 dispatch/storage integration with frozen v1 runner, no paid calls."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from test_operating_horizon_sources_v1 import source_env, context, NOW
from test_operating_horizon_draft_v1 import payload
from value_investment_agent.application.research.agent_review import operating_horizon_task_v2 as mod
from value_investment_agent.infrastructure.agent_runtime.provider import LLMResponse


@pytest.fixture
def env(source_env,monkeypatch):
    root=source_env.root
    monkeypatch.setattr(mod,'_now',lambda value=None:value or NOW)
    monkeypatch.setattr(mod.v1,'_now',lambda value=None:value or NOW)
    cfg=dict(endpoint='https://test-only.invalid/v1/chat/completions',model_id='TEST_ONLY',
        api_key_env='VALUE_AGENT_TEST_ONLY_KEY',timeout_seconds=1,max_completion_tokens_cap=4096,
        max_run_cost='10',input_cost_per_million='1',output_cost_per_million='2',authorized=True,
        authorization_reference='TEST_ONLY',currency='CNY',daily_cost_limit='10')
    (root/mod.live.CONFIG).write_bytes(mod._bytes(cfg))
    calls=[]
    def complete(req):
        calls.append(req)
        response=payload([2026])
        for path in response['years']['2026']['operating_paths'].values():
            path['unit_cost_mechanism']='UNRESOLVED_SENSITIVITY'
            path['drivers']['other_pretax_cny']['evidence_ids']=['test:pre_tax_profit']
        return LLMResponse(json.dumps(response),100,50,'TEST_ONLY')
    provider=SimpleNamespace(complete=complete)
    def service():return mod.OperatingHorizonTaskService(root,test_provider=provider)
    return SimpleNamespace(root=root,source=source_env,calls=calls,service=service)


def create(env):
    return env.service().create(symbol='123456',request_key='TEST_ONLY_v2',years=[2026],now=NOW)['task_id']


def test_v2_result_draft_and_storage_isolation(env):
    old=mod.v1.implementation()
    task=create(env)
    service=env.service()
    spec,_,_=service._load(task)
    assert spec['task_contract']==mod.CONTRACT
    assert mod.draft.__name__ in spec['implementation_sha256']
    assert mod.sources.__name__ in spec['implementation_sha256']
    assert mod.__name__ in spec['implementation_sha256']
    result=service.run(task)
    assert result['status']=='SUCCEEDED',result
    assert result['research_result']['schema_version']=='operating-horizon-draft-v2'
    assert result['research_result']['years']['2026']['unit_cost_mechanisms']['base']=='UNRESOLVED_SENSITIVITY'
    assert 'unit_cost_mechanism' in env.calls[0].output_schema['properties']['years']['properties']['2026']['properties']['operating_paths']['properties']['base']['required']
    assert len(env.calls)==1 and not result['d2_three_role_complete']
    env.source.config.write_bytes(b'{}')
    assert env.service().read(task)['research_result']==result['research_result']
    assert env.service().list_for_symbol('123456')[0]['task_id']==task
    assert env.service().resume(task)['status']=='SUCCEEDED' and len(env.calls)==1
    assert not (env.root/'runtime/operating-horizon-task-v1').exists()
    assert not (service.base/'budget').exists()
    assert (service._budget_service.base/'budget/2026-11-05/current.json').is_file()
    assert mod.v1.implementation()==old
    assert mod.__name__ not in old and mod.draft.__name__ not in old
    with pytest.raises(FileNotFoundError):mod.v1.OperatingHorizonTaskService(env.root).read(task)


def test_v2_source_original_change_blocks_provider(env):
    task=create(env)
    env.source.original.write_bytes(b'changed')
    assert env.service().run(task)['status']=='FAILED'
    assert not env.calls


def test_v2_implementation_change_blocks_provider(env,monkeypatch):
    task=create(env)
    original=mod.implementation
    monkeypatch.setattr(mod,'implementation',lambda:{**original(),'TEST_ONLY':'changed'})
    assert env.service().run(task)['status']=='FAILED' and not env.calls


def test_v2_settlement_failure_cannot_resume_success(env,monkeypatch):
    task=create(env);service=env.service();daily=service._daily_budget
    def fail(*args,**kwargs):
        if kwargs.get('settle'):raise ValueError('DAILY_BUDGET_CHAIN_INVALID')
        return daily(*args,**kwargs)
    monkeypatch.setattr(service,'_daily_budget',fail)
    assert service.run(task)['status']=='FAILED'
    assert env.service().resume(task)['status']=='FAILED'
    assert env.service().run(task)['status']=='FAILED' and len(env.calls)==1
