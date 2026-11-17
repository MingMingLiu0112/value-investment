"""TEST_ONLY annual cash sufficiency checks for numbered parent evidence."""
from datetime import datetime, timezone
import json

import pytest

from value_investment_agent.application.research import direct_owner_cash_staged_v3 as staged
from value_investment_agent.domain.valuation.parent_direct_operating_cash import SCOPE
from value_investment_agent.infrastructure.agent_runtime.provider import LLMRequest


def test_v3_terminal_request_states_existing_stationary_cash_gate(monkeypatch):
    old = LLMRequest(role="FUNDAMENTAL", system="old", user="{}",
                     output_schema={"type": "object"},
                     transport_output_contract="Old terminal contract.")
    monkeypatch.setattr(staged, "staged_parent_cash_request", lambda **_kwargs: old)
    assert staged.staged_parent_cash_request_v3(stage="operating") is old
    updated = staged.staged_parent_cash_request_v3(stage="terminal")
    assert updated is not old
    assert updated.system == old.system and updated.user == old.user
    assert updated.output_schema == old.output_schema
    assert updated.transport_output_contract.startswith(old.transport_output_contract)
    assert "between zero and parent_profit inclusive" in updated.transport_output_contract
    assert "one-time return of investment principal" in updated.transport_output_contract
    assert "12 percent must be 0.12, never 12.00" in updated.transport_output_contract


def test_v3_terminal_request_exposes_forecast_debt_without_certifying_refinancing(monkeypatch, tmp_path):
    old = LLMRequest(role="FUNDAMENTAL", system="old", user="{}",
                     output_schema={"type": "object"}, transport_output_contract="old")
    monkeypatch.setattr(staged, "staged_parent_cash_request", lambda **_kwargs: old)
    monkeypatch.setattr(staged, "_load_spec", lambda *_args: {
        "opening": {"debt": {"anchor": "liabilities", "factor": "1",
                              "classification": "FORECAST_ASSUMPTION"}}})
    request = staged.staged_parent_cash_request_v3(
        stage="terminal", root=tmp_path, spec_binding={},
        verified_context={"facts": {"liabilities": {
            "value_cny": "100", "field": "liabilities_cny"}}},
        prior_drafts={"policy": {"series": {
            "new_borrowing": {"values": ["10", "0"]},
            "debt_repayment": {"values": ["20", "5"]}}}})
    debt = json.loads(request.user)["forecast_closing_debt_after_annual_years"]
    assert debt["value_cny"] == "85"
    assert debt["annual_path"] == [
        {"year": 1, "closing_debt_cny": "90"},
        {"year": 2, "closing_debt_cny": "85"},
    ]
    assert debt["classification"] == "DERIVED_FORECAST_ASSUMPTION_NOT_FACT"
    assert debt["refinancing_guaranteed"] is False
    basis = json.loads(request.user)["opening_debt_basis"]
    assert basis == {
        "amount_cny": "100", "classification": "FORECAST_ASSUMPTION",
        "fact_field": "liabilities_cny",
        "scope": "ALL_PARENT_LIABILITIES_UPPER_BOUND_NOT_FINANCING_FACT",
    }
    assert "not an observed interest-bearing debt balance" in request.transport_output_contract
    assert "maximum gross terminal repayment" in request.transport_output_contract


def test_v3_terminal_rejects_unfunded_debt_policy_before_next_model_call():
    request = LLMRequest(role="FUNDAMENTAL", system="", user=json.dumps({
        "forecast_closing_debt_after_annual_years": {"value_cny": "85"}}),
        output_schema={"type": "object"})
    with pytest.raises(ValueError, match="TERMINAL_DEBT_POLICY_UNSUPPORTED"):
        staged.preflight_terminal_forecast_debt_v3(request=request,
            parsed_stage={"terminal": {"financing": None}})
    with pytest.raises(ValueError, match="TERMINAL_REFINANCING_ARITHMETIC_INVALID"):
        staged.preflight_terminal_forecast_debt_v3(request=request,
            parsed_stage={"terminal": {"financing": {"mode": "CONSTANT_DEBT_REFINANCING"},
                "policy": {"debt_repayment": {"values": ["86"]},
                           "new_borrowing": {"values": ["86"]}}}})


def test_numbered_annual_history_drives_cash_preflight(monkeypatch, tmp_path):
    spec = {
        "symbol": "000568", "valuation_date": "2025-12-31",
        "opening": {"cash": {"classification": "FACT", "anchor": "cash"}},
    }
    historical = {
        "symbol": "000568", "scope": SCOPE, "currency": "CNY",
        "classification": "FACT", "period_start": "2025-01-01",
        "period_end": "2025-12-31", "source_refs": [{"TEST_ONLY": True}],
        "revenue": "100", "cost": "50", "customer_cash": "90",
        "supplier_cash": "40", "cfo": "30",
    }
    monkeypatch.setattr(staged, "_load_spec", lambda *_args: spec)
    monkeypatch.setattr(staged, "_historical_parent_operating_cash",
                        lambda **_kwargs: historical)
    context = {
        "symbol": "000568", "valuation_date": "2025-12-31",
        "opening_fact_anchors": {"cash": "cash"},
        "facts": {"cash": {"field": "closing_cash_and_equivalents_cny",
                           "period_end": "2025-12-31", "scope": SCOPE,
                           "value_cny": "5"}},
    }
    operating = {
        "years": [2026],
        "series": {name: {"values": [value]} for name, value in {
            "revenue": "100", "cost": "50", "other_operating_cash": "-20",
        }.items()},
    }
    policy = {
        "years": [2026],
        "series": {name: {"values": ["0"]} for name in (
            "investment_cash_received", "new_borrowing", "maintenance_capex",
            "growth_capex", "commitments_outside_capex", "debt_repayment",
            "interest_outside_cfo", "other_mandatory_cash", "cash_floor")},
    }
    args = dict(root=tmp_path, spec_binding={"TEST_ONLY": True},
                evaluated_at=datetime(2026, 11, 17, tzinfo=timezone.utc),
                context=context, operating=operating, policy=policy)
    staged.preflight_annual_cash_upper_bound_v3(**args)
    policy["series"]["maintenance_capex"]["values"] = ["40"]
    with pytest.raises(ValueError, match="UNFUNDED_CASH_REQUIREMENT:2026"):
        staged.preflight_annual_cash_upper_bound_v3(**args)
