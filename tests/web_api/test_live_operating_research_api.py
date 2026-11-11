"""TEST_ONLY service transport fixtures; never evidence of a real LIVE model run."""
from copy import deepcopy
import socket
from types import SimpleNamespace

import pytest

from web_api.test_held_continuity_api import client_for,unlock
from test_web_agent_research import state
from test_operating_horizon_task_v4 import env  # noqa: F401 - full bound task fixture
from test_operating_horizon_sources_v1 import source_env  # noqa: F401 - fixture dependency
from test_operating_horizon_draft_v1 import context  # noqa: F401 - fixture dependency
from value_investment_agent.presentation.web_api import live_operating_research_routes as routes
from value_investment_agent.infrastructure.agent_runtime import provider

BASE='/api/v1/operating-research'
LIVE='LIVE_LLM_OPERATING_RESEARCH_NOT_ADMITTED'
_ORIGINAL_SOCKET_CONNECT = socket.socket.connect


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


def test_busy_task_read_is_retryable_not_missing(api):
    client,secret,data,_=api
    unlock(client,secret)
    data.failure=routes.LockTimeout('TEST_ONLY publishing')
    response=client.get(BASE+'/tasks/TEST_ONLY-task')
    assert response.status_code==503
    assert response.json()['status']=='LIVE_STATE_BUSY'
    assert response.headers['retry-after']=='3'
    assert not data.provider_calls


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


def test_public_q3_observation_is_visible_without_a_live_task_or_price_admission(api, monkeypatch):
    from value_investment_agent.application.research import quarter_financial_read_model_v1 as quarter

    client, _, data, root = api
    before = state(root)

    def fixed_source_read(project, symbol, now):
        assert project == root and symbol == '600519' and now.utcoffset() is not None
        return dict(status='VERIFIED_OBSERVATION_ONLY', symbol=symbol,
                    supported_scope='FIXED_SOURCE_600519_Q3_2026', action='no_order',
                    formal_eligibility=False, valuation_admitted=False,
                    current_comparison_changed=False,
                    ytd_9m_observation=dict(symbol=symbol, report_period='2026-09-30',
                        period_basis='YTD_9M', currency='CNY',
                        facts=dict(revenue_ytd_cny='130970743649.04',
                                   attributable_profit_ytd_cny='64467425981.95'),
                        source_sha256='a' * 64, formal_eligibility=False,
                        valuation_admitted=False, action='no_order'))

    monkeypatch.setattr(quarter, 'read_quarter_financial_ocr', fixed_source_read)
    response = client.get(BASE + '/companies/600519')
    body = response.json()
    observed = body['current_capital_observation']['quarter_financial_observation']
    assert response.status_code == 200 and body['status'] == 'NOT_STARTED'
    assert observed['status'] == 'VERIFIED_OBSERVATION_ONLY'
    assert observed['valuation_admitted'] is False
    assert body['formal_eligibility'] is False and body['action'] == 'no_order'
    assert data.provider_calls == [] and state(root) == before


def test_public_h1_share_observation_remains_historical_without_a_live_task(api, monkeypatch):
    from value_investment_agent.application.research import current_capital_h1_ocr_overlay_v2 as shares

    client, _, data, root = api
    registration = root / 'config/current-capital-h1-ocr-v2.json'
    registration.parent.mkdir(parents=True, exist_ok=True)
    registration.write_text('{}', encoding='utf-8')
    before = state(root)

    def fixed_h1_read(project, symbol, now, *, base_observation):
        assert project == root and symbol == '600519' and now.utcoffset() is not None
        assert base_observation['action'] == 'no_order'
        return dict(status='PARTIAL', action='no_order', formal_eligibility=False,
                    current_capital_continuity='NOT_PROVEN',
                    h1_share_observation=dict(status='VERIFIED', report_period_end='2026-06-30',
                        ordinary_shares=1250081601, current_continuity='UNPROVEN',
                        formal_eligibility=False, action='no_order',
                        source=dict(original_sha256='a' * 64)))

    monkeypatch.setattr(shares, 'read_capital_with_h1_shares', fixed_h1_read)
    response = client.get(BASE + '/companies/600519')
    body = response.json()
    observation = body['current_capital_observation']['h1_share_observation']
    assert response.status_code == 200 and body['status'] == 'NOT_STARTED'
    assert observation['status'] == 'VERIFIED'
    assert observation['ordinary_shares'] == 1250081601
    assert observation['current_continuity'] == 'UNPROVEN'
    assert body['formal_eligibility'] is False and body['action'] == 'no_order'
    assert data.provider_calls == [] and state(root) == before


