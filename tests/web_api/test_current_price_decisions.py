import hashlib
import json

import pytest
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


def test_changed_daily_selection_blocks_frozen_action_conditions(tmp_path, monkeypatch):
    _fixture(tmp_path)
    case = capture(tmp_path)
    plan = project_current_price_action_plan(case)
    plan.update(decision_id="hotspot-600519", case_path=case["case_path"], case_sha256=case["case_sha256"],
                daily_selection_binding={"path": "runtime/missing-daily-selection.json", "sha256": "0" * 64})
    packet = {"publication_id": "pub-current", "price_conditions": {"items": [
        {"symbol": "600519", "company_name": "Moutai", "price_action_plan": plan}]}}
    monkeypatch.setattr(module, "_load_snapshot", lambda root: (packet, None))
    loader = module.load_current_price_case
    monkeypatch.setattr(module, "load_current_price_case", lambda **kwargs: loader(**kwargs, now=NOW))
    client = TestClient(module.create_app(tmp_path))
    plan = client.get("/api/v1/daily-decisions").json()["sections"]["hotspot"][0]["price_action_plan"]
    assert plan["signal_state"] == "BLOCKED"
    assert plan["entry_condition"] is None and plan["entry_trigger_price"] is None
    assert plan["formal_eligibility"] is False and plan["portfolio_eligibility"] is None
    # Case originals are still valid: the selection guard alone must suppress
    # every top-level price, signal and bar returned by the chart endpoint.
    chart = client.get("/api/v1/current-price-case/600519").json()
    assert chart["status"] == "UNAVAILABLE"
    assert not {"levels", "bars", "current_reference_price", "signal_state"}.intersection(chart)


def test_selection_original_tamper_suppresses_chart_with_valid_case(tmp_path, monkeypatch):
    from value_investment_agent.domain.hotspot.daily_selection import rank_daily_candidates
    from value_investment_agent.application.hotspot.daily_selection import verify_daily_selection
    _fixture(tmp_path)
    case = capture(tmp_path)
    directory = tmp_path / "runtime/TEST_ONLY-selection"
    directory.mkdir()
    classification = directory / "classification.json"
    classification.write_text(json.dumps({"fetched_at": NOW.isoformat(),
        "rows": [{"code": "600519", "name": "Moutai", "class": "TEST_ONLY"}]}), encoding="utf-8")
    calendar = directory / "calendar.json"
    calendar.write_text("{}", encoding="utf-8")
    fields = [""] * 40
    for index, value in {1: "Moutai", 2: "600519", 3: "10", 4: "10", 30: "20261014150000", 37: "50"}.items():
        fields[index] = value
    original = directory / "quotes.txt"
    original.write_bytes(('v_sh600519="' + '~'.join(fields) + '";').encode("gb18030"))

    def binding(path):
        return {"path": path.relative_to(tmp_path).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    quote = {"symbol": "600519", "company_name": "Moutai", "industry": "TEST_ONLY", "close": "10",
        "change_percent": "0", "amount_cny": "500000", "trade_date": "2026-10-14",
        "status": "DATED_COMPLETED_QUOTE", "sha256": binding(original)["sha256"],
        "available_at": NOW.isoformat(), "source_url": "https://qt.gtimg.cn/q=sh600519",
        "classification_available_at": NOW.isoformat()}
    ranking = rank_daily_candidates([quote], trade_date="2026-10-14")
    report = {"schema_version": "hotspot-daily-selection-v1", "action": "no_order", "trade_date": "2026-10-14",
        "limit": 5, "rows": [quote], "ranking": ranking, "observation_list": ranking["candidates"],
        "hotspot_watch_queue": ranking["candidates"], "source_bindings": [binding(classification), binding(calendar),
            {**binding(original), "available_at": quote["available_at"], "source_url": quote["source_url"]}]}
    verify_daily_selection(tmp_path, report)
    report_path = directory / "report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    plan = project_current_price_action_plan(case)
    plan.update(decision_id="hotspot-600519", case_path=case["case_path"], case_sha256=case["case_sha256"],
        daily_selection_binding=binding(report_path), daily_selection=ranking["candidates"][0])
    packet = {"publication_id": "pub-current", "price_conditions": {"items": [
        {"symbol": "600519", "company_name": "Moutai", "price_action_plan": plan}]}}
    monkeypatch.setattr(module, "_load_snapshot", lambda root: (packet, None))
    loader = module.load_current_price_case
    monkeypatch.setattr(module, "load_current_price_case", lambda **kwargs: loader(**kwargs, now=NOW))
    client = TestClient(module.create_app(tmp_path))
    assert "bars" in client.get("/api/v1/current-price-case/600519").json()
    original.write_bytes(original.read_bytes() + b"TAMPER")
    detail = client.get("/api/v1/decisions/hotspot-600519").json()["decision"]
    assert detail["price_action_plan"]["signal_state"] == "BLOCKED"
    chart = client.get("/api/v1/current-price-case/600519").json()
    assert chart["status"] == "UNAVAILABLE" and "bars" not in chart and "levels" not in chart


@pytest.mark.parametrize("change", ["retire", "remove_registry"])
def test_changed_registry_invalidates_frozen_current_candidate(tmp_path, monkeypatch, change):
    _fixture(tmp_path)
    case = capture(tmp_path)
    plan = project_current_price_action_plan(case)
    plan.update(decision_id="hotspot-600519", case_path=case["case_path"], case_sha256=case["case_sha256"])
    registry = {"schema_version": "current-price-conditions-v1", "action": "no_order",
        "items": [{"symbol": "600519", "case_path": case["case_path"], "case_sha256": case["case_sha256"]}],
        "previous_items": []}
    path = tmp_path / "config/current-price-conditions.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(registry), encoding="utf-8")
    packet = {"publication_id": "pub-current", "price_conditions": {"items": [
        {"symbol": "600519", "company_name": "Moutai", "price_action_plan": plan}]},
        "identity_inputs": {"current_price_conditions": {"path": "config/current-price-conditions.json",
            "observed_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}}}
    monkeypatch.setattr(module, "_load_snapshot", lambda root: (packet, None))
    loader = module.load_current_price_case
    monkeypatch.setattr(module, "load_current_price_case", lambda **kwargs: loader(**kwargs, now=NOW))
    client = TestClient(module.create_app(tmp_path))
    assert client.get("/api/v1/current-price-case/600519").json()["bars"] == case["bars"]
    if change == "retire":
        registry["previous_items"] = registry["items"]
        registry["items"] = []
        path.write_text(json.dumps(registry), encoding="utf-8")
    else:
        path.unlink()
    daily = client.get("/api/v1/daily-decisions").json()["sections"]["hotspot"][0]
    detail = client.get("/api/v1/decisions/hotspot-600519").json()["decision"]
    assert daily == detail
    blocked = detail["price_action_plan"]
    assert blocked["signal_state"] == "BLOCKED"
    assert blocked["current_reference_price"] is None and blocked["levels"] == {}
    assert blocked["action_eligibility"] is False
    chart = client.get("/api/v1/current-price-case/600519").json()
    assert chart["status"] == "UNAVAILABLE" and "bars" not in chart
