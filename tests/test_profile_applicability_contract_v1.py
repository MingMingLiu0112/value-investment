"""Frozen C route contract against the existing registry; no new model."""
import pytest
from value_investment_agent.domain.research.profile_applicability_v1 import contract_for_profile
from value_investment_agent.valuation_router import route_profile

@pytest.mark.parametrize("profile", ["quality_compounder", "mature_manufacturing", "cyclical_cash_return"])
def test_frozen_contract_agrees_with_real_router_without_approving_economics(profile):
    contract = contract_for_profile(profile)
    route = route_profile(profile)
    assert route.status == "SUPPORTED"
    assert route.selected_model == contract["primary_model"]
    assert route.required_inputs
    assert contract["required_economic_inputs"] and contract["refusal_conditions"]
    assert contract["permits_valuation_without_inputs"] is False
    assert contract["permits_approval"] is False
    assert contract["action"] == "no_order"
    contract["applicability_conditions"].clear()
    assert contract_for_profile(profile)["applicability_conditions"]

@pytest.mark.parametrize("profile", ["bank", "insurance", "unknown", "mixed"])
def test_unsupported_economic_types_have_no_implicit_fallback(profile):
    with pytest.raises(ValueError, match="UNSUPPORTED_ECONOMIC_PROFILE"):
        contract_for_profile(profile)

def test_cross_type_model_is_not_an_automatic_alternative():
    for profile, requested in [("quality_compounder", "fcff"),
                               ("cyclical_cash_return", "residual_income_or_equity_value")]:
        route = route_profile(profile, requested)
        assert route.status != "SUPPORTED"
        with pytest.raises(ValueError):
            route.build_model()