def test_public_q3_h1_capital_bridge_is_read_only_and_never_grants_price_admission(api, monkeypatch):
    from value_investment_agent.application.research import current_capital_q3_h1_bridge_v1 as bridge

    client, _, data, root = api
    registration = root / bridge.REGISTRY
    registration.parent.mkdir(parents=True, exist_ok=True)
    registration.write_text('{}', encoding='utf-8')
    before = state(root)

    def fixed_bridge_read(project, now):
        assert project == root and now.utcoffset() is not None
        return dict(status='MONETARY_CAPITAL_VERIFIED_SHARES_UNKNOWN', symbol=bridge.SUPPORTED_SYMBOL,
                    q3_monetary_capital_cny='1250081601.00', q3_ordinary_shares='UNKNOWN',
                    h1_ordinary_shares=1250081601, current_continuity='UNPROVEN',
                    q3_source=dict(original_sha256='a' * 64), formal_eligibility=False,
                    action='no_order')

    monkeypatch.setattr(bridge, 'read_q3_h1_capital_bridge', fixed_bridge_read)
    response = client.get(BASE + '/companies/600519')
    body = response.json()
    observation = body['current_capital_observation']['q3_h1_capital_bridge']
    assert response.status_code == 200 and body['status'] == 'NOT_STARTED'
    assert observation['q3_ordinary_shares'] == 'UNKNOWN'
    assert observation['current_continuity'] == 'UNPROVEN'
    assert body['formal_eligibility'] is False and body['action'] == 'no_order'
    assert data.provider_calls == [] and state(root) == before


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



@pytest.mark.parametrize('owner_active', [True, False])
def test_resume_requires_controller_release_before_requeue(tmp_path, monkeypatch, owner_active):
    from contextlib import contextmanager
    calls=[]
    class TestOnlyNative(routes._NativeLiveService):
        @contextmanager
        def _lock(self, directory, name='state'):
            assert name == 'controller'
            if owner_active:
                raise routes.LockTimeout('TEST_ONLY active controller')
            calls.append('controller-acquired')
            yield
            calls.append('controller-released')
        def resume(self, task_id):
            calls.append('resume')
            return dict(task_id=task_id,status='QUEUED',action='no_order')
    monkeypatch.setattr(routes,'_NativeLiveService',TestOnlyNative)
    monkeypatch.setattr(routes,'LiveOperatingTaskService',TestOnlyNative)
    monkeypatch.setattr(routes,'read_pending_live_task',lambda *a:dict(status='NO_PENDING_FINALIZATION'))
    monkeypatch.setattr(routes,'supervise_live_task',lambda *a:calls.append('enqueue'))
    client,secret=client_for(tmp_path,tmp_path/'TEST_ONLY-journal.jsonl',monkeypatch)
    unlock(client,secret)
    response=client.post(BASE+'/tasks/rt-'+('a'*32)+'/resume')
    if owner_active:
        assert response.status_code == 409
        assert response.json()['status'] == 'LIVE_EXECUTION_STILL_ACTIVE'
        assert calls == []
    else:
        assert response.status_code == 200
        assert calls == ['controller-acquired','resume','controller-released','enqueue']


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


def test_horizon_unauthorized_cannot_start_or_cancel(api):
    client,_,data,root=api
    before=state(root)
    for path in ('/horizon-tasks','/horizon-tasks/rt-'+'a'*32+'/cancel'):
        response=client.post(BASE+path,json=dict(symbol='600323',request_key='TEST_ONLY-horizon',years=[2026]))
        assert response.status_code==401
    assert state(root)==before and not data.provider_calls


def test_horizon_request_cannot_override_source_or_budget(api):
    client,secret,data,root=api
    unlock(client,secret)
    before=state(root)
    response=client.post(BASE+'/horizon-tasks',json=dict(symbol='600323',request_key='TEST_ONLY-horizon',years=[2026],max_run_cost='100'))
    assert response.status_code==422 and response.json()['status']=='HORIZON_TASK_REJECTED'
    assert state(root)==before and not data.provider_calls


def test_horizon_authorized_start_reads_and_cancels_real_service_boundary(api,monkeypatch):
    from value_investment_agent.application.research.agent_review.operating_horizon_task_v2 import OperatingHorizonTaskService
    client,secret,data,root=api
    unlock(client,secret)
    seen=[]
    task='rt-'+'f'*32
    def create(self,**kw):
        seen.append(('create',kw));return dict(task_id=task,status='QUEUED',action='no_order')
    monkeypatch.setattr(OperatingHorizonTaskService,'create',create)
    monkeypatch.setattr(OperatingHorizonTaskService,'run',lambda self,id:seen.append(('run',id)))
    monkeypatch.setattr(OperatingHorizonTaskService,'read',lambda self,id:dict(task_id=id,status='SUCCEEDED',action='no_order',formal_eligibility=False))
    monkeypatch.setattr(OperatingHorizonTaskService,'cancel',lambda self,id:dict(task_id=id,status='CANCELLED',action='no_order'))
    body=dict(symbol='600323',request_key='TEST_ONLY-horizon',years=[2026])
    result=client.post(BASE+'/horizon-tasks',json=body)
    assert result.status_code==202 and seen==[('create',body),('run',task)]
    assert client.get(BASE+'/horizon-tasks/'+task).json()['formal_eligibility'] is False
    assert client.post(BASE+'/horizon-tasks/'+task+'/cancel').json()['status']=='CANCELLED'
    assert not data.provider_calls


