from value_investment_agent.filing_extract import extract_candidates_from_pages


TITLE = '\u4e3b\u8981\u4f1a\u8ba1\u6570\u636e\u548c\u8d22\u52a1\u6307\u6807'
LABEL = '\u5f52\u5c5e\u4e8e\u4e0a\u5e02\u516c\u53f8\u80a1\n\u4e1c\u7684\u51c0\u5229\u6da6'


def test_wrapped_annual_parent_profit_keeps_value_and_page():
    page = TITLE + '\n\u5355\u4f4d\uff1a\u5143\n2025\u5e74 2024\u5e74\n' + LABEL + '\n1,758,171,535.84 1,084,126,917.88'
    rows = extract_candidates_from_pages(['cover', page])
    profit = [r for r in rows if r['field_name'] == 'net_income']
    assert len(profit) == 1
    assert profit[0]['value'] == '1758171535.84'
    assert profit[0]['unit'] == 'CNY' and profit[0]['page'] == 2


def test_summary_explanation_does_not_enable_wrapped_quarterly_values():
    page = TITLE + '\u7684\u8bf4\u660e\n2025\u5e74\u5206\u5b63\u5ea6\u6570\u636e\n' + LABEL + '\n456169406.71 785502421.63'
    assert not any(r['field_name'] == 'net_income' for r in extract_candidates_from_pages([page]))


def test_nonconsecutive_header_does_not_enable_wrapped_row():
    page = TITLE + '\n2025\u5e74 2023\u5e74\n' + LABEL + '\n100.00 80.00'
    assert not any(r['field_name'] == 'net_income' for r in extract_candidates_from_pages([page]))


def test_wrapped_summary_with_inline_thousands():
    page = TITLE + '\n2021\u5e74 2020\u5e74\n' + LABEL + '\uff08\u5343\u5143\uff09\n28,573,650 27,222,969'
    rows = extract_candidates_from_pages([page])
    profit = [r for r in rows if r['field_name'] == 'net_income']
    assert len(profit) == 1
    assert profit[0]['value'] == '28573650000'
    assert profit[0]['unit'] == 'CNY'


def test_wrapped_inline_units_require_consecutive_annual_header():
    page = TITLE + '\n2021\u5e74 2019\u5e74\n' + LABEL + '\uff08\u5343\u5143\uff09\n28,573,650 27,222,969'
    assert not any(r['field_name'] == 'net_income' for r in extract_candidates_from_pages([page]))
