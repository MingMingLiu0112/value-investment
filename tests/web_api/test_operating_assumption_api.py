import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from value_investment_agent.presentation.web_api.app import create_app
"""Public D2 contract: missing sources is not a positive investment conclusion."""
from test_web_agent_research import state
from web_api.test_held_continuity_api import client_for


def test_public_d2_missing_source_reads_without_unlock_or_write(tmp_path,monkeypatch):
    client,_=client_for(tmp_path,tmp_path/"TEST_ONLY.jsonl",monkeypatch)
    before=state(tmp_path)
    response=client.get("/api/v1/research-assumption-drafts/600519")
    assert response.status_code==200
    assert response.headers["cache-control"]=="no-store"
    result=response.json()
    assert result["status"]=="MISSING_SOURCE"
    assert result["symbol"]=="600519"
    assert not result["branches"] and result["formal_eligibility"] is False
    assert result["action"]=="no_order"
    assert state(tmp_path)==before
    assert client.get("/api/v1/research-assumption-drafts/bad").status_code==422


@pytest.mark.parametrize("symbol",["600519","600887"])
def test_real_d2_api_consumes_recomputed_capital_paths(symbol):
    location=os.environ.get("VALUE_OPERATING_ASSUMPTION_REAL_ROOT")
    if not location:
        pytest.skip("Explicit original-source root required")
    root=Path(location)
    with TestClient(create_app(root,port=8791),base_url="http://127.0.0.1:8791",client=("127.0.0.1",51000)) as client:
        response=client.get("/api/v1/research-assumption-drafts/"+symbol)
        assert response.status_code==200,response.text
        result=response.json()
    assert result["status"]=="SOURCE_BOUND_D2_DRAFT",result.get("reason")
    assert result["symbol"]==symbol and len(result["branches"])==3
    assert result["capital_path_recomputed"] and not result["valuation_computed"]
    assert result["action"]=="no_order" and result["formal_eligibility"] is False
    assert all(len(scenario["operating_capital_path"]["rows"])==10
        for branch in result["branches"] for scenario in branch["scenarios"].values())
