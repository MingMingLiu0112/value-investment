import pytest
from value_investment_agent.financing_table import TITLE, financing_applicability, extract_financing_total


@pytest.mark.parametrize('checked',['\uf052','\u2611','\u221a'])
def test_explicit_nonapplicability_is_not_zero_debt(checked):
    text = TITLE+'\n\n\u25a1适用 '+checked+'不适用\n'
    assert financing_applicability(text)=='declared_not_applicable'
    assert extract_financing_total(text) is None


def test_applicable_and_unclear_markers_are_distinct():
    assert financing_applicability(TITLE+'\n\uf052适用 □不适用')=='declared_applicable'
    assert financing_applicability(TITLE+'\n□适用 □不适用')=='unspecified'
    assert financing_applicability('other section\n□适用 \uf052不适用')=='section_not_found'
    assert financing_applicability(TITLE+'\n'+TITLE)=='ambiguous_section'
