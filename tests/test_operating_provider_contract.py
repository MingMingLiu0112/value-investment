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
