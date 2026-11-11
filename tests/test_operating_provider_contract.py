"""TEST_ONLY transport: bounded operating responses, never network or real keys."""
import json

import pytest

from value_investment_agent.infrastructure.agent_runtime import provider as mod


def provider(**kwargs):
    return mod.OpenAICompatibleChatProvider(endpoint='https://example.invalid/v1/chat/completions',
        model_id='TEST_ONLY',api_key_env='VALUE_AGENT_TEST_ONLY',**kwargs)


def request(tokens=512):
    return mod.LLMRequest('TEST_ONLY','TEST_ONLY system','TEST_ONLY user',{'type':'object'},tokens)


@pytest.fixture
def transport(monkeypatch):
    payload=dict(model='TEST_ONLY',choices=[dict(finish_reason='stop',message=dict(content='{}'))],
        usage=dict(prompt_tokens=20,completion_tokens=10))
    calls=[]
    class Reply:
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def read(self,limit):
            calls.append(('read',limit))
            return json.dumps(payload).encode()[:limit]
    class Opener:
        def open(self,req,timeout):
            calls.append(('open',json.loads(req.data)))
            return Reply()
    monkeypatch.setenv('VALUE_AGENT_TEST_ONLY','TEST_ONLY_NOT_A_KEY')
    monkeypatch.setattr(mod,'build_opener',lambda *_:Opener())
    return payload,calls


def test_default_caps_remain_legacy_and_explicit_operating_caps_work(transport):
    payload,calls=transport
    legacy=provider()
    assert legacy.complete(request()).completion_tokens==10
    assert calls[-1]==('read',65537)
    with pytest.raises(ValueError,match='completion budget'):
        legacy.complete(request(513))
    payload['choices'][0]['message']['content']='x'*70000
    with pytest.raises(ValueError,match='size limit'):legacy.complete(request())
    payload['usage']['completion_tokens']=8192
    expanded=provider(max_completion_tokens_cap=8192,response_size_cap=262144)
    result=expanded.complete(request(8192))
    assert result.completion_tokens==8192 and len(result.text)==70000
    assert calls[-1]==('read',262145)
    assert calls[-2][1]['max_completion_tokens']==8192
    assert calls[-2][1]['store'] is False and 'tools' not in calls[-2][1]


@pytest.mark.parametrize('field,values',[
    ('max_completion_tokens_cap',[0,-1,8193,True,512.0,'8192',None]),
    ('response_size_cap',[0,-1,262145,True,65536.0,'262144',None])])
def test_invalid_constructor_caps_rejected(field,values):
    for value in values:
        with pytest.raises(ValueError):provider(**{field:value})


@pytest.mark.parametrize('tokens',[0,-1,True,512.0,'512',8193])
def test_invalid_request_budget_rejected_before_transport(transport,tokens):
    _,calls=transport
    with pytest.raises(ValueError,match='completion budget'):provider().complete(request(tokens))
    assert calls==[]


@pytest.mark.parametrize('reason',['length','content_filter','refusal','tool_calls','function_call','unknown'])
def test_incomplete_or_refused_finish_rejected(transport,reason):
    payload,_=transport
    payload['choices'][0]['finish_reason']=reason
    with pytest.raises(ValueError,match='incomplete'):provider().complete(request())


@pytest.mark.parametrize('missing',[True,False])
def test_old_missing_finish_reason_and_stop_compatible(transport,missing):
    payload,_=transport
    if missing:payload['choices'][0].pop('finish_reason')
    assert provider().complete(request()).text=='{}'


@pytest.mark.parametrize('field,value',[('prompt_tokens',-1),('prompt_tokens',True),
    ('completion_tokens',-1),('completion_tokens',True),('completion_tokens',513),
    ('completion_tokens',10.0),('prompt_tokens','20')])
def test_illegal_usage_rejected(transport,field,value):
    payload,_=transport
    payload['usage'][field]=value
    with pytest.raises(ValueError,match='usage'):provider().complete(request())


@pytest.mark.parametrize('usage',[None,{},[],{'prompt_tokens':20},{'completion_tokens':10},'TEST_ONLY'])
def test_usage_required(transport,usage):
    payload,_=transport
    payload['usage']=usage
    with pytest.raises(ValueError,match='usage'):provider().complete(request())


@pytest.mark.parametrize('field,value',[('tool_calls',[{'id':'TEST_ONLY'}]),
    ('function_call',{'name':'TEST_ONLY'}),('refusal','TEST_ONLY refusal')])
def test_tool_calls_and_message_refusals_rejected(transport,field,value):
    payload,_=transport
    payload['choices'][0]['message'][field]=value
    with pytest.raises(ValueError):provider().complete(request())


def test_explicit_response_cap_still_enforced(transport):
    payload,_=transport
    payload['choices'][0]['message']['content']='x'*262144
    with pytest.raises(ValueError,match='size limit'):
        provider(response_size_cap=262144).complete(request())