def test_cash_policy_horizon_uses_distinct_v4_service_and_real_lifecycle(api,monkeypatch):
    from value_investment_agent.application.research.agent_review.operating_horizon_task_v4 import OperatingHorizonTaskService
    client,secret,data,root=api
    unlock(client,secret)
    seen=[]; task='rt-'+'e'*32
    def create(self,**kw):
        seen.append(('create',kw));return dict(task_id=task,status='QUEUED',action='no_order')
    monkeypatch.setattr(OperatingHorizonTaskService,'create',create)
    monkeypatch.setattr(OperatingHorizonTaskService,'run',lambda self,id:seen.append(('run',id)))
    monkeypatch.setattr(OperatingHorizonTaskService,'read',lambda self,id:dict(task_id=id,status='SUCCEEDED',action='no_order',formal_eligibility=False,workflow='operating-horizon-task-v4-cash-policy'))
    monkeypatch.setattr(OperatingHorizonTaskService,'cancel',lambda self,id:dict(task_id=id,status='CANCELLED',action='no_order'))
    body=dict(symbol='600323',request_key='TEST_ONLY-cash-policy',years=[2026])
    result=client.post(BASE+'/horizon-cash-policy-tasks',json=body)
    assert result.status_code==202 and seen==[('create',body),('run',task)]
    assert client.get(BASE+'/horizon-cash-policy-tasks/'+task).json()['workflow']=='operating-horizon-task-v4-cash-policy'
    assert client.post(BASE+'/horizon-cash-policy-tasks/'+task+'/cancel').json()['status']=='CANCELLED'
    assert not data.provider_calls


def test_parent_wc_horizon_explicit_v5_dispatch_is_authorized_and_read_only(api, monkeypatch):
    from value_investment_agent.application.research.agent_review.operating_horizon_task_v5_wc import (
        OperatingHorizonTaskService as V5, CONTRACT)
    from value_investment_agent.application.research.agent_review.operating_horizon_task_v4 import (
        OperatingHorizonTaskService as V4)
    from value_investment_agent.application.research import operating_horizon_cash_policy_e2_v1 as e2

    client, secret, data, root = api
    path = BASE + '/horizon-cash-policy-tasks'
    task_id = 'rt-' + '9' * 32
    body = dict(symbol='600519', request_key='TEST_ONLY-v5-route', years=[2027], task_contract=CONTRACT)
    before = state(root)
    for method, url in [('post', path), ('get', path + '?symbol=600519&task_contract=' + CONTRACT),
                        ('get', path + '/' + task_id), ('get', path + '/' + task_id + '/e2-input'),
                        ('post', path + '/' + task_id + '/cancel')]:
        response = client.post(url, json=body) if method == 'post' else client.get(url)
        assert response.status_code == 401
    assert state(root) == before and not data.provider_calls

    calls = []
    monkeypatch.setattr(V4, 'create', lambda self, **kw: pytest.fail('V5 request fell through to V4'))
    monkeypatch.setattr(V5, 'create', lambda self, **kw: (calls.append(('create', kw)) or
        dict(task_id=task_id, status='QUEUED', action='no_order', formal_eligibility=False)))
    monkeypatch.setattr(V5, 'run', lambda self, id: calls.append(('run', id)))
    monkeypatch.setattr(V5, 'read', lambda self, id: (calls.append(('read', id)) or
        dict(task_id=id, symbol='600519', updated_at='2026-11-11T00:00:00+00:00',
             status='WAITING_EVIDENCE', action='no_order', formal_eligibility=False)))
    monkeypatch.setattr(V5, '_load', lambda self, id: (None, None, None))
    monkeypatch.setattr(V5, 'cancel', lambda self, id: (calls.append(('cancel', id)) or
        dict(task_id=id, status='CANCELLED', action='no_order')))
    monkeypatch.setattr(V5, 'resume', lambda self, id: (calls.append(('resume', id)) or
        dict(task_id=id, status='QUEUED', action='no_order')))
    monkeypatch.setattr(e2, 'read_d2_cash_policy_e2_input', lambda **kw:
        (calls.append(('e2', kw['service'].__class__)) or
         dict(status='UNASSESSABLE', action='no_order', formal_eligibility=False)))
    # Only task-store identity is needed by the route; mocked methods make no
    # provider call and cannot turn this fixture into a real research result.
    from value_investment_agent.application.research.agent_review import operating_q3_cash_source_loader_v1 as loader
    store = V5(root, allow_live=True, source_loader=loader.load_current,
               source_loader_version=loader.VERSION)._directory(task_id)
    store.mkdir(parents=True)
    (store / 'input.json').write_text('{"mode":"LIVE_OPERATING"}', encoding='utf-8')
    unlock(client, secret)
    assert client.post(path, json=body).status_code == 202
    assert calls[:2] == [('create', {key: body[key] for key in ('symbol', 'request_key', 'years')}),
                         ('run', task_id)]
    assert client.get(path + '?symbol=600519&task_contract=' + CONTRACT).json()['items'][0]['task_id'] == task_id
    assert client.get(path + '?symbol=600519&task_contract=unknown').status_code == 422
    assert client.get(path + '/' + task_id).json()['status'] == 'WAITING_EVIDENCE'
    assert client.get(path + '/' + task_id + '/e2-input').json()['status'] == 'UNASSESSABLE'
    assert ('e2', V5) in calls
    assert client.post(path + '/' + task_id + '/cancel').json()['status'] == 'CANCELLED'
    assert client.post(path + '/' + task_id + '/resume').json()['status'] == 'QUEUED'
    assert calls[-2:] == [('resume', task_id), ('run', task_id)]
    assert not data.provider_calls


