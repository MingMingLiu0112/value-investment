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
