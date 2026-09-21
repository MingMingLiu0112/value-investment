from value_investment_agent.filing_extract import extract_candidates_from_pages


def test_wrapped_cashflow_label_on_continuation_page():
    pages = ['合并现金流量表\n单位：元\n2025年 2024年',
             '经营活动产生的现金流\n量净额\n480,244,967.37 398,766,454.60']
    rows = extract_candidates_from_pages(pages)
    assert [(r['field_name'], r['value'], r['page']) for r in rows] == [
        ('operating_cash_flow', '480244967.37', 2)]


def test_wrapped_cashflow_does_not_enable_parent_statement():
    pages = ['合并现金流量表\n单位：元', '母公司现金流量表\n单位：元\n'
             '经营活动产生的现金流\n量净额\n480,244,967.37 398,766,454.60']
    assert extract_candidates_from_pages(pages) == []


def test_wrapped_cashflow_without_statement_scope_is_not_accepted():
    assert extract_candidates_from_pages(['单位：元\n经营活动产生的现金流\n量净额\n480,244,967.37']) == []