def test_split_v6_dispatch_is_opt_in_and_damaged_task_never_falls_back(api, monkeypatch):
    from value_investment_agent.application.research.agent_review.operating_horizon_task_v6_split import (
        OperatingHorizonTaskService as V6, CONTRACT)
    from value_investment_agent.application.research.agent_review.operating_horizon_task_v4 import (
        OperatingHorizonTaskService as V4)
    from value_investment_agent.application.research.agent_review import operating_q3_cash_source_loader_v1 as loader

    client, secret, data, root = api
    path = BASE + '/horizon-cash-policy-tasks'
    body = dict(symbol='600519', request_key='TEST_ONLY-v6-route', years=[2027], task_contract=CONTRACT)
    before = state(root)
    assert client.post(path, json=body).status_code == 401
    assert state(root) == before and not data.provider_calls
    task_id = 'rt-' + '6' * 32
    calls = []
    monkeypatch.setattr(V4, 'create', lambda self, **kw: pytest.fail('V6 fell through to V4'))
    monkeypatch.setattr(V6, 'create', lambda self, **kw: (calls.append(('create', kw)) or
        dict(task_id=task_id, status='QUEUED', symbol='600519', action='no_order', formal_eligibility=False)))
    monkeypatch.setattr(V6, 'run', lambda self, id: calls.append(('run', id)))
    monkeypatch.setattr(V6, 'read', lambda self, id: (calls.append(('read', id)) or
        dict(task_id=id, symbol='600519', updated_at='2026-11-11T00:00:00+00:00',
             status='QUEUED', action='no_order', formal_eligibility=False)))
    monkeypatch.setattr(V6, '_load', lambda self, id: (None, None, None))
    directory = V6(root, allow_live=True, source_loader=loader.load_current,
        source_loader_version=loader.VERSION)._directory(task_id)
    directory.mkdir(parents=True)
    (directory / 'input.json').write_text('{"mode":"LIVE_OPERATING"}', encoding='utf-8')
    unlock(client, secret)
    assert client.post(path, json=body).status_code == 202
    assert calls[:2] == [('create', {key: body[key] for key in ('symbol', 'request_key', 'years')}),
                         ('run', task_id)]
    assert client.get(path + '?symbol=600519&task_contract=' + CONTRACT).json()['items'][0]['task_id'] == task_id
    assert client.get(path + '/' + task_id).json()['status'] == 'QUEUED'
    assert not data.provider_calls
    (directory / 'input.json').unlink()
    assert client.get(path + '/' + task_id).status_code == 422
    assert client.get(path + '?symbol=600519&task_contract=' + CONTRACT).status_code == 422
    assert not data.provider_calls


def test_split_v7_dispatch_is_explicit_and_corruption_never_falls_back(api, monkeypatch):
    from value_investment_agent.application.research.agent_review.operating_horizon_task_v7_split import (
        OperatingHorizonTaskService as V7, CONTRACT)
    from value_investment_agent.application.research.agent_review.operating_horizon_task_v4 import (
        OperatingHorizonTaskService as V4)
    from value_investment_agent.application.research.agent_review import operating_q3_cash_source_loader_v1 as loader

    client, secret, data, root = api
    path = BASE + '/horizon-cash-policy-tasks'
    body = dict(symbol='600519', request_key='TEST_ONLY-v7-route', years=[2027], task_contract=CONTRACT)
    before = state(root)
    assert client.post(path, json=body).status_code == 401
    assert state(root) == before and not data.provider_calls
    task_id = 'rt-' + '8' * 32
    calls = []
    monkeypatch.setattr(V4, 'create', lambda self, **kw: pytest.fail('V7 fell through to V4'))
    monkeypatch.setattr(V7, 'create', lambda self, **kw: (calls.append(('create', kw)) or
        dict(task_id=task_id, status='QUEUED', symbol='600519', action='no_order', formal_eligibility=False)))
    monkeypatch.setattr(V7, 'run', lambda self, id: calls.append(('run', id)))
    monkeypatch.setattr(V7, 'read', lambda self, id: (calls.append(('read', id)) or
        dict(task_id=id, symbol='600519', updated_at='2026-11-11T00:00:00+00:00',
             status='QUEUED', action='no_order', formal_eligibility=False)))
    monkeypatch.setattr(V7, '_load', lambda self, id: (None, None, None))
    directory = V7(root, allow_live=True, source_loader=loader.load_current,
        source_loader_version=loader.VERSION)._directory(task_id)
    directory.mkdir(parents=True)
    (directory / 'input.json').write_text('{"mode":"LIVE_OPERATING"}', encoding='utf-8')
    unlock(client, secret)
    assert client.post(path, json=body).status_code == 202
    assert calls[:2] == [('create', {key: body[key] for key in ('symbol', 'request_key', 'years')}),
                         ('run', task_id)]
    assert client.get(path + '?symbol=600519&task_contract=' + CONTRACT).json()['items'][0]['task_id'] == task_id
    assert client.get(path + '/' + task_id).json()['status'] == 'QUEUED'
    assert not data.provider_calls
    (directory / 'input.json').unlink()
    assert client.get(path + '/' + task_id).status_code == 422
    assert client.get(path + '?symbol=600519&task_contract=' + CONTRACT).status_code == 422
    assert not data.provider_calls


