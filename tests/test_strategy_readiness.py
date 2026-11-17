from copy import deepcopy

import pytest

from value_investment_agent.application.decision.strategy_readiness import (
    attach_strategy_readiness, build_strategy_readiness,
)
from value_investment_agent.application.decision.public_strategy_assessment import summarize_actionable_evaluations


def packet():
    return dict(action="no_order", packet_status="CURRENT", source_bindings_verified=True,
        publication_id="TEST_ONLY", dates={"research_as_of": "2026-10-11"},
        company_statuses={"600519": dict(symbol="600519", registered_research={
            "summary": "TEST_ONLY source-bound research", "missing_inputs": ["Economic assumptions pending"]},
            price_bridge=dict(status="QUOTE_VERIFIED_WITHOUT_RESEARCH_DISPLAY_ONLY",
                              quote_date="2026-10-21", current_price="100"))},
        valuation_statuses={"600519": dict(symbol="600519", published_code="UNDER_REVIEW",
            conditional_range=dict(bear="80", base="100", bull="120", currency="CNY"),
            model_validity=dict(status="UNKNOWN", blockers=["pending review"]))})


def value_item():
    return dict(symbol="600519", name="TEST_ONLY", strategy="value")


def test_bound_scenarios_survive_unapproved_model_without_promoting_action():
    source = packet()
    before = deepcopy(source)
    item = value_item()
    original = summarize_actionable_evaluations([item])
    output = attach_strategy_readiness(original, [item], source)
    row = output["items"][0]
    readiness = row.pop("readiness")
    assert output == original
    assert readiness["conditional_valuation"] == dict(bear="80", base="100", bull="120",
        currency="CNY", as_of="2026-10-11", scope="UNAPPROVED_RESEARCH_ONLY")
    assert readiness["primary_gap"]["category"] == "RESEARCH"
    assert readiness["price_snapshot"] is None  # Frozen quote is not a current verification.
    assert readiness["authorization_granted"] is False
    assert source == before


@pytest.mark.parametrize("value", [None, "NaN", "Infinity", True, "-1", {}, "bad"])
def test_invalid_values_never_become_valuation(value):
    source = packet()
    source["valuation_statuses"]["600519"]["conditional_range"]["base"] = value
    assert build_strategy_readiness(value_item(), source)["conditional_valuation"] is None


def test_unordered_scenarios_are_not_displayed_as_valid_range():
    source = packet()
    source["valuation_statuses"]["600519"]["conditional_range"]["bear"] = "200"
    assert build_strategy_readiness(value_item(), source)["conditional_valuation"] is None


@pytest.mark.parametrize("field,value", [("action", "buy"), ("source_bindings_verified", False),
    ("packet_status", "UNAVAILABLE"), ("publication_id", None)])
def test_unverified_packets_cannot_supply_scenarios_or_prices(field, value):
    source = packet()
    source[field] = value
    result = build_strategy_readiness(value_item(), source)
    assert result["conditional_valuation"] is result["price_snapshot"] is None


def test_other_security_cannot_supply_scenarios():
    source = packet()
    source["valuation_statuses"]["600519"]["symbol"] = "000333"
    assert build_strategy_readiness(value_item(), source)["conditional_valuation"] is None


def test_missing_model_review_is_separate_from_missing_estimate():
    source = packet()
    source["company_statuses"]["600519"]["registered_research"]["missing_inputs"] = []
    result = build_strategy_readiness(value_item(), source)
    assert result["primary_gap"]["code"] == "MODEL_AND_EVENT_REVIEW_PENDING"
    assert result["conditional_valuation"] is not None
    assert {x["key"]: x["status"] for x in result["steps"]}["model_validity"] == "PENDING"


