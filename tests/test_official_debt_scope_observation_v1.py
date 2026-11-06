from value_investment_agent.application.discovery.official_debt_scope_observation_v1 import review


def test_official_components_explain_scope_gap_without_admission():
    result = review(
        symbol="600001", period="2025-12-31",
        official_summary={
            "components": [
                {"field": "short_term_borrowings", "value": "100", "unit": "CNY"},
                {"field": "lease_liabilities_current", "value": "20", "unit": "CNY"},
            ],
            "errors": [],
        },
    )
    assert result["status"] == "PARTIAL_OFFICIAL_COMPONENTS"
    assert "long_term_borrowings" in result["missing_components"]
    assert result["complete_debt_verified"] is False
    assert result["formal_admission"] is False
    assert result["action"] == "no_order"


def test_source_ambiguity_never_becomes_complete_scope():
    result = review(
        symbol="600001", period="2025-12-31",
        official_summary={"components": [], "errors": ["DUPLICATE_FINANCING_BUCKET:short_term_borrowings"]},
    )
    assert result["status"] == "SOURCE_CONFLICT_OR_AMBIGUITY"
    assert result["complete_debt_verified"] is False
    assert "OFFICIAL_SOURCE:DUPLICATE_FINANCING_BUCKET:short_term_borrowings" in result["issues"]
