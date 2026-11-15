from decimal import Decimal

import pytest

from value_investment_agent.infrastructure.filings.numbered_annual_parent_wc import (
    read_numbered_annual_parent_wc,
)


NOTE = """示例公司
财务报表附注
2025年12月31日止年度
（除特别注明外，金额单位为人民币元）
十七、母公司财务报表主要项目附注 - 续
15. 母公司现金流量表补充资料
项目 本年累计数 上年累计数
1．将净利润调节为经营活动现金流量： —— ——
存货的减少（增加以“-”号填列） 10.00 -20.00
经营性应收项目的减少（增加以“-”号填列） -40.00 50.00
经营性应付项目的增加（减少以“-”号填列） 16.00 -12.00
经营活动产生的现金流量净额 -200.00 -300.00
"""
CFO = (Decimal("-200.00"), Decimal("-300.00"))


def read(pages, cfo=CFO):
    return read_numbered_annual_parent_wc(
        pages, issuer_name="示例公司", period_end="2025-12-31", verified_parent_cfo_cny=cfo,
    )


def test_numbered_parent_annual_note_preserves_pages_and_cash_sign():
    row = read(["other page", NOTE])
    assert row["physical_page"] == 2
    assert row["cash_impact_cny"] == ["-14.00", "18.00"]
    assert row["parent_cfo_cny"] == ["-200.00", "-300.00"]
    assert row["scope"] == "ISSUER_PARENT_STANDALONE"


@pytest.mark.parametrize(("before", "after", "reason"), [
    ("示例公司", "其他公司", "ISSUER_PERIOD_CURRENCY_OR_SCOPE_INVALID"),
    ("2025年", "2024年", "ISSUER_PERIOD_CURRENCY_OR_SCOPE_INVALID"),
    ("人民币元", "人民币万元", "ISSUER_PERIOD_CURRENCY_OR_SCOPE_INVALID"),
    ("母公司财务报表", "合并财务报表", "ISSUER_PERIOD_CURRENCY_OR_SCOPE_INVALID"),
    ("本年累计数 上年累计数", "上年累计数 本年累计数", "NOTE_MISSING_OR_AMBIGUOUS"),
    ("10.00 -20.00", "10.00", "CASH_ROW_MISSING_OR_AMBIGUOUS"),
])
def test_numbered_parent_annual_note_rejects_wrong_scope_or_columns(before, after, reason):
    with pytest.raises(ValueError, match=reason):
        read([NOTE.replace(before, after)])


def test_numbered_parent_annual_note_requires_unique_note_and_independent_ordered_cfo():
    with pytest.raises(ValueError, match="NOTE_MISSING_OR_AMBIGUOUS"):
        read([NOTE, NOTE])
    with pytest.raises(ValueError, match="PARENT_CFO_MISMATCH"):
        read([NOTE], tuple(reversed(CFO)))
