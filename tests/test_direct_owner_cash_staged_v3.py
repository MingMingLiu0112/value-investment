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
    assert "exact forecast terminal opening debt is 85 CNY" in request.transport_output_contract
    assert "Do not round the amount upward" in request.transport_output_contract
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
    context["historical_financing_observations"] = [{
        "financing_cash_flows": {
            "period_start": "2026-01-01", "period_end": "2026-06-30",
            "components": {
                "borrowings_received_cny": {"classification": "FACT", "value_cny": "10"},
                "debt_repayments_paid_cny": {"classification": "FACT", "value_cny": "25"},
            },
        },
    }]
    with pytest.raises(ValueError, match="BELOW_REALISED_CASH:2026:new_borrowing"):
        staged.preflight_annual_cash_upper_bound_v3(**args)
    policy["series"]["new_borrowing"]["values"] = ["10"]
    with pytest.raises(ValueError, match="BELOW_REALISED_CASH:2026:debt_repayment"):
        staged.preflight_annual_cash_upper_bound_v3(**args)
    policy["series"]["debt_repayment"]["values"] = ["25"]
    staged.preflight_annual_cash_upper_bound_v3(**args)
    context["annual_capex_floor"] = {"year": 2026, "minimum_cny": "5"}
    with pytest.raises(ValueError, match="PARENT_V3_ANNUAL_CAPEX_BELOW_REALISED_CASH:2026"):
        staged.preflight_annual_cash_upper_bound_v3(**args)
    policy["series"]["maintenance_capex"]["values"] = ["2"]
    policy["series"]["growth_capex"]["values"] = ["3"]
    staged.preflight_annual_cash_upper_bound_v3(**args)
    context["annual_investment_receipts_floor"] = {"year": 2026, "minimum_cny": "4"}
    with pytest.raises(ValueError, match="PARENT_V3_ANNUAL_INVESTMENT_RECEIPTS_BELOW_REALISED_CASH:2026"):
        staged.preflight_annual_cash_upper_bound_v3(**args)
    policy["series"]["investment_cash_received"]["values"] = ["4"]
    staged.preflight_annual_cash_upper_bound_v3(**args)
    context["annual_paid_note_interest_floor"] = {"year": 2026, "minimum_cny": "1"}
    with pytest.raises(ValueError, match="PARENT_V3_ANNUAL_INTEREST_BELOW_REALISED_CASH:2026"):
        staged.preflight_annual_cash_upper_bound_v3(**args)
    policy["series"]["interest_outside_cfo"]["values"] = ["1"]
    staged.preflight_annual_cash_upper_bound_v3(**args)
    policy["series"]["maintenance_capex"]["values"] = ["40"]
    with pytest.raises(ValueError, match="UNFUNDED_CASH_REQUIREMENT:2026"):
        staged.preflight_annual_cash_upper_bound_v3(**args)


@pytest.mark.parametrize("debt,interest,reason", [
    ("0", "1", "TERMINAL_REFINANCING_ARITHMETIC_INVALID"),
    ("85", "0", "TERMINAL_CASH_INTEREST_REQUIRED"),
    ("85", "1", None),
])
def test_v3_terminal_refinancing_checks_opening_debt_and_cash_interest(debt, interest, reason):
    request = LLMRequest(role="FUNDAMENTAL", system="", user=json.dumps({
        "forecast_closing_debt_after_annual_years": {"value_cny": debt}}),
        output_schema={"type": "object"})
    stage = {"terminal": {"financing": {"mode": "CONSTANT_DEBT_REFINANCING"},
             "policy": {"debt_repayment": {"values": ["0"]},
                        "new_borrowing": {"values": ["0"]},
                        "interest_outside_cfo": {"values": [interest]}}}}
    if reason:
        with pytest.raises(ValueError, match=reason):
            staged.preflight_terminal_forecast_debt_v3(request=request, parsed_stage=stage)
    else:
        staged.preflight_terminal_forecast_debt_v3(request=request, parsed_stage=stage)

def test_v3_rejects_finite_commitment_before_next_scenario():
    request = LLMRequest(role="FUNDAMENTAL", system="", user=json.dumps({
        "forecast_closing_debt_after_annual_years": {"value_cny": "0"}}),
        output_schema={"type": "object"})
    policy = {"commitments_outside_capex": {"values": ["410000000.00"]}}
    stage = {"terminal": {"policy": policy, "financing": None}}
    with pytest.raises(ValueError, match="FINITE_COMMITMENT_IN_TERMINAL"):
        staged.preflight_terminal_forecast_debt_v3(request=request, parsed_stage=stage)
    policy["commitments_outside_capex"]["values"][0] = "0"
    staged.preflight_terminal_forecast_debt_v3(request=request, parsed_stage=stage)


def test_policy_request_separates_cash_drivers_and_reserves(monkeypatch):
    request = LLMRequest(role="FUNDAMENTAL", system="", user=json.dumps({
        "required_years": [2026], "source_context": {
            "historical_financing_observations": [{"financing_cash_flows": {
                "period_start": "2026-01-01", "period_end": "2026-06-30",
                "components": {field: {"classification": "FACT", "value_cny": "1"}
                               for field in ("borrowings_received_cny", "debt_repayments_paid_cny")},
            }}],
        },
    }), output_schema={"type": "object"}, transport_output_contract="Bound request.")
    monkeypatch.setattr(staged, "staged_parent_cash_request", lambda **kwargs: request)

    revised = staged.staged_parent_cash_request_v3(stage="policy")

    assert "working-capital residual again" in revised.transport_output_contract
    assert "not a minimum operating reserve" in revised.transport_output_contract


def test_policy_money_wire_rejects_extra_billion_multiplier():
    policy = {"years": [2026, 2027], "series": {
        "growth_capex": {"values": ["6500000000.0000", "6000000000000000000.00"]},
        "payout_ratio": {"values": ["0.70", "0.68"]},
    }}
    with pytest.raises(ValueError, match="PARENT_V3_POLICY_CNY_WIRE_INVALID:2027:growth_capex"):
        staged.validate_policy_money_wire(policy)
    policy["series"]["growth_capex"]["values"][1] = "6000000000.00"
    staged.validate_policy_money_wire(policy)


def test_q3_repayment_floor_adds_only_later_issues_due_same_year():
    from decimal import Decimal

    def issue(code, start, maturity, amount):
        return dict(code=code, issue_date=start, maturity=maturity, principal_cny=amount,
                    classification="FACT", scope="ISSUER_FINANCING_DISCLOSURE", currency="CNY")

    context = {"constraints": {"issued_financing": [
        issue("IN_YTD", "2026-06-30", "2026-09-29", "70"),
        issue("LATER", "2026-10-12", "2026-12-30", "80"),
        issue("NEXT_YEAR", "2026-10-28", "2027-11-12", "90"),
    ]}}
    assert staged._post_observation_repayment_floor(context, 2026, "2026-09-30", "200") == Decimal("280")
