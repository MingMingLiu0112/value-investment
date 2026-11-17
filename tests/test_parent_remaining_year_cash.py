"""Direct tests for same-parent annual minus 9M and conditional Q4 arithmetic."""
from copy import deepcopy
from datetime import date
from decimal import Decimal, localcontext
import json

import pytest

from value_investment_agent.domain.valuation.parent_remaining_year_cash import build_parent_remaining_year_cash


def inputs():
    basis = dict(symbol="600887", scope="ISSUER_PARENT_STANDALONE", currency="CNY",
                 classification="FACT", period_start="2025-01-01",
                 revenue="400", cost="240", customer_cash="380", supplier_cash="250",
                 cfo="70")
    fy = dict(basis, period_end="2025-12-31", source_refs=[{"id": "TEST_ONLY/fy"}])
    nine = dict(basis, period_end="2025-09-30", revenue="300", cost="180",
                customer_cash="285", supplier_cash="190", cfo="50",
                source_refs=[{"id": "TEST_ONLY/old-9m"}])
    current = dict(nine, period_start="2026-01-01", period_end="2026-09-30",
                   revenue="330", cost="198", customer_cash="310",
                   supplier_cash="210", cfo="55",
                   source_refs=[{"id": "TEST_ONLY/current-9m"}])
    forecast = dict(symbol="600887", scope="ISSUER_PARENT_STANDALONE", currency="CNY",
        classification="FORECAST_ASSUMPTION", period_start="2026-10-01",
        period_end="2026-12-31", revenue="110", cost="66",
        other_operating_cash="-10", rationale="TEST_ONLY Q4 sales and cost scenario",
        counter_evidence="TEST_ONLY collections can change",
        reopen_condition="TEST_ONLY new quarterly report",
        source_refs=[{"id": "TEST_ONLY/forecast-assumption"}])
    return dict(historical_full_year=fy, historical_nine_months=nine,
                current_nine_months=current, q4_forecast=forecast,
                as_of=date(2026, 11, 18))


def test_same_season_q4_and_full_year_components_remain_separate():
    data = inputs()
    before = deepcopy(data)
    with localcontext() as ctx:
        ctx.prec = 8
        result = build_parent_remaining_year_cash(**data)
    assert data == before
    assert result["historical_q4"]["period_start"] == "2025-10-01"
    assert {k: result["historical_q4"][k] for k in ("revenue", "cost", "customer_cash", "supplier_cash", "cfo")} == {
        "revenue": "100", "cost": "60", "customer_cash": "95", "supplier_cash": "60", "cfo": "20"}
    assert result["conditional_q4"]["period_start"] == "2026-10-01"
    assert result["conditional_q4"]["period_end"] == "2026-12-31"
    assert "07-01" not in json.dumps(result, ensure_ascii=False)
    assert result["conditional_q4"]["coefficients"]["customer_cash_to_revenue"] == "0.95"
    assert result["conditional_q4"]["coefficients"]["supplier_cash_to_cost"] == "1"
    assert Decimal(result["conditional_q4"]["customer_cash"]) == Decimal("104.50")
    assert Decimal(result["conditional_q4"]["supplier_cash"]) == Decimal("66")
    assert Decimal(result["conditional_q4"]["cfo"]) == Decimal("28.50")
    for key, expected in {"revenue": "440", "cost": "264", "customer_cash": "414.50",
                          "supplier_cash": "276", "cfo": "83.50"}.items():
        row = result["full_year"][key]
        assert Decimal(row["total"]) == Decimal(expected)
        assert Decimal(row["total"]) == Decimal(row["fact_9m"]) + Decimal(row["forecast_q4"])
        assert row["fact_classification"] == "FACT"
        assert row["forecast_classification"] == "FORECAST_ASSUMPTION"
    assert result["current_nine_months"]["source_refs"] == data["current_nine_months"]["source_refs"]
    assert result["historical_q4"]["source_refs"]["full_year"] == data["historical_full_year"]["source_refs"]
    assert result["conditional_q4"]["source_refs"] == data["q4_forecast"]["source_refs"]
    assert result["annualized_nine_months"] is False
    assert result["automatic_dividend"] is None and result["distribution_capacity"] is None
    assert result["formal_eligibility"] is False and result["action"] == "no_order"


@pytest.mark.parametrize("part,field,value", [
    ("historical_full_year", "symbol", "600519"),
    ("historical_full_year", "classification", "DERIVED_FACT"),
    ("historical_nine_months", "currency", "USD"),
    ("current_nine_months", "scope", "CONSOLIDATED"),
    ("current_nine_months", "period_end", "2026-10-01"),
    ("current_nine_months", "period_start", "2025-01-01"),
    ("historical_nine_months", "period_end", "2024-09-30"),
    ("q4_forecast", "period_start", "2026-09-30"),
    ("q4_forecast", "currency", "USD"),
    ("q4_forecast", "classification", "FACT"),
    ("current_nine_months", "classification", "FORECAST_ASSUMPTION"),
    ("historical_full_year", "source_refs", []),
    ("q4_forecast", "source_refs", []),
    ("historical_full_year", "customer_cash", "100"),
    ("historical_full_year", "supplier_cash", "100"),
])
def test_rejects_identity_period_source_and_negative_derived_receipts(part, field, value):
    data = inputs()
    data[part][field] = value
    with pytest.raises(ValueError):
        build_parent_remaining_year_cash(**data)


def test_rejects_future_facts_missing_fields_and_explanations():
    data = inputs()
    data["as_of"] = date(2026, 9, 29)
    with pytest.raises(ValueError):
        build_parent_remaining_year_cash(**data)
    data = inputs()
    for key in ("historical_full_year", "historical_nine_months"):
        data[key]["period_start"] = data[key]["period_start"].replace("2025", "2024")
        data[key]["period_end"] = data[key]["period_end"].replace("2025", "2024")
    with pytest.raises(ValueError, match="SAME_ISSUER_PERIOD_CHAIN"):
        build_parent_remaining_year_cash(**data)
    for part, key in (("historical_nine_months", "cfo"),
                      ("current_nine_months", "supplier_cash"),
                      ("q4_forecast", "other_operating_cash")):
        data = inputs()
        del data[part][key]
        with pytest.raises((ValueError, KeyError)):
            build_parent_remaining_year_cash(**data)
    data = inputs()
    data["q4_forecast"]["rationale"] = ""
    with pytest.raises(ValueError):
        build_parent_remaining_year_cash(**data)