def test_split_v6_test_only_task_is_not_a_live_api_result(api, monkeypatch):
    from value_investment_agent.application.research.agent_review.operating_horizon_task_v6_split import (
        OperatingHorizonTaskService as V6, CONTRACT)
    from value_investment_agent.application.research.agent_review import operating_q3_cash_source_loader_v1 as loader

    client, secret, data, root = api
    task_id = 'rt-' + '7' * 32
    service = V6(root, allow_live=True, source_loader=loader.load_current,
        source_loader_version=loader.VERSION)
    directory = service._directory(task_id)
    directory.mkdir(parents=True)
    (directory / 'input.json').write_text('{"mode":"TEST_ONLY_LIVE_CONTRACT"}', encoding='utf-8')
    monkeypatch.setattr(V6, '_load', lambda self, id: (None, None, None))
    monkeypatch.setattr(V6, 'read', lambda self, id: pytest.fail('TEST_ONLY V6 returned as LIVE'))
    unlock(client, secret)
    path = BASE + '/horizon-cash-policy-tasks'
    listing = client.get(path + '?symbol=600519&task_contract=' + CONTRACT)
    assert listing.status_code == 200 and listing.json()['items'] == []
    direct = client.get(path + '/' + task_id)
    assert direct.status_code == 422
    assert direct.json()['reason'] == 'V6_SPLIT_TEST_ONLY_NOT_LIVE_RESEARCH'
    assert not data.provider_calls


def test_parent_wc_mixed_modes_list_excludes_verified_test_only_and_rejects_direct_read(api, monkeypatch):
    from value_investment_agent.application.research.agent_review.operating_horizon_task_v5_wc import (
        OperatingHorizonTaskService as V5, CONTRACT)
    from value_investment_agent.application.research.agent_review.operating_horizon_task_v4 import (
        OperatingHorizonTaskService as V4)
    from value_investment_agent.application.research.agent_review import operating_q3_cash_source_loader_v1 as loader
    from value_investment_agent.application.research.agent_review.task_execution_v1 import VERSION, _bytes, _hash

    client, secret, data, root = api
    service = V5(root, allow_live=True, source_loader=loader.load_current,
                 source_loader_version=loader.VERSION)
    test_id, live_id = 'rt-' + '2' * 32, 'rt-' + '3' * 32

    def artifact(task_id, mode):
        directory = service._directory(task_id)
        (directory / 'versions').mkdir(parents=True)
        spec = dict(schema_version=VERSION, task_id=task_id, workflow='operating_research',
                    action='no_order', mode=mode, task_contract=CONTRACT, years=[2027])
        raw = _bytes(spec)
        (directory / 'input.json').write_bytes(raw)
        row = dict(schema_version=VERSION, task_id=task_id, input_sha256=_hash(raw),
                   version=1, previous=None, status='QUEUED', action='no_order',
                   formal_eligibility=False, new_llm_calls=0)
        data_bytes = _bytes(row)
        record = directory / 'versions' / ('0001-' + _hash(data_bytes) + '.json')
        record.write_bytes(data_bytes)
        (directory / 'current.json').write_bytes(_bytes(service._binding(record)))
        return directory

    test_dir = artifact(test_id, 'TEST_ONLY_LIVE_CONTRACT')
    artifact(live_id, 'LIVE_OPERATING')
    seen = []
    monkeypatch.setattr(V5, 'read', lambda self, id: (seen.append(id) or
        dict(task_id=id, symbol='600519', updated_at='2026-11-11T00:00:00+00:00',
             status='QUEUED', action='no_order', formal_eligibility=False)))
    monkeypatch.setattr(V4, 'read', lambda self, id: pytest.fail('V5 artifact fell through to V4'))
    unlock(client, secret)
    path = BASE + '/horizon-cash-policy-tasks'
    listing = client.get(path + '?symbol=600519&task_contract=' + CONTRACT)
    assert listing.status_code == 200
    assert [item['task_id'] for item in listing.json()['items']] == [live_id]
    assert seen == [live_id] and not data.provider_calls
    for suffix in ('', '/e2-input'):
        result = client.get(path + '/' + test_id + suffix)
        assert result.status_code == (200 if suffix else 422)
        assert result.json()['reason'] == 'V5_WC_TEST_ONLY_NOT_LIVE_RESEARCH'
        if suffix:
            assert result.json()['status'] == 'UNASSESSABLE'
    assert client.post(path + '/' + test_id + '/cancel').status_code == 409
    assert seen == [live_id] and not data.provider_calls

    # A missing input in an existing V5 directory is corruption, not V4.
    (test_dir / 'input.json').unlink()
    damaged = client.get(path + '/' + test_id)
    assert damaged.status_code == 422
    assert damaged.json()['reason'] == 'V5_WC_INPUT_MISSING_OR_DAMAGED'
    assert client.get(path + '?symbol=600519&task_contract=' + CONTRACT).status_code == 422
    assert not data.provider_calls


