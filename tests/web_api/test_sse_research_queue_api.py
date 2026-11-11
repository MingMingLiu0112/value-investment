"""TEST_ONLY API wiring; no account session or financial approval required."""
from datetime import datetime,timezone
from fastapi.testclient import TestClient
from value_investment_agent.presentation.web_api.app import create_app
from value_investment_agent.application.research import sse_research_pipeline_v1 as pipeline


def test_public_queue_endpoint_is_independent_of_private_session(tmp_path,monkeypatch):
    calls=[]
    def read(**kwargs):
        calls.append(kwargs)
        return dict(schema_version=pipeline.VERSION,action='no_order',scope='SSE_MAIN_A_ONLY',status='AVAILABLE',source_status='TEST_ONLY',source_available_at=datetime.now(timezone.utc).isoformat(),generated_at=datetime.now(timezone.utc).isoformat(),total_candidates=3,tracking_count=0,items=[],blockers=[],queue_binding=None,history_available=False)
    monkeypatch.setattr(pipeline,'read_sse_research_pool',read)
    with TestClient(create_app(tmp_path)) as client:
        response=client.get('/api/v1/value-screening/sse-main/research-queue')
    assert response.status_code==200 and response.json()['action']=='no_order'
    assert response.headers['cache-control']=='no-store' and calls[0]['root']==tmp_path.resolve()


def test_source_failure_reports_unknown_not_zero(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        response=client.get('/api/v1/value-screening/sse-main/research-queue')
    payload=response.json()
    assert payload['status']=='UNAVAILABLE' and payload['total_candidates'] is None and payload['tracking_count'] is None
    assert not payload['history_available'] and payload['action']=='no_order'

def test_new_sse_company_detail_does_not_require_legacy_shortlist(tmp_path,monkeypatch):
    from value_investment_agent.application.discovery import dual_strategy_selection,sse_main_screening,value_candidate_selection
    from value_investment_agent.application.research import value_research_analysis,value_enrichment_batch
    monkeypatch.setattr(value_research_analysis,'load_current_value_research_analysis',lambda **kw:None)
    monkeypatch.setattr(value_candidate_selection,'load_current_public_candidate_research',lambda **kw:None)
    monkeypatch.setattr(dual_strategy_selection,'build_dual_strategy_selection',lambda **kw:dict(value=dict(items=[],quote_date=None),hotspot=dict(items=[])))
    monkeypatch.setattr(value_enrichment_batch,'read_verified_enrichment_progress',lambda **kw:None)
    def screen(**kw):
        return dict(status='PARTIAL',available_at='2026-11-02T00:00:00+00:00',source_refs=[],items=[dict(symbol='600066',name='TEST_ONLY_SOURCE_COMPANY',status='CANDIDATE',reason='TEST_ONLY_SOURCE_REASON',gaps=['TEST_ONLY_QUALITY_PENDING'],industry='TEST_ONLY',channels=['value'],quote_date=None,channel_evaluations=[])])
    monkeypatch.setattr(sse_main_screening,'read_screen',screen)
    with TestClient(create_app(tmp_path)) as client:
        response=client.get('/api/v1/decisions/600066?strategy=value')
    payload=response.json()
    assert response.status_code==200 and payload['status']=='RESEARCH_ONLY'
    assert payload['selection_candidate']['reasons']==['TEST_ONLY_SOURCE_REASON']
    assert payload['decision']['name']=='TEST_ONLY_SOURCE_COMPANY'
    assert payload['formal_eligibility'] is False and payload['trade_eligible'] is False
    assert payload['selection_candidate']['quote_date'] is None
    assert payload['action']=='no_order'
