"""TEST_ONLY application wiring; does not prove strategy or real-data quality."""
from datetime import datetime, timezone
from pathlib import Path
import json
import pytest
from value_investment_agent.application.research import sse_value_refresh_v1 as app
from value_investment_agent.application.research import value_enrichment_batch as enrichment


@pytest.fixture
def cycle(tmp_path, monkeypatch):
    (tmp_path/'.tmp').mkdir()
    source=tmp_path/'runtime/source.json';source.parent.mkdir();source.write_text('{}')
    ref=app.pipeline._binding(tmp_path,source)
    (tmp_path/app.screen.POINTER).write_text(json.dumps({'manifest':ref}))
    calls=[]
    def prepare(**kw):
        calls.append(('prepare',kw['execution_budget'],kw['allow_network']))
        folder=kw['output_path'].parent;folder.mkdir(parents=True)
        q=dict(candidate_count=2,tracking_count=1,deep_research_priority=[],
            evidence_enrichment_work_queue=[dict(symbol='600001',tracking_selected=True)])
        kw['output_path'].write_text(json.dumps(q))
        execution=None
        if kw['execution_budget']:
            p=folder/'execution.json';p.write_text(json.dumps(dict(attempted_count=1,status='COMPLETED_WITH_GAPS')))
            execution=app.pipeline._binding(tmp_path,p)
        p=folder/'manifest.json';p.write_text(json.dumps(dict(execution=execution)))
        return dict(queue=app.pipeline._binding(tmp_path,kw['output_path']),manifest=app.pipeline._binding(tmp_path,p))
    monkeypatch.setattr(app.pipeline,'prepare_sse_research_run',prepare)
    monkeypatch.setattr(enrichment,'reobserve_registered_public_adoptions',
        lambda **kw:dict(status='TEST_ONLY_UNCHANGED',items=[]),raising=False)
    from value_investment_agent.application.research.agent_review import operating_task_v2
    monkeypatch.setattr(operating_task_v2,'model_configuration',lambda root:{'research_contract':'TEST_ONLY'})
    monkeypatch.setattr(operating_task_v2,'research_context',lambda context,**kw:context)
    return tmp_path,calls


def test_finite_batches_have_final_consumption_and_no_model_calls(cycle):
    root,calls=cycle
    result=app.run_value_research_refresh(root=root,output_dir=root/'runtime/cycle',enrichment_batches=2)
    assert calls==[('prepare',0,False),('prepare',3,False),('prepare',3,False),('prepare',0,False)]
    assert result['operating_research']==[] and len(result['batches'])==2
    assert result['status']=='PARTIAL' and result['orders_created']==0
    assert result['formal_eligibility'] is False
    assert json.loads((root/'runtime/cycle/cycle.json').read_bytes())['latest_research']==result['latest_research']


@pytest.mark.parametrize('kwargs',[{'enrichment_batches':True},{'enrichment_batches':11},
    {'operating_budget':4},{'tracking_budget':0},{'source_mode':'TODAY'},
    {'source_mode':'FRESH','allow_network':False}])
def test_invalid_or_unauthorized_budget_has_no_output(cycle,kwargs):
    root,_=cycle
    with pytest.raises(ValueError):
        app.run_value_research_refresh(root=root,output_dir=root/'runtime/no-write',**kwargs)
    assert not (root/'runtime/no-write').exists()


def test_cancel_records_real_stop_without_running_queue(cycle):
    root,calls=cycle
    result=app.run_value_research_refresh(root=root,output_dir=root/'runtime/cancel',cancelled=lambda:True)
    assert result['status']=='CANCELLED' and not calls
    assert result['latest_research'] is None


def test_source_failure_retains_previous_run_and_records_error(cycle,monkeypatch):
    root,calls=cycle
    sentinel=root/'runtime/prior.json';sentinel.write_bytes(b'unchanged')
    def fail(**kw):raise ValueError('TEST_ONLY_SOURCE_CONFLICT')
    monkeypatch.setattr(app.pipeline,'prepare_sse_research_run',fail)
    result=app.run_value_research_refresh(root=root,output_dir=root/'runtime/failed')
    assert result['status']=='FAILED' and 'SOURCE_CONFLICT' in result['stop_reason']
    assert sentinel.read_bytes()==b'unchanged'


