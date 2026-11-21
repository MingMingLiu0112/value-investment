"""Tests for strict multi-page standalone cash statement extraction."""
import pytest

from value_investment_agent.infrastructure.filings.quarterly_parent_cash_facts_v2 import (
    parse_paginated_parent_cash,
)


def pages():
    return [
        "证券代码：600323\n某公司 2026 年第三季度报告",
        "\n".join([
            "母公司现金流量表", "2026 年 1—9 月", "编制单位：某公司",
            "单位：元 币种：人民币 审计类型：未经审计", "项目",
            "2026 年前三季度", "（1-9月）", "2025 年前三季度", "（1-9月）",
            "一、经营活动产生的现金流量：",
            "销售商品、提供劳务收到的现金 20.00 21.00",
            "购买商品、接受劳务支付的现金 10.00 11.00",
            "经营活动产生的现金流量净额 4.00 5.00",
            "二、投资活动产生的现金流量：",
            "取得投资收益收到的现金 4.00 5.00",
        ]),
        "\n".join([
            "购建固定资产、无形资产和其他长期", "资产支付的现金", "2.00 3.00",
            "投资活动产生的现金流量净额 -2.00 -3.00",
            "三、筹资活动产生的现金流量：",
            "取得借款收到的现金 3.00 5.00", "偿还债务支付的现金 4.00 6.00",
            "分配股利、利润或偿付利息支付的现", "金", "1.00 1.00",
            "筹资活动产生的现金流量净额 -2.00 -2.00",
            "五、现金及现金等价物净增加额 0.00 0.00",
            "加：期初现金及现金等价物余额 50.00 60.00",
            "六、期末现金及现金等价物余额 50.00 60.00",
            "公司负责人：某人",
        ]),
    ]


def parse(printed):
    return parse_paginated_parent_cash(
        printed, symbol="600323", issuer_name="某公司", period_end="2026-09-30",
    )


def test_two_page_receives_explicit_periods_and_original_page():
    result = parse(pages())
    assert result["fields"]["cfo"]["current"] == "4.00"
    assert result["fields"]["cash_capex"]["physical_page"] == 3
    assert result["fields"]["cash_capex"]["comparative"] == "3.00"
    assert result["net_change_minus_reported_flows_cny"] == {"current": "0.00", "comparative": "0.00"}


@pytest.mark.parametrize(("page", "old", "new", "error"), [
    (0, "600323", "600066", "COVER_MISMATCH"),
    (1, "2025 年前三季度", "2024 年前三季度", "COLUMNS_OR_SCOPE_MISMATCH"),
    (1, "单位：元", "单位：万元", "COLUMNS_OR_SCOPE_MISMATCH"),
    (2, "2.00 3.00", "2.00", "ROW_MISSING_OR_AMBIGUOUS:cash_capex"),
    (2, "50.00 60.00\n公司负责人", "51.00 60.00\n公司负责人", "CASH_BALANCE_MISMATCH"),
    (2, "公司负责人：某人", "", "TABLE_END_UNVERIFIED"),
])
def test_rejects_ambiguous_or_inconsistent_statements(page, old, new, error):
    printed = pages()
    printed[page] = printed[page].replace(old, new)
    with pytest.raises(ValueError, match=error):
        parse(printed)
