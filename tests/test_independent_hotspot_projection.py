from copy import deepcopy
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from value_investment_agent.application.hotspot import independent_price_conditions as projection
from value_investment_agent.presentation.web_api.app import create_app


@pytest.fixture
def isolated(monkeypatch):
    plan = {"schema_version": "price-action-plan-current-v1", "symbol": "000333",
        "action": "no_order", "signal_state": "TRIGGER_OBSERVED",
        "model_or_rule_version": "test-rule-v1", "case_path": "case.json", "case_sha256": "a" * 64,
        "blockers": ["VALUE_GATE_NOT_PROVEN"],
        "opportunity_quality": {"structure_tier": "STRUCTURE_QUALIFIED_OBSERVATION"}}
    old = {"items": [{"symbol": "000333", "price_action_plan": plan}]}
    admission = {"namespace": "TEST_ONLY", "rule_version": "test-rule-v1", "blockers": [],
        "risk_review_eligible": True, "gate_source_bindings": {
            "price_structure": [{"path": "case.json", "sha256": "a" * 64}]}}
    monkeypatch.setattr(projection, "load_price_conditions", lambda *a, **kw: old)
    monkeypatch.setattr(projection, "load_independent_admission", lambda *a, **kw: admission)
    return old, admission


def project(tmp_path):
    return projection.load_independent_price_conditions(tmp_path,
        now=datetime.now(timezone.utc), research_version="TEST_ONLY")["items"][0]["price_action_plan"]


def test_successor_preserves_legacy_and_never_grants_trade(isolated, tmp_path):
    old, _ = isolated
    original = deepcopy(old)
    result = project(tmp_path)
    assert result["risk_review_eligible"] is True
    assert result["legacy_observation_blockers"] == ["VALUE_GATE_NOT_PROVEN"]
    assert "VALUE_GATE_NOT_PROVEN" not in result["blockers"]
    assert result["formal_eligibility"] is result["trade_eligible"] is False
    assert result["action"] == "no_order"
    assert old == original


@pytest.mark.parametrize("change", ["case", "rule", "structure", "entry", "retired", "display"])
def test_signed_release_cannot_override_current_plan(isolated, tmp_path, change):
    old, admission = isolated
    plan = old["items"][0]["price_action_plan"]
    if change == "case":
        plan["case_sha256"] = "b" * 64
    elif change == "rule":
        admission["rule_version"] = "another-rule"
    elif change == "structure":
        plan["opportunity_quality"]["structure_tier"] = "CONFLICT_OR_REJECTED"
    elif change == "entry":
        plan["signal_state"] = "WATCH"
    elif change == "retired":
        plan["candidate_lifecycle"] = "PREVIOUS_CANDIDATE_NOT_SELECTED_TODAY"
    else:
        plan["observation_scope"] = "LAST_COMPLETED_CLOSE_DISPLAY_ONLY"
    assert project(tmp_path)["risk_review_eligible"] is False


def test_invalid_release_stays_observation_only(isolated, monkeypatch, tmp_path):
    def reject(*args, **kwargs):
        raise ValueError("signature invalid")
    monkeypatch.setattr(projection, "load_independent_admission", reject)
    result = project(tmp_path)
    assert result["risk_review_eligible"] is False
    assert "INDEPENDENT_RELEASE_INVALID" in result["blockers"]


def test_new_api_requires_verified_publication(tmp_path):
    client = TestClient(create_app(root=tmp_path, bootstrap_secret="TEST_ONLY"))
    response = client.get("/api/v1/independent-hotspot-conditions")
    assert response.status_code == 200
    assert response.json()["status"] == "UNAVAILABLE"
    assert response.json()["items"] == []
    assert response.json()["action"] == "no_order"
