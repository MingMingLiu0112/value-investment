from value_investment_agent.research_profile import PROFILES


def test_three_case_profiles_use_economic_contracts_not_symbols():
    assert set(PROFILES) == {"quality_compounder", "mature_manufacturing", "cyclical_cash_return"}
    assert PROFILES["mature_manufacturing"].primary_valuation_model == "fcff"
    assert PROFILES["cyclical_cash_return"].primary_valuation_model == "cyclical_normalized"
    assert "fcff_default" in PROFILES["cyclical_cash_return"].unsupported_models