def test_parent_wc_version_chain_tamper_fails_closed_without_v4_fallback(api, monkeypatch):
    from value_investment_agent.application.research.agent_review.operating_horizon_task_v5_wc import (
        OperatingHorizonTaskService as V5)
    from value_investment_agent.application.research.agent_review.operating_horizon_task_v4 import (
        OperatingHorizonTaskService as V4)
    from value_investment_agent.application.research.agent_review import operating_q3_cash_source_loader_v1 as loader
    client, secret, data, root = api
    service = V5(root, allow_live=True, source_loader=loader.load_current,
                 source_loader_version=loader.VERSION)
    task_id = 'rt-' + '4' * 32
    directory = service._directory(task_id)
    directory.mkdir(parents=True)
    (directory / 'input.json').write_text('{"mode":"LIVE_OPERATING"}', encoding='utf-8')
    monkeypatch.setattr(V4, 'read', lambda self, id: pytest.fail('corrupt V5 fell through to V4'))
    unlock(client, secret)
    response = client.get(BASE + '/horizon-cash-policy-tasks/' + task_id)
    assert response.status_code == 422
    assert 'INVALID_LIVE_TASK' in response.json()['reason']
    assert not data.provider_calls


def test_cash_policy_horizon_requires_authorization_and_exact_request(api):
    client,_,data,root=api
    before=state(root)
    unauthorized=client.post(BASE+'/horizon-cash-policy-tasks',json=dict(symbol='600323',request_key='TEST_ONLY-cash-policy',years=[2026]))
    assert unauthorized.status_code==401 and state(root)==before and not data.provider_calls


def test_cash_policy_horizon_history_recovers_failed_task_without_model_call(api, monkeypatch):
    from value_investment_agent.application.research.agent_review.operating_horizon_task_v4 import OperatingHorizonTaskService
    client, secret, data, root = api
    path = BASE + '/horizon-cash-policy-tasks?symbol=600323'
    before = state(root)
    assert client.get(path).status_code == 401
    unlock(client, secret)
    task_id = 'rt-' + 'f' * 32
    failed = dict(task_id=task_id, symbol='600323', status='FAILED',
                  error_code='HORIZON_PROVIDER_RESPONSE_INCOMPLETE', action='no_order',
                  formal_eligibility=False)
    monkeypatch.setattr(OperatingHorizonTaskService, 'list_for_symbol',
                        lambda self, symbol: [failed] if symbol == '600323' else [])
    result = client.get(path)
    assert result.status_code == 200
    assert result.json() == dict(action='no_order', symbol='600323', items=[failed])
    assert client.get(BASE + '/horizon-cash-policy-tasks?symbol=bad').status_code == 422
    assert not data.provider_calls and state(root) == before


def test_cash_policy_e2_read_projects_ready_or_unassessable_without_provider(api,monkeypatch):
    from value_investment_agent.application.research import operating_horizon_cash_policy_e2_v1 as e2
    from value_investment_agent.application.research.agent_review.operating_horizon_task_v4 import OperatingHorizonTaskService
    client,secret,data,root=api
    unlock(client,secret)
    before=state(root)
    task_id='rt-'+'a'*32
    ready=dict(status='SOURCE_BOUND_D2_V4_CASH_POLICY_READY_FOR_E2',action='no_order',
        formal_eligibility=False,condition_price=None,symbol='600323',task_id=task_id,
        blockers=['MAIN_ECONOMIC_RANGE_ADOPTION_REQUIRED'])
    seen=[]
    def project(**kwargs):
        seen.append(kwargs)
        return ready
    monkeypatch.setattr(e2,'read_d2_cash_policy_e2_input',project)
    response=client.get(BASE+'/horizon-cash-policy-tasks/'+task_id+'/e2-input')
    assert response.status_code==200 and response.json()==ready
    assert len(seen)==1 and isinstance(seen[0]['service'],OperatingHorizonTaskService)
    monkeypatch.setattr(e2,'read_d2_cash_policy_e2_input',lambda **kwargs:(_ for _ in ()).throw(
        ValueError('COMPLETE_UNAPPROVED_D2_CASH_POLICY_REQUIRED')))
    rejected=client.get(BASE+'/horizon-cash-policy-tasks/'+task_id+'/e2-input')
    assert rejected.status_code==200
    assert rejected.json()['status']=='UNASSESSABLE'
    assert rejected.json()['reason']=='COMPLETE_UNAPPROVED_D2_CASH_POLICY_REQUIRED'
    assert rejected.json()['action']=='no_order' and not data.provider_calls and state(root)==before


