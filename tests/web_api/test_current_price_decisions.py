from fastapi.testclient import TestClient

from value_investment_agent.presentation.web_api import app as module
from value_investment_agent.application.hotspot.price_action_case import project_current_price_action_plan
from test_hotspot_current_price_case import capture, NOW
from test_read_api import _fixture


def test_frozen_current_daily_detail_chart_and_tamper(tmp_path, monkeypatch):
    _fixture(tmp_path)
    case = capture(tmp_path)
    plan = project_current_price_action_plan(case)
    plan.update(decision_id="hotspot-600519", research_version="research-current",
                case_path=case["case_path"], case_sha256=case["case_sha256"])
    packet = {"publication_id": "pub-current", "price_conditions": {"items": [
        {"symbol": "600519", "company_name": "Moutai", "price_action_plan": plan}]}}
    monkeypatch.setattr(module, "_load_snapshot", lambda root: (packet, None))
    loader = module.load_current_price_case
    monkeypatch.setattr(module, "load_current_price_case", lambda **kwargs: loader(**kwargs, now=NOW))
    client = TestClient(module.create_app(tmp_path))
    daily = client.get("/api/v1/daily-decisions").json()
    row = daily["sections"]["hotspot"][0]
    assert row["id"] == "hotspot-600519" and row["price_action_plan"] == plan
    detail = client.get("/api/v1/decisions/hotspot-600519").json()["decision"]
    assert detail == row
    chart = client.get("/api/v1/current-price-case/600519").json()
    assert chart["price_action_plan"] == plan
    assert chart["bars"]["60m"] == case["bars"]["60m"]
    source = tmp_path / case["source_bindings"]["60m"]["path"]
    source.write_bytes(source.read_bytes() + b" ")
    blocked = client.get("/api/v1/daily-decisions").json()["sections"]["hotspot"][0]
    assert blocked["price_action_plan"]["signal_state"] == "BLOCKED"
    assert blocked["price_action_plan"]["entry_trigger_price"] is None
    assert blocked["price_action_plan"]["action_eligibility"] is False
    assert client.get("/api/v1/current-price-case/600519").json()["status"] == "UNAVAILABLE"
    packet["identity_inputs"] = {"chain": [{"role": "changed", "path": "changed", "sha256": "bad"}]}
    assert client.get("/api/v1/daily-decisions").json()["status"] == "UNAVAILABLE"
    assert client.get("/api/v1/decisions/hotspot-600519").json()["status"] == "UNAVAILABLE"
    assert client.get("/api/v1/current-price-case/600519").json()["status"] == "UNAVAILABLE"