@pytest.mark.parametrize('mode,thinking',[('json_schema',None),('json_object',None),('json_object','disabled')])
def test_explicit_json_object_and_disabled_thinking_no_fallback(transport,mode,thinking):
    _,calls=transport
    result=provider(response_format_mode=mode,thinking_mode=thinking).complete(request())
    body=calls[0][1]
    assert result.text=='{}' and sum(row[0]=='open' for row in calls)==1
    assert body['response_format']['type']==mode
    if mode=='json_object':
        assert body['response_format']=={'type':'json_object'}
        assert body['max_tokens']==512 and 'max_completion_tokens' not in body
    else:
        assert body['max_completion_tokens']==512 and 'max_tokens' not in body
        assert body['response_format']['json_schema']['strict'] is True
    if thinking is None:assert 'thinking' not in body
    else:assert body['thinking']=={'type':'disabled'}


@pytest.mark.parametrize('kwargs',[
    {'response_format_mode':'text'},{'response_format_mode':None},
    {'response_format_mode':True},{'response_format_mode':{}},
    {'thinking_mode':'enabled'},{'thinking_mode':'auto'},{'thinking_mode':False},
])
def test_invalid_response_and_thinking_modes_before_transport(transport,kwargs):
    _,calls=transport
    with pytest.raises(ValueError):provider(**kwargs)
    assert calls==[]


def test_default_transport_still_strict_schema_without_thinking(transport):
    _,calls=transport
    provider().complete(request())
    assert calls[0][1]['response_format']['type']=='json_schema'
    assert calls[0][1]['response_format']['json_schema']['strict'] is True
    assert 'thinking' not in calls[0][1]


@pytest.mark.parametrize('options',[
    {},{'response_format_mode':'json_object'},
    {'response_format_mode':'json_object','thinking_mode':'disabled'},
])
def test_service_optional_modes_validate_and_reach_runtime_provider(tmp_path,transport,options):
    from value_investment_agent.application.research.agent_review import operating_task_v2 as service
    cfg=dict(endpoint='https://example.invalid/v1/chat/completions',model_id='TEST_ONLY',
        api_key_env='VALUE_AGENT_TEST_ONLY',timeout_seconds=1,max_completion_tokens_cap=512,
        max_run_cost='0.1',input_cost_per_million='1',output_cost_per_million='2',
        authorized=True,authorization_reference='TEST_ONLY',currency='CNY',daily_cost_limit='1',**options)
    path=tmp_path/service.CONFIG
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(cfg),encoding='utf-8')
    assert service.model_configuration(tmp_path)==cfg
    adapter=service.LiveOperatingTaskService(tmp_path)._provider({'config':cfg})
    adapter.complete(request())
    _,calls=transport
    body=calls[0][1]
    assert body['response_format']['type']==options.get('response_format_mode','json_schema')
    assert body.get('thinking')==({'type':'disabled'} if options.get('thinking_mode') else None)
    assert sum(row[0]=='open' for row in calls)==1
    for invalid in ({'response_format_mode':'text'},{'thinking_mode':'enabled'},{'unexpected':'TEST_ONLY'}):
        path.write_text(json.dumps({**cfg,**invalid}),encoding='utf-8')
        with pytest.raises((ValueError,PermissionError)):service.model_configuration(tmp_path)
    assert sum(row[0]=='open' for row in calls)==1


def test_json_object_carries_exact_trusted_schema_within_existing_prompt_reserve(transport):
    from value_investment_agent.application.research.agent_review.operating_task_v2 import _bytes
    schema={'type':'object','additionalProperties':False,'required':['TEST_ONLY'],
        'properties':{'TEST_ONLY':{'type':'string','description':'公司来源原文'}}}
    req=mod.LLMRequest('TEST_ONLY','TEST_ONLY system JSON','TEST_ONLY user data',schema,1024)
    provider(response_format_mode='json_object',thinking_mode='disabled',
        max_completion_tokens_cap=1024).complete(req)
    _,calls=transport
    body=calls[0][1]
    system,user=body['messages']
    assert system['content']==req.system
    assert user['content'].startswith(req.user+'\n\nTRUSTED OUTPUT SCHEMA:')
    assert 'strictly conforming' in user['content']
    assert json.loads(user['content'].split('\n')[-1])==schema
    assert body['max_tokens']==1024 and 'max_completion_tokens' not in body
    assert body['thinking']=={'type':'disabled'}
    assert len(json.dumps(body,ensure_ascii=False).encode())<=len(_bytes(req.__dict__))+4096
    assert req.user=='TEST_ONLY user data' and req.output_schema==schema
    assert sum(row[0]=='open' for row in calls)==1


def test_old_schema_mode_does_not_change_messages_or_token_key(transport):
    req=request()
    provider().complete(req)
    _,calls=transport
    body=calls[0][1]
    assert body['messages']==[{'role':'system','content':req.system},{'role':'user','content':req.user}]
    assert body['max_completion_tokens']==req.max_completion_tokens and 'max_tokens' not in body
