"""TEST_ONLY public C transport; actual retained-source validation is separate."""
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from value_investment_agent.presentation.web_api.app import create_app
from value_investment_agent.application.research import company_profile

def test_profile_endpoint_is_public_read_only_and_bound_to_requested_symbol(tmp_path, monkeypatch):
    calls = []
    def load(*, root, symbol, now):
        assert root == tmp_path
        assert now.utcoffset() is not None
        calls.append(symbol)
        return dict(schema_version="company-research-profile-v1", symbol=symbol,
            status="UNASSESSABLE", action="no_order", formal_eligibility=False,
            blockers=["TEST_ONLY_NO_SOURCE"], route=None, profile=None)
    monkeypatch.setattr(company_profile, "load_company_profile", load)
    before = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*"))
    client = TestClient(create_app(tmp_path))
    response = client.get("/api/v1/research-profiles/600519")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["symbol"] == "600519"
    assert response.json()["formal_eligibility"] is False
    assert calls == ["600519"]
    assert sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*")) == before

def test_invalid_symbol_never_calls_source_loader(tmp_path, monkeypatch):
    def forbidden(**kwargs):
        raise AssertionError("invalid symbol reached loader")
    monkeypatch.setattr(company_profile, "load_company_profile", forbidden)
    assert TestClient(create_app(tmp_path)).get("/api/v1/research-profiles/not-a-symbol").status_code == 422

def test_corrupt_profile_sources_fail_closed_without_leaking_a_route(tmp_path, monkeypatch):
    def rejected(**kwargs):
        raise ValueError("TEST_ONLY source mismatch")
    monkeypatch.setattr(company_profile, "load_company_profile", rejected)
    data = TestClient(create_app(tmp_path)).get("/api/v1/research-profiles/600519").json()
    assert data["status"] == "SOURCE_OR_PROFILE_UNAVAILABLE"
    assert data["route"] is None and data["formal_eligibility"] is False
    assert data["evidence_refs"] == []
