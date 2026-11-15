from decimal import Decimal

import pytest

from value_investment_agent.infrastructure.filings.annual_parent_cfo_scan import (
    read_annual_parent_cfo_columns,
)


def token(text, x, y, score=.99):
    return dict(text=text, score=score, box=[[x, y], [x+30, y], [x+30, y+8], [x, y+8]])


def rows():
    return [
        token("示例股份有限公司", 95, 10), token("2025年12月31日止年度", 95, 20),
        token("母公司现金流量表", 95, 30), token("单位：人民币元", 140, 40),
        token("本年金额", 105, 50), token("上年金额", 155, 50),
        token("经营活动产生的现金流量净额", 5, 100),
        token("-200.00", 105, 100), token("300.00", 155, 100),
        token("二、投资活动产生的现金流量", 5, 130),
    ]


def read(data):
    return read_annual_parent_cfo_columns(data, size=(240, 160),
                                          issuer_name="示例股份有限公司", period_end="2025-12-31")


def test_replay_identifies_each_cash_column_and_preserves_sign():
    assert read(rows()) == (Decimal("-200.00"), Decimal("300.00"))


@pytest.mark.parametrize("replacement,position,code", [
    (token("合并现金流量表", 95, 30), 2, "MISSING_DUPLICATE"),
    (token("单位：人民币万元", 140, 40), 3, "MISSING_DUPLICATE"),
    (token("本年金额", 195, 50), 4, "STATEMENT_ORDER_INVALID"),
    (token("-200.00", 105, 113), 7, "AMOUNT_MISSING"),
    (token("-200.00", 105, 100, .97), 7, "LOW_CONFIDENCE"),
    (token("-200.00", 230, 100), 7, "INVALID_GEOMETRY"),
])
def test_scan_rejects_wrong_label_columns_or_geometry(replacement, position, code):
    data = rows()
    data[position] = replacement
    with pytest.raises(ValueError, match=code):
        read(data)
