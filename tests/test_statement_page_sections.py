from value_investment_agent.filing_extract import extract_candidates_from_pages


def test_continuation_before_parent_heading_retains_consolidated_bond():
    pages = [
        '\u5408\u5e76\u8d44\u4ea7\u8d1f\u503a\u8868\n\u5355\u4f4d\uff1a\u5143\n',
        '\u5e94\u4ed8\u503a\u5238 500,624,657.53\n'
        '\u6bcd\u516c\u53f8\u8d44\u4ea7\u8d1f\u503a\u8868\n\u5355\u4f4d\uff1a\u4e07\u5143\n'
        '\u5e94\u4ed8\u503a\u5238 12.34\n',
        '\u957f\u671f\u501f\u6b3e 999.00\n',
    ]
    rows = extract_candidates_from_pages(pages)
    assert [(r['field_name'], r['value'], r['page']) for r in rows] == [
        ('bonds_payable', '500624657.53', 2)]


def test_parent_then_consolidated_same_page_switches_scope_and_unit():
    page = ('\u6bcd\u516c\u53f8\u5229\u6da6\u8868\n\u5355\u4f4d\uff1a\u5143\n'
            '\u8425\u4e1a\u6210\u672c 999.00\n'
            '\u5408\u5e76\u5229\u6da6\u8868\n\u5355\u4f4d\uff1a\u4e07\u5143\n'
            '\u8425\u4e1a\u6210\u672c 12.50\n')
    rows = extract_candidates_from_pages([page])
    assert [(r['field_name'], r['value'], r['page']) for r in rows] == [
        ('operating_cost', '125000.00', 1)]


def test_unit_declared_after_parent_heading_cannot_validate_previous_segment():
    rows = extract_candidates_from_pages([
        '\u5408\u5e76\u8d44\u4ea7\u8d1f\u503a\u8868\n'
        '\u5e94\u4ed8\u503a\u5238 100.00\n'
        '\u6bcd\u516c\u53f8\u8d44\u4ea7\u8d1f\u503a\u8868\n\u5355\u4f4d\uff1a\u5143\n'])
    assert rows == []