def test_full_cash_policy_e2_route_reads_its_own_bound_task(env, monkeypatch):
    service = env.service()
    created = service.create(symbol='123456', request_key='TEST_ONLY_BOUND_FULL_E2', years=[2026])
    assert service.run(created['task_id'])['status'] == 'SUCCEEDED'
    # The source fixture blocks all sockets; Starlette's local event-loop pipe
    # needs loopback. Never grant an external connection to this route test.
    def local_event_loop_only(sock, address):
        if not isinstance(address, tuple) or address[0] != '127.0.0.1':
            pytest.fail('Network forbidden')
        return _ORIGINAL_SOCKET_CONNECT(sock, address)
    monkeypatch.setattr(socket.socket, 'connect', local_event_loop_only)
    client, secret = client_for(env.root, env.root/'TEST_ONLY-full-e2-journal.jsonl', monkeypatch)
    unlock(client, secret)
    before = state(env.root)
    response = client.get(BASE+'/horizon-cash-policy-tasks/'+created['task_id']+'/e2-input')
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['status'] == 'SOURCE_BOUND_D2_V4_CASH_POLICY_READY_FOR_E2'
    assert result['task_id'] == created['task_id']
    assert result['policy_years']['2026']['base']['complete'] is True
    assert result['main_range_adopted'] is False
    assert result['condition_price'] is None
    assert result['formal_eligibility'] is False and result['action'] == 'no_order'
    assert state(env.root) == before


def test_compact_cash_policy_auth_lifecycle_list_and_read_only_e2(api,monkeypatch):
    from value_investment_agent.application.research.agent_review.notice_task_dispatch_v1 import NoticeAwareTaskService
    from value_investment_agent.application.research import operating_horizon_cash_policy_e2_v1 as e2
    client,secret,data,root=api
    task_id='rt-'+'b'*32
    path=BASE+'/cash-policy-tasks'
    calls=[]
    body=dict(symbol='600323',request_key='TEST_ONLY-compact',years=[2026])
    for method,url in [('get',path+'?symbol=600323'),('get',path+'/'+task_id),
                       ('get',path+'/'+task_id+'/e2-input'),('post',path),
                       ('post',path+'/'+task_id+'/cancel'),('post',path+'/'+task_id+'/resume')]:
        response=getattr(client,method)(url,json=body) if method=='post' else client.get(url)
        assert response.status_code==401
    assert not calls and not data.provider_calls
    unlock(client,secret)
    monkeypatch.setattr(NoticeAwareTaskService,'create',lambda self,**kw:(calls.append(('create',kw)) or
        dict(task_id=task_id,status='QUEUED',action='no_order')))
    monkeypatch.setattr(NoticeAwareTaskService,'run',lambda self,id:calls.append(('run',id)))
    monkeypatch.setattr(NoticeAwareTaskService,'read',lambda self,id:(calls.append(('read',id)) or
        dict(task_id=id,symbol='600323',status='WAITING_EVIDENCE',action='no_order',formal_eligibility=False,
             research_as_of='2026-01-01T00:00:00+00:00',workflow='operating-cash-policy-task-v1')))
    monkeypatch.setattr(NoticeAwareTaskService,'cancel',lambda self,id:(calls.append(('cancel',id)) or
        dict(task_id=id,status='CANCELLED',action='no_order')))
    monkeypatch.setattr(NoticeAwareTaskService,'resume',lambda self,id:(calls.append(('resume',id)) or
        dict(task_id=id,status='QUEUED',action='no_order')))
    created=client.post(path,json=body)
    assert created.status_code==202 and calls[:2]==[('create',body),('run',task_id)]
    assert client.get(path+'/'+task_id).json()['status']=='WAITING_EVIDENCE'
    # Reuse bounded task-store discovery; do not scan the directory ad hoc.
    service=NoticeAwareTaskService(root,kind='cash')
    monkeypatch.setattr(NoticeAwareTaskService,'list_for_symbol',
        lambda self,symbol:[self.read(task_id)] if symbol=='600323' else [])
    listed=client.get(path+'?symbol=600323')
    assert listed.status_code==200 and listed.json()==dict(action='no_order',symbol='600323',
        items=[dict(task_id=task_id,symbol='600323',status='WAITING_EVIDENCE',action='no_order',formal_eligibility=False,
                    research_as_of='2026-01-01T00:00:00+00:00',workflow='operating-cash-policy-task-v1')])
    assert client.get(path+'?symbol=bad').status_code==422
    incomplete=client.get(path+'/'+task_id+'/e2-input')
    assert incomplete.status_code==200 and incomplete.json()['status']=='UNASSESSABLE'
    assert incomplete.json()['reason']=='SUCCEEDED_BOUND_D2_CASH_POLICY_TASK_REQUIRED'
    seen=[]
    def project(**kwargs):
        seen.append(kwargs)
        return dict(action='no_order',status='D2_CASH_POLICY_INCOMPLETE',formal_eligibility=False)
    monkeypatch.setattr(e2,'read_d2_cash_policy_e2_input',project)
    before=list(calls)
    response=client.get(path+'/'+task_id+'/e2-input')
    assert response.status_code==200 and response.json()['status']=='D2_CASH_POLICY_INCOMPLETE'
    assert seen[0]['service'].base==service.base and calls==before
    assert client.post(path+'/'+task_id+'/cancel').json()['status']=='CANCELLED'
    assert client.post(path+'/'+task_id+'/resume').json()['status']=='QUEUED'
    assert calls[-2:]==[('resume',task_id),('run',task_id)]
    assert not data.provider_calls


