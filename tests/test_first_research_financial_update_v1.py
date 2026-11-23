from value_investment_agent.application.research.first_research_financial_update_v1 import (
    compare_first_input_financial_update,
)


def inputs():
    native = {"symbol": "600519", "financial_basis": "2026-06-30", "facts": [
        {"field": "revenue", "scope": "consolidated", "period_end": "2026-06-30", "unit": "CNY", "value": "90"},
        {"field": "parent_profit", "scope": "consolidated_parent", "period_end": "2026-06-30", "unit": "CNY", "value": "44"},
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
    requirements = result["e1_recompile_requirements"]
    assert {"cost", "da", "tax"} <= set(requirements["current_ytd_source_fields_missing"])
    assert "revenue" not in requirements["current_ytd_source_fields_missing"]
    assert requirements["parent_accessible_cash_at_new_basis"] == "UNVERIFIED"
    assert requirements["ordinary_shares_at_new_basis"] == "UNVERIFIED"
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


def test_parent_standalone_profit_cannot_be_subtracted_from_consolidated_ytd():
    native, q3 = inputs()
    native["facts"][1]["scope"] = "parent_standalone"
    result = compare_first_input_financial_update(symbol="600519", financial_basis="2026-06-30",
                                                   native_facts=native, q3_read_model=q3)
    assert result["status"] == "UNASSESSABLE"
    assert result["reason"] == "FINANCIAL_UPDATE_H1_SCOPE_MISMATCH:parent_profit"
    assert "derived_q3_quarter_cny" not in result


def test_unsupported_issuer_has_no_q3_claim():
    native, _ = inputs()
    assert compare_first_input_financial_update(symbol="600519", financial_basis="2026-06-30",
        native_facts=native, q3_read_model={"status": "NOT_SUPPORTED"}) is None


def test_verified_income_removes_only_covered_gaps_and_conflict_rejects():
    native, q3 = inputs()
    income = {"status": "VERIFIED_REPORTED_Q3_INCOME_FACTS_ONLY", "symbol": "600519",
              "report_period": "2026-09-30", "currency": "CNY", "unit": "yuan",
              "period_basis": "YTD_9M", "facts": {"2026": {
                  "revenue": "130", "parent_profit": "64", "cost": "20", "tax": "10"}}}
    def evaluate():
        return compare_first_input_financial_update(symbol="600519", financial_basis="2026-06-30",
            native_facts=native, q3_read_model=q3, income_read_model=income)
    result = evaluate()
    missing = result["e1_recompile_requirements"]["current_ytd_source_fields_missing"]
    assert "cost" not in missing and "tax" not in missing and "da" in missing
    assert result["valuation_recomputed"] is False and result["price_admitted"] is False
    income["facts"]["2026"]["revenue"] = "131"
    assert evaluate()["reason"] == "FINANCIAL_UPDATE_INCOME_FACT_CONFLICT"

def test_q3_nonrecurring_requires_matching_reported_total():
    import pytest

    from value_investment_agent.application.research.quarter_income_facts_v2 import (
        _reported_nonrecurring_ytd,
    )

    first = (
        "单位：元 币种：人民币 年初至报告期末\n"
        "归属于上市公司股东的 扣除非经常性损益的净 利润 10.00 1.00 99.00 2.00"
    )
    second = "非经常性损益项目和金额 单位：元 币种：人民币 年初至报告期末 合计 0.20 1.00"
    assert _reported_nonrecurring_ytd([first, second], "100.00") == "1.00"
    with pytest.raises(ValueError, match="Q3_NONRECURRING_PROFIT_RECONCILIATION_FAILED"):
        _reported_nonrecurring_ytd([first, second], "100.01")
    with pytest.raises(ValueError, match="Q3_NONRECURRING_ROWS_UNVERIFIED"):
        _reported_nonrecurring_ytd([first, second + " 合计 0.20 1.00"], "100.00")
