import pytest

from value_investment_agent.corporate_actions import (
    distribution_title_status, is_distribution_disclosure,
)


@pytest.mark.parametrize('title,status', [
    ('中国神华关于派发2020年度末期股息的公告', 'implementation_requires_body_verification'),
    ('派发2016年度末期股息及公司特别股息公告', 'implementation_requires_body_verification'),
    ('2020年年度利润分配实施公告（已取消）', 'cancelled_retained_for_lineage'),
    ('2020年年度利润分配实施公告（更新后）', 'revised_requires_linkage'),
    ('关于2020年度利润分配实施公告的更正公告', 'correction_requires_linkage'),
    ('2022年度回报股东特别分红实施公告', 'implementation_requires_body_verification'),
    ('2015年度利润分配及资本公积金转增股本实施公告', 'implementation_requires_body_verification'),
])
def test_preserve_implementation_and_revision_chain(title, status):
    assert is_distribution_disclosure(title)
    assert distribution_title_status(title) == status


@pytest.mark.parametrize('title', [
    '关于派发特别股息预案说明的公告',
    '关于实施2024年年度权益分派后调整回购股份价格上限的公告',
    '2024年度利润分配预案',
    '关于实施2018年度利润分配方案后调整发行价格的公告',
])
def test_exclude_proposals_and_price_adjustments(title):
    assert not is_distribution_disclosure(title)
