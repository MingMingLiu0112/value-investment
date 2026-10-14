"""Preview binding, missing-data vetoes and delegation without journal writes."""
from copy import deepcopy
from datetime import datetime

import pytest

from value_investment_agent.application.portfolio import private_risk_preview as preview
from test_private_ips_policy import service

NOW = datetime.fromisoformat("2026-10-14T20:00:00+08:00")
ASSUMPTIONS = {key: "0" for key in preview.ASSUMPTION_FIELDS}
ASSUMPTIONS.update(lot_size="100", max_trade_notional_cny="1000")


def binding():
    return {"publication_id": "TEST_ONLY", "plan": {"symbol": "300364",
        "research_version": "TEST_ONLY", "case_sha256": "a" * 64,
        "entry_trigger_price": "30", "invalidation_price": "25",
        "market_trade_date": "2026-10-14", "data_available_at": "2026-10-14T15:01:00+08:00",
        "expires_after_session": "2026-10-15", "formal_eligibility": False,
        "current_reference_close": {"limit_up": False, "limit_down": False}}}


def test_missing_assumptions_and_public_plan_keep_facts_and_null_quantity(service, tmp_path):
    before = service.journal.path.read_bytes()
    result = preview.preview_private_hotspot_risk(service.journal, repository_root=tmp_path,
        generated_at=NOW, payload={"symbol": "300364"})
    assert result["facts"]["cash_cny"] == "8000"
    assert result["sizing_preview"]["review_quantity"] is None
    assert "PUBLIC_SNAPSHOT_UNAVAILABLE" in result["sizing_preview"]["blockers"]
    assert "ASSUMPTION_MISSING:lot_size" in result["sizing_preview"]["blockers"]
    assert service.journal.path.read_bytes() == before


@pytest.mark.parametrize("forged", ["entry_price_cny", "stop_price_cny", "formal_eligibility", "security_attributes"])
def test_client_cannot_supply_prices_or_verified_eligibility(service, tmp_path, forged):
    with pytest.raises(ValueError, match="只接受"):
        preview.preview_private_hotspot_risk(service.journal, repository_root=tmp_path,
            generated_at=NOW, payload={"symbol": "300364", forged: True})


@pytest.mark.parametrize("field,value", [("lot_size", "0"), ("lot_size", "1.5"),
    ("gap_stress_cny", "NaN"), ("buy_fee_fraction", "1.1"), ("sell_fee_fraction", True)])
def test_invalid_explicit_assumptions_refused(service, tmp_path, field, value):
    with pytest.raises(ValueError):
        preview.preview_private_hotspot_risk(service.journal, repository_root=tmp_path,
            generated_at=NOW, payload={"symbol": "300364", "assumptions": {field: value}})


def test_real_unknown_execution_attributes_do_not_become_defaults(service, tmp_path, monkeypatch):
    plan = binding()
    plan["plan"]["current_reference_close"] = {}
    monkeypatch.setattr(preview, "_current_plan", lambda *args: (plan, None))
    monkeypatch.setattr(preview, "load_verified_security_attributes", lambda *args, **kwargs: [
        {"symbol": "300364", "liquidity_profile": "UNKNOWN"}])
    result = preview.preview_private_hotspot_risk(service.journal, repository_root=tmp_path,
        generated_at=NOW, payload={"symbol": "300364", "assumptions": ASSUMPTIONS})
    assert result["sizing_preview"]["review_quantity"] is None
    assert {"CANDIDATE_LIQUIDITY_UNKNOWN", "PRICE_LIMIT_STATE_UNKNOWN"} <= set(result["sizing_preview"]["blockers"])


def test_full_test_only_binding_delegates_to_existing_engine_and_never_grants_admission(service, tmp_path, monkeypatch):
    calls = []
    def engine(*args, **kwargs):
        calls.append(kwargs)
        return {"action": "no_order", "blockers": [], "engine": {"hotspot_quantity_review":
            {"review_quantity": 100, "status": "QUANTITY_REVIEW_ONLY", "blockers": []}}}
    monkeypatch.setattr(preview, "review_private_risk_rehearsal", engine)
    monkeypatch.setattr(preview, "_current_plan", lambda *args: (binding(), None))
    monkeypatch.setattr(preview, "load_verified_security_attributes", lambda *args, **kwargs: [
        {"symbol": "300364", "liquidity_profile": "LIQUID"}])
    before = service.journal.path.read_bytes()
    result = preview.preview_private_hotspot_risk(service.journal, repository_root=tmp_path,
        generated_at=NOW, payload={"symbol": "300364", "assumptions": ASSUMPTIONS})
    request = calls[-1]["hotspot_request"]
    assert request["entry_price_cny"] == "30"
    assert request["stop_price_cny"] == "25"
    assert request["lot_size"] == 100
    assert result["sizing_preview"]["review_quantity"] == 100
    assert result["sizing_preview"]["trade_eligible"] is False
    assert result["sizing_preview"]["formal_eligibility"] is False
    assert service.journal.path.read_bytes() == before


@pytest.mark.parametrize("mutation", ["chain", "registry", "plan", "retired", "stale"])
def test_current_binding_rejects_chain_registry_plan_and_lifecycle_changes(tmp_path, monkeypatch, mutation):
    plan = binding()["plan"]
    plan["signal_state"] = "WATCH"
    packet = {"publication_id": "TEST_ONLY", "research_version": "TEST_ONLY",
        "identity_inputs": {"chain": [], "current_price_conditions": {"TEST_ONLY": True}},
        "price_conditions": {"items": [{"symbol": "300364", "price_action_plan": deepcopy(plan)}]}}
    if mutation == "chain":
        packet["identity_inputs"]["chain"] = ["old"]
    elif mutation == "registry":
        packet["identity_inputs"]["current_price_conditions"] = {"old": True}
    elif mutation == "plan":
        plan["entry_trigger_price"] = "31"
    elif mutation == "retired":
        plan["candidate_lifecycle"] = "PREVIOUS_CANDIDATE_NOT_SELECTED_TODAY"
        packet["price_conditions"]["items"][0]["price_action_plan"] = deepcopy(plan)
    elif mutation == "stale":
        plan["signal_state"] = "STALE"
        packet["price_conditions"]["items"][0]["price_action_plan"] = deepcopy(plan)
    monkeypatch.setattr(preview, "load_current_packet", lambda root: (packet, None))
    monkeypatch.setattr(preview, "load_current_chain", lambda root: {"bindings": []})
    monkeypatch.setattr(preview, "registry_identity", lambda root: {"TEST_ONLY": True})
    monkeypatch.setattr(preview, "load_price_conditions", lambda *args, **kwargs: {
        "items": [{"symbol": "300364", "price_action_plan": plan}]})
    observed, error = preview._current_plan(tmp_path, "300364", NOW)
    assert observed is None
    assert error
