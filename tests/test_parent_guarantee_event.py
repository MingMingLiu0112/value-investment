from decimal import Decimal

import pytest

from value_investment_agent.infrastructure.filings.parent_guarantee_event import (
    parse_parent_guarantee_event,
)


PAGES = [
    "1\n证券代码：600001 证券简称：测试 公告编号：临 2026-001"
    "测试股份有限公司关于为全资子公司提供担保的进展公告"
    "担保的基本情况2026年10月30日，测试股份有限公司与银行签署了保证协议。"
    "1新西兰元对人民币3.7624元。担保债务本金合计不超过3.3亿新西兰元。",
    "2\n三、担保协议的主要内容担保最高本金限额：1亿新西兰元。连带责任保证担保。"
    "担保授信金额：1.75亿新西兰元。连带责任保证担保。"
    "担保贷款本金余额：合计不超过0.55亿新西兰元。连带责任保证担保。"
    "四、担保的必要性和合理性特此公告测试股份有限公司董事会二〇二六年十一月三日",
]


def test_guarantee_principal_is_reconciled_and_kept_outside_cash():
    result = parse_parent_guarantee_event(PAGES, symbol="600001")
    assert result["published_date"] == "2026-11-03"
    assert Decimal(result["principal_limit_cny"]) == Decimal("1241592000")
    assert result["effective_date"] is None
    assert result["affected_model_fields"] == []
    assert result["action"] == "no_order"
    assert sum(e["field"] == "bank_principal_limit" for e in result["evidence_excerpts"]) == 3


@pytest.mark.parametrize("pages,symbol", [
    (PAGES, "600002"),
    (PAGES[:1], "600001"),
    ([PAGES[0], PAGES[1].replace("1.75亿", "1.76亿")], "600001"),
])
def test_wrong_identity_incomplete_pages_or_conflicting_principal_fail(pages, symbol):
    with pytest.raises(ValueError):
        parse_parent_guarantee_event(pages, symbol=symbol)
