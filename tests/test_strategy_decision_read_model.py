"""Isolated public adapter tests: no files, credentials or services required."""
from copy import deepcopy

import pytest

from value_investment_agent.presentation.read_models.strategy_decision import project_strategy_decision


@pytest.fixture
def value_plan():
    from value_investment_agent.domain.decision.value_action_plan import build_value_action_plan

    return build_value_action_plan(explanation={
        "symbol": "000333", "action": "no_order", "decision_as_of": "2026-10-16",
        "thesis_breakers": ["Economic thesis fails"],
    }).as_policy()


@pytest.fixture(params=["price-action-plan-current-v1", "price-action-plan-independent-v2"])
def hotspot_plan(request):
    return dict(schema_version=request.param,
        strategy="HOTSPOT_SATELLITE", symbol="000333", action="no_order",
        market_trade_date="2026-10-16", data_available_at="2026-10-16T15:30:00+08:00",
        model_or_rule_version="structure-v1", trend_state="NOT_CONFIRMED",
        entry_condition=dict(price="12", rule="Completed bar required", observed=False,
                             action="no_order", formal_eligibility=False),
        exit_condition=dict(price="10", rule="Structure invalidation"),
        invalidation_condition=dict(price="10", rule="Structure invalidation"),
        risk_reward_ratio="2", evidence_refs=["a" * 64], formal_eligibility=False)


def test_real_value_plan_keeps_thesis_semantics_without_inventing_prices(value_plan):
    result = project_strategy_decision(value_plan, symbol="000333")
    assert result["strategy"] == "CORE_VALUE"
    assert result["as_of"] == value_plan["decision_as_of"]
    assert result["entry_condition"] is None
    assert result["invalidation_condition"]["reasons"] == ["Economic thesis fails"]
    assert result["data_available_at"] is None
    assert result["rule_version"] == value_plan["model_or_rule_version"]


def test_hotspot_versions_preserve_observations_and_do_not_promote(hotspot_plan):
    before = deepcopy(hotspot_plan)
    result = project_strategy_decision(hotspot_plan)
    assert result["entry_condition"] == hotspot_plan["entry_condition"]
    assert result["risk_basis"]["risk_reward_ratio"] == "2"
    assert result["as_of"] == hotspot_plan["market_trade_date"]
    assert result["formal_eligibility"] is False
    assert result["review_status"] == "UNKNOWN"
    assert hotspot_plan == before
    result["entry_condition"]["price"] = "999"
    result["evidence_refs"].append("b" * 64)
    assert hotspot_plan == before


def test_private_extensions_and_authority_are_not_public(hotspot_plan):
    hotspot_plan.update(account_id="SECRET", position_guidance={"quantity": 100},
        personal_risk_status="APPROVED", formal_eligibility=True,
        evidence_refs=[dict(sha256="a" * 64, path="SECRET", account_id="SECRET")])
    hotspot_plan["entry_condition"].update(private_holdings="SECRET", personal_permission=True)
    result = project_strategy_decision(hotspot_plan)
    assert "SECRET" not in repr(result)
    assert result["formal_eligibility"] is False
    assert result["portfolio_eligibility"] is None
    assert result["entry_condition"]["personal_permission"] is False
    assert result["personal_risk_status"] == "UNKNOWN_PRIVATE_INPUT_NOT_PROJECTED"


def test_missing_unknown_fields_do_not_supply_qualification(value_plan):
    plan = {key: value_plan[key] for key in ("schema_version", "strategy", "symbol", "action")}
    plan.update(review_status={"approved": True}, unknown={"private": "SECRET"})
    result = project_strategy_decision(plan)
    assert result["research_or_structure_basis"] == {}
    assert result["risk_basis"] == {}
    assert result["rule_version"] is None
    assert result["review_status"] == "UNKNOWN"
    assert result["evidence_refs"] == []
    assert result["action"] == "no_order"


@pytest.mark.parametrize("review", ["REJECTED", "PENDING", "VERIFIED"])
def test_independent_review_label_is_display_only(hotspot_plan, review):
    hotspot_plan.update(review_status="CLIENT_APPROVED", formal_eligibility=True,
        risk_review_eligible=True, action_eligibility=True,
        independent_admission=dict(review_status=review, formal_eligibility=True,
                                   position_guidance={"quantity": 999}))
    result = project_strategy_decision(hotspot_plan)
    expected = review if hotspot_plan["schema_version"] == "price-action-plan-independent-v2" else "UNKNOWN"
    assert result["review_status"] == expected
    assert result["formal_eligibility"] is False
    assert result["portfolio_eligibility"] is None
    assert "risk_review_eligible" not in result
    assert "position_guidance" not in result


@pytest.mark.parametrize("admission", [None, "APPROVED", {"review_status": {"approved": True}}])
def test_malformed_independent_review_stays_unknown(hotspot_plan, admission):
    hotspot_plan.update(independent_admission=admission, review_status="CLIENT_APPROVED")
    assert project_strategy_decision(hotspot_plan)["review_status"] == "UNKNOWN"


def test_unimplemented_current_v2_schema_is_rejected(hotspot_plan):
    hotspot_plan["schema_version"] = "price-action-plan-current-v2"
    with pytest.raises(ValueError, match="schema"):
        project_strategy_decision(hotspot_plan)


@pytest.mark.parametrize("change", [
    {"schema_version": "unknown"}, {"action": "BUY"}, {"action": None},
    {"symbol": "123"}, {"symbol": "１２３４５６"}, {"strategy": "HOTSPOT_SATELLITE"},
    {"sleeve": "HOTSPOT_SATELLITE"}, {"entry_condition": {"action": "SELL"}},
])
def test_invalid_contract_rejected(value_plan, change):
    value_plan.update(change)
    with pytest.raises(ValueError):
        project_strategy_decision(value_plan)


def test_wrong_requested_security_and_non_object_rejected(value_plan):
    with pytest.raises(ValueError):
        project_strategy_decision(value_plan, symbol="600519")
    with pytest.raises(ValueError):
        project_strategy_decision(None)
