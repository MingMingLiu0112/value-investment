"""TEST_ONLY service transport fixtures; never evidence of a real LIVE model run."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from web_api.test_held_continuity_api import client_for,unlock
from test_web_agent_research import state
from value_investment_agent.presentation.web_api import live_operating_research_routes as routes
from value_investment_agent.infrastructure.agent_runtime import provider

BASE='/api/v1/operating-research'
LIVE='LIVE_LLM_OPERATING_RESEARCH_NOT_ADMITTED'


@pytest.fixture
def api(tmp_path,monkeypatch):
    data=SimpleNamespace(calls=[],rows=[],failure=None,provider_calls=[],views={})
    def no_provider(*args,**kwargs):
        data.provider_calls.append(True)
        raise AssertionError('TEST_ONLY API must never call a provider or network')
    monkeypatch.setattr(provider.OpenAICompatibleChatProvider,'complete',no_provider)
    monkeypatch.setattr(provider,'build_opener',no_provider)
    class TestOnlyService:
        def __init__(self,root):self.root=root
        def create(self,**kwargs):
            data.calls.append(('create',kwargs))
            if data.failure:raise data.failure
            if 'create' in data.views:return data.views['create']
            return dict(task_id='TEST_ONLY-task',symbol=kwargs['symbol'],status='QUEUED',
                action='no_order',formal_eligibility=False,scope='TEST_ONLY_LIVE_CONTRACT')
        def run(self,task_id):data.calls.append(('run',task_id))
        def list_for_symbol(self,symbol):
            data.calls.append(('list',symbol))
            if data.failure:raise data.failure
            return deepcopy(data.rows)
        def read(self,task_id):
            data.calls.append(('read',task_id))
            if data.failure:raise data.failure
            if 'read' in data.views:return data.views['read']
            return dict(task_id=task_id,status='WAITING_EVIDENCE',action='no_order',formal_eligibility=False)
        def cancel(self,task_id):
            data.calls.append(('cancel',task_id))
            if 'cancel' in data.views:return data.views['cancel']
            return dict(task_id=task_id,status='CANCELLED',action='no_order')
        def resume(self,task_id):
            data.calls.append(('resume',task_id))
            if 'resume' in data.views:return data.views['resume']
            return dict(task_id=task_id,status='QUEUED',action='no_order')
    monkeypatch.setattr(routes,'LiveOperatingTaskService',TestOnlyService)
    client,secret=client_for(tmp_path,tmp_path/'TEST_ONLY-journal.jsonl',monkeypatch)
    return client,secret,data,tmp_path


def test_unauthorized_post_never_creates_or_calls_provider(api):
    client,_,data,root=api
    before=state(root)
    for path in ('/tasks','/tasks/TEST_ONLY-task/resume','/tasks/TEST_ONLY-task/cancel'):
        response=client.post(BASE+path,json=dict(symbol='600519',request_key='TEST_ONLY-key'))
        assert response.status_code==401,response.text
        assert response.json()['action']=='no_order'
    assert data.calls==[] and data.provider_calls==[] and state(root)==before


def test_public_get_and_model_status_no_account_no_network_no_writes(api):
    client,_,data,root=api
    before=state(root)
    response=client.get(BASE+'/model-status')
    assert response.status_code==200 and response.headers['cache-control']=='no-store'
    body=response.json()
    assert body['status']=='MODEL_AUTHORIZATION_REQUIRED'
    assert body['real_calls_started'] is False and body['credential_present'] is False
    assert body['action']=='no_order'
    result=client.get(BASE+'/companies/600519')
    assert result.status_code==200 and result.headers['cache-control']=='no-store'
    assert result.json()['status']=='NOT_STARTED' and result.json()['formal_eligibility'] is False
    assert client.get(BASE+'/tasks?symbol=600519').status_code==401
    assert client.get(BASE+'/companies/bad').status_code==422
    assert not data.provider_calls and state(root)==before


@pytest.mark.parametrize('extra',[{'endpoint':'https://example.invalid'}, {'key':'TEST_ONLY'},
    {'api_key':'TEST_ONLY'}, {'api_key_env':'VALUE_AGENT_TEST_ONLY'},
    {'sourcepath':'runtime/TEST_ONLY'}, {'source_path':'runtime/TEST_ONLY'},
    {'source_binding':{'path':'runtime/TEST_ONLY','sha256':'0'*64}},
    {'model_id':'TEST_ONLY'}, {'max_run_cost':'1'}])
def test_body_cannot_choose_credentials_sources_or_costs(api,extra):
    client,secret,data,_=api
    unlock(client,secret)
    response=client.post(BASE+'/tasks',json=dict(symbol='600519',request_key='TEST_ONLY-key',**extra))
    assert response.status_code==422 and response.json()['action']=='no_order'
    assert response.json()['status']=='LIVE_TASK_REJECTED_SOURCE_CONFIG_OR_BUDGET'
    assert not data.calls and not data.provider_calls


def test_authorized_create_queues_existing_service_without_claiming_live_success(api):
    client,secret,data,_=api
    unlock(client,secret)
    response=client.post(BASE+'/tasks',json=dict(symbol='600519',request_key='TEST_ONLY-key'))
    assert response.status_code==202,response.text
    assert response.json()['status']=='QUEUED' and response.json()['action']=='no_order'
    assert response.json()['formal_eligibility'] is False
    assert [call[0] for call in data.calls]==['create','run']
    read=client.get(BASE+'/tasks/TEST_ONLY-task')
    assert read.status_code==200 and read.json()['status']=='WAITING_EVIDENCE'
    assert read.json()['action']=='no_order' and not data.provider_calls


def result(scope=LIVE,status='SUCCEEDED'):
    # Synthetic fields solely test the projection whitelist, not LIVE acceptance.
    return dict(symbol='600519',status=status,task_id='TEST_ONLY-task',scope=scope,
        model_id='TEST_ONLY_MODEL',new_llm_calls=3,research_draft={'label':'TEST_ONLY'},
        context_fingerprint='TEST_ONLY-fingerprint',source_binding={'label':'TEST_ONLY'},
        research_as_of='2026-10-31',formal_fact_count=0,approval_changed=False,
        main_range_adopted=False,condition_price=None,personal_quantity=None,
        research_completeness=dict(scenario_count=3,numeric_assumption_count=6,
            unknown_assumption_count=2,status='REVIEW_REQUIRED',economic_validation='NOT_APPROVED'),
        TEST_ONLY_internal='MUST_NOT_BE_PUBLIC')


@pytest.mark.parametrize('scope',['TEST_ONLY_LIVE_CONTRACT','SAVED_RESPONSE','MOCK_STRUCTURED_RESEARCH'])
def test_public_result_never_upgrades_test_only_or_saved_scope(api,scope):
    client,_,data,_=api
    data.rows=[result(scope)]
    body=client.get(BASE+'/companies/600519').json()
    assert body['status']=='UNASSESSABLE' and body['reason']=='LATEST_TASK_NOT_VERIFIED_LIVE_RESEARCH'
    assert body['latest_task_status']=='SUCCEEDED'
    assert 'research_draft' not in body and body['action']=='no_order'


def test_public_success_only_selects_live_scope_and_preserves_research_boundaries(api):
    client,_,data,root=api
    data.rows=[result(),result('TEST_ONLY_LIVE_CONTRACT'),result(status='FAILED')]
    before=state(root)
    response=client.get(BASE+'/companies/600519')
    body=response.json()
    assert response.status_code==200 and body['status']=='SUCCEEDED'
    assert body['scope']==LIVE and body['research_draft']=={'label':'TEST_ONLY'}
    assert body['research_completeness']==dict(scenario_count=3,numeric_assumption_count=6,
        unknown_assumption_count=2,status='REVIEW_REQUIRED',economic_validation='NOT_APPROVED')
    assert body['formal_eligibility'] is False and body['formal_fact_count']==0
    assert body['approval_changed'] is False and body['main_range_adopted'] is False
    assert body['condition_price'] is None and body['personal_quantity'] is None
    assert body['action']=='no_order' and 'TEST_ONLY_internal' not in body
    assert not data.provider_calls and state(root)==before


def test_source_failure_does_not_fall_back_to_saved_success(api):
    client,secret,data,root=api
    data.rows=[result()]
    data.failure=ValueError('TEST_ONLY source hash mismatch')
    before=state(root)
    body=client.get(BASE+'/companies/600519').json()
    assert body['status']=='UNASSESSABLE' and body['reason']=='LIVE_SOURCE_OR_CHECKPOINT_NOT_VERIFIED'
    assert 'research_draft' not in body and body['formal_eligibility'] is False
    unlock(client,secret)
    response=client.post(BASE+'/tasks',json=dict(symbol='600519',request_key='TEST_ONLY-key'))
    assert response.status_code==422 and response.json()['action']=='no_order'
    assert not any(call[0]=='run' for call in data.calls)
    assert not data.provider_calls and state(root)==before


@pytest.mark.parametrize('present',[False,True])
def test_model_status_reports_credential_presence_without_calls_or_secret_exposure(api,monkeypatch,present):
    from value_investment_agent.application.research.agent_review import operating_task_v2 as service
    client,_,data,root=api
    cfg=dict(model_id='TEST_ONLY_MODEL',api_key_env='VALUE_AGENT_TEST_ONLY_STATUS',
        max_run_cost='0.1',currency='CNY',daily_cost_limit='1',
        endpoint='https://TEST_ONLY.invalid/chat/completions')
    monkeypatch.setattr(service,'model_configuration',lambda root:cfg)
    if present:monkeypatch.setenv(cfg['api_key_env'],'TEST_ONLY_NOT_A_REAL_KEY')
    else:monkeypatch.delenv(cfg['api_key_env'],raising=False)
    before=state(root)
    response=client.get(BASE+'/model-status')
    body=response.json()
    assert response.status_code==200 and body['credential_present'] is present
    assert body['status']==('READY' if present else 'MODEL_CREDENTIAL_REQUIRED')
    assert body['real_calls_started'] is False and body['action']=='no_order'
    assert all(text not in response.text for text in ('TEST_ONLY_NOT_A_REAL_KEY','api_key_env','endpoint'))
    assert not data.calls and not data.provider_calls and state(root)==before


def test_model_authorization_required_never_runs_background(api):
    client,secret,data,_=api
    unlock(client,secret)
    data.failure=PermissionError('MODEL_AUTHORIZATION_REQUIRED')
    response=client.post(BASE+'/tasks',json=dict(symbol='600519',request_key='TEST_ONLY-key'))
    assert response.status_code==409 and response.json()['status']=='MODEL_AUTHORIZATION_REQUIRED'
    assert response.json()['action']=='no_order'
    assert not any(call[0]=='run' for call in data.calls) and not data.provider_calls


@pytest.mark.parametrize('status,scope,error',[
    ('FAILED',LIVE,'TEST_ONLY_SOURCE_HASH_MISMATCH'),
    ('WAITING_EVIDENCE',LIVE,'TEST_ONLY_SOURCE_INVALID'),
    ('SUCCEEDED','TEST_ONLY_LIVE_CONTRACT',None),
    ('RUNNING',LIVE,None),
    ('CANCELLED',LIVE,None),
])
def test_latest_task_never_falls_back_to_older_live_success(api,status,scope,error):
    client,_,data,root=api
    latest=result(scope,status)
    latest['task_id']='TEST_ONLY-latest'
    if error:latest['error_code']=error
    old=result()
    old['task_id']='TEST_ONLY-older-success'
    old['research_draft']={'label':'TEST_ONLY_OLD_MUST_NOT_ESCAPE'}
    data.rows=[latest,old]
    before=state(root)
    response=client.get(BASE+'/companies/600519')
    body=response.json()
    assert response.status_code==200 and response.headers['cache-control']=='no-store'
    assert body['status']=='UNASSESSABLE' and body['latest_task_status']==status
    assert body['task_id']=='TEST_ONLY-latest'
    assert body['reason']==(error or 'LATEST_TASK_NOT_VERIFIED_LIVE_RESEARCH')
    assert body['action']=='no_order' and body['formal_eligibility'] is False
    assert 'research_draft' not in body and 'valuation' not in body
    assert 'TEST_ONLY_OLD_MUST_NOT_ESCAPE' not in response.text
    assert not data.provider_calls and state(root)==before


@pytest.mark.parametrize('status',['FAILED','WAITING_EVIDENCE','RUNNING','CANCELLED'])
def test_latest_live_verified_partial_exposes_completed_roles_without_call_or_old_fallback(api,status):
    client,_,data,root=api
    latest=result(status=status)
    latest['task_id']='TEST_ONLY-latest-partial'
    latest['error_code']='DAILY_BUDGET_EXHAUSTED_BEFORE_CALL'
    latest['new_llm_calls']=2
    latest['research_draft']={
        'FUNDAMENTAL':{'draft':{'label':'TEST_ONLY verified fundamental'}},
        'COUNTER_EVIDENCE':{'draft':{'label':'TEST_ONLY verified countercase'}}}
    old=result()
    old['research_draft']={'label':'TEST_ONLY_OLD_MUST_NOT_ESCAPE'}
    data.rows=[latest,old]
    before=state(root)
    response=client.get(BASE+'/companies/600519')
    body=response.json()
    assert response.status_code==200 and response.headers['cache-control']=='no-store'
    assert body['status']=='PARTIAL' and body['execution_status']==status
    assert body['task_id']=='TEST_ONLY-latest-partial'
    assert body['reason']==body['error_code']=='DAILY_BUDGET_EXHAUSTED_BEFORE_CALL'
    assert body['completed_roles']==['FUNDAMENTAL','COUNTER_EVIDENCE']
    assert body['pending_roles']==['EVENT']
    for key in ('scope','source_binding','model_id','new_llm_calls','research_draft',
                'research_completeness','context_fingerprint','research_as_of'):
        assert body[key]==latest[key]
    assert body['action']=='no_order' and body['formal_eligibility'] is False
    assert body['formal_fact_count']==0 and body['approval_changed'] is False
    assert body['main_range_adopted'] is False and body['condition_price'] is None
    assert body['personal_quantity'] is None
    assert 'TEST_ONLY_OLD_MUST_NOT_ESCAPE' not in response.text
    assert not data.provider_calls and state(root)==before


@pytest.mark.parametrize('damage',['missing_draft','empty_draft','source_invalid',
    'checkpoint_invalid','test_only','unknown_role'])
def test_partial_requires_verified_live_draft_and_never_uses_old_success(api,damage):
    client,_,data,root=api
    latest=result(status='FAILED')
    latest['task_id']='TEST_ONLY-latest-invalid'
    latest['research_draft']={'FUNDAMENTAL':{'draft':{'label':'TEST_ONLY'}}}
    if damage=='missing_draft':latest.pop('research_draft')
    if damage=='empty_draft':latest['research_draft']={}
    if damage=='source_invalid':
        latest['error_code']='SOURCE_OR_IMPLEMENTATION_CHANGED'
        latest.pop('research_draft')  # _view does not return a draft on failed source replay.
    if damage=='checkpoint_invalid':latest['error_code']='LIVE_CHECKPOINT_INVALID'
    if damage=='test_only':latest['scope']='TEST_ONLY_LIVE_CONTRACT_NOT_REAL_RESEARCH'
    if damage=='unknown_role':latest['research_draft']={'TEST_ONLY_UNKNOWN':{}}
    data.rows=[latest,result()]
    before=state(root)
    response=client.get(BASE+'/companies/600519')
    body=response.json()
    assert response.status_code==200 and body['status']=='UNASSESSABLE'
    assert body['latest_task_status']=='FAILED' and body['task_id']==latest['task_id']
    assert 'research_draft' not in body and 'completed_roles' not in body
    assert body['action']=='no_order' and body['formal_eligibility'] is False
    assert not data.provider_calls and state(root)==before


def reviewed_result(status='SUCCEEDED'):
    value=result(status=status)
    value['roles']={role:{'path':'runtime/TEST_ONLY-'+role+'.json','sha256':letter*64}
        for role,letter in [('FUNDAMENTAL','a'),('COUNTER_EVIDENCE','b')]}
    value['research_draft']={role:{'draft':{'label':'TEST_ONLY'}} for role in value['roles']}
    value['independent_review']=dict(source_context_fingerprint=value['context_fingerprint'],
        reviewed_role_responses=deepcopy(value['roles']),status='REVIEW_REQUIRED_NOT_APPROVAL',
        findings=[dict(priority='P2',role='COUNTER_EVIDENCE',claim_index=5,
            reason='TEST_ONLY: 原草案已区分库存口径，反证未准确引用。')])
    return value


@pytest.mark.parametrize('status',['SUCCEEDED','FAILED'])
def test_independent_review_requires_exact_source_and_role_pins_without_approval(api,status):
    client,_,data,root=api
    value=reviewed_result(status)
    data.rows=[value]
    before=state(root)
    response=client.get(BASE+'/companies/600519')
    body=response.json()
    assert body['status']==('SUCCEEDED' if status=='SUCCEEDED' else 'PARTIAL')
    assert body['independent_review']==value['independent_review']
    assert body['independent_review_status']=='REVIEW_REQUIRED_NOT_APPROVAL'
    assert body['research_draft']==value['research_draft']
    assert body['formal_eligibility'] is False and body['formal_fact_count']==0
    assert body['approval_changed'] is False and body['main_range_adopted'] is False
    assert body['action']=='no_order'
    assert data.rows==[value] and state(root)==before and not data.provider_calls


@pytest.mark.parametrize('damage',['fingerprint','role_hash','missing_pin','extra_pin',
    'missing_roles','approval','malformed'])
def test_misbound_review_hidden_without_hiding_verified_draft_or_approving(api,damage):
    client,_,data,root=api
    value=reviewed_result('FAILED')
    review=value['independent_review']
    if damage=='fingerprint':review['source_context_fingerprint']='TEST_ONLY-other-source'
    if damage=='role_hash':review['reviewed_role_responses']['FUNDAMENTAL']['sha256']='c'*64
    if damage=='missing_pin':review['reviewed_role_responses'].pop('COUNTER_EVIDENCE')
    if damage=='extra_pin':review['reviewed_role_responses']['EVENT']={'path':'runtime/TEST_ONLY','sha256':'d'*64}
    if damage=='missing_roles':value.pop('roles')
    if damage=='approval':review['status']='APPROVED'
    if damage=='malformed':value['independent_review']=None
    data.rows=[value]
    before=state(root)
    body=client.get(BASE+'/companies/600519').json()
    assert body['status']=='PARTIAL' and body['execution_status']=='FAILED'
    assert body['independent_review_status']=='REVIEW_BINDING_INVALID'
    assert 'independent_review' not in body
    assert body['research_draft']==value['research_draft']
    assert body['formal_eligibility'] is False and body['approval_changed'] is False
    assert body['main_range_adopted'] is False and body['action']=='no_order'
    assert state(root)==before and not data.provider_calls


def test_absent_review_remains_optional(api):
    client,_,data,_=api
    data.rows=[result()]
    body=client.get(BASE+'/companies/600519').json()
    assert body['status']=='SUCCEEDED'
    assert 'independent_review' not in body and 'independent_review_status' not in body


@pytest.mark.parametrize('endpoint',['read','create','cancel','resume','history'])
@pytest.mark.parametrize('valid',[True,False])
def test_authorized_endpoints_share_bound_review_projection_without_task_mutation(api,endpoint,valid):
    client,secret,data,root=api
    value=reviewed_result()
    value['action']='no_order'
    value['formal_eligibility']=False
    value['status']={'read':'FAILED','create':'QUEUED','resume':'QUEUED','cancel':'CANCELLED','history':'FAILED'}[endpoint]
    if not valid:value['independent_review']['reviewed_role_responses']['FUNDAMENTAL']['sha256']='f'*64
    data.views[endpoint]=value
    data.rows=[value]
    snapshot=deepcopy(value)
    unlock(client,secret)
    before=state(root)
    if endpoint=='read':response=client.get(BASE+'/tasks/TEST_ONLY-task')
    elif endpoint=='history':response=client.get(BASE+'/tasks?symbol=600519')
    elif endpoint=='create':response=client.post(BASE+'/tasks',json=dict(symbol='600519',request_key='TEST_ONLY-review'))
    else:response=client.post(BASE+'/tasks/TEST_ONLY-task/'+endpoint)
    assert response.status_code==(202 if endpoint=='create' else 200),response.text
    assert response.headers['cache-control']=='no-store'
    body=response.json()['items'][0] if endpoint=='history' else response.json()
    assert body['status']==value['status'] and body['action']=='no_order'
    assert body['formal_eligibility'] is False
    if valid:
        assert body['independent_review']==value['independent_review']
        assert body['independent_review_status']=='REVIEW_REQUIRED_NOT_APPROVAL'
    else:
        assert 'independent_review' not in body
        assert body['independent_review_status']=='REVIEW_BINDING_INVALID'
    assert value==snapshot and state(root)==before and not data.provider_calls
    assert sum(call[0]=='run' for call in data.calls)==(1 if endpoint in {'create','resume'} else 0)


def test_resume_changed_role_pins_invalidates_old_review_on_control_read_and_public(api):
    client,secret,data,_=api
    value=reviewed_result('FAILED')
    value.update(action='no_order',formal_eligibility=False)
    data.views['read']=value
    data.rows=[value]
    unlock(client,secret)
    assert client.get(BASE+'/tasks/TEST_ONLY-task').json()['independent_review_status']=='REVIEW_REQUIRED_NOT_APPROVAL'
    resumed=deepcopy(value)
    resumed['roles']['COUNTER_EVIDENCE']['sha256']='e'*64
    resumed['status']='QUEUED'
    data.views['resume']=resumed
    data.views['read']=resumed
    data.rows=[resumed]
    responses=[client.post(BASE+'/tasks/TEST_ONLY-task/resume'),
        client.get(BASE+'/tasks/TEST_ONLY-task'),client.get(BASE+'/companies/600519')]
    for response in responses:
        body=response.json()
        assert response.status_code==200
        assert 'independent_review' not in body
        assert body['independent_review_status']=='REVIEW_BINDING_INVALID'
        assert body['formal_eligibility'] is False and body['action']=='no_order'
    assert resumed['independent_review']==value['independent_review']
    assert not data.provider_calls


@pytest.mark.parametrize('status',['SUCCEEDED','FAILED'])
def test_public_driver_bridge_is_service_projection_without_account_write_or_approval(api,status):
    client,_,data,root=api
    value=reviewed_result(status)
    # Opaque TEST_ONLY transport marker, not a fabricated v2 bridge or source acceptance.
    bridge={'TEST_ONLY_service_projection':{'strict_upper':'0.585','unknowns':['TEST_ONLY']},
        'action':'no_order','formal_eligibility':False}
    value['operating_driver_bridge']=deepcopy(bridge)
    data.rows=[value]
    original=deepcopy(value)
    before=state(root)
    assert 'x-local-session' not in client.headers
    for _ in range(2):
        response=client.get(BASE+'/companies/600519')
        body=response.json()
        assert response.status_code==200 and response.headers['cache-control']=='no-store'
        assert body['status']==('SUCCEEDED' if status=='SUCCEEDED' else 'PARTIAL')
        assert body['operating_driver_bridge']==bridge
        assert body['research_draft']==value['research_draft']
        assert body['action']=='no_order' and body['formal_eligibility'] is False
        assert body['formal_fact_count']==0 and body['approval_changed'] is False
        assert body['main_range_adopted'] is False
        assert body['condition_price'] is None and body['personal_quantity'] is None
    assert data.rows==[original] and state(root)==before and not data.provider_calls
    assert all(call[0]=='list' for call in data.calls)


@pytest.mark.parametrize('status',['SUCCEEDED','FAILED'])
def test_legacy_public_result_without_driver_bridge_never_synthesizes_one(api,status):
    client,_,data,root=api
    value=reviewed_result(status)
    assert 'operating_driver_bridge' not in value
    data.rows=[value]
    before=state(root)
    body=client.get(BASE+'/companies/600519').json()
    assert body['status']==('SUCCEEDED' if status=='SUCCEEDED' else 'PARTIAL')
    assert 'operating_driver_bridge' not in body
    assert body['action']=='no_order' and body['formal_eligibility'] is False
    assert state(root)==before and not data.provider_calls


def test_driver_bridge_does_not_admit_test_only_public_research(api):
    client,_,data,_=api
    value=reviewed_result()
    value['scope']='TEST_ONLY_LIVE_CONTRACT_NOT_REAL_RESEARCH'
    value['operating_driver_bridge']={'TEST_ONLY':'must not escape rejected scope'}
    data.rows=[value]
    body=client.get(BASE+'/companies/600519').json()
    assert body['status']=='UNASSESSABLE' and 'operating_driver_bridge' not in body
    assert body['action']=='no_order' and body['formal_eligibility'] is False
    assert not data.provider_calls



def test_native_http_execution_uses_bounded_controller(tmp_path, monkeypatch):
    calls=[]
    class TestOnlyNative(routes._NativeLiveService):
        def create(self, **kwargs):
            return dict(task_id='rt-'+'a'*32,symbol=kwargs['symbol'],
                status='QUEUED',action='no_order',formal_eligibility=False,
                scope='TEST_ONLY_LIVE_CONTRACT')
        def run(self, task_id):
            raise AssertionError('Unbounded parent execution must not run')
    monkeypatch.setattr(routes,'_NativeLiveService',TestOnlyNative)
    monkeypatch.setattr(routes,'LiveOperatingTaskService',TestOnlyNative)
    monkeypatch.setattr(routes,'supervise_live_task',
        lambda root,task_id:calls.append((root,task_id)))
    client,secret=client_for(tmp_path,tmp_path/'TEST_ONLY-journal.jsonl',monkeypatch)
    unlock(client,secret)
    response=client.post(BASE+'/tasks',json=dict(symbol='600519',request_key='TEST_ONLY-controller'))
    assert response.status_code==202,response.text
    assert len(calls)==1 and calls[0][1]=='rt-'+'a'*32



def test_injected_native_subclass_keeps_its_own_runner(tmp_path, monkeypatch):
    calls=[]
    class TestOnlyInjected(routes._NativeLiveService):
        def create(self, **kwargs):
            return dict(task_id='rt-'+'b'*32,symbol=kwargs['symbol'],
                status='QUEUED',action='no_order',formal_eligibility=False,
                scope='TEST_ONLY_LIVE_CONTRACT')
        def run(self, task_id):
            calls.append(('injected',task_id))
    monkeypatch.setattr(routes,'LiveOperatingTaskService',TestOnlyInjected)
    monkeypatch.setattr(routes,'supervise_live_task',
        lambda *args:calls.append(('wrong_native',args)))
    client,secret=client_for(tmp_path,tmp_path/'TEST_ONLY-journal.jsonl',monkeypatch)
    unlock(client,secret)
    response=client.post(BASE+'/tasks',json=dict(symbol='600519',request_key='TEST_ONLY-injected'))
    assert response.status_code==202,response.text
    assert calls==[('injected','rt-'+'b'*32)]



def test_explicit_finalization_is_authorized_and_never_runs_model(tmp_path, monkeypatch):
    calls=[]
    class TestOnlyNative(routes._NativeLiveService):
        def read(self, task_id):
            calls.append('read')
            return dict(task_id=task_id,status='FAILED',action='no_order',
                formal_eligibility=False,error_code='TEST_ONLY_ORIGINAL_TIMEOUT')
        def run(self, task_id):
            raise AssertionError('finalization must never run a model')
        def resume(self, task_id):
            raise AssertionError('finalization must not resume research')
    monkeypatch.setattr(routes,'_NativeLiveService',TestOnlyNative)
    monkeypatch.setattr(routes,'LiveOperatingTaskService',TestOnlyNative)
    monkeypatch.setattr(routes,'finalize_pending_live_task',lambda *a:calls.append('finalize'))
    monkeypatch.setattr(routes,'read_pending_live_task',
        lambda *a:dict(status='NO_PENDING_FINALIZATION',action='no_order'))
    client,secret=client_for(tmp_path,tmp_path/'TEST_ONLY-journal.jsonl',monkeypatch)
    url=BASE+'/tasks/rt-'+'c'*32+'/finalize'
    assert client.post(url).status_code==401 and not calls
    unlock(client,secret)
    response=client.post(url)
    assert response.status_code==200,response.text
    assert response.json()['status']=='FAILED'
    assert calls==['finalize','read']


def test_pending_terminal_read_exposes_pending_without_recovery_writes(tmp_path, monkeypatch):
    calls=[]
    class TestOnlyNative(routes._NativeLiveService):
        def _load(self, *a, **kw):
            calls.append('load')
            return {},{},{}
        def _view(self,*a):
            return dict(task_id='rt-'+'d'*32,status='RUNNING',action='no_order',
                formal_eligibility=False)
        def read(self,*a):
            raise AssertionError('pending read must not hold the expensive view lock')
        def _save(self,*a,**kw):
            raise AssertionError('GET must not finalize state')
    monkeypatch.setattr(routes,'_NativeLiveService',TestOnlyNative)
    monkeypatch.setattr(routes,'LiveOperatingTaskService',TestOnlyNative)
    waiting=dict(status='FINALIZATION_PENDING',action='no_order',model_calls=0,
        pending_bindings=[{'path':'TEST_ONLY_HASH_BOUND_PENDING'}])
    monkeypatch.setattr(routes,'read_pending_live_task',lambda *a:waiting)
    monkeypatch.setattr(routes,'finalize_pending_live_task',
        lambda *a:(_ for _ in ()).throw(AssertionError('GET must not recover')))
    client,secret=client_for(tmp_path,tmp_path/'TEST_ONLY-journal.jsonl',monkeypatch)
    unlock(client,secret)
    response=client.get(BASE+'/tasks/rt-'+'d'*32)
    assert response.status_code==200,response.text
    assert response.json()['status']=='RUNNING'  # Persisted state is not fabricated as complete.
    assert response.json()['controller_finalization']==waiting
    assert calls==['load']