def test_explicit_fresh_refresh_invokes_existing_collector_then_queue(cycle,monkeypatch):
    root,calls=cycle
    monkeypatch.setattr(app.screen,'refresh',lambda **kw:calls.append(('refresh',kw['allow_network'])))
    result=app.run_value_research_refresh(root=root,output_dir=root/'runtime/fresh',
        source_mode='FRESH',allow_network=True,enrichment_batches=1)
    assert calls[0]==('refresh',True)
    assert ('prepare',3,True) in calls
    assert result['network_authorized'] is True


def test_operating_tasks_use_existing_service_and_finite_explicit_budget(cycle,monkeypatch):
    from value_investment_agent.application.research.agent_review import operating_sources_v1,operating_task_v2
    root,calls=cycle; seen=[]
    monkeypatch.setattr(operating_sources_v1,'build_operating_source_context',lambda **kw:dict(source_binding={'path':'runtime/TEST_ONLY.json','sha256':'a'*64}))
    monkeypatch.setattr(operating_task_v2,'implementation',lambda: {'TEST_ONLY':'1'})
    class Service:
        def __init__(self,root):pass
        def create(self,**kw):
            seen.append(kw);return dict(task_id='rt-test',status='QUEUED')
        def run(self,task_id):
            return dict(task_id=task_id,status='SUCCEEDED',new_llm_calls=3)
    monkeypatch.setattr(operating_task_v2,'LiveOperatingTaskService',Service)
    result=app.run_value_research_refresh(root=root,output_dir=root/'runtime/operating',enrichment_batches=0,operating_budget=1)
    assert len(seen)==1 and result['new_llm_calls']==3
    assert result['operating_research'][0]['status']=='SUCCEEDED'
    assert result['formal_eligibility'] is False and result['status']=='PARTIAL'


def test_no_due_work_stops_loop_but_still_consumes(cycle,monkeypatch):
    root,calls=cycle
    real=app.pipeline.prepare_sse_research_run
    def no_due(**kw):
        r=real(**kw)
        if kw['execution_budget']:
            mp=root/r['manifest']['path'];m=json.loads(mp.read_bytes());p=root/m['execution']['path'];p.write_text(json.dumps(dict(attempted_count=0,status='COMPLETED_WITH_GAPS')));m['execution']=app.pipeline._binding(root,p);mp.write_text(json.dumps(m));r['manifest']=app.pipeline._binding(root,mp)
        return r
    monkeypatch.setattr(app.pipeline,'prepare_sse_research_run',no_due)
    result=app.run_value_research_refresh(root=root,output_dir=root/'runtime/no-due',enrichment_batches=10)
    assert len(result['batches'])==1 and calls[-1][1]==0
    assert result['stop_reason'].startswith('NO_DUE')


def test_parser_update_replays_bound_inputs_without_restamping_originals(cycle,monkeypatch):
    root,calls=cycle
    pointer=json.loads((root/app.screen.POINTER).read_bytes())
    source=root/pointer['manifest']['path'];source.write_text(json.dumps({'implementation':{'old':'1'},'inputs':{'retained_clock':'2026-11-01'}}))
    pointer['manifest']=app.pipeline._binding(root,source);(root/app.screen.POINTER).write_text(json.dumps(pointer))
    monkeypatch.setattr(app.screen,'implementation',lambda:{'new':'2'})
    def publish(**kw):
        assert kw['inputs']=={'retained_clock':'2026-11-01'}
        calls.append(('source-reobservation',kw['inputs']))
        return {'manifest':pointer['manifest']}
    monkeypatch.setattr(app.screen,'publish_inputs',publish)
    result=app.run_value_research_refresh(root=root,output_dir=root/'runtime/parser-change',enrichment_batches=0)
    assert calls[0][0]=='source-reobservation'
    assert any(e['stage']=='SOURCE_IMPLEMENTATION_REOBSERVATION' for e in result['stages'])
    assert result['source_mode']=='RETAINED' and not result['network_authorized']


