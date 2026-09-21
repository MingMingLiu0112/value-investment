import pytest
from value_investment_agent.disclosures import _report_kind


@pytest.mark.parametrize('title', [
    '长江电力关于《2022年年度报告》《2023年第一季度报告》披露日期变更的公告',
    '2025年年度报告披露提示性公告',
    '关于2026年半年度报告的更正公告',
    '关于取消披露2026年第一季度报告',
    '工商银行H股公告-2026年第一季度报告披露日期变更公告',
    '境内同步披露公告-关于2026年第一季度报告的更正公告',
])
def test_notices_are_not_financial_reports(title):
    assert _report_kind(title) is None


@pytest.mark.parametrize('title,kind', [
    ('长江电力2025年年度报告', 'annual'),
    ('2025年年度报告（修订版）', 'annual'),
    ('2026年第一季度报告', 'first_quarter'),
    ('2026年半年度报告', 'interim'),
    ('工商银行H股公告-2026年第一季度报告', 'first_quarter'),
    ('H股公告 - 郑州银行股份有限公司2023年第一季度报告（H股）', 'first_quarter'),
    ('境内同步披露公告-2026年第一季度报告（H股）', 'first_quarter'),
])
def test_actual_reports_remain_eligible(title, kind):
    assert _report_kind(title) == kind
