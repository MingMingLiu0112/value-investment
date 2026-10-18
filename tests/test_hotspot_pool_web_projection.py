"""API pool membership and retired filtering keep active evidence fail closed."""
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from test_hotspot_candidate_pool_registry import _report, _write
from value_investment_agent.presentation.web_api import app as module


@pytest.fixture
def pool_api(tmp_path, monkeypatch):
    report = _report(tmp_path)
    member = report["candidate_pool"][1]
    assert member["symbol"] not in {row["symbol"] for row in report["observation_list"]}
    binding = _write(tmp_path, "runtime/selection.json", report)
    symbol = member["symbol"]
    plan = {
        "schema_version": "price-action-plan-current-v1", "symbol": symbol,
        "strategy": "HOTSPOT_SATELLITE", "action": "no_order", "signal_state": "WATCH",
        "decision_id": "hotspot-" + symbol, "market_trade_date": report["trade_date"],
        "case_path": "runtime/synthetic-case.json", "case_sha256": "a" * 64,
        "daily_selection_binding": binding, "daily_selection": deepcopy(member),
        "blockers": ["TEST_ONLY_OBSERVATION"], "explanation": "TEST_ONLY",
        "entry_trigger_price": "12.34", "invalidation_price": "11.20",
        "entry_condition": {"price": "12.34", "action": "no_order"},
        "formal_eligibility": False, "portfolio_eligibility": None,
    }
    row = {"symbol": symbol, "company_name": "TEST_ONLY", "price_action_plan": plan}
    packet = {"publication_id": "TEST_ONLY_PUBLICATION", "research_version": "TEST_ONLY",
              "price_conditions": {"items": [row]}}
    successor = deepcopy(row)
    successor["price_action_plan"]["schema_version"] = "price-action-plan-independent-v2"
    independent = {"action": "no_order", "status": "CURRENT_OBSERVATION", "items": [successor]}
    # Existing API tests freeze snapshot/case-loader seams. Selection originals
    # and replay remain real, as does the public strategy-decision projection.
    monkeypatch.setattr(module, "_load_snapshot", lambda root: (packet, None))
    monkeypatch.setattr(module, "_public", lambda root: {"bindings": []})
    monkeypatch.setattr(module, "load_current_price_case", lambda **kwargs: {})
    monkeypatch.setattr(module, "load_independent_price_conditions", lambda *args, **kwargs: deepcopy(independent))
    return TestClient(module.create_app(tmp_path, bootstrap_secret="SYNTHETIC_TEST_ONLY")), packet, independent


def test_pool_only_published_plan_is_accepted_by_detail_and_independent_api(pool_api):
    client, packet, _ = pool_api
    row = packet["price_conditions"]["items"][0]
    detail = client.get("/api/v1/decisions/" + row["price_action_plan"]["decision_id"])
    assert detail.status_code == 200
    plan = detail.json()["decision"]["price_action_plan"]
    assert plan == row["price_action_plan"]
    assert plan["daily_selection"]["candidate_pool_rank"] == 2
    response = client.get("/api/v1/independent-hotspot-conditions")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "CURRENT_OBSERVATION"
    assert [item["symbol"] for item in payload["items"]] == [row["symbol"]]
    assert payload["decision_views"][0]["formal_eligibility"] is False


def test_forged_pool_metadata_blocks_frozen_plan_and_independent_api(pool_api):
    client, packet, _ = pool_api
    row = packet["price_conditions"]["items"][0]
    row["price_action_plan"]["daily_selection"]["industry"] = "FORGED_INDUSTRY"
    plan = client.get("/api/v1/decisions/" + row["price_action_plan"]["decision_id"]).json()["decision"]["price_action_plan"]
    assert plan["signal_state"] == "BLOCKED"
    assert plan["entry_trigger_price"] is None and plan["entry_condition"] is None
    assert plan["formal_eligibility"] is False
    payload = client.get("/api/v1/independent-hotspot-conditions").json()
    assert payload["status"] == "UNAVAILABLE" and payload["items"] == []


def test_retired_stale_item_is_filtered_without_poisoning_active_list_or_detail(pool_api):
    client, packet, independent = pool_api
    retired = deepcopy(packet["price_conditions"]["items"][0])
    retired["symbol"] = "600999"
    retired["price_action_plan"].update(
        symbol="600999", decision_id="hotspot-600999", signal_state="STALE",
        candidate_lifecycle="PREVIOUS_CANDIDATE_NOT_SELECTED_TODAY",
    )
    retired["price_action_plan"].pop("daily_selection_binding")
    retired["price_action_plan"].pop("daily_selection")
    packet["price_conditions"]["items"].append(retired)
    retired_successor = deepcopy(retired)
    retired_successor["price_action_plan"]["schema_version"] = "price-action-plan-independent-v2"
    independent["items"].append(retired_successor)
    before = deepcopy(independent)
    payload = client.get("/api/v1/independent-hotspot-conditions").json()
    assert payload["status"] == "CURRENT_OBSERVATION"
    assert [row["symbol"] for row in payload["items"]] == ["600002"]
    assert [row["symbol"] for row in payload["decision_views"]] == ["600002"]
    detail = client.get("/api/v1/decisions/hotspot-600999").json()["decision"]["price_action_plan"]
    assert detail["candidate_lifecycle"] == "PREVIOUS_CANDIDATE_NOT_SELECTED_TODAY"
    assert detail["signal_state"] == "STALE"
    assert independent == before


@pytest.mark.parametrize("state", ["STALE", "BLOCKED"])
def test_active_unavailable_plan_still_rejects_entire_independent_list(pool_api, state):
    client, packet, independent = pool_api
    packet["price_conditions"]["items"][0]["price_action_plan"]["signal_state"] = state
    assert "candidate_lifecycle" not in independent["items"][0]["price_action_plan"]
    payload = client.get("/api/v1/independent-hotspot-conditions").json()
    assert payload["status"] == "UNAVAILABLE"
    assert payload["items"] == []
    assert payload["reason"] == "INDEPENDENT_HOTSPOT_EVIDENCE_UNAVAILABLE"