def test_missing_first_company_source_does_not_starve_next_company(cycle,monkeypatch):
    from value_investment_agent.application.research.agent_review import operating_sources_v1,operating_task_v2
    root,calls=cycle; real=app.pipeline.prepare_sse_research_run; ran=[]
    def prepare(**kw):
        r=real(**kw);p=root/r['queue']['path'];q=json.loads(p.read_bytes())
        q['evidence_enrichment_work_queue'].append(dict(symbol='600002',tracking_selected=True))
        p.write_text(json.dumps(q));r['queue']=app.pipeline._binding(root,p);return r
    monkeypatch.setattr(app.pipeline,'prepare_sse_research_run',prepare)
    def context(**kw):
        if kw['symbol']=='600001':raise ValueError('TEST_ONLY_NO_ORIGINAL')
        return {'source_binding':{'path':'runtime/TEST_ONLY.json','sha256':'a'*64}}
    monkeypatch.setattr(operating_sources_v1,'build_operating_source_context',context)
    monkeypatch.setattr(operating_task_v2,'implementation',lambda:{})
    class Service:
        def __init__(self,root):pass
        def create(self,**kw):ran.append(kw['symbol']);return {'task_id':'rt-test','status':'QUEUED'}
        def run(self,task_id):return {'task_id':task_id,'status':'SUCCEEDED','new_llm_calls':3}
    monkeypatch.setattr(operating_task_v2,'LiveOperatingTaskService',Service)
    result=app.run_value_research_refresh(root=root,output_dir=root/'runtime/continue',enrichment_batches=0,operating_budget=1)
    assert ran==['600002'] and result['new_llm_calls']==3
    assert [r['status'] for r in result['operating_research']]==['BLOCKED','SUCCEEDED']


def test_verified_zero_candidates_is_not_source_failure(cycle,monkeypatch):
    root,calls=cycle;real=app.pipeline.prepare_sse_research_run
    def empty(**kw):
        r=real(**kw);p=root/r['queue']['path'];q=json.loads(p.read_bytes());q.update(candidate_count=0,tracking_count=0,evidence_enrichment_work_queue=[])
        p.write_text(json.dumps(q));r['queue']=app.pipeline._binding(root,p);return r
    monkeypatch.setattr(app.pipeline,'prepare_sse_research_run',empty)
    def unexpected(**kw):raise AssertionError('No reobservation without candidates')
    monkeypatch.setattr(enrichment,'reobserve_registered_public_adoptions',unexpected)
    result=app.run_value_research_refresh(root=root,output_dir=root/'runtime/zero',enrichment_batches=0)
    assert result['status']=='PARTIAL' and result['stop_reason'] is None
    assert result['reobservations'][0]['status']=='NO_TRACKED_CANDIDATES'


@pytest.mark.parametrize('locked',[False,True])
def test_reused_model_calls_and_lock_contention_are_not_new_calls(cycle,monkeypatch,locked):
    from value_investment_agent.application.research.agent_review import operating_sources_v1,operating_task_v2
    root,calls=cycle;ran=[]
    monkeypatch.setattr(operating_sources_v1,'build_operating_source_context',lambda **kw:{'source_binding':{'path':'runtime/TEST_ONLY.json','sha256':'a'*64}})
    monkeypatch.setattr(operating_task_v2,'implementation',lambda:{})
    class Service:
        def __init__(self,root):pass
        def create(self,**kw):
            if locked:raise app.LockTimeout('TEST_ONLY_BUSY')
            return {'task_id':'rt-old','status':'SUCCEEDED','new_llm_calls':3}
        def run(self,task_id):ran.append(task_id);raise AssertionError('Do not rerun completed research')
    monkeypatch.setattr(operating_task_v2,'LiveOperatingTaskService',Service)
    result=app.run_value_research_refresh(root=root,output_dir=root/'runtime/reused',enrichment_batches=0,operating_budget=1)
    assert result['new_llm_calls']==0 and not ran and result['status']=='PARTIAL'
    assert result['operating_research'][0]['status']==('BLOCKED' if locked else 'SUCCEEDED')
    assert (root/'runtime/reused/cycle.json').is_file()


def test_driver_calendar_preflight_blocks_missing_baseline_before_task_or_fees(cycle,monkeypatch):
    from value_investment_agent.application.research.agent_review import operating_sources_v1,operating_task_v2
    root,_=cycle; calls=[]
    monkeypatch.setattr(operating_sources_v1,'build_operating_source_context',lambda **kw:dict(as_of='2026-11-03',evidence=[]))
    monkeypatch.setattr(operating_task_v2,'model_configuration',lambda root:{'research_contract':'operating-drivers-v2'})
    class Service:
        def __init__(self,root):pass
        def create(self,**kw):calls.append(kw);raise AssertionError('No task before valid baseline')
    monkeypatch.setattr(operating_task_v2,'LiveOperatingTaskService',Service)
    result=app.run_value_research_refresh(root=root,output_dir=root/'runtime/no-baseline',enrichment_batches=0,operating_budget=1)
    assert not calls and result['new_llm_calls']==0
    assert result['operating_research'][0]['reason']=='ValueError:VERIFIED_BASELINE_REQUIRED'
