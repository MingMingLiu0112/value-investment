"""TEST_ONLY fixtures exercise scope before budgets and the real shared engine."""
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
import json
import pytest
from value_investment_agent.application.discovery import sse_main_screening as app
from test_m2_opportunity_discovery import _official_payload,_tencent_payload,_sina_payload,_dividend_payload,_financial_points

NOW=datetime(2026,11,2,6,tzinfo=timezone.utc)


@pytest.fixture
def inputs(tmp_path,monkeypatch):
    payload=dict(official=_official_payload(),tencent=_tencent_payload(),sina=_sina_payload(),
                 dividend=_dividend_payload(),financial=dict(points=_financial_points()))
    for k in ['tencent','sina','dividend']:payload[k]['fetched_at']='2026-11-02T03:00:00+00:00'
    payload['official'].update(complete=False,scope='SSE_MAIN_A_ONLY')
    manifest=dict(status='COMPLETE_INPUTS',finished_at='2026-11-02T03:01:00+00:00',
                  inputs={k:dict(path='runtime/sse-main-screening/'+k+'.json',sha256='a'*64,
                                fetched_at='2026-11-02T03:00:00+00:00') for k in payload})
    monkeypatch.setattr(app.sources,'verify_inputs',lambda *a,**kw:deepcopy(payload))
    return tmp_path,manifest,payload


def test_shared_engine_scoped_before_budget_and_no_formal_action(inputs):
    root,manifest,payload=inputs
    # Unrelated 50 outside-scope cheap companies cannot consume the main-board budget.
    for n in range(50):
        payload['tencent']['rows'].append(dict(payload['tencent']['rows'][0],code='sz'+str(100000+n)))
    result,receipt=app.compile_inputs(root=root,inputs=manifest,now=NOW,run_id='TEST_ONLY')
    assert result['counts']['universe']==4
    assert len(result['rows'])==4 and all(r['symbol'].startswith('600') for r in result['rows'])
    assert any(r['status']=='CANDIDATE' for r in result['rows'])
    assert not result['buy_eligible'] and not result['formal_eligibility']
    assert result['quote_date'] is None and result['quote_date_verified'] is False
    assert len({r['symbol'] for r in result['rows']})==4


@pytest.mark.parametrize('field,value',[('exchange','SZSE'),('board','科创板'),('security_type','境内存托凭证')])
def test_wrong_scope_rejected(inputs,field,value):
    root,manifest,payload=inputs;payload['official']['records'][0][field]=value
    with pytest.raises(ValueError,match='SSE_MAIN_A'):app.compile_inputs(root=root,inputs=manifest,now=NOW,run_id='TEST_ONLY')


def test_publish_read_replay_pages_and_get_is_readonly(inputs):
    root,manifest,payload=inputs
    output=root/'runtime/sse-main-screening/test';output.mkdir(parents=True)
    app.publish_inputs(root=root,inputs=manifest,output=output,run_id='TEST_ONLY')
    before={p.relative_to(root): (p.read_bytes(),p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()}
    now=datetime.now(timezone.utc)
    a=app.read_screen(root=root,now=now,status='ALL',limit=2)
    b=app.read_screen(root=root,now=now,status='ALL',offset=2,limit=2)
    assert a['pagination']['total']==4, a
    assert set(r['symbol'] for r in a['items']).isdisjoint(r['symbol'] for r in b['items'])
    assert sum(a['counts'][k] for k in ['candidate','excluded','unassessable'])==4
    q=app.read_screen(root=root,now=now,status='ALL',query='600001')
    assert [r['symbol'] for r in q['items']]==['600001']
    after={p.relative_to(root): (p.read_bytes(),p.stat().st_mtime_ns) for p in root.rglob('*') if p.is_file()}
    assert before==after
    pointer=json.loads((root/app.POINTER).read_bytes())
    source=app._read(root,pointer['manifest'])
    (root/source['result']['path']).write_bytes(b'{}')
    broken=app.read_screen(root=root,now=now)
    assert broken['status']=='UNAVAILABLE' and broken['pagination']['total'] is None


def test_no_pointer_does_not_claim_zero_candidates(tmp_path):
    out=app.read_screen(root=tmp_path,now=NOW)
    assert out['status']=='UNAVAILABLE' and out['pagination']['total'] is None


def test_api_public_no_scan_and_query_validation(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from value_investment_agent.presentation.web_api.app import create_app
    calls=[]
    def read(**kwargs):calls.append(kwargs);return dict(action='no_order',status='PARTIAL',items=[])
    monkeypatch.setattr(app,'read_screen',read)
    client=TestClient(create_app(tmp_path))
    assert client.get('/api/v1/value-screening/sse-main?offset=20&status=EXCLUDED').status_code==200
    assert calls[0]['offset']==20 and calls[0]['status']=='EXCLUDED'
    for query in ['limit=0','offset=-1','status=BUY']:
        assert client.get('/api/v1/value-screening/sse-main?'+query).status_code==422


def test_failed_refresh_preserves_last_valid_snapshot(inputs,monkeypatch):
    root,manifest,payload=inputs
    output=root/'runtime/sse-main-screening/retained'
    app.publish_inputs(root=root,inputs=manifest,output=output,run_id='TEST_ONLY')
    before=(root/app.POINTER).read_bytes()
    def unavailable(*args,**kwargs):raise OSError('TEST_ONLY_PROVIDER_UNAVAILABLE')
    monkeypatch.setattr(app.sources,'collect_inputs',unavailable)
    with pytest.raises(OSError):
        app.refresh(root=root,allow_network=True)
    assert (root/app.POINTER).read_bytes()==before
    view=app.read_screen(root=root,now=datetime.now(timezone.utc),status='ALL')
    assert view['pagination']['total']==4


def test_source_order_not_economic_change(inputs):
    root,manifest,payload=inputs
    first=app.compile_inputs(root=root,inputs=manifest,now=NOW,run_id='TEST_ONLY')
    manifest['inputs']=dict(reversed(list(manifest['inputs'].items())))
    second=app.compile_inputs(root=root,inputs=manifest,now=NOW,run_id='TEST_ONLY')
    assert app._bytes(first)==app._bytes(second)


def test_display_budget_preserves_economic_entry_reason(inputs):
    root,manifest,payload=inputs
    for n in range(60):
        symbol=str(600100+n)
        payload['official']['records'].append(dict(payload['official']['records'][0],symbol=symbol,name='样本'+str(n)))
        payload['tencent']['rows'].append(dict(payload['tencent']['rows'][0],code='sh'+symbol,name='样本'+str(n)))
        payload['sina']['rows'].append(dict(payload['sina']['rows'][0],code=symbol,name='样本'+str(n)))
    result,_=app.compile_inputs(root=root,inputs=manifest,now=NOW,run_id='TEST_ONLY')
    budget=[r for r in result['rows'] if any(e['status']=='BUDGET_EXCLUDED' for e in r['channel_evaluations'])]
    assert budget
    for row in budget:
        assert row['status']=='CANDIDATE'
        assert '市盈率' in row['reason']
        assert '超出单通道展示预算' not in row['reason']
