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


def test_only_safe_one_to_one_bucket_is_compared():
    result = review(
        symbol="600001", period="2025-12-31",
        official_summary={"components": [
            {"field": "short_term_borrowings", "value": "100", "unit": "CNY"},
            {"field": "lease_liabilities_current", "value": "20", "unit": "CNY"},
        ]},
        provider_components=[
            {"field": "short_term_borrowings", "value": "100", "status": "IDENTIFIED_FINANCING"},
            {"field": "lease_liabilities_noncurrent", "value": "50", "status": "IDENTIFIED_FINANCING"},
        ],
    )
    assert result["matched_component_count"] == 1
    assert result["conflicting_component_count"] == 0
    assert result["independent_comparisons"][1]["status"] == "NO_SAFE_PROVIDER_MAPPING"
    assert result["complete_debt_verified"] is False
