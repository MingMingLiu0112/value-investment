"""Synthetic source-bound prices, real lifecycle engine, no account or network."""
from copy import deepcopy
from datetime import datetime
import json

from fastapi.testclient import TestClient
import pytest

from test_hotspot_lifecycle_bound_history import _history, _assert_no_permission, CURRENT_AT
from value_investment_agent.application.hotspot.price_action_case import project_current_price_action_plan
from value_investment_agent.application.product.hotspot_lifecycle_surface import current_hotspot_lifecycle
from value_investment_agent.presentation.web_api import app as module


@pytest.fixture
def bound_case(tmp_path):
    _, _, _, case = _history(tmp_path)
    plan = project_current_price_action_plan(case)
    plan.update(case_path=case["case_path"], case_sha256=case["case_sha256"], decision_id="hotspot-600519")
    return tmp_path, case, plan


def test_public_current_explanation_does_not_invent_owned_entry(bound_case):
    root, case, plan = bound_case
    original = deepcopy(plan)
    result = current_hotspot_lifecycle(root=root, symbol="600519", plan=plan, now=CURRENT_AT)
    assert result["schema_version"] == "hotspot-entry-structure-continuity-v2"
    assert result["observed_review"] == "WATCH"
    assert result["entry_case_binding"] is None and result["original_entry_comparison"] is None
    assert result["decision_explanation"]["decision_path"][1]["outcome"] == "NOT_SUPPLIED"
    assert result["current_case_binding"] == {"path": case["case_path"], "sha256": case["case_sha256"]}
    _assert_no_permission(result)
    assert plan == original


@pytest.mark.parametrize("field,value", [
    ("symbol", "000333"), ("action", "order"), ("signal_state", "BLOCKED"),
    ("signal_state", "STALE"), ("case_path", "../outside.json"),
    ("case_sha256", "bad"), ("market_trade_date", "2026-09-23"),
    ("candidate_lifecycle", "PREVIOUS_CANDIDATE_NOT_SELECTED_TODAY"),
])
def test_rejected_or_mixed_parent_plan_is_not_revived(bound_case, field, value):
    root, _, plan = bound_case
    plan[field] = value
    assert current_hotspot_lifecycle(root=root, symbol="600519", plan=plan, now=CURRENT_AT) is None


def test_stale_and_changed_originals_do_not_create_current_observations(bound_case):
    root, case, plan = bound_case
    result = current_hotspot_lifecycle(root=root, symbol="600519", plan=plan,
        now=CURRENT_AT.replace(day=28))
    assert result["current_data_status"] == "STALE" and result["observed_review"] == "UNKNOWN"
    assert not result["current_conditions"]
    path = root / case["case_path"]
    original = json.loads(path.read_bytes())
    original["current_reference_price"] = "999"
    path.write_text(json.dumps(original), encoding="utf-8")
    result = current_hotspot_lifecycle(root=root, symbol="600519", plan=plan, now=CURRENT_AT)
    assert result["source_integrity"] == "NOT_VERIFIED" and result["observed_review"] == "UNKNOWN"
    _assert_no_permission(result)


def test_existing_detail_route_replays_lifecycle_without_a_private_account(bound_case, monkeypatch):
    root, case, plan = bound_case
    row = {"symbol": "600519", "company_name": "TEST_ONLY", "price_action_plan": plan}
    packet = {"publication_id": "TEST_ONLY", "research_version": "TEST_ONLY",
              "price_conditions": {"items": [row]}}

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return CURRENT_AT.astimezone(tz) if tz else CURRENT_AT

    monkeypatch.setattr(module, "datetime", Clock)
    monkeypatch.setattr(module, "_load_snapshot", lambda root: (packet, None))
    monkeypatch.setattr(module, "_public", lambda root: {"bindings": []})
    real_loader = module.load_current_price_case
    monkeypatch.setattr(module, "load_current_price_case", lambda **kw: real_loader(**kw, now=CURRENT_AT))
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    client = TestClient(module.create_app(root, bootstrap_secret="TEST_ONLY"))
    response = client.get("/api/v1/decisions/hotspot-600519").json()
    assert response["publication"]["publication_id"] == "TEST_ONLY"
    assert response["decision"]["price_action_plan"] == plan
    _assert_no_permission(response["hotspot_lifecycle_review"])
    assert response["hotspot_lifecycle_review"]["current_case_binding"]["sha256"] == case["case_sha256"]
    assert client.get("/api/v1/decisions/hotspot-000333").json()["hotspot_lifecycle_review"] is None
    assert before == {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
