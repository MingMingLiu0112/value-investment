import hashlib
import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "shenhua_valuation_applicability",
    ROOT / "scripts" / "research_cases" / "shenhua" / "build_shenhua_valuation_applicability.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _payload():
    payload = MODULE.build_payload()
    pointer = ROOT / "runtime/company-research/shenhua-valuation-applicability-latest.json"
    pin = json.loads(pointer.read_text(encoding="utf-8"))
    evidence = ROOT / pin["path"] / "evidence.json"
    assert hashlib.sha256(evidence.read_bytes()).hexdigest() == pin["sha256"]
    return payload


def test_shenhua_cyclical_route_is_authorized_while_other_families_are_blocked():
    payload = _payload()

    assert payload["symbol"] == "601088"
    assert payload["package_version"] == "shenhua-valuation-applicability-v1"
    route = payload["profile_route"]
    assert route["profile_id"] == "cyclical_cash_return"
    assert route["primary_route"]["status"] == "SUPPORTED"
    assert route["primary_route"]["selected_model"] == "cyclical_normalized"
    assert route["primary_route"]["model_type"] == "cyclical_normalized"
    assert route["primary_route"]["facts_contract"] == "CyclicalFacts"
    assert route["unauthorized_requests"] == {
        "residual_income_or_equity_value": {
            "status": "UNSUPPORTED",
            "blockers": ["model_not_authorized_for_profile:residual_income_or_equity_value"],
        },
        "fcff": {
            "status": "UNSUPPORTED",
            "blockers": ["model_not_authorized_for_profile:fcff"],
        },
    }
    assert payload["new_model_family_created"] is False


def test_shenhua_contract_reports_the_full_input_gap_without_arithmetic():
    payload = _payload()
    contract = payload["facts_contract"]

    required = contract["required_inputs"]
    assert len(required) == 13
    assert len(set(required)) == 13
    assert sorted(contract["missing_inputs_without_admitted_facts"]) == sorted(required)
    assert contract["admitted_inputs"] == []
    assert contract["registered_inputs"] == {}
    assert set(payload["per_input_admission"]) == set(required)
    assert {
        item["admission"] for item in payload["per_input_admission"].values()
    } == {"NOT_ADMITTED"}
    assert payload["per_input_admission"]["trough_parent_operating_profit"]["series_decision"] == (
        "descriptive_series_does_not_by_itself_establish_trough"
    )
    assert payload["per_input_admission"]["cash_tax_rate"]["series_decision"] == (
        "candidate_upper_bound_only_cash_taxes_paid_includes_all_taxes"
    )


def test_shenhua_applicability_retains_the_fail_closed_result_and_stops():
    payload = _payload()
    anchor = payload["fail_closed_result_anchor"]

    assert anchor["result_status"] == "not_ready"
    assert anchor["price_bridge_status"] == "PENDING_EXTERNAL_DATA"
    assert anchor["scenario_values"] is None
    assert len(anchor["missing_blockers"]) == 13
    assert payload["evidence_stops"] == [
        {
            "stop_id": "601088-acquisition-adjusted-through-cycle-profit",
            "blocker_id": "current_perimeter_parent_earnings_bridge_incomplete",
            "reopen_condition": (
                "New official evidence bridges the final consolidation perimeter, "
                "attribution, tax/NCI and financing, with enough comparable history "
                "to calibrate the cycle."
            ),
        }
    ]
    assert payload["decision"] == "CYCLE_MODEL_ROUTE_VERIFIED_INPUTS_NOT_ADMITTED"
    assert payload["valuation_status"] == "NOT_ESTABLISHED"
    assert payload["valuation_run_status"] == "NOT_RUN_ADMITTED_INPUTS_UNAVAILABLE"
    assert payload["research_registration"] == {
        "performed": False,
        "expected_product_state": "PENDING_RESEARCH",
    }
    assert payload["registered_valuation_model"] is None
    assert payload["registered_valuation_inputs"] == {}
    assert payload["formal_fair_value"] is None
    assert payload["valuation_approved"] is False
    assert payload["simulation_eligible"] is False
    assert payload["trade_approved"] is False
    assert payload["live_eligible"] is False
    assert payload["blockers"] == [
        "parent_pretax_operating_profit_allocation_not_disclosed",
        "ordinary_share_denominator_changed_after_period_end",
        "attributable_net_cash_and_restricted_cash_not_allocated",
        "maintenance_and_growth_capex_split_not_disclosed",
        "working_capital_change_is_raw_not_normalized",
        "resource_life_is_a_static_ratio_not_a_reviewed_life",
        "absolute_unit_cost_curve_not_available",
        "discount_rate_and_terminal_growth_have_no_reviewed_basis",
        "no_candidate_is_approved_as_a_model_input",
    ]
    assert all(
        (ROOT / ref["path"]).is_relative_to(ROOT / "runtime")
        for ref in payload["evidence_refs"]
        if ref["id"] != "shenhua_2025_official_pdf"
    )
    assert "order" not in payload
    assert "position" not in payload


def test_shenhua_applicability_declares_reopen_conditions():
    payload = _payload()

    conditions = payload["reopen_conditions"]
    assert len(conditions) == len(set(conditions)) == 6
    assert all(isinstance(item, str) and item.strip() for item in conditions)
    assert all(item["admission"] == "NOT_ADMITTED"
               for item in payload["per_input_admission"].values())
