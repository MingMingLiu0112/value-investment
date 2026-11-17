from value_investment_agent.application.research.first_research_financial_update_v1 import (
    compare_first_input_financial_update,
)


def inputs():
    native = {"symbol": "600519", "financial_basis": "2026-06-30", "facts": [
        {"field": "revenue", "period_end": "2026-06-30", "unit": "CNY", "value": "90"},
        {"field": "parent_profit", "period_end": "2026-06-30", "unit": "CNY", "value": "44"},
    ]}
    q3 = {"status": "VERIFIED_OBSERVATION_ONLY", "symbol": "600519",
          "source_bindings": {"original": {"path": "runtime/q3.pdf", "sha256": "a" * 64}},
          "ytd_9m_observation": {
              "symbol": "600519", "status": "VERIFIED_REPORTED_Q3_UNAUDITED_OBSERVATION",
              "report_period": "2026-09-30", "period_basis": "YTD_9M", "currency": "CNY",
              "unit": "yuan", "facts": {"revenue_ytd_cny": "130", "attributable_profit_ytd_cny": "64"}}}
    return native, q3


def test_newer_reported_period_requires_e1_without_repricing():
    native, q3 = inputs()
    result = compare_first_input_financial_update(symbol="600519", financial_basis="2026-06-30",
                                                   native_facts=native, q3_read_model=q3)
    assert result["status"] == "SOURCE_BOUND_NEW_FINANCIAL_FACT_REQUIRES_E1_RECOMPILE"
    assert result["derived_q3_quarter_cny"] == {"revenue": "40", "attributable_profit": "20"}
    assert result["source_bindings"] == q3["source_bindings"]
    assert result["valuation_recomputed"] is False and result["price_admitted"] is False
    assert result["action"] == "no_order"


def test_mismatched_scope_or_missing_h1_does_not_claim_update():
    native, q3 = inputs()
    native["facts"].pop()
    assert compare_first_input_financial_update(symbol="600519", financial_basis="2026-06-30",
        native_facts=native, q3_read_model=q3)["status"] == "UNASSESSABLE"
    native, q3 = inputs()
    q3["ytd_9m_observation"]["currency"] = "USD"
    assert compare_first_input_financial_update(symbol="600519", financial_basis="2026-06-30",
        native_facts=native, q3_read_model=q3)["status"] == "UNASSESSABLE"
    native, q3 = inputs()
    q3["ytd_9m_observation"]["report_period"] = "2027-09-30"
    assert compare_first_input_financial_update(symbol="600519", financial_basis="2026-06-30",
        native_facts=native, q3_read_model=q3)["status"] == "UNASSESSABLE"


def test_unsupported_issuer_has_no_q3_claim():
    native, _ = inputs()
    assert compare_first_input_financial_update(symbol="600519", financial_basis="2026-06-30",
        native_facts=native, q3_read_model={"status": "NOT_SUPPORTED"}) is None
