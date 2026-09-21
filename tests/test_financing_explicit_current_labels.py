import pytest
from value_investment_agent.financing_table import financing_label_category


@pytest.mark.parametrize('label,category', [
    ('银行借款(含一年内到期)', 'borrowings'),
    ('应付债券（含一年内到期）', 'bonds'),
    ('租赁负债(含一年内到期)', 'leases'),
])
def test_explicit_current_inclusive_categories(label, category):
    assert financing_label_category(label) == category


@pytest.mark.parametrize('label', ['银行借款及其他', '一年内到期的非流动负债',
                                   '长期应付款(含一年内到期)', '应付债券担保'])
def test_mixed_or_different_obligations_still_need_notes(label):
    assert financing_label_category(label) == 'requires_note'