def test_hotspot_has_no_value_gate_and_private_capacity_is_not_assumed():
    result = build_strategy_readiness(dict(symbol="600519", strategy="hotspot"), packet())
    assert result["independent_of_value_valuation"] is True
    assert result["conditional_valuation"] is None
    assert not {"valuation", "model_validity", "research"} & {x["key"] for x in result["steps"]}
    assert next(x for x in result["steps"] if x["key"] == "portfolio")["status"] == "NOT_EVALUATED"


def test_identity_mismatch_fails_instead_of_attaching_another_company():
    with pytest.raises(ValueError, match="identities"):
        attach_strategy_readiness({"items": [{"symbol": "000333"}]}, [value_item()], packet())


def test_row_count_mismatch_does_not_silently_omit_workflow():
    with pytest.raises(ValueError, match="complete"):
        attach_strategy_readiness({"items": []}, [value_item()], packet())


def test_invalid_plan_does_not_supply_hotspot_reference_price():
    item = dict(symbol="600519", strategy="hotspot", price_action_plan=dict(
        schema_version="price-action-plan-independent-v2", strategy="HOTSPOT_SATELLITE",
        symbol="000333", action="no_order", current_reference_price="100",
        market_trade_date="2026-10-21", signal_state="TRIGGER_OBSERVED"))
    assert build_strategy_readiness(item, packet())["price_snapshot"] is None


def analysis_item():
    from value_investment_agent.domain.decision.value_action_plan import build_value_action_plan
    plan = build_value_action_plan(explanation={"symbol": "600519", "action": "no_order",
        "decision_as_of": "2026-10-22", "thesis_breakers": ["TEST_ONLY"]}).as_policy()
    plan["research_analysis"] = dict(schema_version="value-research-analysis-v1",
        symbol="600519", action="no_order", status="CONDITIONAL_ANALYSIS_VERIFIED",
        arithmetic_complete=True, economic_assumptions_reviewed=False, action_admitted=False,
        valuation_date="2026-10-21", scenarios=[dict(scenario=key, per_share_value=value)
            for key, value in zip(("bear", "base", "bull"), ("70", "90", "110"))])
    return {**value_item(), "price_action_plan": plan}


def test_current_verified_analysis_keeps_its_own_values_and_date_without_approval():
    source = packet()
    before = deepcopy(source)
    result = build_strategy_readiness(analysis_item(), source)
    assert result["conditional_valuation"]["base"] == "90"
    assert result["conditional_valuation"]["as_of"] == "2026-10-21"
    assert result["authorization_granted"] is False
    assert source == before


@pytest.mark.parametrize("key,value", [("symbol", "000333"), ("arithmetic_complete", False),
    ("status", "SOURCE_OR_REPLAY_UNAVAILABLE"), ("action_admitted", True),
    ("scenarios", []), ("valuation_date", "invalid")])
def test_invalid_current_analysis_cannot_fall_back_to_older_scenarios(key, value):
    item = analysis_item()
    item["price_action_plan"]["research_analysis"][key] = value
    assert build_strategy_readiness(item, packet())["conditional_valuation"] is None


def test_new_analysis_never_inherits_previous_model_validity():
    source = packet()
    source["company_statuses"]["600519"]["registered_research"]["missing_inputs"] = []
    source["valuation_statuses"]["600519"]["model_validity"] = dict(status="VALID", blockers=[])
    result = build_strategy_readiness(analysis_item(), source)
    assert next(x for x in result["steps"] if x["key"] == "model_validity")["status"] == "PENDING"
    assert result["primary_gap"]["code"] == "MODEL_AND_EVENT_REVIEW_PENDING"


@pytest.mark.parametrize("verified", [True, False])
def test_current_quote_needs_reverification_not_a_frozen_bridge(verified):
    item = analysis_item()
    item["price_action_plan"].update(current_quote_verified=verified,
        reference_close="99" if verified else None, market_trade_date="2026-10-22")
    result = build_strategy_readiness(item, packet())
    assert result["price_snapshot"] == (dict(value="99", date="2026-10-22", usage="DISPLAY_ONLY")
        if verified else None)