def test_split_d2_e2_read_and_annual_history_are_explicit_and_read_only(api, monkeypatch):
    from value_investment_agent.application.research import operating_horizon_cash_policy_e2_v1 as e2
    from value_investment_agent.application.research.agent_review.operating_horizon_task_v2 import OperatingHorizonTaskService
    client, secret, data, root = api
    cash_id = 'rt-' + 'a' * 32
    annual_id = 'rt-' + 'b' * 32
    history = BASE + '/horizon-tasks?symbol=600323'
    joined = BASE + '/cash-policy-tasks/' + cash_id + '/e2-input?annual_task_id=' + annual_id
    before = state(root)
    assert client.get(history).status_code == 401
    assert client.get(joined).status_code == 401
    unlock(client, secret)
    monkeypatch.setattr(OperatingHorizonTaskService, 'list_for_symbol',
                        lambda self, symbol: [dict(task_id=annual_id, symbol=symbol,
                            status='SUCCEEDED', action='no_order', formal_eligibility=False)])
    listed = client.get(history)
    assert listed.status_code == 200 and listed.json()['items'][0]['task_id'] == annual_id
    assert client.get(BASE + '/horizon-tasks?symbol=bad').status_code == 422
    seen = []
    def project(**kwargs):
        seen.append(kwargs)
        return dict(status='SOURCE_BOUND_SPLIT_D2_READY_FOR_E2', action='no_order',
            formal_eligibility=False, condition_price=None)
    monkeypatch.setattr(e2, 'read_split_d2_e2_input', project)
    response = client.get(joined)
    assert response.status_code == 200
    assert response.json()['formal_eligibility'] is False
    assert seen[0]['annual_task_id'] == annual_id and seen[0]['cash_task_id'] == cash_id
    assert seen[0]['root'] == root
    assert not data.provider_calls and state(root) == before


def test_anchored_annual_v3_uses_existing_authorized_task_lifecycle(api, monkeypatch):
    from value_investment_agent.application.research.agent_review.notice_task_dispatch_v1 import NoticeAwareTaskService
    client, secret, data, root = api
    task_id = 'rt-' + 'c' * 32
    path = BASE + '/horizon-v3-tasks'
    body = dict(symbol='600323', request_key='TEST_ONLY_annual_v3', years=[2026])
    before = state(root)
    assert client.post(path, json=body).status_code == 401
    assert client.get(path + '/' + task_id).status_code == 401
    assert state(root) == before
    unlock(client, secret)
    calls = []
    monkeypatch.setattr(NoticeAwareTaskService, 'create',
        lambda self, **kw: (calls.append(('create', kw)) or
            dict(task_id=task_id, symbol='600323', status='QUEUED', action='no_order',
                 formal_eligibility=False, workflow='operating-horizon-task-v3')))
    monkeypatch.setattr(NoticeAwareTaskService, 'run',
                        lambda self, id: calls.append(('run', id)))
    monkeypatch.setattr(NoticeAwareTaskService, 'read',
                        lambda self, id: dict(task_id=id, symbol='600323',
                            status='SUCCEEDED', action='no_order', formal_eligibility=False,
                            workflow='operating-horizon-task-v3'))
    created = client.post(path, json=body)
    assert created.status_code == 202 and calls == [('create', body), ('run', task_id)]
    assert client.get(path + '/' + task_id).json()['workflow'] == 'operating-horizon-task-v3'
    assert client.post(path, json={**body, 'max_run_cost': '100'}).status_code == 422
    assert state(root) == before and not data.provider_calls
