import pytest

from value_investment_agent.application.research.parent_direct_operating_observations_v1 import (
    _other_cash,
    _wrapped_operating_rows,
)


@pytest.fixture
def table():
    return [
        (15, "一、经营活动产生的现金流量： 销售商品、提供劳务收到的"),
        (15, "现金"),
        (15, "1,100.00 900.00"),
        (15, "购买商品、接受劳务支付的"),
        (15, "现金"),
        (15, "200.00 300.00"),
        (15, "二、投资活动产生的现金流量："),
    ]


def test_replays_both_columns_and_keeps_original_page(table):
    result = _wrapped_operating_rows(table)
    assert result["customer_cash"]["current"] == "1100.00"
    assert result["customer_cash"]["comparative"] == "900.00"
    assert result["supplier_cash"]["physical_page"] == 15
    assert result["supplier_cash"]["excerpt"].endswith("200.00 300.00")


@pytest.mark.parametrize(
    ("replacement", "reason"),
    [((15, "1,100.00"), "TWO_COLUMNS_REQUIRED"),
     ((16, "1,100.00 900.00"), "ROW_BOUNDARY"),
     ((15, "1,100.00 900.00 1.00"), "TWO_COLUMNS_REQUIRED")],
)
def test_does_not_infer_columns_or_join_across_pages(table, replacement, reason):
    table[2] = replacement
    with pytest.raises(ValueError, match=reason):
        _wrapped_operating_rows(table)


def test_rejects_duplicate_operating_rows(table):
    table[6:6] = table[3:6]
    with pytest.raises(ValueError, match="ROW_NOT_UNIQUE"):
        _wrapped_operating_rows(table)


def test_non_trade_cash_is_a_historical_residual_not_a_policy(table):
    rows = _wrapped_operating_rows(table)
    rows.update(inflow={"current": "1200.00"}, outflow={"current": "420.00"})
    assert _other_cash(rows, "current") == {
        "classification": "DERIVED_FACT",
        "other_operating_receipts_cny": "100.00",
        "other_operating_payments_cny": "220.00",
        "other_operating_net_cash_cny": "-120.00",
        "recurrence": "UNKNOWN",
    }
    rows["outflow"]["current"] = "100.00"
    with pytest.raises(ValueError, match="TRADE_ROWS_EXCEED_SUBTOTAL"):
        _other_cash(rows, "current")
