import pytest
from value_investment_agent.financing_table import financing_label_category


@pytest.mark.parametrize('label,category',[
    ('短期借款','borrowings'),('长期借款（含一年内到期部分）','borrowings'),
    ('应付债券（含一年内到期的应付债券）','bonds'),('短期应付债券','bonds'),
    ('租赁负债（含一年内到期的租赁负债）','leases'),
    ('其他应付款 - 应付股利','dividends_excluded'),('应付股利','dividends_excluded'),
])
def test_explicit_labels_have_distinct_categories(label,category):
    assert financing_label_category(label)==category


@pytest.mark.parametrize('label',[
    '其他应付款','其他流动负债','长期应付款','短期借款担保余额',
    '其他应付款-应付股利及拆借款','租赁负债利息费用','长期借款（母公司）',
])
def test_ambiguous_combined_or_wrong_scope_needs_notes(label):
    assert financing_label_category(label)=='requires_note'
