from decimal import Decimal

import pytest

from value_investment_agent.infrastructure.filings.quarter_operating_breakdown import (
    parse_quarter_operating_breakdown,
    parse_ytd_operating_breakdown,
)


PAGE = (
    "1\n证券代码：600001证券简称：测试公告编号：临2026-001"
    "测试股份有限公司关于2026年第三季度经营数据的公告"
    "（一）主营业务收入按产品类别分类情况单位：元币种：人民币"
    "产品类别2026年7-9月2026年1-9月产品甲2.003.00产品乙1.003.00合计3.006.00"
    "（二）主营业务收入按销售模式分类情况单位：元币种：人民币"
    "销售模式2026年7-9月2026年1-9月经销3.006.00合计3.006.00"
    "（三）主营业务收入按地区分部分类情况单位：元币种：人民币"
    "地区分部2026年7-9月2026年1-9月华南3.006.00合计3.006.00"
    "二、经销商总数变化情况特此公告测试股份有限公司董事会二〇二六年十月三十日"
)


def test_quarter_and_year_to_date_stay_separate():
    result = parse_quarter_operating_breakdown([PAGE], symbol="600001")
    assert Decimal(result["groups"]["product"]["q3_total_cny"]) == 3
    assert Decimal(result["groups"]["product"]["ytd_total_cny"]) == 6
    assert result["physical_pages"] == [1]
    assert result["effective_date"] is None


@pytest.mark.parametrize("page", [
    PAGE.replace("产品乙1.003.00", "产品乙1.004.00"),
    PAGE.replace("华南3.006.00合计3.006.00", "华南2.003.00合计2.003.00"),
    PAGE.replace("2026年7-9月", "2026年1-9月"),
])
def test_conflicting_amounts_or_periods_are_rejected(page):
    with pytest.raises(ValueError):
        parse_quarter_operating_breakdown([page], symbol="600001")



YTD_PAGE = (
    "证券简称：测试证券代码：600001编号：临2026-001"
    "测试股份有限公司2026年第三季度主要经营数据公告测试资料。"
    "一、经营情况单位：万元币种：人民币项目按产品档次按销售渠道按地区分部"
    "茅台酒系列酒直销批发代理国内国外年初至报告期末的主营业务收入"
    "20.003.0014.009.0021.002.00"
    "注：年初至报告期末，公司通过“i茅台”数字营销平台实现酒类不含税收入10.00万元。"
    "二、经销商变动情况测试资料。特此公告。测试股份有限公司董事会2026年10月30日"
)


def test_ytd_platform_is_a_subset_not_an_extra_revenue_line():
    result = parse_ytd_operating_breakdown([YTD_PAGE], symbol="600001")
    assert result["period_start"] == "2026-01-01"
    assert result["period_end"] == "2026-09-30"
    assert Decimal(result["revenue_cny"]["digital_platform"]) == 100000
    assert Decimal(result["revenue_cny"]["other_direct"]) == 40000
    assert "q3_cny" not in result and result["action"] == "no_order"


@pytest.mark.parametrize(("old", "new"), [
    ("万元币种", "元币种"),
    ("21.002.00", "20.002.00"),
    ("收入10.00万元", "收入15.00万元"),
    ("2026年10月30日", "2025年10月30日"),
    ("证券代码：600001", "证券代码：600002"),
])
def test_ytd_layout_rejects_inconsistent_scope(old, new):
    with pytest.raises(ValueError):
        parse_ytd_operating_breakdown([YTD_PAGE.replace(old, new)], symbol="600001")
